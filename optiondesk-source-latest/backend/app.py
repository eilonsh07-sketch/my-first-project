"""
app.py — OptionDesk FastAPI server (port 8000).
Endpoints power the 7-tab decision calculator.
All heavy quant runs here in Python: BS, Monte Carlo, technicals, fundamentals.
"""
from __future__ import annotations

import os
import math
import threading
from datetime import datetime, date

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional, List

from engine.provider import PROVIDER
from engine import technicals as T
from engine import fundamentals as F
from engine import scoring as SC
from engine import strategies as ST
from engine import spreads as SP
from engine import store as DB
from engine.pricing import (bs_price, bs_greeks, monte_carlo_option,
                            monte_carlo_option_early, mc_distribution)

app = FastAPI(title="OptionDesk")

# CORS: allow the deployed frontend origin(s). Defaults to "*" so local dev and
# the Perplexity preview keep working; set ALLOWED_ORIGINS (comma-separated) in
# production to lock it down to your Vercel URL.
_origins_env = os.environ.get("ALLOWED_ORIGINS", "").strip()
_allow_origins = [o.strip() for o in _origins_env.split(",") if o.strip()] or ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allow_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ----------------------------- access gate -----------------------------
# Server-side authentication: every /api/* call must carry the correct access
# code in the X-Access-Code header, otherwise the data never leaves the server.
# This protects the quant results (pricing, rankings, ideas) from anyone who
# discovers the backend URL but does not have the code. The pricing/ranking
# FORMULAS themselves already live only on the server (never shipped to the
# browser); this gate additionally locks down the RESULTS.
#
# To change the code, set ACCESS_CODE in the environment (Render dashboard).
# Defaults to the same code the frontend gate uses.
ACCESS_CODE = os.environ.get("ACCESS_CODE", "7777").strip()

# Paths that must stay open (no code required):
#   - /api/health      : the frontend pings this to wake the server BEFORE the
#                        user has entered the code, so it must be public.
#   - docs/openapi      : harmless, and only useful for debugging.
_OPEN_PATHS = {"/api/health", "/", "/docs", "/openapi.json", "/redoc"}


@app.middleware("http")
async def _require_access_code(request: Request, call_next):
    path = request.url.path
    # CORS preflight (OPTIONS) carries no custom headers by design — let it pass
    # so the browser can complete the preflight and then send the real request.
    if request.method == "OPTIONS" or path in _OPEN_PATHS:
        return await call_next(request)
    # Only guard the API surface; static/other paths are not sensitive.
    if not path.startswith("/api/"):
        return await call_next(request)
    supplied = (request.headers.get("X-Access-Code") or "").strip()
    if supplied != ACCESS_CODE:
        print(f"[AUTH] FAIL — supplied_len={len(supplied)} expected_len={len(ACCESS_CODE)} match={supplied==ACCESS_CODE}")
        return JSONResponse(
            status_code=401,
            content={"detail": "קוד גישה שגוי או חסר."},
        )
    print(f"[AUTH] OK — len={len(supplied)}")
    return await call_next(request)

try:
    DB.init_db()
except Exception as _e:  # storage is optional for the calculator core
    print(f"[store] init skipped: {_e}")

INDEX = "SPY"
MAX_LEAPS_DTE = 730  # allow up to ~2 years when LEAPS toggle is on

# Scanner performance tuning (keeps scans responsive on small servers).
# We keep FULL expiry coverage (no subsampling) and instead fetch the option
# chains in PARALLEL — the real bottleneck on a free-tier host is the sequential
# Yahoo network round-trips (one per expiry), not the scan breadth itself.
SCAN_MAX_EXPIRIES = 16  # safety cap on number of in-range expiries to scan
SCAN_BULK_MC = 1500     # Monte Carlo sims per contract during bulk filtering
# Yahoo throttles bursts of option-metadata requests from a single IP, so high
# concurrency makes per-expiry chain fetches come back empty ("Available
# expirations are: []"). Empirically 2 concurrent fetches return 8/8 reliably
# while 3+ start dropping chains. Combined with the retry-with-fresh-session
# logic in provider.option_chain, 2 workers gives full coverage and stays fast.
SCAN_FETCH_WORKERS = 2  # parallel option-chain fetches against the provider


def _inrange_scan_expiries(exps: List[str], horizon: int,
                           max_count: int = SCAN_MAX_EXPIRIES) -> List[str]:
    """Return ALL expiries that fall inside the active horizon (sorted nearest
    first), capped at `max_count` as a safety limit. No subsampling — full
    breadth is restored; the chains are fetched in parallel for speed."""
    today = date.today()
    valid = []
    for e in exps:
        try:
            d = (datetime.strptime(e, "%Y-%m-%d").date() - today).days
        except Exception:
            continue
        if 0 < d <= horizon:
            valid.append((d, e))
    valid.sort(key=lambda t: t[0])
    return [e for _, e in valid[:max_count]]


def _fetch_chains_parallel(ticker: str, exps: List[str]) -> List[tuple]:
    """Fetch option chains for many expiries concurrently. Returns a list of
    (expiry, chain) tuples in the SAME order as `exps`. Expiries whose fetch
    fails are skipped. This parallelizes the per-expiry network round-trips so
    full-breadth scans stay fast even on a slow free-tier host."""
    from concurrent.futures import ThreadPoolExecutor

    def _one(e):
        try:
            return e, PROVIDER.option_chain(ticker, e)
        except Exception:
            return e, None

    if not exps:
        return []
    workers = min(SCAN_FETCH_WORKERS, len(exps))
    with ThreadPoolExecutor(max_workers=workers) as ex:
        fetched = dict(ex.map(_one, exps))
    return [(e, fetched[e]) for e in exps if fetched.get(e) is not None]

# Cache for Hebrew company descriptions (per ticker, in-memory)
_DESC_CACHE: dict[str, str] = {}


def _first_sentences(text: str, max_sentences: int = 3, max_chars: int = 480) -> str:
    """Trim a long English summary down to its first few sentences so the
    translated Hebrew stays concise (and within the free endpoint's limits)."""
    import re
    text = (text or "").strip()
    if not text:
        return ""
    parts = re.split(r"(?<=[.!?])\s+", text)
    out = ""
    for p in parts[:max_sentences]:
        if len(out) + len(p) + 1 > max_chars and out:
            break
        out = (out + " " + p).strip()
    if not out:
        out = text[:max_chars]
    return out


def _translate_to_hebrew_free(text: str) -> Optional[str]:
    """Translate English text to Hebrew using free, key-less public endpoints.
    Tries the Google translate gateway first, then MyMemory as a backup.
    Returns None if both fail (caller falls back to the English text)."""
    import urllib.request, urllib.parse, json
    text = (text or "").strip()
    if not text:
        return None
    headers = {"User-Agent": "Mozilla/5.0"}
    # 1) Google translate gateway (no key). 'iw' is the legacy code for Hebrew.
    try:
        params = {"client": "gtx", "sl": "en", "tl": "iw", "dt": "t", "q": text}
        url = "https://translate.googleapis.com/translate_a/single?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=8) as r:
            data = json.loads(r.read().decode("utf-8"))
        out = "".join(seg[0] for seg in data[0] if seg and seg[0]).strip()
        if out:
            return out
    except Exception:
        pass
    # 2) MyMemory backup (no key). Limited to ~500 chars per request.
    try:
        params = {"q": text[:480], "langpair": "en|he"}
        url = "https://api.mymemory.translated.net/get?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=8) as r:
            data = json.loads(r.read().decode("utf-8"))
        out = (data.get("responseData", {}) or {}).get("translatedText", "").strip()
        # MyMemory echoes the input on failure; reject if it returns no Hebrew.
        if out and any("\u0590" <= ch <= "\u05ea" for ch in out):
            return out
    except Exception:
        pass
    return None


def _hebrew_business_summary(ticker: str, info: dict) -> Optional[str]:
    """Summarize the company's business in 2-3 Hebrew sentences using the LLM.
    Cached per ticker. When no LLM endpoint is configured, falls back to a
    free key-less translation of the English summary, and finally to the raw
    English text if translation is unavailable."""
    key = ticker.upper()
    if key in _DESC_CACHE:
        return _DESC_CACHE[key]
    raw = info.get("longBusinessSummary") or info.get("description")
    name = info.get("longName") or info.get("shortName") or key
    sector = info.get("sector")
    industry = info.get("industry")
    if not raw and not sector:
        return None
    # The LLM summary only works where an Anthropic-compatible endpoint is
    # available (Perplexity preview, or an external host with ANTHROPIC_API_KEY).
    # Otherwise we fall back to a free Hebrew translation of the summary, and
    # finally to the raw English text below.
    if not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_BASE_URL")):
        source = _first_sentences(raw) if raw else (
            f"{name} operates in the {industry or sector} sector.")
        translated = _translate_to_hebrew_free(source)
        result = translated or raw
        if result:
            _DESC_CACHE[key] = result
        return result
    try:
        from anthropic import Anthropic
        client = Anthropic()
        model_name = os.environ.get("ANTHROPIC_MODEL", "claude_sonnet_4_6")
        context = f"Company: {name}\nSector: {sector}\nIndustry: {industry}\n\nBusiness summary (English):\n{raw or '(none provided)'}"
        msg = client.messages.create(
            model=model_name,
            max_tokens=350,
            messages=[{
                "role": "user",
                "content": (
                    "סכם ב-2 עד 3 משפטים בעברית תקינה וברורה במה החברה עוסקת — מוצרים, שירותים ותחומי פעילות עיקריים. "
                    "כתוב רק את התיאור בעברית, ללא הקדמה וללא מילים באנגלית. אל תמציא עובדות שלא מופיעות למטה.\n\n" + context
                ),
            }],
        )
        text = "".join(b.text for b in msg.content if getattr(b, "type", None) == "text").strip()
        if text:
            _DESC_CACHE[key] = text
            return text
    except Exception:
        pass
    # fallback: return raw English summary (frontend will label it)
    return raw


# ----------------------------- helpers -----------------------------
def _drift_from_tech(tech, fallback=0.08):
    """Estimate a modest real-world annualized drift, bounded for sanity."""
    rs = tech.get("relative_strength") if tech else None
    base = fallback
    if rs and rs.get("stock_return") is not None:
        base = max(-0.15, min(0.25, rs["stock_return"]))  # damp historical to forward
    return base


def _cagr_3y(ticker):
    """Annualized 3-year price CAGR from history; None if insufficient data."""
    try:
        h = PROVIDER.history(ticker, "3y")
        if h is None or len(h) < 200:
            return None
        close = h["Close"] if "Close" in h else h.iloc[:, 0]
        start = float(close.iloc[0])
        end = float(close.iloc[-1])
        if start <= 0 or end <= 0:
            return None
        years = max(len(close) / 252.0, 0.5)
        return (end / start) ** (1.0 / years) - 1.0
    except Exception:
        return None


def _iv_band(chain, S):
    """Crude IV band from the chain (min/max IV among near-money options)."""
    ivs = [c["iv"] for c in chain["calls"] + chain["puts"]
           if c.get("iv") and 0.5 * S <= c["strike"] <= 1.5 * S]
    if len(ivs) < 3:
        return None
    return (min(ivs), max(ivs))


def _full_context(ticker):
    """Fetch everything needed across tabs once."""
    q = PROVIDER.quote(ticker)
    S = q["price"]
    hist = PROVIDER.history(ticker, "1y")
    try:
        idx = PROVIDER.history(INDEX, "1y")
    except Exception:
        idx = None
    info = PROVIDER.info(ticker)
    tech = T.technical_summary(hist, idx)
    return q, S, hist, info, tech


# ----------------------------- models -----------------------------
class ScanReq(BaseModel):
    ticker: str
    mode: str = "percent"          # 'percent' | 'target'
    target_return_pct: float = 100  # e.g. 100 => +100%
    target_price: Optional[float] = None
    max_dte: int = 183
    atr_filter: bool = True
    leaps: bool = False            # allow expiries beyond 6 months (up to ~2y)
    instrument: str = "call"       # 'call' | 'put' | 'bull_call' | 'bear_put'


class DistReq(BaseModel):
    ticker: str
    expiry: str
    strike: float
    kind: str = "call"
    target_return_pct: float = 100
    n: int = 10000


class WhatIfReq(BaseModel):
    spot: float
    strike: float
    dte: int
    iv: float                       # annualized sigma (e.g. 0.55)
    premium: float                  # entry premium per share
    kind: str = "call"
    mu: float = 0.08                # real-world annualized drift
    target_return_pct: float = 100
    n: int = 6000


class RankReq(BaseModel):
    tickers: List[str]


class WatchAddReq(BaseModel):
    kind: str = "stock"            # 'option' | 'stock'
    ticker: str
    label: Optional[str] = None
    contract: Optional[str] = None
    option_kind: Optional[str] = None
    strike: Optional[float] = None
    expiry: Optional[str] = None
    target_return_pct: float = 100
    alert_score: float = 70
    notes: Optional[str] = None


class WatchUpdateReq(BaseModel):
    label: Optional[str] = None
    target_return_pct: Optional[float] = None
    alert_score: Optional[float] = None
    notes: Optional[str] = None


class StrategyReq(BaseModel):
    ticker: str
    strategy: str = "long_call"
    spot: Optional[float] = None
    iv: Optional[float] = None
    dte: int = 30
    target_return_pct: float = 100
    legs: Optional[list] = None
    earnings_crush: bool = False


class CompareReq(BaseModel):
    contracts: List[dict]   # each: {ticker, expiry, kind, strike}


# ----------------------------- endpoints -----------------------------
@app.get("/api/health")
def health():
    return {"ok": True, "provider": PROVIDER.name}


@app.get("/api/verify")
def verify():
    """Lightweight authenticated ping — Gate.jsx calls this to confirm the access code is correct."""
    return {"ok": True}


class BacktestReq(BaseModel):
    ticker: str
    otm_pct: float = 5.0
    dte: int = 30
    target_return_pct: float = 50.0
    stop_loss_pct: float = 50.0
    vol_window: int = 30


@app.post("/api/backtest")
def backtest(req: BacktestReq):
    """מבחן היסטורי מבוסס-מודל לאסטרטגיית call על פני 3 שנים."""
    try:
        from engine import backtest as BT
        hist = PROVIDER.history(req.ticker, "3y")
        closes = [float(x) for x in hist["Close"].dropna().tolist()]
        result = BT.run_backtest(
            closes,
            otm_pct=req.otm_pct, dte=req.dte,
            target_return_pct=req.target_return_pct,
            stop_loss_pct=req.stop_loss_pct, vol_window=req.vol_window,
        )
        if result.get("ok"):
            result["score_component"] = BT.backtest_score_component(result["summary"])
        result["ticker"] = req.ticker.upper()
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/economist")
def economist():
    """Economist Agent — macro regime, VIX rank, yield curve, Fed stance, VRP signal.
    All data is free (yfinance + FRED public API). No API key required.
    Cached 30 minutes — macro data doesn't change minute-to-minute."""
    from engine.provider import _cache_get, _cache_set
    cached = _cache_get("economist:macro", 1800)
    if cached is not None:
        return cached
    try:
        from engine.economist import macro_regime_report
        out = macro_regime_report()
        _cache_set("economist:macro", out)
        return out
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/market")
def market():
    """מצב שוק — S&P 500, סנטימנט סקטורים, VIX ואירועים כלכליים קרובים.
    כל הנתונים חינמיים (yfinance); הניסוח בעברית נעשה בקוד.

    מתוחזק ב-cache ל-90 שניות: בניית הסקירה דורשת ~13 שליפות (S&P + VIX + 11
    סקטורים) שאיטיות בתוכנית החינמית, אז הקריאה הראשונה איטית והשאר מיידיות.
    """
    from engine.provider import _cache_get, _cache_set
    cached = _cache_get("overview:market", 90)
    if cached is not None:
        return cached
    try:
        from engine import market as MK
        out = MK.build_overview(PROVIDER)
        _cache_set("overview:market", out)
        return out
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/quote/{ticker}")
def quote(ticker: str, leaps: bool = False):
    try:
        q = PROVIDER.quote(ticker)
        exps = PROVIDER.expirations(ticker)
        cap = MAX_LEAPS_DTE if leaps else SC.MAX_DTE
        # filter expirations to the active horizon (6mo default, ~2y with LEAPS)
        valid = []
        for e in exps:
            try:
                d = (datetime.strptime(e, "%Y-%m-%d").date() - date.today()).days
                if 0 < d <= cap:
                    valid.append({"date": e, "dte": d, "bucket": SC.dte_bucket(d),
                                  "leaps": d > SC.MAX_DTE})
            except Exception:
                continue
        # representative ATM IV
        atm_iv = None
        if valid:
            ch = PROVIDER.option_chain(ticker, valid[min(2, len(valid)-1)]["date"])
            near = sorted(ch["calls"], key=lambda c: abs((c["strike"] or 0) - q["price"]))
            if near and near[0].get("iv"):
                atm_iv = near[0]["iv"]
        q["atm_iv"] = atm_iv
        q["expirations"] = valid
        return q
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/scan")
def scan(req: ScanReq):
    try:
        q, S, hist, info, tech = _full_context(req.ticker)
        rv = tech.get("realized_vol")
        mu = _drift_from_tech(tech)
        exps = PROVIDER.expirations(req.ticker)

        if req.mode == "target" and req.target_price and req.target_price < S:
            warning = f"מחיר היעד (${req.target_price}) נמוך מהמחיר הנוכחי (${round(S,2)}) — קריאה דובית"
        else:
            warning = None

        target_return = 1.0 + (req.target_return_pct / 100.0)
        # active horizon: respect LEAPS toggle, capped at ~2y
        horizon = min(req.max_dte, MAX_LEAPS_DTE) if req.leaps else min(req.max_dte, SC.MAX_DTE)
        instrument = (req.instrument or "call").lower()

        # ---- Spread instruments (feature 5): scan real debit verticals ----
        if instrument in ("bull_call", "bear_put"):
            # Full expiry coverage, chains fetched in parallel for speed.
            spread_exps = _inrange_scan_expiries(exps, horizon)
            chain_by_expiry = _fetch_chains_parallel(req.ticker, spread_exps)
            sp_results = SP.scan_spreads(chain_by_expiry, S, mu, target_return,
                                         strategy=instrument)
            return {
                "ticker": req.ticker.upper(), "spot": S, "warning": warning,
                "drift_used": mu, "realized_vol": rv, "leaps": req.leaps,
                "instrument": instrument,
                "count": len(sp_results), "results": sp_results[:40],
            }

        # ---- Single-leg instruments: calls (default) or puts (feature 5) ----
        kind = "put" if instrument == "put" else "call"
        results = []
        # Stock-level context for the COMBINED scan score (option + technical +
        # focused fundamental). Computed ONCE per ticker, not per contract.
        ms = SC.momentum_score(tech)                       # technical momentum 0-100
        fund_risk = SC.fundamental_option_risk(info)       # focused fundamental haircut
        earnings_ts = info.get("earningsTimestamp") or info.get("earningsDate")
        # Full expiry coverage restored: scan EVERY in-range expiry. The chains
        # are fetched in parallel (the slow part is the network round-trips, not
        # the math), so breadth no longer costs us a multi-minute scan.
        scan_exps = _inrange_scan_expiries(exps, horizon)
        for e, chain in _fetch_chains_parallel(req.ticker, scan_exps):
            band = _iv_band(chain, S)
            pool = chain["puts"] if kind == "put" else chain["calls"]
            for c in pool:
                if not c.get("strike") or not c.get("iv"):
                    continue
                # near & slightly OTM window (mirror for puts: OTM is below spot)
                if kind == "call":
                    if c["strike"] < S * 0.85 or c["strike"] > S * 1.45:
                        continue
                else:
                    if c["strike"] < S * 0.55 or c["strike"] > S * 1.15:
                        continue
                ev = SC.evaluate_option(
                    c, S, e, mu=mu, realized_vol=rv,
                    target_return=target_return,
                    target_price=req.target_price,
                    n_mc=SCAN_BULK_MC, iv_band=band, max_dte=horizon,
                    early_exit=False,  # skip path sim in bulk; computed for top 40 below
                    american=False,    # תמחור אמריקאי רק למנצח היחיד (למטה) — שומר על מהירות/זיכרון
                )
                if not ev["passed_filters"]:
                    continue
                # ATR/sigma filter: reject moves needing > 2.5 std-dev
                if req.atr_filter and ev["sigma_move"] and ev["sigma_move"] > SC.MAX_SIGMA_MOVE:
                    continue
                # ---- Combined scan score: option quality + technical momentum,
                # adjusted by the focused fundamental option-risk layer and an
                # earnings-before-expiry haircut. This is what we rank by now.
                en_flag, en_days, en_note = SC.earnings_before_expiry(earnings_ts, ev["dte"])
                ev["momentum_score"] = ms
                ev["fundamental_risk"] = fund_risk
                ev["earnings_before_expiry"] = {
                    "flag": en_flag, "days_to_earnings": en_days, "note": en_note,
                }
                ev["scan_score"] = SC.scan_score(
                    ev["option_score"], ms,
                    fund_multiplier=fund_risk["multiplier"],
                    earnings_flag=en_flag,
                )
                results.append(ev)

        # Rank by the COMBINED score (option + technical + fundamental), not the
        # raw option score alone.
        results.sort(key=lambda r: r["scan_score"], reverse=True)
        top = results[:40]
        # Compute the early-exit ("sell before expiry") probability only for the
        # top results so the table can show both the early and expiry numbers
        # without running a path simulation on every scanned contract.
        for ev in top:
            mc = ev.get("monte_carlo")
            if mc and ev.get("premium") and ev.get("iv") and mc.get("T_years", 0) > 0:
                early = monte_carlo_option_early(
                    S, ev["strike"], mc["T_years"], SC.RISK_FREE, ev["iv"],
                    ev["premium"], ev.get("kind", "call"),
                    target_return=target_return, n=3000, steps=32, mu=mu,
                )
                mc["prob_hit_target_early"] = early["prob_hit_target_early"]
                mc["expected_max_value"] = early["expected_max_value"]
        return {
            "ticker": req.ticker.upper(), "spot": S, "warning": warning,
            "drift_used": mu, "realized_vol": rv, "leaps": req.leaps,
            "instrument": kind,
            # Stock-level context behind the combined score (shown in the UI).
            "momentum_score": ms,
            "fundamental_risk": fund_risk,
            "count": len(results), "results": top,
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/research/{ticker}")
def research(ticker: str):
    try:
        q, S, hist, info, tech = _full_context(ticker)
        mult = F.multiples_summary(info)
        sector = F.sector_comparison(info)
        # earnings date
        edate = info.get("earningsDate") or info.get("earningsTimestamp")
        return {
            "ticker": ticker.upper(), "spot": S, "quote": q,
            "technical": tech,
            "fundamental": mult,
            "sector_comparison": sector,
            "analyst": {
                "target_mean": F._g(info, "targetMeanPrice"),
                "target_high": F._g(info, "targetHighPrice"),
                "target_low": F._g(info, "targetLowPrice"),
                "recommendation": F._g(info, "recommendationKey"),
                "num_analysts": F._g(info, "numberOfAnalystOpinions"),
            },
            "earnings_date": str(edate) if edate else None,
            "name": info.get("longName") or info.get("shortName"),
            "momentum_score": SC.momentum_score(tech),
            "scorecard": T.technical_scorecard(tech),
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/company/{ticker}")
def company(ticker: str):
    try:
        q, S, hist, info, tech = _full_context(ticker)
        return {
            "ticker": ticker.upper(), "spot": S,
            "name": info.get("longName") or info.get("shortName"),
            "business_he": _hebrew_business_summary(ticker, info),
            "profile": {
                "sector": info.get("sector"),
                "industry": info.get("industry"),
                "employees": info.get("fullTimeEmployees"),
                "website": info.get("website"),
                "country": info.get("country"),
                "city": info.get("city"),
            },
            "dcf": F.dcf_fair_value(info, {}),
            "roic_wacc": F.roic_vs_wacc(info),
            "altman_z": F.altman_z(info),
            "multiples": F.multiples_summary(info),
            "sector_comparison": F.sector_comparison(info),
            "growth": {
                "revenue_growth": F._g(info, "revenueGrowth"),
                "earnings_growth": F._g(info, "earningsGrowth"),
            },
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/strategy")
def strategy(req: StrategyReq):
    try:
        q = PROVIDER.quote(req.ticker)
        S = req.spot if req.spot else q["price"]
        sigma = req.iv if req.iv else (q.get("atm_iv") or 0.5)
        if not req.iv:
            # fetch a representative IV
            exps = PROVIDER.expirations(req.ticker)
            if exps:
                ch = PROVIDER.option_chain(req.ticker, exps[min(2, len(exps)-1)])
                near = sorted([c for c in ch["calls"] if c.get("iv")],
                              key=lambda c: abs(c["strike"] - S))
                if near:
                    sigma = near[0]["iv"]
        T_years = max(req.dte, 1) / 365.0
        sigma_eff = ST.apply_iv_crush(sigma) if req.earnings_crush else sigma

        legs = ST.build_strategy(req.strategy, S, sigma_eff, T_years, req.legs)
        entry = ST.net_premium(legs, S, sigma_eff, T_years)
        greeks = ST.net_greeks(legs, S, sigma_eff, T_years)
        curve_exp = ST.pnl_curve(legs, S, sigma_eff, T_years, entry, at_expiry=True)
        curve_now = ST.pnl_curve(legs, S, sigma_eff, T_years, entry, at_expiry=False)
        expiry_label = (date.today().toordinal() + req.dte)
        exp_date = date.fromordinal(expiry_label).isoformat()
        target = ST.profit_target_solver(legs, S, sigma_eff, T_years, entry,
                                         req.target_return_pct / 100.0, exp_date)
        return {
            "ticker": req.ticker.upper(), "spot": S, "iv": sigma, "iv_effective": sigma_eff,
            "dte": req.dte, "strategy": req.strategy, "legs": legs,
            "entry_cost": round(entry * 100, 2), "entry_per_share": round(entry, 4),
            "greeks": greeks,
            "pnl_expiry": curve_exp, "pnl_now": curve_now,
            "profit_target": target,
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/compare")
def compare(req: CompareReq):
    """Compare options across DIFFERENT underlyings on a normalized basis."""
    try:
        out = []
        for c in req.contracts:
            ticker = c["ticker"]
            q, S, hist, info, tech = _full_context(ticker)
            rv = tech.get("realized_vol")
            mu = _drift_from_tech(tech)
            chain = PROVIDER.option_chain(ticker, c["expiry"])
            band = _iv_band(chain, S)
            pool = chain["calls"] if c.get("kind", "call") == "call" else chain["puts"]
            match = min(pool, key=lambda o: abs((o["strike"] or 0) - c["strike"]))
            try:
                _dp = PROVIDER.dividend_params(ticker)
            except Exception:
                _dp = None
            ev = SC.evaluate_option(match, S, c["expiry"], mu=mu, realized_vol=rv,
                                    target_return=2.0, n_mc=6000, iv_band=band,
                                    div_params=_dp, american=True)
            ms = SC.momentum_score(tech)
            verdict = SC.final_verdict(ev["option_score"], ms)
            out.append({
                "ticker": ticker.upper(), "spot": S,
                "option": ev, "momentum_score": ms, "verdict": verdict,
                "name": info.get("shortName"),
            })
        out.sort(key=lambda x: x["verdict"]["composite"], reverse=True)
        return {"comparison": out, "winner": out[0]["ticker"] if out else None}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/analyze")
def analyze(req: ScanReq):
    """Full 7-stage pipeline → Bottom Line. Returns the single best recommendation
    with both scores, plus per-stage transparency data."""
    try:
        q, S, hist, info, tech = _full_context(req.ticker)
        rv = tech.get("realized_vol")
        mu = _drift_from_tech(tech)
        ms = SC.momentum_score(tech)

        # Stage 1: chain pull (full horizon). Chains fetched in PARALLEL and the
        # bulk search uses a light MC with no path sim — same fast pattern as the
        # scanner. The single winning contract is then re-priced at full
        # precision below, so the Bottom Line stays both fast AND accurate.
        horizon = min(req.max_dte, MAX_LEAPS_DTE) if req.leaps else min(req.max_dte, SC.MAX_DTE)
        exps = _inrange_scan_expiries(PROVIDER.expirations(req.ticker), horizon)
        target_return = 1.0 + (req.target_return_pct / 100.0)

        best = None
        evaluated = 0
        # Track the contract that came CLOSEST to passing, so when nothing
        # qualifies we can still show "the near-miss" with the exact reasons it
        # was blocked (instead of an empty message). "Closest" = fewest blocking
        # reasons, then smallest required move in std-devs (the usual binding
        # constraint), then nearest to at-the-money.
        near_miss = None
        near_key = None
        for e, chain in _fetch_chains_parallel(req.ticker, exps):
            band = _iv_band(chain, S)
            for c in chain["calls"]:
                if not c.get("strike") or not c.get("iv"):
                    continue
                if c["strike"] < S * 0.85 or c["strike"] > S * 1.45:
                    continue
                ev = SC.evaluate_option(c, S, e, mu=mu, realized_vol=rv,
                                        target_return=target_return,
                                        target_price=req.target_price,
                                        n_mc=SCAN_BULK_MC, iv_band=band,
                                        max_dte=horizon, early_exit=False,
                                        american=False)  # באזור הסריקה — BS בלבד
                # Collect every blocking reason (hard filters + the ATR/sigma
                # filter, which is applied here rather than inside the engine).
                reasons = list(ev.get("fail_reasons") or [])
                atr_blocked = bool(
                    req.atr_filter and ev["sigma_move"]
                    and ev["sigma_move"] > SC.MAX_SIGMA_MOVE
                )
                if atr_blocked:
                    sm = round(ev["sigma_move"], 1)
                    reasons.append(
                        f"תנועה נדרשת {sm} סטיות-תקן (מעל {SC.MAX_SIGMA_MOVE}) — "
                        "היעד אגרסיבי מדי לתנודתיות"
                    )
                if reasons:
                    # Rank near-misses: fewer reasons first, then smaller
                    # required sigma-move, then closer to ATM.
                    key = (len(reasons),
                           ev["sigma_move"] if ev["sigma_move"] is not None else 9e9,
                           ev["otm_pct"])
                    if near_key is None or key < near_key:
                        near_key = key
                        nm = dict(ev)
                        nm["fail_reasons"] = reasons
                        near_miss = nm
                    continue
                evaluated += 1
                if best is None or ev["option_score"] > best["option_score"]:
                    best = ev

        # Re-price the single winning contract at FULL precision (path MC +
        # early-exit probability) so the headline recommendation is accurate.
        if best is not None:
            be = best
            try:
                _dp = PROVIDER.dividend_params(req.ticker)
            except Exception:
                _dp = None
            full = SC.evaluate_option(
                {"strike": be["strike"], "kind": be.get("kind", "call"),
                 "iv": be["iv"], "mid": be["premium"], "last": be["premium"],
                 "bid": None, "ask": None, "open_interest": be.get("liquidity_detail", {}).get("oi"),
                 "volume": be.get("liquidity_detail", {}).get("volume"),
                 "contract": be.get("contract")},
                S, be["expiry"], mu=mu, realized_vol=rv,
                target_return=target_return, target_price=req.target_price,
                n_mc=10000, iv_band=None, max_dte=horizon, early_exit=True,
                div_params=_dp, american=True)
            # keep liquidity/score from the original (full chain row had real bid/ask)
            full["option_score"] = be["option_score"]
            full["liquidity"] = be["liquidity"]
            full["liquidity_detail"] = be["liquidity_detail"]
            best = full

        # --- Historical backtest of the chosen strategy, folded INTO the score ---
        # Derive the strategy params from the single winning contract (its OTM %
        # and remaining life), reconstruct it over 3 years with full Black-Scholes,
        # and let the resulting evidence score become a real pillar of the verdict.
        backtest_block = None
        bt_score = None
        if best is not None:
            try:
                from engine import backtest as BT
                # Use a dedicated 3-year history (the shared context is only 1y,
                # which is too short for a meaningful backtest).
                bt_hist = PROVIDER.history(req.ticker, "3y")
                closes = [float(x) for x in bt_hist["Close"].dropna().tolist()]
                otm_pct = max(0.0, round((best["strike"] / S - 1.0) * 100.0, 1))
                bt_dte = int(best.get("dte") or 30)
                bt_res = BT.run_backtest(
                    closes, otm_pct=otm_pct, dte=bt_dte,
                    target_return_pct=req.target_return_pct,
                    stop_loss_pct=50.0, vol_window=30,
                )
                if bt_res.get("ok"):
                    bt_res["score_component"] = BT.backtest_score_component(bt_res["summary"])
                    bt_score = bt_res["score_component"]["score"]
                backtest_block = bt_res
            except Exception:
                backtest_block = None

        verdict = SC.final_verdict(best["option_score"], ms, backtest_score=bt_score) if best else \
                  {"composite": 0, "label": "אין אופציה כשירה", "tone": "avoid",
                   "base_score": 0, "option_score": 0, "momentum_score": ms,
                   "backtest_score": None, "backtest_multiplier": 1.0,
                   "weights": {"option": 0.6, "momentum": 0.4, "backtest_multiplier": 1.0}}

        # Long-term (3+ yr) buy-and-hold attractiveness of the UNDERLYING stock
        long_term = F.long_term_score(info, tech=tech, cagr_3y=_cagr_3y(req.ticker))

        return {
            "ticker": req.ticker.upper(), "spot": S, "name": info.get("shortName"),
            "long_term": long_term,
            "stages": {
                "chain": {"expirations_scanned": len(exps), "evaluated": evaluated},
                "pricing": {"realized_vol": rv, "drift": mu},
                "monte_carlo": best["monte_carlo"] if best else None,
                "technical": {"momentum_score": ms, "summary": tech,
                              "scorecard": T.technical_scorecard(tech)},
                "news": {"earnings_date": str(info.get("earningsDate")) if info.get("earningsDate") else None},
                "recommendation": best,
                "backtest": backtest_block,
                "tracker": {"contract": best["contract"] if best else None},
            },
            "backtest": backtest_block,
            "best_option": best,
            # When nothing qualified, surface the closest blocked contract and
            # the exact reasons it was rejected (frontend shows this instead of
            # an empty "no qualifying option" message).
            "near_miss": near_miss if best is None else None,
            "momentum_score": ms,
            "verdict": verdict,
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# ===================== Feature 4: MC distribution chart =====================
@app.post("/api/distribution")
def distribution(req: DistReq):
    """Histogram of the 10,000-scenario P&L distribution for one contract."""
    try:
        q, S, hist, info, tech = _full_context(req.ticker)
        mu = _drift_from_tech(tech)
        chain = PROVIDER.option_chain(req.ticker, req.expiry)
        pool = chain["calls"] if req.kind == "call" else chain["puts"]
        match = min([o for o in pool if o.get("iv") and (o.get("mid") or o.get("last"))],
                    key=lambda o: abs((o["strike"] or 0) - req.strike), default=None)
        if not match:
            raise HTTPException(status_code=400, detail="לא נמצאה אופציה תואמת בשרשרת")
        sigma = match["iv"]
        premium = match.get("mid") or match.get("last")
        T = max((datetime.strptime(req.expiry, "%Y-%m-%d").date() - date.today()).days, 1) / 365.0
        target_return = 1.0 + (req.target_return_pct / 100.0)
        dist = mc_distribution(S, match["strike"], T, SC.RISK_FREE, sigma, premium,
                               req.kind, target_return=target_return, n=req.n, mu=mu)
        return {
            "ticker": req.ticker.upper(), "spot": S, "strike": match["strike"],
            "kind": req.kind, "expiry": req.expiry, "premium": premium, "iv": sigma,
            "drift_mu": mu, "T_years": round(T, 4),
            "distribution": dist,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# ===================== Feature 3: live what-if recompute =====================
@app.post("/api/whatif")
def whatif(req: WhatIfReq):
    """Recompute pricing + probabilities for slider-driven μ/σ/time/spot changes.
    Pure quant — no network — so the frontend can call it on every slider move."""
    try:
        T = max(req.dte, 1) / 365.0
        target_return = 1.0 + (req.target_return_pct / 100.0)
        theo = bs_price(req.spot, req.strike, T, SC.RISK_FREE, req.iv, req.kind)
        greeks = bs_greeks(req.spot, req.strike, T, SC.RISK_FREE, req.iv, req.kind)
        mc = monte_carlo_option(req.spot, req.strike, T, SC.RISK_FREE, req.iv,
                                req.premium, req.kind, target_return=target_return,
                                n=req.n, mu=req.mu)
        early = monte_carlo_option_early(req.spot, req.strike, T, SC.RISK_FREE, req.iv,
                                         req.premium, req.kind, target_return=target_return,
                                         n=min(req.n, 4000), steps=40, mu=req.mu)
        if req.kind == "call":
            breakeven = req.strike + req.premium
        else:
            breakeven = req.strike - req.premium
        return {
            "theo_price": round(theo, 4),
            "edge": round(req.premium - theo, 4),
            "breakeven": round(breakeven, 2),
            "greeks": greeks,
            "prob_profit": mc["prob_profit"],
            "prob_hit_target": mc["prob_hit_target"],
            "prob_hit_target_early": early["prob_hit_target_early"],
            "prob_total_loss": mc["prob_total_loss"],
            "expected_pnl_pct": mc["expected_pnl_pct"],
            "expected_max_value": early["expected_max_value"],
            "median_terminal": mc["median_terminal"],
            "p10_terminal": mc["p10_terminal"],
            "p90_terminal": mc["p90_terminal"],
            "drift_mu": req.mu, "sigma": req.iv, "T_years": round(T, 4),
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# ============ Feature 6: long-term stock comparison / ranking ===============
def _long_term_for(ticker: str) -> dict:
    q, S, hist, info, tech = _full_context(ticker)
    lt = F.long_term_score(info, tech=tech, cagr_3y=_cagr_3y(ticker))
    return {
        "ticker": ticker.upper(),
        "name": info.get("shortName") or info.get("longName"),
        "spot": S,
        "sector": info.get("sector"),
        "score": lt.get("score"),
        "label": lt.get("label"),
        "tone": lt.get("tone"),
        "note": lt.get("note"),
        "axes": lt.get("axes"),
        "metrics": lt.get("metrics"),
    }


@app.post("/api/rank")
def rank(req: RankReq):
    """Rank several stocks by long-term buy-and-hold attractiveness (0-100)."""
    try:
        rows, errors = [], []
        seen = set()
        for t in req.tickers:
            tk = (t or "").strip().upper()
            if not tk or tk in seen:
                continue
            seen.add(tk)
            try:
                rows.append(_long_term_for(tk))
            except Exception as ex:
                errors.append({"ticker": tk, "error": str(ex)})
        rows.sort(key=lambda r: (r["score"] is not None, r["score"] or 0), reverse=True)
        return {"ranking": rows, "errors": errors, "count": len(rows)}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# ============ Features 1 & 2: Watchlist + Tracker + Alerts ==================
def _track_snapshot_for(item: dict) -> dict:
    """Compute today's tracked metrics for a watchlist item and return the payload
    (also used by the alerts checker)."""
    ticker = item["ticker"]
    q, S, hist, info, tech = _full_context(ticker)
    payload = {"spot": S}
    if item.get("kind") == "option" and item.get("strike") and item.get("expiry"):
        kind = item.get("option_kind") or "call"
        mu = _drift_from_tech(tech)
        rv = tech.get("realized_vol")
        try:
            chain = PROVIDER.option_chain(ticker, item["expiry"])
            band = _iv_band(chain, S)
            pool = chain["calls"] if kind == "call" else chain["puts"]
            match = min([o for o in pool if o.get("iv") and (o.get("mid") or o.get("last"))],
                        key=lambda o: abs((o["strike"] or 0) - item["strike"]), default=None)
        except Exception:
            match = None
        if match:
            tr = 1.0 + (float(item.get("target_return_pct", 100)) / 100.0)
            try:
                _dp = PROVIDER.dividend_params(ticker)
            except Exception:
                _dp = None
            ev = SC.evaluate_option(match, S, item["expiry"], mu=mu, realized_vol=rv,
                                    target_return=tr, n_mc=4000, iv_band=band,
                                    early_exit=True, div_params=_dp, american=True)
            mc = ev.get("monte_carlo") or {}
            payload.update({
                "metric": "option",
                "option_score": ev.get("option_score"),
                "premium": ev.get("premium"),
                "iv": ev.get("iv"),
                "prob_profit": mc.get("prob_profit"),
                "prob_hit_target": mc.get("prob_hit_target"),
                "prob_hit_target_early": mc.get("prob_hit_target_early"),
                "dte": ev.get("dte"),
                "hold_label": (ev.get("hold_to_expiry") or {}).get("he_label"),
            })
    else:
        lt = F.long_term_score(info, tech=tech, cagr_3y=_cagr_3y(ticker))
        payload.update({
            "metric": "stock",
            "long_term_score": lt.get("score"),
            "label": lt.get("label"),
            "tone": lt.get("tone"),
        })
    return payload


@app.get("/api/watchlist")
def watchlist_list():
    try:
        return {"items": DB.list_items()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/watchlist")
def watchlist_add(req: WatchAddReq):
    try:
        item = DB.add_item(req.dict())
        # take an immediate baseline snapshot so the tracker has a starting point
        try:
            snap = _track_snapshot_for(item)
            DB.add_snapshot(item["id"], snap.get("spot"), snap)
        except Exception:
            pass
        return {"item": item}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.patch("/api/watchlist/{item_id}")
def watchlist_update(item_id: int, req: WatchUpdateReq):
    try:
        fields = {k: v for k, v in req.dict().items() if v is not None}
        item = DB.update_item(item_id, fields)
        if not item:
            raise HTTPException(status_code=404, detail="פריט לא נמצא")
        return {"item": item}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.delete("/api/watchlist/{item_id}")
def watchlist_delete(item_id: int):
    try:
        DB.delete_item(item_id)
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/watchlist/{item_id}/history")
def watchlist_history(item_id: int):
    try:
        item = DB.get_item(item_id)
        if not item:
            raise HTTPException(status_code=404, detail="פריט לא נמצא")
        return {"item": item, "snapshots": DB.list_snapshots(item_id)}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/watchlist/{item_id}/track")
def watchlist_track(item_id: int):
    """Take a fresh snapshot now (manual refresh / daily tracker)."""
    try:
        item = DB.get_item(item_id)
        if not item:
            raise HTTPException(status_code=404, detail="פריט לא נמצא")
        snap = _track_snapshot_for(item)
        saved = DB.add_snapshot(item_id, snap.get("spot"), snap)
        return {"snapshot": saved}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/alerts/check")
def alerts_check():
    """Scan the whole watchlist, snapshot each item, and return any that BREACH
    their alert threshold. Designed to be hit by a morning scheduled task
    (feature 2). Options alert when option_score >= alert_score; stocks alert
    when long_term_score >= alert_score."""
    try:
        items = DB.list_items()
        triggered, checked, errors = [], 0, []
        for item in items:
            try:
                snap = _track_snapshot_for(item)
                DB.add_snapshot(item["id"], snap.get("spot"), snap)
                checked += 1
                thr = float(item.get("alert_score") or 70)
                if item.get("kind") == "option":
                    sc = snap.get("option_score")
                    if sc is not None and sc >= thr:
                        triggered.append({
                            "id": item["id"], "kind": "option", "ticker": item["ticker"],
                            "label": item.get("label"),
                            "score": sc, "threshold": thr,
                            "detail": snap,
                        })
                else:
                    sc = snap.get("long_term_score")
                    if sc is not None and sc >= thr:
                        triggered.append({
                            "id": item["id"], "kind": "stock", "ticker": item["ticker"],
                            "label": item.get("label"),
                            "score": sc, "threshold": thr,
                            "detail": snap,
                        })
            except Exception as ex:
                errors.append({"id": item.get("id"), "ticker": item.get("ticker"), "error": str(ex)})
        return {"checked": checked, "triggered": triggered, "errors": errors,
                "as_of": datetime.now().isoformat()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ----------------------------- Israeli market (TASE) -----------------------------
# Tel Aviv indices via Yahoo. Index quotes have NO volume on Yahoo, so we
# suppress volume-based indicators (OBV/VWAP) to avoid false signals.
ISRAEL_INDICES = {
    "TA35": {"yahoo": "TA35.TA", "name_he": "תל אביב 35", "name_en": "TA-35"},
    "TA125": {"yahoo": "^TA125.TA", "name_he": "תל אביב 125", "name_en": "TA-125"},
    "TA90": {"yahoo": "TA90.TA", "name_he": "תל אביב 90", "name_en": "TA-90"},
}


def _israel_quote_from_hist(hist):
    """Build a quote dict for an index from its daily history (Yahoo gives no
    reliable .info quote for TASE indices, so derive from the bars)."""
    close = hist["Close"].astype(float)
    price = float(close.iloc[-1])
    prev = float(close.iloc[-2]) if len(close) > 1 else None
    return {
        "price": price,
        "previous_close": prev,
        "change": (price - prev) if prev else None,
        "change_pct": ((price / prev - 1) * 100) if prev else None,
        "year_high": float(close.tail(252).max()),
        "year_low": float(close.tail(252).min()),
    }


@app.get("/api/israel/index/{index_id}")
def israel_index(index_id: str):
    """ניתוח טכני על מדד ישראלי (ברירת מחדל ת"א-35).
    מושך היסטוריה יומית מ-Yahoo (TA35.TA) ומריץ את מנוע הניתוח הטכני הקיים.
    מדדים ב-Yahoo ללא נתוני נפח — לכן OBV/VWAP מוסתרים."""
    key = (index_id or "TA35").upper()
    meta = ISRAEL_INDICES.get(key)
    if not meta:
        raise HTTPException(status_code=404,
                            detail=f"מדד לא נתמך: {index_id}. זמינים: {', '.join(ISRAEL_INDICES)}")
    try:
        hist = PROVIDER.history(meta["yahoo"], "2y")
        if hist is None or len(hist) < 60:
            raise ValueError("אין מספיק נתוני היסטוריה לניתוח טכני")
        tech = T.technical_summary(hist)
        # Yahoo index 'volume' is unreliable (often 0 intraday, inconsistent
        # historically, and never true market-wide volume for an index).
        # Volume-based indicators (OBV/VWAP) are therefore not trustworthy for
        # an index -> suppress them UNCONDITIONALLY to avoid false signals.
        has_volume = False  # indices: treat as volumeless on principle
        tech["obv_trend"] = None
        tech["vwap"] = None
        tech["above_vwap"] = None
        scorecard = T.technical_scorecard(tech, currency="₪")
        quote = _israel_quote_from_hist(hist)
        return {
            "index_id": key,
            "name_he": meta["name_he"],
            "name_en": meta["name_en"],
            "symbol": meta["yahoo"],
            "quote": quote,
            "technical": tech,
            "scorecard": scorecard,
            "has_volume": has_volume,
            "bars": int(len(hist)),
            "as_of": datetime.now().isoformat(),
            "available_indices": [
                {"id": k, "name_he": v["name_he"]} for k, v in ISRAEL_INDICES.items()
            ],
            "currency": "ILS",
            "note_he": "נתונים מ-Yahoo Finance (מדד תל אביב). למדד אין נתוני נפח — אינדיקטורים מבוססי-נפח מוסתרים. לא ייעוץ השקעות.",
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# ----------------------------- Maof options (TA-35 only) -----------------------------
# יש אופציות מעו"ף רק על מדד ת"א-35. הסורק מתמחר ב-BSM מלא (r שקלי, q דיבידנד)
# על רשת מחירי-מימוש×פקיעות, עם PoP מבוסס-היסטוריה (drift ריאלי, מנצח בתיקוף).
from engine import maof as MAOF


@app.get("/api/israel/maof")
def israel_maof(anchor_iv: float | None = None, iv_override: float | None = None):
    """סורק אופציות מעו"ף על מדד ת"א-35 (המדד היחיד עם אופציות מעו"ף).

    anchor_iv   — IV עוגן (VTA35) כאחוז (למשל 22.8). ברירת מחדל 22.8%.
    iv_override — IV אחיד מגלובס כאחוז, גובר על העוגן.
    תמחור Black-Scholes-Merton מלא (r=3.75% שקלי, q=2% דיבידנד) — ללא פישוטים."""
    try:
        hist = PROVIDER.history("TA35.TA", "2y")
        if hist is None or len(hist) < 130:
            raise ValueError("אין מספיק נתוני היסטוריה למדד תל אביב 35")
        close = hist["Close"].astype(float).to_numpy()
        spot = float(close[-1])
        # קלט באחוזים → שבר עשרוני
        a_iv = (anchor_iv / 100.0) if (anchor_iv and anchor_iv > 1) else anchor_iv
        o_iv = (iv_override / 100.0) if (iv_override and iv_override > 1) else iv_override
        out = MAOF.scan_maof(spot, close, anchor_iv=a_iv, iv_override=o_iv)
        out["index_name_he"] = "תל אביב 35"
        out["symbol"] = "TA35.TA"
        out["currency"] = "ILS"
        out["vta35_default_pct"] = round(MAOF.VTA35_DEFAULT * 100, 2)
        return out
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# ----------------------------- Maof geopolitical scenarios (Stage 3) -----------------------------
# ממחזר אופציית מעוף בודדת תחת תרחישי הלם גיאופוליטיים (זעזוע ספוט + קפיצת VTA35),
# מכוילים על קפיצות IV היסטוריות אמיתיות. תמחור BSM מלא.
from engine import scenarios as SCEN


@app.get("/api/israel/maof/scenarios")
def israel_maof_scenarios(strike: float | None = None, expiry: str | None = None,
                          kind: str | None = None, current_iv: float | None = None,
                          entry_premium: float | None = None, expiry_type: str | None = None,
                          anchor_iv: float | None = None, iv_override: float | None = None):
    """מתמחר אופציית מעוף תחת תרחישים גיאופוליטיים.

    אם לא נמסרו strike/expiry/kind — נבחרת האופציה המומלצת ביותר מהסורק.
    current_iv  — IV נוכחי כאחוז (ברירת מחדל: ה-IV של האופציה הנבחרת/VTA35).
    תמחור Black-Scholes-Merton מלא (r שקלי, q דיבידנד) — ללא פישוטים."""
    try:
        hist = PROVIDER.history("TA35.TA", "2y")
        if hist is None or len(hist) < 130:
            raise ValueError("אין מספיק נתוני היסטוריה למדד תל אביב 35")
        close = hist["Close"].astype(float).to_numpy()
        spot = float(close[-1])
        a_iv = (anchor_iv / 100.0) if (anchor_iv and anchor_iv > 1) else anchor_iv
        o_iv = (iv_override / 100.0) if (iv_override and iv_override > 1) else iv_override

        # אם חסר פרמטר של אופציה — נשתמש באופציה המומלצת ביותר מהסורק
        chosen_label = None
        if not (strike and expiry and kind):
            scan = MAOF.scan_maof(spot, close, anchor_iv=a_iv, iv_override=o_iv)
            best = scan.get("best_overall")
            if not best:
                raise ValueError("לא נמצאה אופציה מתאימה לתרחישים")
            strike = float(best["strike"])
            expiry = best["expiry"]
            kind = best["kind"]
            if current_iv is None:
                current_iv = best["iv"] * 100.0  # שמירה על אחידות אחוזים
            if entry_premium is None:
                entry_premium = best["premium"]
            if expiry_type is None:
                expiry_type = best.get("expiry_type")
            chosen_label = best.get("kind_he")

        c_iv = (current_iv / 100.0) if (current_iv and current_iv > 1) else current_iv
        if c_iv is None:
            c_iv = o_iv or a_iv or MAOF.VTA35_DEFAULT

        out = SCEN.price_option_under_scenarios(
            spot=spot, strike=float(strike), expiry=expiry, kind=kind,
            current_iv=c_iv, entry_premium=entry_premium, expiry_type=expiry_type,
        )
        out["index_name_he"] = "תל אביב 35"
        out["symbol"] = "TA35.TA"
        out["currency"] = "ILS"
        out["auto_selected"] = chosen_label is not None
        if chosen_label:
            out["option"]["selected_from_he"] = "נבחרה אוטומטית: האופציה המומלצת מהסורק"
        return out
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# ----------------------------- Investment Ideas scanner -----------------------------
# סורק יקום מניות (S&P 500 + נאסד"ק-100) ומדרג לפי ציון אטרקטיביות משוקלל
# (טכני + פונדמנטלי + עיוות מחיר + הזדמנות תנודתיות). משקלים נבחרו לפי תיקוף היסטורי.
from engine import ideas as IDEAS

_IDEAS_SCANNER = IDEAS.IdeasScanner(PROVIDER, ttl_seconds=1800)


@app.on_event("startup")
def _warm_up():
    """Self-warm after every (cold) start so the user doesn't land on a slow,
    empty market screen. Render's free tier sleeps after ~15 min idle; on wake
    this pre-builds & caches the market overview (the ~13-fetch slow path).

    NOTE: we deliberately do NOT auto-start the 515-name ideas scan here. That
    scan briefly peaks memory near the 512MB free-tier limit, and paying that
    cost at every cold boot — when no user has asked for it — was OOM-killing the
    service. The scan now stays lazy: it starts the first time a user opens the
    Ideas or LEAPS tab, and the frontend already polls until it's ready.
    """
    def _bg():
        try:
            from engine.provider import _cache_get, _cache_set
            from engine import market as MK
            if _cache_get("overview:market", 90) is None:
                _cache_set("overview:market", MK.build_overview(PROVIDER))
        except Exception:
            pass
    threading.Thread(target=_bg, daemon=True).start()


@app.get("/api/ideas")
def investment_ideas(universe: str = "both", min_score: float | None = None,
                     limit: int = 40, refresh: bool = False):
    """רעיונות השקעה: סורק יקום מניות ומדרג לפי ציון אטרקטיביות משוקלל.

    universe   — sp500 | nasdaq100 | both (ברירת מחדל both).
    min_score  — סף ציון מינימלי לסינון.
    limit      — מספר תוצאות מקסימלי (ברירת מחדל 40).
    refresh    — לכפות סריקה מחדש (אחרת משתמש במטמון בן 30 דק').
    הסריקה רצה ברקע; כל עוד status=='building' מוחזרות תוצאות חלקיות/קודמות.
    """
    try:
        uni = (universe or "both").lower()
        if uni not in ("sp500", "nasdaq100", "both"):
            uni = "both"
        snap = _IDEAS_SCANNER.get(uni, refresh=refresh)
        rows = snap.get("rows", [])
        if min_score is not None:
            rows = [r for r in rows if r.get("score") is not None and r["score"] >= min_score]
        ranked = rows[: max(1, min(int(limit), 100))]
        return {
            "status": snap.get("status"),
            "universe": uni,
            "scanned": snap.get("scanned", 0),
            "total": snap.get("total", 0),
            "done": snap.get("done", 0),
            "as_of": snap.get("as_of"),
            "error": snap.get("error"),
            "weights": IDEAS.WEIGHTS,
            "count": len(rows),
            "ranked": ranked,
            "distortion_caution_he": ("שים לב: רכיב 'עיוות מחיר' (זול מול ערך הוגן) היה היסטורית "
                                       "מנבא קונטרני — מניות שנראו זולות לא בהכרח הניבו תשואה עודפת "
                                       "בטווח הקצר. הוא משוקלל נמוך ומוצג כמידע בלבד."),
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# ----------------------- אסטרטגיית LEAPS המנצחת (מהבקטסט) -----------------------
# לוקח את ההמלצות המובילות מסורק רעיונות ההשקעה ובונה על כל אחת קול LEAPS
# (~500 יום) לפי פרופיל הסטרייק שניצח בבקטסט המחמיר: ITM-10 (ברירת מחדל),
# ATM, ITM-20 או OTM-10. כל פרמיה היא Black-Scholes מלא על תנודתיות ממומשת.
from engine import leaps_plays as LEAPS


@app.get("/api/leaps-plays")
def leaps_plays(universe: str = "both", profile: str = "itm10",
                top_n: int = 20, refresh: bool = False):
    """אסטרטגיית LEAPS המנצחת: בונה קול ארוך (~500 יום) על ההמלצות המובילות.

    profile — itm10 (ברירת מחדל) | itm20 | atm | otm10. סטרייק לפי הבקטסט.
    top_n   — כמה שמות לבנות (Top-20 ברירת מחדל — הסינון שהוסיף הכי הרבה ערך).
    הציון והדירוג מגיעים מסורק רעיונות ההשקעה (מבוסס סטטיסטיקת הצלחה).
    """
    try:
        uni = (universe or "both").lower()
        if uni not in ("sp500", "nasdaq100", "both"):
            uni = "both"
        prof = (profile or "itm10").lower()
        if prof not in LEAPS.PROFILES:
            prof = LEAPS.DEFAULT_PROFILE
        n = max(1, min(int(top_n), 40))

        snap = _IDEAS_SCANNER.get(uni, refresh=refresh)
        rows = snap.get("rows", [])
        plays, meta = LEAPS.build_plays(rows, PROVIDER, profile=prof, top_n=n)
        return {
            "status": snap.get("status"),
            "universe": uni,
            "as_of": snap.get("as_of"),
            "scanned": snap.get("scanned", 0),
            "total": snap.get("total", 0),
            "profiles": {k: {"label_he": v["label_he"], "blurb_he": v["blurb_he"],
                             "pct": v["pct"]} for k, v in LEAPS.PROFILES.items()},
            "meta": meta,
            "plays": plays,
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
