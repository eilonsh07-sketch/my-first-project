"""
backtest.py — model-based historical backtest for a CALL option strategy.

Yahoo does NOT provide historical option premiums for free, so we reconstruct
them with the SAME engine the rest of the app uses: real Black-Scholes priced
against the realized (historical) volatility that prevailed at each entry date.
No simplifications — every theoretical premium is a full BS price.

Method (per entry date t):
  1. sigma_t = trailing realized vol (annualized) over `vol_window` days.
  2. Strike K = S_t * (1 + otm_pct/100)  (OTM call by chosen %).
  3. Entry premium = bs_price(S_t, K, T=dte/365, r, sigma_t).
  4. Walk forward day by day, re-pricing the option with the remaining time and
     the spot path. Exit on FIRST of:
       - option value >= entry*(1+target_return_pct/100)  → win (sold early)
       - option value <= entry*(1-stop_loss_pct/100)       → stop
       - expiry (intrinsic value only)                     → settle
Aggregates: win rate, avg P&L %, expectancy, profit factor, max drawdown.
"""
from __future__ import annotations

import math
from datetime import date

import numpy as np

from .pricing import bs_price

TRADING_DAYS = 252
RISK_FREE = 0.045


def _realized_vol(closes, end_idx, window):
    """Annualized realized volatility from daily log returns ending at end_idx."""
    lo = max(1, end_idx - window + 1)
    seg = closes[lo:end_idx + 1]
    if len(seg) < 5:
        return None
    rets = np.diff(np.log(seg))
    if len(rets) < 2:
        return None
    sd = float(np.std(rets, ddof=1))
    return sd * math.sqrt(TRADING_DAYS)


def run_backtest(closes, *, otm_pct=5.0, dte=30, target_return_pct=50.0,
                 stop_loss_pct=50.0, vol_window=30, r=RISK_FREE,
                 step_days=5, min_history=260):
    """Run the backtest over a list of daily closing prices (oldest→newest).

    step_days: spacing between entry signals (5 = roughly weekly) to avoid
               massively overlapping trades and keep runtime fast.
    Returns a dict with summary stats + a sample of trades + an equity curve.
    """
    n = len(closes)
    if n < min_history:
        return {"ok": False, "reason": "אין מספיק היסטוריה ל-backtest"}

    closes = [float(c) for c in closes]
    horizon = dte  # calendar days held at most; we map ~trading days below
    trades = []
    equity = 0.0
    equity_curve = []
    peak = 0.0
    max_dd = 0.0

    # We index in trading days; convert dte (calendar) to ~trading days.
    hold_td = max(3, int(round(dte * (TRADING_DAYS / 365.0))))

    start = vol_window + 1
    last_entry = n - hold_td - 1  # need room to walk forward
    i = start
    while i <= last_entry:
        S0 = closes[i]
        sigma = _realized_vol(closes, i, vol_window)
        if not sigma or sigma <= 0 or S0 <= 0:
            i += step_days
            continue
        K = S0 * (1 + otm_pct / 100.0)
        T0 = dte / 365.0
        entry = bs_price(S0, K, T0, r, sigma, kind="call")
        if entry <= 0.01:
            i += step_days
            continue

        target_val = entry * (1 + target_return_pct / 100.0)
        stop_val = entry * (1 - stop_loss_pct / 100.0)

        outcome = None
        exit_val = None
        days_held = 0
        for d in range(1, hold_td + 1):
            idx = i + d
            if idx >= n:
                break
            S = closes[idx]
            T_rem = max(1e-6, (dte - d * (365.0 / TRADING_DAYS)) / 365.0)
            val = bs_price(S, K, T_rem, r, sigma, kind="call")
            days_held = d
            if val >= target_val:
                outcome, exit_val = "win", target_val
                break
            if val <= stop_val:
                outcome, exit_val = "stop", stop_val
                break
        if outcome is None:
            # expiry — intrinsic value only
            S_exp = closes[min(i + hold_td, n - 1)]
            exit_val = max(0.0, S_exp - K)
            outcome = "win" if exit_val > entry else "loss"

        pnl = exit_val - entry
        pnl_pct = (pnl / entry) * 100.0
        equity += pnl * 100.0  # one contract = 100 shares
        peak = max(peak, equity)
        max_dd = min(max_dd, equity - peak)
        equity_curve.append(round(equity, 2))
        trades.append({
            "entry_spot": round(S0, 2),
            "strike": round(K, 2),
            "sigma": round(sigma, 4),
            "entry_premium": round(entry, 3),
            "exit_premium": round(exit_val, 3),
            "pnl_pct": round(pnl_pct, 1),
            "outcome": outcome,
            "days_held": days_held,
        })
        i += step_days

    if not trades:
        return {"ok": False, "reason": "לא נוצרו עסקאות בפרמטרים אלו"}

    wins = [t for t in trades if t["pnl_pct"] > 0]
    losses = [t for t in trades if t["pnl_pct"] <= 0]
    win_rate = 100.0 * len(wins) / len(trades)
    avg_pnl = float(np.mean([t["pnl_pct"] for t in trades]))
    avg_win = float(np.mean([t["pnl_pct"] for t in wins])) if wins else 0.0
    avg_loss = float(np.mean([t["pnl_pct"] for t in losses])) if losses else 0.0
    gross_win = sum(t["pnl_pct"] for t in wins)
    gross_loss = abs(sum(t["pnl_pct"] for t in losses))
    profit_factor = (gross_win / gross_loss) if gross_loss > 0 else None
    # expectancy per trade (%)
    expectancy = avg_pnl

    return {
        "ok": True,
        "params": {
            "otm_pct": otm_pct, "dte": dte,
            "target_return_pct": target_return_pct,
            "stop_loss_pct": stop_loss_pct, "vol_window": vol_window,
        },
        "summary": {
            "trades": len(trades),
            "win_rate": round(win_rate, 1),
            "avg_pnl_pct": round(avg_pnl, 1),
            "avg_win_pct": round(avg_win, 1),
            "avg_loss_pct": round(avg_loss, 1),
            "expectancy_pct": round(expectancy, 1),
            "profit_factor": round(profit_factor, 2) if profit_factor else None,
            "total_pnl_usd": round(equity, 0),
            "max_drawdown_usd": round(abs(max_dd), 0),
        },
        "equity_curve": equity_curve,
        "trades_sample": trades[-12:],  # last dozen for display
    }


def backtest_score_component(summary):
    """Translate backtest stats into a 0-100 'evidence' score and a Hebrew note.
    Combines win rate (how often it worked) and expectancy (how profitable),
    so a high win-rate-but-tiny-edge strategy doesn't over-score."""
    if not summary:
        return None
    wr = summary.get("win_rate") or 0
    exp = summary.get("expectancy_pct") or 0
    # win-rate maps 30%→0, 65%→100
    wr_pts = max(0.0, min(100.0, (wr - 30) * (100.0 / 35.0)))
    # expectancy maps -20%→0, +40%→100
    exp_pts = max(0.0, min(100.0, (exp + 20) * (100.0 / 60.0)))
    score = round(0.55 * wr_pts + 0.45 * exp_pts)
    if score >= 65:
        label, tone = "ראיות היסטוריות חזקות", "good"
    elif score >= 45:
        label, tone = "ראיות מעורבות", "warn"
    else:
        label, tone = "ראיות היסטוריות חלשות", "bad"
    note = (f"במבחן היסטורי: {summary.get('win_rate')}% עסקאות מרוויחות, "
            f"תוחלת {summary.get('expectancy_pct')}% לעסקה על פני {summary.get('trades')} עסקאות.")
    return {"score": score, "label_he": label, "tone": tone, "note_he": note}
