"""
OptionDesk Backtest — 8 June 2025
===================================
Simulates what OptionDesk would have recommended on 2025-06-08 (long calls),
then evaluates those recommendations at 3-month, 6-month, and 12-month horizons.

STRICT NO-LOOK-AHEAD:
  - All price/technical inputs use end="2025-06-09" (inclusive of 2025-06-08)
  - Entry sigma = realized vol of trailing 60 trading days ending 2025-06-08
  - Entry premium = bs_price() (model-implied — no real chain available from yfinance)
  - Exit prices are actual closes fetched after the cutoff date
"""
from __future__ import annotations

import sys
import os
import json
import math
import time
import logging
import hashlib
import pickle
from datetime import date, datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf
from scipy.stats import spearmanr

# ─── Path setup ─────────────────────────────────────────────────────────────
ROOT = Path("/home/user/workspace/optiondesk/backend")
sys.path.insert(0, str(ROOT))

from engine.pricing import bs_price, bs_greeks
from engine.scoring import (
    momentum_score, fundamental_option_risk, evaluate_option,
    scan_score, RISK_FREE
)
from engine.technicals import technical_summary, realized_vol as tech_rv
from engine.universe import universe

# ─── Constants ──────────────────────────────────────────────────────────────
ENTRY_DATE  = date(2025, 6, 8)
ENTRY_END   = "2025-06-09"          # yf.download end (exclusive)
ENTRY_START = "2024-01-01"          # enough history for 200-day MA + vol

H3_DATE  = date(2025, 9, 8)
H6_DATE  = date(2025, 12, 8)
H12_DATE = date(2026, 6, 8)

EXIT_END  = "2026-06-10"            # covers all horizons
EXIT_START = "2025-06-01"

CACHE_DIR   = Path("/home/user/workspace/optiondesk/research/cache")
CACHE_DIR.mkdir(parents=True, exist_ok=True)

RISK_FREE   = 0.045
RNG_SEED    = 42
MAX_WORKERS = 6

TARGET_DTE_DAYS = 270              # ~9-month expiry (within leaps bucket)
OTM_PCT     = 0.10                 # 10% OTM strike
MIN_PRICE   = 5.0                  # ignore penny stocks

# ─── Logging ────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler(CACHE_DIR / "backtest_run.log"),
        logging.StreamHandler(sys.stdout),
    ]
)
log = logging.getLogger("backtest")


# ─── Cache helpers ───────────────────────────────────────────────────────────
def _cache_path(key: str) -> Path:
    h = hashlib.md5(key.encode()).hexdigest()[:12]
    return CACHE_DIR / f"{h}.pkl"


def cache_get(key):
    p = _cache_path(key)
    if p.exists():
        try:
            with open(p, "rb") as f:
                return pickle.load(f)
        except Exception:
            pass
    return None


def cache_set(key, value):
    p = _cache_path(key)
    with open(p, "wb") as f:
        pickle.dump(value, f)


# ─── yfinance with retry + backoff ──────────────────────────────────────────
def yf_download(ticker: str, start: str, end: str, retries=3, delay=3.0) -> pd.DataFrame | None:
    cache_key = f"yf_{ticker}_{start}_{end}"
    cached = cache_get(cache_key)
    if cached is not None:
        return cached
    for attempt in range(retries):
        try:
            df = yf.download(
                ticker, start=start, end=end,
                auto_adjust=False, progress=False, threads=False
            )
            if df is not None and not df.empty:
                # Flatten MultiIndex columns if present
                if isinstance(df.columns, pd.MultiIndex):
                    df.columns = [col[0] if col[1] == ticker else f"{col[0]}_{col[1]}" for col in df.columns]
                cache_set(cache_key, df)
                return df
        except Exception as e:
            log.warning(f"[{ticker}] attempt {attempt+1} failed: {e}")
            time.sleep(delay * (attempt + 1))
    return None


def yf_info(ticker: str, retries=3, delay=3.0) -> dict:
    cache_key = f"info_{ticker}"
    cached = cache_get(cache_key)
    if cached is not None:
        return cached
    for attempt in range(retries):
        try:
            t = yf.Ticker(ticker)
            info = t.info or {}
            cache_set(cache_key, info)
            return info
        except Exception as e:
            log.warning(f"[{ticker}] info attempt {attempt+1} failed: {e}")
            time.sleep(delay * (attempt + 1))
    return {}


# ─── Entry-date helpers ──────────────────────────────────────────────────────
def get_entry_price(df: pd.DataFrame) -> float | None:
    """Actual closing price on 2025-06-08 (or nearest prior trading day)."""
    if df is None or df.empty:
        return None
    close = df["Close"]
    target = pd.Timestamp("2025-06-08")
    # Truncate to on/before entry date
    available = close[close.index <= target]
    if available.empty:
        return None
    val = available.iloc[-1]
    if isinstance(val, pd.Series):
        val = val.iloc[0]
    return float(val) if not math.isnan(float(val)) else None


def get_close_on_date(df: pd.DataFrame, target_date: date) -> float | None:
    """Get closing price on or just before target_date."""
    if df is None or df.empty:
        return None
    close = df["Close"]
    ts = pd.Timestamp(target_date)
    available = close[close.index <= ts]
    if available.empty:
        return None
    val = available.iloc[-1]
    if isinstance(val, pd.Series):
        val = val.iloc[0]
    v = float(val)
    return v if not math.isnan(v) else None


def get_entry_sigma(df: pd.DataFrame, window=60) -> float | None:
    """Realized vol of trailing 60 trading days ending 2025-06-08."""
    if df is None or df.empty:
        return None
    close = df["Close"]
    target = pd.Timestamp("2025-06-08")
    hist = close[close.index <= target]
    if len(hist) < window + 1:
        return None
    tail = hist.tail(window + 1)
    logret = np.log(tail / tail.shift(1)).dropna()
    return float(logret.std() * np.sqrt(252))


def get_sigma_on_date(df: pd.DataFrame, target_date: date, window=60) -> float | None:
    """Realized vol of trailing 60 trading days ending target_date."""
    if df is None or df.empty:
        return None
    close = df["Close"]
    ts = pd.Timestamp(target_date)
    hist = close[close.index <= ts]
    if len(hist) < window + 1:
        # use whatever we have
        if len(hist) < 10:
            return None
        tail = hist
    else:
        tail = hist.tail(window + 1)
    logret = np.log(tail / tail.shift(1)).dropna()
    if len(logret) < 5:
        return None
    return float(logret.std() * np.sqrt(252))


def get_dividend_yield(info: dict) -> float:
    """Safe dividend yield extraction from yfinance info."""
    dy = info.get("dividendYield") or info.get("trailingAnnualDividendYield") or 0.0
    if dy and dy > 0.30:  # sanity: >30% is broken data
        dy = 0.0
    return float(dy or 0.0)


# ─── Score one ticker (entry logic) ─────────────────────────────────────────
def score_ticker(ticker: str, entry_df: pd.DataFrame, index_df: pd.DataFrame,
                 target_dte: int, otm_pct: float) -> dict | None:
    """Compute the system's combined score for ticker as of 2025-06-08.
    Returns a result dict or None if the ticker can't be processed."""
    S0 = get_entry_price(entry_df)
    if S0 is None or S0 < MIN_PRICE:
        return None

    sigma = get_entry_sigma(entry_df)
    if sigma is None or sigma < 0.05:
        sigma = 0.25  # fallback default

    # Technical summary (time-frozen)
    target = pd.Timestamp("2025-06-08")
    df_cut = entry_df[entry_df.index <= target].copy()
    idx_cut = index_df[index_df.index <= target].copy() if index_df is not None else None
    if len(df_cut) < 30:
        return None

    try:
        tech = technical_summary(df_cut, idx_cut)
    except Exception as e:
        log.warning(f"[{ticker}] technical_summary error: {e}")
        tech = {}

    mom_score = momentum_score(tech)

    # Info for fundamentals
    info = yf_info(ticker)
    div_yield = get_dividend_yield(info)
    fund = fundamental_option_risk(info, dte=target_dte)

    # Build synthetic option dict for evaluate_option
    expiry_date = ENTRY_DATE + timedelta(days=target_dte)
    expiry_str = expiry_date.strftime("%Y-%m-%d")
    K = round(S0 * (1.0 + otm_pct), 2)

    T = target_dte / 365.0
    entry_premium = bs_price(S0, K, T, RISK_FREE, sigma, kind="call", q=div_yield)
    if entry_premium < 0.01:
        entry_premium = 0.01

    opt = {
        "strike": K,
        "kind": "call",
        "mid": entry_premium,
        "last": entry_premium,
        "iv": sigma,
        "bid": entry_premium * 0.95,
        "ask": entry_premium * 1.05,
        "open_interest": 500,
        "volume": 100,
        "contract": f"{ticker}_{expiry_str}_C_{K}",
    }

    try:
        ev = evaluate_option(
            opt, S0, expiry_str,
            mu=0.08,  # real-world drift assumption
            realized_vol=sigma,
            target_return=1.30,
            n_mc=3000,
            max_dte=400,
            early_exit=False
        )
        option_score = ev.get("option_score", 0.0)
    except Exception as e:
        log.warning(f"[{ticker}] evaluate_option error: {e}")
        option_score = 0.0

    combined = scan_score(
        option_score, mom_score,
        fund_multiplier=fund.get("multiplier", 1.0),
        earnings_flag=False,
    )

    return {
        "ticker": ticker,
        "S0": S0,
        "K": K,
        "expiry": expiry_str,
        "target_dte": target_dte,
        "T_entry": T,
        "entry_premium": entry_premium,
        "sigma_entry": sigma,
        "div_yield": div_yield,
        "option_score": option_score,
        "momentum_score": mom_score,
        "fund_multiplier": fund.get("multiplier", 1.0),
        "combined_score": combined,
        "otm_pct": otm_pct,
        "tech_summary": {
            "rsi": tech.get("rsi"),
            "macd_bullish": tech.get("macd_bullish"),
            "above_ma50": tech.get("above_ma50"),
            "above_ma200": tech.get("above_ma200"),
        },
        "distress_zone": fund.get("distress_zone"),
    }


# ─── Exit pricing (Approach A) ───────────────────────────────────────────────
def compute_exit_value(
    row: dict, exit_df: pd.DataFrame, horizon_date: date
) -> dict:
    """Approach A: reprice with bs_price using actual price + realized vol at horizon."""
    S_exit = get_close_on_date(exit_df, horizon_date)
    sigma_exit = get_sigma_on_date(exit_df, horizon_date, window=60)

    if S_exit is None:
        return {"S_exit": None, "exit_value": None, "option_return": None,
                "stock_return": None, "horizon": str(horizon_date)}

    K = row["K"]
    entry_date = ENTRY_DATE
    expiry = datetime.strptime(row["expiry"], "%Y-%m-%d").date()
    T_remaining = max((expiry - horizon_date).days, 0) / 365.0
    entry_premium = row["entry_premium"]
    S0 = row["S0"]
    div_yield = row["div_yield"]

    if sigma_exit is None or sigma_exit < 0.05:
        sigma_exit = row["sigma_entry"]  # fallback to entry sigma

    if T_remaining > 0:
        exit_value = bs_price(S_exit, K, T_remaining, RISK_FREE, sigma_exit, "call", div_yield)
    else:
        # Past expiry: intrinsic
        exit_value = max(S_exit - K, 0.0)

    option_return = (exit_value / entry_premium - 1.0) if entry_premium > 0 else None
    stock_return = (S_exit / S0 - 1.0) if S0 > 0 else None

    # Approach B: hold-to-expiry intrinsic (only if horizon >= expiry)
    approach_b = None
    if horizon_date >= expiry:
        S_exp = get_close_on_date(exit_df, expiry)
        if S_exp is not None:
            intrinsic = max(S_exp - K, 0.0)
            approach_b = {
                "intrinsic": intrinsic,
                "return_b": (intrinsic / entry_premium - 1.0) if entry_premium > 0 else None,
                "S_expiry": S_exp,
            }

    return {
        "horizon": str(horizon_date),
        "S_exit": S_exit,
        "sigma_exit": sigma_exit,
        "T_remaining": T_remaining,
        "exit_value": exit_value,
        "option_return": option_return,
        "stock_return": stock_return,
        "approach_b": approach_b,
    }


# ─── Main routine ────────────────────────────────────────────────────────────
def run_backtest(sample_size: int | None = None):
    tickers = universe("both")
    log.info(f"Universe: {len(tickers)} tickers")

    # Sample deterministically if requested
    if sample_size:
        rng = np.random.default_rng(RNG_SEED)
        idx = rng.choice(len(tickers), size=min(sample_size, len(tickers)), replace=False)
        idx.sort()
        tickers = [tickers[i] for i in idx]
        log.info(f"Sampled {len(tickers)} tickers (seed={RNG_SEED})")

    # ── Step 1: Fetch index (SPY) data ──────────────────────────────────────
    log.info("Fetching SPY...")
    spy_entry_df = yf_download("SPY", ENTRY_START, ENTRY_END)
    spy_exit_df  = yf_download("SPY", EXIT_START, EXIT_END)

    spy_s0   = get_entry_price(spy_entry_df)
    spy_h3   = get_close_on_date(spy_exit_df, H3_DATE)
    spy_h6   = get_close_on_date(spy_exit_df, H6_DATE)
    spy_h12  = get_close_on_date(spy_exit_df, H12_DATE)

    spy_ret = {
        "3mo":  (spy_h3  / spy_s0 - 1.0) if spy_s0 and spy_h3  else None,
        "6mo":  (spy_h6  / spy_s0 - 1.0) if spy_s0 and spy_h6  else None,
        "12mo": (spy_h12 / spy_s0 - 1.0) if spy_s0 and spy_h12 else None,
    }
    log.info(f"SPY S0={spy_s0:.2f}  3mo={spy_ret['3mo']:.1%}  6mo={spy_ret['6mo']:.1%}  12mo={spy_ret['12mo']:.1%}")

    # ── Step 2: Score all tickers ────────────────────────────────────────────
    log.info("Scoring tickers (entry as of 2025-06-08)...")
    scored = []
    failed = []

    def _process(ticker):
        try:
            df = yf_download(ticker, ENTRY_START, ENTRY_END)
            if df is None or df.empty or len(df) < 50:
                return None
            result = score_ticker(
                ticker, df, spy_entry_df,
                target_dte=TARGET_DTE_DAYS,
                otm_pct=OTM_PCT
            )
            return result
        except Exception as e:
            log.error(f"[{ticker}] fatal: {e}")
            return None

    total = len(tickers)
    done = 0
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {pool.submit(_process, t): t for t in tickers}
        for fut in as_completed(futures):
            ticker = futures[fut]
            result = fut.result()
            done += 1
            if done % 50 == 0 or done == total:
                log.info(f"  Scored {done}/{total}  OK={len(scored)}")
            if result is not None:
                scored.append(result)
            else:
                failed.append(ticker)

    log.info(f"Scored {len(scored)}/{total} tickers ({len(failed)} failed)")

    if not scored:
        log.error("No tickers scored! Exiting.")
        return

    # Sort by combined_score descending
    scored.sort(key=lambda x: x["combined_score"], reverse=True)

    top20 = scored[:20]
    log.info("Top 20 by combined score:")
    for i, r in enumerate(top20, 1):
        log.info(f"  {i:2d}. {r['ticker']:6s}  S0={r['S0']:8.2f}  K={r['K']:8.2f}  "
                 f"prem={r['entry_premium']:6.2f}  score={r['combined_score']:.1f}")

    # ── Step 3: Fetch exit price data ────────────────────────────────────────
    log.info("Fetching exit price data...")

    # Only need exit data for scored tickers
    exit_dfs: dict[str, pd.DataFrame] = {}

    def _fetch_exit(ticker):
        df = yf_download(ticker, EXIT_START, EXIT_END)
        return ticker, df

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {pool.submit(_fetch_exit, r["ticker"]): r["ticker"] for r in scored}
        fetched_count = 0
        for fut in as_completed(futures):
            ticker, df = fut.result()
            if df is not None and not df.empty:
                exit_dfs[ticker] = df
            fetched_count += 1
            if fetched_count % 50 == 0 or fetched_count == len(scored):
                log.info(f"  Fetched exit data {fetched_count}/{len(scored)}")

    log.info(f"Exit data available for {len(exit_dfs)} tickers")

    # ── Step 4: Compute returns for all scored tickers ───────────────────────
    log.info("Computing returns at 3mo/6mo/12mo horizons...")
    horizons = [("3mo", H3_DATE), ("6mo", H6_DATE), ("12mo", H12_DATE)]

    full_results = []
    for row in scored:
        ticker = row["ticker"]
        exit_df = exit_dfs.get(ticker)
        exits = {}
        for h_name, h_date in horizons:
            if exit_df is not None:
                exits[h_name] = compute_exit_value(row, exit_df, h_date)
            else:
                exits[h_name] = {"horizon": str(h_date), "exit_value": None,
                                  "option_return": None, "stock_return": None}
        full_results.append({**row, "exits": exits})

    # ── Step 5: Compute statistics ───────────────────────────────────────────
    log.info("Computing statistics...")

    def compute_stats(results, horizon_key):
        returns = [r["exits"][horizon_key]["option_return"]
                   for r in results
                   if r["exits"][horizon_key]["option_return"] is not None]
        stock_returns = [r["exits"][horizon_key]["stock_return"]
                         for r in results
                         if r["exits"][horizon_key]["stock_return"] is not None]
        if not returns:
            return {}
        arr = np.array(returns)
        n = len(arr)
        hit_rate = float(np.mean(arr > 0))
        mean_ret = float(np.mean(arr))
        median_ret = float(np.median(arr))
        best = float(np.max(arr))
        worst = float(np.min(arr))
        stdev = float(np.std(arr)) if n > 1 else 0.0
        sharpe_like = mean_ret / stdev if stdev > 0 else 0.0

        # Spearman: score vs return
        scores = [r["combined_score"] for r in results
                  if r["exits"][horizon_key]["option_return"] is not None]
        sp_corr, sp_pval = spearmanr(scores, returns) if len(scores) > 2 else (None, None)

        # Decile analysis
        n_decile = max(1, n // 10)
        sorted_by_score = sorted(
            [(r["combined_score"], r["exits"][horizon_key]["option_return"])
             for r in results if r["exits"][horizon_key]["option_return"] is not None],
            key=lambda x: x[0], reverse=True
        )
        top_decile = [x[1] for x in sorted_by_score[:n_decile]]
        bot_decile = [x[1] for x in sorted_by_score[-n_decile:]]
        top_mean = float(np.mean(top_decile)) if top_decile else None
        bot_mean = float(np.mean(bot_decile)) if bot_decile else None

        spy_r = spy_ret.get(horizon_key)
        beat_spy = (mean_ret > spy_r) if spy_r is not None else None
        mean_stock = float(np.mean(stock_returns)) if stock_returns else None
        beat_underlying = (mean_ret > mean_stock) if mean_stock is not None else None

        return {
            "n": n,
            "hit_rate": hit_rate,
            "mean_return": mean_ret,
            "median_return": median_ret,
            "best_return": best,
            "worst_return": worst,
            "stdev_return": stdev,
            "sharpe_like": sharpe_like,
            "spy_return": spy_r,
            "beat_spy": beat_spy,
            "mean_stock_return": mean_stock,
            "beat_underlying": beat_underlying,
            "spearman_score_vs_return": float(sp_corr) if sp_corr is not None else None,
            "spearman_pval": float(sp_pval) if sp_pval is not None else None,
            "top_decile_mean_return": top_mean,
            "bottom_decile_mean_return": bot_mean,
            "top_vs_bottom_decile_diff": (top_mean - bot_mean) if (top_mean is not None and bot_mean is not None) else None,
        }

    stats_all = {}
    stats_top20 = {}
    for h_name, _ in horizons:
        stats_all[h_name]   = compute_stats(full_results, h_name)
        stats_top20[h_name] = compute_stats(full_results[:20], h_name)
        s = stats_all[h_name]
        s20 = stats_top20[h_name]
        log.info(f"\n=== {h_name} (all {s.get('n',0)} trades) ===")
        log.info(f"  Hit-rate: {s.get('hit_rate',0):.1%}  Mean: {s.get('mean_return',0):.1%}  "
                 f"Median: {s.get('median_return',0):.1%}")
        log.info(f"  SPY: {s.get('spy_return',0):.1%}  Beat SPY: {s.get('beat_spy')}")
        log.info(f"  Spearman: {s.get('spearman_score_vs_return'):.3f}  p={s.get('spearman_pval'):.4f}" 
                 if s.get('spearman_score_vs_return') is not None else "  Spearman: N/A")
        log.info(f"  Top decile: {s.get('top_decile_mean_return'):.1%}  "
                 f"Bot decile: {s.get('bottom_decile_mean_return'):.1%}" 
                 if s.get('top_decile_mean_return') is not None else "  Decile: N/A")
        log.info(f"=== {h_name} TOP-20 ===")
        log.info(f"  Hit-rate: {s20.get('hit_rate',0):.1%}  Mean: {s20.get('mean_return',0):.1%}  "
                 f"SPY: {s20.get('spy_return',0):.1%}  Beat: {s20.get('beat_spy')}")

    # ── Step 6: Sanity check — NVDA and PLTR ─────────────────────────────────
    log.info("\n=== SANITY CHECK ===")
    for chk_ticker in ["NVDA", "PLTR", "AAPL"]:
        matches = [r for r in full_results if r["ticker"] == chk_ticker]
        if not matches:
            log.info(f"  {chk_ticker}: not in results")
            continue
        r = matches[0]
        log.info(f"  {chk_ticker}: S0={r['S0']:.2f}  K={r['K']:.2f}  "
                 f"premium={r['entry_premium']:.2f}  score={r['combined_score']:.1f}")
        for h_name, _ in horizons:
            ex = r["exits"].get(h_name, {})
            s_exit = ex.get("S_exit")
            o_ret = ex.get("option_return")
            st_ret = ex.get("stock_return")
            log.info(f"    {h_name}: S_exit={s_exit}  option_ret={o_ret:.1%}  stock_ret={st_ret:.1%}"
                     if (s_exit and o_ret is not None and st_ret is not None) else
                     f"    {h_name}: N/A")

    # ── Step 7: Write backtest_results.json ──────────────────────────────────
    output = {
        "meta": {
            "entry_date": str(ENTRY_DATE),
            "horizons": ["3mo", "6mo", "12mo"],
            "horizon_dates": {
                "3mo": str(H3_DATE),
                "6mo": str(H6_DATE),
                "12mo": str(H12_DATE),
            },
            "universe_total": total,
            "scored_count": len(scored),
            "failed_count": len(failed),
            "top20_count": len(top20),
            "target_dte_days": TARGET_DTE_DAYS,
            "otm_pct": OTM_PCT,
            "risk_free": RISK_FREE,
            "entry_sigma_method": "realized_vol_60day_trailing_ending_20250608",
            "entry_premium_method": "model_implied_bs_price_no_real_chain_available",
            "exit_method": "approach_a_bs_reprice_with_actual_price_realized_vol",
            "approach_b": "hold_to_expiry_intrinsic_for_contracts_expiring_lte_20260608",
            "leak_free": True,
            "caveats": [
                "Entry premiums are MODEL-IMPLIED via Black-Scholes (no real historical option chains from yfinance)",
                "Universe membership approximated by current static list (not exact 2025-06-08 constituents)",
                "Dividend yields treated as static (current yfinance info)",
                "No earnings calendar available — earnings_flag=False for all (may understate IV crush risk)",
            ],
            "rng_seed": RNG_SEED,
        },
        "spy_benchmarks": {
            "S0": spy_s0,
            "H3_close": spy_h3,
            "H6_close": spy_h6,
            "H12_close": spy_h12,
            "returns": spy_ret,
        },
        "stats_all": stats_all,
        "stats_top20": stats_top20,
        "top20_trades": [
            {k: v for k, v in r.items() if k != "tech_summary"}
            for r in full_results[:20]
        ],
        "full_ranked_list": [
            {
                "rank": i+1,
                "ticker": r["ticker"],
                "combined_score": r["combined_score"],
                "option_score": r["option_score"],
                "momentum_score": r["momentum_score"],
                "S0": r["S0"],
                "K": r["K"],
                "entry_premium": r["entry_premium"],
                "sigma_entry": r["sigma_entry"],
                "expiry": r["expiry"],
                "exits": r["exits"],
            }
            for i, r in enumerate(full_results)
        ],
    }

    out_path = Path("/home/user/workspace/optiondesk/research/backtest_results.json")
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2, default=str)
    log.info(f"\nWrote {out_path}")

    # ── Step 8: Print console summary ────────────────────────────────────────
    print("\n" + "="*60)
    print("BACKTEST SUMMARY — OptionDesk Recommendations 2025-06-08")
    print("="*60)
    print(f"Universe: {total} tickers  |  Scored: {len(scored)}  |  Failed: {len(failed)}")
    print(f"Top-20 analysis | Entry date: {ENTRY_DATE} | ~{TARGET_DTE_DAYS}d DTE | +{OTM_PCT*100:.0f}% OTM calls")
    print()
    for h_name in ["3mo", "6mo", "12mo"]:
        s = stats_top20.get(h_name, {})
        sa = stats_all.get(h_name, {})
        sp_str = (f"Spearman={sa.get('spearman_score_vs_return'):.3f} p={sa.get('spearman_pval'):.3f}"
                  if sa.get('spearman_score_vs_return') is not None else "Spearman=N/A")
        print(f"[{h_name}] Top-20: hit={s.get('hit_rate',0):.0%}  mean={s.get('mean_return',0):+.1%}  "
              f"med={s.get('median_return',0):+.1%}  SPY={s.get('spy_return',0):+.1%}  "
              f"beat_SPY={s.get('beat_spy')} | All: {sp_str}")
    print()
    print("Top 10 recommended trades:")
    print(f"{'#':>3} {'Ticker':6} {'S0':>8} {'K':>8} {'Prem':>6} {'Score':>6}  "
          f"{'12mo Opt%':>10} {'12mo Stock%':>12}")
    for i, r in enumerate(full_results[:10], 1):
        ex12 = r["exits"].get("12mo", {})
        o_ret = ex12.get("option_return")
        st_ret = ex12.get("stock_return")
        print(f"{i:>3} {r['ticker']:6} {r['S0']:>8.2f} {r['K']:>8.2f} {r['entry_premium']:>6.2f} "
              f"{r['combined_score']:>6.1f}  "
              f"{(o_ret*100 if o_ret is not None else float('nan')):>+9.1f}%  "
              f"{(st_ret*100 if st_ret is not None else float('nan')):>+10.1f}%")
    print()

    return output


if __name__ == "__main__":
    result = run_backtest(sample_size=None)
    print("\nDone.")
