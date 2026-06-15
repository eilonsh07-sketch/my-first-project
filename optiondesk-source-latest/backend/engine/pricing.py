"""
pricing.py — Real Black-Scholes pricing, Greeks, implied vol, and Monte Carlo.
No simplifications. All math vectorized with numpy where possible.
"""
from __future__ import annotations

import math
import numpy as np
from scipy.stats import norm

SQRT_2PI = math.sqrt(2.0 * math.pi)


# ---------------------------------------------------------------------------
# Black-Scholes-Merton
# ---------------------------------------------------------------------------
def _d1_d2(S, K, T, r, sigma, q=0.0):
    """Compute d1, d2. T in years, sigma annualized, q = continuous dividend yield."""
    S = float(S); K = float(K); T = max(float(T), 1e-9); sigma = max(float(sigma), 1e-9)
    d1 = (math.log(S / K) + (r - q + 0.5 * sigma * sigma) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    return d1, d2


def bs_price(S, K, T, r, sigma, kind="call", q=0.0):
    """Black-Scholes-Merton price for a European option."""
    S = float(S); K = float(K); T = float(T); sigma = float(sigma)
    if T <= 0:
        # Expiry: intrinsic value
        if kind == "call":
            return max(S - K, 0.0)
        return max(K - S, 0.0)
    if sigma <= 0:
        sigma = 1e-9
    d1, d2 = _d1_d2(S, K, T, r, sigma, q)
    if kind == "call":
        return S * math.exp(-q * T) * norm.cdf(d1) - K * math.exp(-r * T) * norm.cdf(d2)
    return K * math.exp(-r * T) * norm.cdf(-d2) - S * math.exp(-q * T) * norm.cdf(-d1)


def bs_greeks(S, K, T, r, sigma, kind="call", q=0.0):
    """Return full Greeks dict: delta, gamma, theta (per day), vega (per 1% IV),
    rho (per 1% rate), plus 2nd-order vanna & charm."""
    S = float(S); K = float(K); T = max(float(T), 1e-9); sigma = max(float(sigma), 1e-9)
    d1, d2 = _d1_d2(S, K, T, r, sigma, q)
    pdf_d1 = math.exp(-0.5 * d1 * d1) / SQRT_2PI
    disc_q = math.exp(-q * T)
    disc_r = math.exp(-r * T)
    sqrtT = math.sqrt(T)

    if kind == "call":
        delta = disc_q * norm.cdf(d1)
    else:
        delta = -disc_q * norm.cdf(-d1)

    gamma = disc_q * pdf_d1 / (S * sigma * sqrtT)
    vega = S * disc_q * pdf_d1 * sqrtT  # per 1.0 vol; scale to per 1% below

    # Theta (per year), then convert to per calendar day
    term1 = -(S * disc_q * pdf_d1 * sigma) / (2 * sqrtT)
    if kind == "call":
        theta = term1 - r * K * disc_r * norm.cdf(d2) + q * S * disc_q * norm.cdf(d1)
        rho = K * T * disc_r * norm.cdf(d2)
    else:
        theta = term1 + r * K * disc_r * norm.cdf(-d2) - q * S * disc_q * norm.cdf(-d1)
        rho = -K * T * disc_r * norm.cdf(-d2)

    # 2nd order
    vanna = -disc_q * pdf_d1 * d2 / sigma  # dDelta/dVol
    charm_common = disc_q * pdf_d1 * (2 * (r - q) * T - d2 * sigma * sqrtT) / (2 * T * sigma * sqrtT)
    if kind == "call":
        charm = q * disc_q * norm.cdf(d1) - charm_common
    else:
        charm = -q * disc_q * norm.cdf(-d1) - charm_common

    return {
        "delta": delta,
        "gamma": gamma,
        "theta": theta / 365.0,          # per calendar day
        "vega": vega / 100.0,            # per 1% change in IV
        "rho": rho / 100.0,             # per 1% change in rate
        "vanna": vanna / 100.0,
        "charm": charm / 365.0,
    }


# ---------------------------------------------------------------------------
# Implied volatility (Newton with bisection fallback)
# ---------------------------------------------------------------------------
def implied_vol(price, S, K, T, r, kind="call", q=0.0):
    """Solve for IV given a market price. Returns annualized sigma or None."""
    price = float(price)
    if T <= 0 or price <= 0:
        return None
    intrinsic = max(S - K, 0.0) if kind == "call" else max(K - S, 0.0)
    if price < intrinsic - 1e-6:
        return None

    sigma = 0.5
    for _ in range(60):
        p = bs_price(S, K, T, r, sigma, kind, q)
        d1, _ = _d1_d2(S, K, T, r, sigma, q)
        vega = S * math.exp(-q * T) * (math.exp(-0.5 * d1 * d1) / SQRT_2PI) * math.sqrt(T)
        diff = p - price
        if abs(diff) < 1e-6:
            return max(sigma, 1e-4)
        if vega < 1e-8:
            break
        sigma -= diff / vega
        if sigma <= 0 or sigma > 8:
            sigma = 0.5
            break

    # Bisection fallback
    lo, hi = 1e-4, 8.0
    for _ in range(100):
        mid = 0.5 * (lo + hi)
        p = bs_price(S, K, T, r, mid, kind, q)
        if abs(p - price) < 1e-6:
            return mid
        if p > price:
            hi = mid
        else:
            lo = mid
    return 0.5 * (lo + hi)


# ---------------------------------------------------------------------------
# Monte Carlo — GBM terminal & path simulation
# ---------------------------------------------------------------------------
def monte_carlo_terminal(S0, T, r, sigma, q=0.0, n=10000, seed=None):
    """Simulate terminal prices S_T under GBM (risk-neutral by default but
    we let caller pass a drift via r). Returns array of terminal prices."""
    rng = np.random.default_rng(seed)
    z = rng.standard_normal(n)
    drift = (r - q - 0.5 * sigma * sigma) * T
    diff = sigma * math.sqrt(T) * z
    return S0 * np.exp(drift + diff)


def monte_carlo_option(S0, K, T, r, sigma, entry_premium, kind="call", q=0.0,
                       target_return=1.30, n=10000, mu=None, seed=42):
    """
    Full MC analysis for a single option.
    - target_return: e.g. 1.30 means "did the option reach +130% of premium?"
    - mu: real-world drift for the underlying (annualized). If None, uses r (risk-neutral).
    Returns dict with prob of hitting target, P(profit), expected P&L, distribution stats.
    """
    drift = r if mu is None else mu
    ST = monte_carlo_terminal(S0, T, drift, sigma, q, n, seed)

    # Option value at expiry (intrinsic — holding to expiration)
    if kind == "call":
        payoff = np.maximum(ST - K, 0.0)
    else:
        payoff = np.maximum(K - ST, 0.0)

    pnl = payoff - entry_premium  # per share
    pnl_pct = payoff / max(entry_premium, 1e-9) - 1.0

    target_value = entry_premium * target_return
    prob_hit_target = float(np.mean(payoff >= target_value))
    prob_profit = float(np.mean(payoff > entry_premium))
    prob_total_loss = float(np.mean(payoff <= 1e-9))

    return {
        "prob_hit_target": prob_hit_target,
        "prob_profit": prob_profit,
        "prob_total_loss": prob_total_loss,
        "drift_mu": float(drift),   # real-world annualized drift fed to the sim
        "sigma": float(sigma),      # annualized vol (option IV) fed to the sim
        "T_years": float(T),
        "expected_pnl": float(np.mean(pnl)),
        "expected_pnl_pct": float(np.mean(pnl_pct)),
        "median_terminal": float(np.median(ST)),
        "p10_terminal": float(np.percentile(ST, 10)),
        "p90_terminal": float(np.percentile(ST, 90)),
        "expected_value_per_contract": float(np.mean(pnl) * 100),
        "cvar5": float(np.mean(pnl[pnl <= np.percentile(pnl, 5)])) if n > 20 else float(np.min(pnl)),
        "n_sims": n,
    }


def _bs_price_vec(S, K, T, r, sigma, kind="call", q=0.0):
    """Vectorized Black-Scholes over arrays of S (and scalar/array T).
    Returns option value per share. Handles T->0 by falling back to intrinsic."""
    S = np.asarray(S, dtype=float)
    T = np.asarray(T, dtype=float)
    sigma = max(float(sigma), 1e-9)
    intrinsic = np.maximum(S - K, 0.0) if kind == "call" else np.maximum(K - S, 0.0)
    # Where time remains, use full BS; otherwise intrinsic.
    Tsafe = np.maximum(T, 1e-9)
    sqrtT = np.sqrt(Tsafe)
    d1 = (np.log(np.maximum(S, 1e-9) / K) + (r - q + 0.5 * sigma * sigma) * Tsafe) / (sigma * sqrtT)
    d2 = d1 - sigma * sqrtT
    if kind == "call":
        val = S * np.exp(-q * Tsafe) * norm.cdf(d1) - K * np.exp(-r * Tsafe) * norm.cdf(d2)
    else:
        val = K * np.exp(-r * Tsafe) * norm.cdf(-d2) - S * np.exp(-q * Tsafe) * norm.cdf(-d1)
    return np.where(T <= 1e-9, intrinsic, val)


def monte_carlo_option_early(S0, K, T, r, sigma, entry_premium, kind="call", q=0.0,
                             target_return=1.30, n=10000, steps=60, mu=None, seed=43):
    """Path-based MC that assumes the option is TRADED and can be SOLD before expiry.
    At each time step the option is re-priced with Black-Scholes using the remaining
    time-to-expiry (so it captures TIME VALUE, not just intrinsic at expiry).
    Returns the probability that the option's MARKET VALUE reaches the target
    (premium * target_return) at any point during its life, plus the expected
    max value reached.
    """
    drift = r if mu is None else mu
    rng = np.random.default_rng(seed)
    dt = T / steps
    log_drift = (drift - q - 0.5 * sigma * sigma) * dt
    vol_step = sigma * math.sqrt(dt)
    logS = np.full(n, math.log(S0))
    target_value = entry_premium * target_return
    hit = np.zeros(n, dtype=bool)
    max_val = np.full(n, _bs_price_vec(np.array([S0]), K, T, r, sigma, kind, q)[0])
    for i in range(1, steps + 1):
        logS += log_drift + vol_step * rng.standard_normal(n)
        S_t = np.exp(logS)
        rem_T = max(T - i * dt, 0.0)
        val = _bs_price_vec(S_t, K, rem_T, r, sigma, kind, q)
        max_val = np.maximum(max_val, val)
        hit |= val >= target_value
    return {
        "prob_hit_target_early": float(np.mean(hit)),
        "expected_max_value": float(np.mean(max_val)),
        "median_max_value": float(np.median(max_val)),
        "target_value": float(target_value),
        "n_sims": n,
        "steps": steps,
    }


def mc_distribution(S0, K, T, r, sigma, entry_premium, kind="call", q=0.0,
                    target_return=1.30, n=10000, mu=None, seed=42, bins=40):
    """Return a histogram of the option's P&L-% distribution at expiry plus key
    markers (breakeven=0%, target line). Used by the distribution chart (feature 4).
    Bins are over option VALUE as a multiple of premium (so -100% = total loss)."""
    drift = r if mu is None else mu
    ST = monte_carlo_terminal(S0, T, drift, sigma, q, n, seed)
    if kind == "call":
        payoff = np.maximum(ST - K, 0.0)
    else:
        payoff = np.maximum(K - ST, 0.0)
    prem = max(entry_premium, 1e-9)
    ret_pct = (payoff / prem - 1.0) * 100.0   # P&L as % of premium paid
    # clip extreme upside for a readable chart, but keep the true max as a stat
    true_max = float(np.max(ret_pct))
    cap = float(min(true_max, np.percentile(ret_pct, 99.5)))
    cap = max(cap, 50.0)
    clipped = np.clip(ret_pct, -100.0, cap)
    counts, edges = np.histogram(clipped, bins=bins, range=(-100.0, cap))
    total = max(int(counts.sum()), 1)
    hist = []
    for i in range(len(counts)):
        lo = float(edges[i]); hi = float(edges[i + 1])
        hist.append({
            "lo": round(lo, 1), "hi": round(hi, 1),
            "mid": round((lo + hi) / 2.0, 1),
            "count": int(counts[i]),
            "pct": round(100.0 * counts[i] / total, 2),
        })
    target_pct = (target_return - 1.0) * 100.0
    return {
        "bins": hist,
        "breakeven_pct": 0.0,
        "target_pct": round(target_pct, 1),
        "max_pct": round(true_max, 1),
        "mean_pct": round(float(np.mean(ret_pct)), 1),
        "median_pct": round(float(np.median(ret_pct)), 1),
        "prob_profit": round(float(np.mean(payoff > prem)), 4),
        "prob_total_loss": round(float(np.mean(payoff <= 1e-9)), 4),
        "prob_hit_target": round(float(np.mean(payoff >= prem * target_return)), 4),
        "n_sims": n,
    }


def prob_touch_target_price(S0, target, T, r, sigma, q=0.0, mu=None, n=10000, steps=60, seed=7):
    """Probability the underlying TOUCHES a target price at any point before T
    (path-dependent), plus probability it ends >= target."""
    drift = r if mu is None else mu
    rng = np.random.default_rng(seed)
    dt = T / steps
    log_drift = (drift - q - 0.5 * sigma * sigma) * dt
    vol_step = sigma * math.sqrt(dt)
    logS = np.full(n, math.log(S0))
    touched = np.zeros(n, dtype=bool)
    up = target >= S0
    for _ in range(steps):
        logS += log_drift + vol_step * rng.standard_normal(n)
        prices = np.exp(logS)
        if up:
            touched |= prices >= target
        else:
            touched |= prices <= target
    final = np.exp(logS)
    end_beyond = final >= target if up else final <= target
    return {
        "prob_touch": float(np.mean(touched)),
        "prob_end_beyond": float(np.mean(end_beyond)),
    }
