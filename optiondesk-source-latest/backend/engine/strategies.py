"""
strategies.py — Multi-leg strategy pricing & P&L curves.
Long Call, Bull Call Spread, Call Ratio Spread.
Computes BS price per leg, net Greeks, P&L grid, breakevens, profit-target solver.
"""
from __future__ import annotations

import math
import numpy as np
from .pricing import bs_price, bs_greeks

RISK_FREE = 0.045


def _leg_value(S, K, T, sigma, kind, qty):
    """Value of a leg at given S (qty positive=long, negative=short)."""
    return qty * bs_price(S, K, T, RISK_FREE, sigma, kind)


def build_strategy(strategy, S, sigma, T, legs_override=None):
    """
    strategy: 'long_call' | 'bull_spread' | 'ratio_spread'
    Returns leg definitions [{K, kind, qty}].
    legs_override lets the sandbox pass custom strikes.
    """
    if legs_override:
        return legs_override
    atm = round(S)
    if strategy == "long_call":
        return [{"K": atm, "kind": "call", "qty": 1}]
    if strategy == "bull_spread":
        return [{"K": atm, "kind": "call", "qty": 1},
                {"K": atm + max(1, round(S * 0.08)), "kind": "call", "qty": -1}]
    if strategy == "ratio_spread":
        return [{"K": atm, "kind": "call", "qty": 1},
                {"K": atm + max(1, round(S * 0.08)), "kind": "call", "qty": -2}]
    return [{"K": atm, "kind": "call", "qty": 1}]


def net_premium(legs, S, sigma, T):
    """Net debit (positive) / credit (negative) to open."""
    total = 0.0
    for leg in legs:
        total += _leg_value(S, leg["K"], T, sigma, leg["kind"], leg["qty"])
    return total


def net_greeks(legs, S, sigma, T):
    agg = {"delta": 0, "gamma": 0, "theta": 0, "vega": 0, "rho": 0}
    for leg in legs:
        g = bs_greeks(S, leg["K"], max(T, 1e-9), RISK_FREE, sigma, leg["kind"])
        for k in agg:
            agg[k] += g[k] * leg["qty"]
    return {k: round(v, 4) for k, v in agg.items()}


def pnl_curve(legs, S, sigma, T_now, entry_cost, price_range=None, at_expiry=True):
    """
    P&L across a range of underlying prices.
    at_expiry=True: intrinsic payoff at expiration.
    at_expiry=False: BS value at T_now (current theoretical curve).
    Returns {prices, pnl, breakevens, max_profit, max_loss}.
    """
    if price_range is None:
        lo, hi = S * 0.6, S * 1.6
    else:
        lo, hi = price_range
    prices = np.linspace(lo, hi, 80)
    pnl = []
    for p in prices:
        if at_expiry:
            val = 0.0
            for leg in legs:
                intrinsic = max(p - leg["K"], 0) if leg["kind"] == "call" else max(leg["K"] - p, 0)
                val += leg["qty"] * intrinsic
        else:
            val = net_premium(legs, p, sigma, max(T_now, 1e-6))
        pnl.append(val - entry_cost)

    pnl = np.array(pnl)
    # Breakevens (sign changes)
    breakevens = []
    for i in range(1, len(pnl)):
        if pnl[i - 1] * pnl[i] < 0:
            x0, x1 = prices[i - 1], prices[i]
            y0, y1 = pnl[i - 1], pnl[i]
            be = x0 - y0 * (x1 - x0) / (y1 - y0)
            breakevens.append(round(float(be), 2))

    return {
        "prices": [round(float(p), 2) for p in prices],
        "pnl": [round(float(v) * 100, 2) for v in pnl],  # per contract (x100)
        "breakevens": breakevens,
        "max_profit": round(float(np.max(pnl)) * 100, 2),
        "max_loss": round(float(np.min(pnl)) * 100, 2),
    }


def profit_target_solver(legs, S, sigma, T, entry_cost, target_pnl_pct, expiry_date):
    """
    Find the underlying price needed to reach target_pnl_pct profit at expiry.
    Returns the required price and a sentence.
    """
    target_profit = entry_cost * target_pnl_pct
    target_value = entry_cost + target_profit
    # Search upward (bull strategies)
    for p in np.linspace(S, S * 3, 500):
        val = 0.0
        for leg in legs:
            intrinsic = max(p - leg["K"], 0) if leg["kind"] == "call" else max(leg["K"] - p, 0)
            val += leg["qty"] * intrinsic
        if val >= target_value:
            return {
                "required_price": round(float(p), 2),
                "move_pct": round(float(p / S - 1) * 100, 1),
                "by_date": expiry_date,
                "sentence": f"המניה צריכה להגיע ל-${round(float(p),2)} עד {expiry_date} (תנועה של {round(float(p/S-1)*100,1)}%)",
            }
    return {"required_price": None, "sentence": "יעד הרווח אינו ניתן להשגה במבנה זה (רווח מוגבל)"}


def apply_iv_crush(sigma, crush_pct=0.30):
    """Reduce IV after an earnings date by crush_pct (default 30%)."""
    return sigma * (1 - crush_pct)
