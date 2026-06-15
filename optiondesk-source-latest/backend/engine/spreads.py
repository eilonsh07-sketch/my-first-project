"""
spreads.py — Scan REAL option chains for debit vertical spreads (feature 5).

Builds two-leg debit spreads from the live chain and scores them with real
Black-Scholes + Monte Carlo (path-based, sell-before-expiry aware):

  * bull_call  : long lower-strike call  + short higher-strike call  (bullish)
  * bear_put   : long higher-strike put  + short lower-strike  put   (bearish)

For each candidate we compute net debit, max profit, max loss, breakeven,
required move, and a Monte-Carlo probability that the spread's MARKET VALUE
reaches a target multiple of the debit before expiry (matches the user's
trade-and-sell-before-expiry assumption), plus probability of profit.
All pricing uses mid quotes from the chain; the MC re-prices each leg with BS
incl. remaining time value, so it captures the real spread mechanics.
"""
from __future__ import annotations

import math
import numpy as np

from .pricing import _bs_price_vec, bs_price, monte_carlo_terminal
from .scoring import years_to_expiry, RISK_FREE, dte_bucket

# Reuse the same anti-casino DTE horizon as single-leg scanning.
MAX_SIGMA_MOVE = 2.5


def _mid(o):
    return o.get("mid") or o.get("last")


def _spread_mc(S, legs, T, sigma_map, entry_debit, target_return, mu, n=4000, steps=40, seed=51):
    """Path-based MC on the net spread value. legs: list of (K, kind, qty).
    sigma_map: {K: iv} per leg. Returns prob_hit_target_early, prob_profit,
    expected_max_value, expected_pnl_pct."""
    rng = np.random.default_rng(seed)
    dt = T / steps
    # Use the long-leg IV as the path-vol driver (dominant exposure).
    long_leg = next((l for l in legs if l[2] > 0), legs[0])
    sigma_path = max(sigma_map.get(long_leg[0], 0.5), 1e-6)
    log_drift = (mu - 0.5 * sigma_path * sigma_path) * dt
    vol_step = sigma_path * math.sqrt(dt)
    logS = np.full(n, math.log(S))

    def spread_value(S_arr, rem_T):
        val = np.zeros_like(S_arr, dtype=float)
        for K, kind, qty in legs:
            sg = max(sigma_map.get(K, sigma_path), 1e-6)
            val = val + qty * _bs_price_vec(S_arr, K, rem_T, RISK_FREE, sg, kind)
        return val

    start_val = float(spread_value(np.array([S]), T)[0])
    max_val = np.full(n, start_val)
    hit = np.zeros(n, dtype=bool)
    target_value = entry_debit * target_return
    for i in range(1, steps + 1):
        logS += log_drift + vol_step * rng.standard_normal(n)
        S_t = np.exp(logS)
        rem_T = max(T - i * dt, 0.0)
        val = spread_value(S_t, rem_T)
        max_val = np.maximum(max_val, val)
        hit |= val >= target_value
    # terminal P&L (intrinsic at expiry)
    final_val = spread_value(np.exp(logS), 0.0)
    pnl_pct = final_val / max(entry_debit, 1e-9) - 1.0
    return {
        "prob_hit_target_early": float(np.mean(hit)),
        "prob_profit": float(np.mean(final_val > entry_debit)),
        "expected_max_value": float(np.mean(max_val)),
        "expected_pnl_pct": float(np.mean(pnl_pct)),
        "n_sims": n,
        "steps": steps,
    }


def _candidates(chain, S, kind):
    """Return near-money options of the requested kind with valid mid+iv, sorted by strike."""
    pool = chain["calls"] if kind == "call" else chain["puts"]
    out = []
    for o in pool:
        k = o.get("strike")
        iv = o.get("iv")
        mid = _mid(o)
        if not k or not iv or not mid or mid <= 0:
            continue
        if k < S * 0.80 or k > S * 1.30:
            continue
        out.append(o)
    out.sort(key=lambda o: o["strike"])
    return out


def evaluate_spread(strategy, lo_leg, hi_leg, S, expiry, mu, target_return):
    """Build & score a single two-leg debit spread.
    strategy: 'bull_call' | 'bear_put'. Returns dict or None if not a valid debit."""
    T, dte = years_to_expiry(expiry)
    if T <= 0:
        return None
    Kl, Kh = lo_leg["strike"], hi_leg["strike"]
    iv_l, iv_h = lo_leg.get("iv"), hi_leg.get("iv")
    mid_l, mid_h = _mid(lo_leg), _mid(hi_leg)
    if Kh <= Kl:
        return None

    if strategy == "bull_call":
        # long lower call, short higher call -> debit
        legs = [(Kl, "call", 1), (Kh, "call", -1)]
        debit = mid_l - mid_h
        max_profit = (Kh - Kl) - debit
        breakeven = Kl + debit
        long_k, short_k = Kl, Kh
        long_iv, short_iv = iv_l, iv_h
        sigma_map = {Kl: iv_l, Kh: iv_h}
    elif strategy == "bear_put":
        # long higher put, short lower put -> debit
        legs = [(Kh, "put", 1), (Kl, "put", -1)]
        debit = mid_h - mid_l
        max_profit = (Kh - Kl) - debit
        breakeven = Kh - debit
        long_k, short_k = Kh, Kl
        long_iv, short_iv = iv_h, iv_l
        sigma_map = {Kh: iv_h, Kl: iv_l}
    else:
        return None

    if debit <= 0.05 or max_profit <= 0:
        return None  # must be a real debit with positive payoff potential

    width = Kh - Kl
    max_loss = debit
    rr = max_profit / max_loss if max_loss > 0 else None
    req_move_pct = (breakeven - S) / S

    mc = _spread_mc(S, legs, T, sigma_map, debit, target_return, mu)

    # Spread score: probability of profit + reward/risk + early-target prob + reachability
    pp = mc["prob_profit"]
    pe = mc["prob_hit_target_early"]
    rr_norm = max(0.0, min(1.0, (rr or 0) / 2.0))  # rr of 2.0 => full marks
    reach = max(0.0, 1.0 - min(abs(req_move_pct) / 0.30, 1.0))
    score = round(100 * (0.35 * pp + 0.25 * pe + 0.25 * rr_norm + 0.15 * reach), 1)

    return {
        "strategy": strategy,
        "kind": "spread",
        "expiry": expiry,
        "dte": dte,
        "dte_bucket": dte_bucket(dte),
        "long_strike": long_k,
        "short_strike": short_k,
        "width": round(width, 2),
        "debit": round(debit, 3),
        "debit_per_contract": round(debit * 100, 2),
        "max_profit": round(max_profit, 3),
        "max_profit_per_contract": round(max_profit * 100, 2),
        "max_loss": round(max_loss, 3),
        "max_loss_per_contract": round(max_loss * 100, 2),
        "reward_risk": round(rr, 2) if rr else None,
        "breakeven": round(breakeven, 2),
        "required_move_pct": req_move_pct,
        "long_iv": long_iv,
        "short_iv": short_iv,
        "monte_carlo": {
            "prob_profit": round(mc["prob_profit"], 4),
            "prob_hit_target_early": round(mc["prob_hit_target_early"], 4),
            "expected_max_value": round(mc["expected_max_value"], 4),
            "expected_pnl_pct": round(mc["expected_pnl_pct"], 4),
            "target_value": round(debit * target_return, 3),
            "T_years": round(T, 4),
            "drift_mu": round(mu, 4),
            "n_sims": mc["n_sims"],
        },
        "option_score": score,
        "passed_filters": True,
        # spreads are typically managed before expiry; surface the same note
        "hold_to_expiry": {
            "recommend": "sell",
            "he_label": "למכור לפני פקיעה",
            "he_note": "מרווח דביט — ממומש בדרך כלל לפני פקיעה כשנפתח רוב הרווח, להימנע מסיכון פין.",
        },
    }


def scan_spreads(chain_by_expiry, S, mu, target_return, strategy="bull_call",
                 max_per_expiry=6, width_steps=(1, 2, 3)):
    """Scan multiple expiries' chains for the best debit spreads.
    chain_by_expiry: list of (expiry, chain). Returns sorted list of spread evals.
    width_steps: how many strike increments apart the legs can be."""
    kind = "call" if strategy == "bull_call" else "put"
    results = []
    for expiry, chain in chain_by_expiry:
        cands = _candidates(chain, S, kind)
        if len(cands) < 2:
            continue
        per_exp = []
        for i in range(len(cands)):
            for step in width_steps:
                j = i + step
                if j >= len(cands):
                    continue
                lo_leg, hi_leg = cands[i], cands[j]
                ev = evaluate_spread(strategy, lo_leg, hi_leg, S, expiry, mu, target_return)
                if ev:
                    per_exp.append(ev)
        per_exp.sort(key=lambda r: r["option_score"], reverse=True)
        results.extend(per_exp[:max_per_expiry])
    results.sort(key=lambda r: r["option_score"], reverse=True)
    return results
