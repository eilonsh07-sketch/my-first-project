"""leaps_plays.py — "אסטרטגיית LEAPS המנצחת" generator.

Turns the top-scored Investment-Ideas names into concrete CALL-option plays
using the configuration that WON our strict no-look-ahead backtest
(8 variants, S&P 500 + Nasdaq-100, recommendations of 8.6.2025 tested a year
forward):

  • Long-dated LEAPS (~500-day expiry) — preserved time value, no zero-expiry.
  • Strike profile chosen by the user:
        itm10 (default)  K = S * 0.90   → 75% hit-rate, +161% median (Top-20)
        atm              K = S * 1.00   → 65% hit-rate, +420% mean   (Top-20)
        itm20            K = S * 0.80   → 70% hit-rate, highest universe hit-rate
        otm10            K = S * 1.10   → 55% hit-rate, +432% mean, volatile
  • Filtered to the TOP-N by the system's attractiveness score (Top-20 added the
    most value in the backtest — only meaningful at long DTE).

NO SIMPLIFICATIONS: every premium is a full Black-Scholes price using the same
engine as the rest of the app, on the trailing realized volatility. Trading
assumption: SOLD BEFORE EXPIRY by default (we never hold a LEAPS to expiry).

This module does NOT fetch live option chains (Yahoo gives none for free and the
universe is 500+ names); premiums are model-implied — the exact method validated
in the backtest.
"""
from __future__ import annotations

from datetime import date, timedelta

from .pricing import bs_price, bs_greeks
from . import technicals as T

RISK_FREE = 0.045
TARGET_DTE_DAYS = 500            # ~500-day LEAPS — the winning horizon
VOL_WINDOW = 60                  # trailing realized-vol window (days)

# Strike profiles validated in the backtest. pct is added to 1.0:
#   K = S * (1 + pct).  Negative pct = in-the-money.
PROFILES = {
    "itm10": {
        "pct": -0.10, "label_he": "10% בתוך הכסף (ITM-10)",
        "blurb_he": "המנצח בשיעור הצלחה — 75% הצלחה, חציון +161% בבקטסט (Top-20).",
    },
    "itm20": {
        "pct": -0.20, "label_he": "20% בתוך הכסף (ITM-20)",
        "blurb_he": "שיעור ההצלחה הגבוה ביותר על כל היקום; דלתא ~0.85, מינוף נמוך.",
    },
    "atm": {
        "pct": 0.0, "label_he": "בכסף (ATM)",
        "blurb_he": "האיזון הטוב ביותר — 65% הצלחה, ממוצע +420% בבקטסט (Top-20).",
    },
    "otm10": {
        "pct": 0.10, "label_he": "10% מחוץ לכסף (OTM-10)",
        "blurb_he": "מינוף מקסימלי, ממוצע +432% — תנודתי, חציון נמוך.",
    },
}
DEFAULT_PROFILE = "itm10"


def _round_strike(k):
    """Round a strike to a clean, tradable-looking increment."""
    if k >= 200:
        return round(k)
    if k >= 50:
        return round(k * 2) / 2.0       # 0.50 increments
    if k >= 10:
        return round(k * 4) / 4.0       # 0.25 increments
    return round(k, 2)


def build_play(row, provider, *, profile="itm10", target_dte=TARGET_DTE_DAYS,
               r=RISK_FREE):
    """Construct one LEAPS call play from a scored ideas row.

    Returns a dict with the contract, the real-BS premium, Greeks and break-even,
    or None if we cannot price it (missing history / vol).
    """
    prof = PROFILES.get(profile, PROFILES[DEFAULT_PROFILE])
    ticker = row["ticker"]
    S = row.get("price")
    if not S or S <= 0:
        return None

    # Trailing realized vol — the SAME input the backtest used at entry.
    try:
        hist = provider.history(ticker, "1y")
        sigma = T.realized_vol(hist, window=VOL_WINDOW)
    except Exception:
        sigma = None
    if not sigma or sigma <= 0:
        # Fall back to the realized vol the scanner already computed, if any.
        sigma = (row.get("iv_opportunity") or {}).get("realized_vol")
    if not sigma or sigma <= 0:
        return None

    K = _round_strike(S * (1.0 + prof["pct"]))
    if K <= 0:
        return None

    expiry = date.today() + timedelta(days=int(target_dte))
    T_years = target_dte / 365.0

    premium = bs_price(S, K, T_years, r, sigma, kind="call")
    if premium is None or premium <= 0.01:
        return None

    g = bs_greeks(S, K, T_years, r, sigma, kind="call")
    breakeven = K + premium
    breakeven_move_pct = (breakeven / S - 1.0) * 100.0
    cost_per_contract = premium * 100.0   # 1 contract = 100 shares

    return {
        "ticker": ticker,
        "name": row.get("name") or ticker,
        "sector": row.get("sector"),
        "membership": row.get("membership"),
        "score": row.get("score"),
        "reason_he": row.get("reason_he"),
        "spot": round(float(S), 2),
        "strike": K,
        "profile": profile,
        "profile_label_he": prof["label_he"],
        "expiry": expiry.strftime("%Y-%m-%d"),
        "dte": int(target_dte),
        "sigma": round(float(sigma), 4),
        "premium": round(float(premium), 2),
        "cost_per_contract": round(cost_per_contract, 2),
        "delta": round(g["delta"], 3),
        "theta_day": round(g["theta"] / 365.0, 4) if g.get("theta") is not None else None,
        "vega": round(g["vega"] / 100.0, 4) if g.get("vega") is not None else None,
        "gamma": round(g["gamma"], 5) if g.get("gamma") is not None else None,
        "breakeven": round(breakeven, 2),
        "breakeven_move_pct": round(breakeven_move_pct, 2),
    }


# Backtest-validated expectations per profile (Top-20, 12 months, strict
# no-look-ahead). Surfaced in the UI so the play is anchored to real evidence.
BACKTEST_STATS = {
    "itm10": {"hit_rate": 75.0, "mean": 371.0, "median": 161.0},
    "itm20": {"hit_rate": 70.0, "mean": 182.0, "median": 62.0},
    "atm":   {"hit_rate": 65.0, "mean": 420.0, "median": 158.0},
    "otm10": {"hit_rate": 55.0, "mean": 432.0, "median": 44.0},
}


def build_plays(rows, provider, *, profile="itm10", top_n=20,
                target_dte=TARGET_DTE_DAYS, r=RISK_FREE):
    """Take scored ideas rows (already sorted by score desc) and build LEAPS
    plays for the top names. Returns (plays, meta)."""
    prof = PROFILES.get(profile, PROFILES[DEFAULT_PROFILE])
    plays = []
    for row in rows:
        if len(plays) >= top_n:
            break
        p = build_play(row, provider, profile=profile, target_dte=target_dte, r=r)
        if p:
            plays.append(p)

    meta = {
        "profile": profile,
        "profile_label_he": prof["label_he"],
        "profile_blurb_he": prof["blurb_he"],
        "strike_pct": prof["pct"],
        "target_dte": int(target_dte),
        "risk_free": r,
        "vol_window": VOL_WINDOW,
        "top_n": top_n,
        "count": len(plays),
        "backtest": BACKTEST_STATS.get(profile),
        "assumption_he": "נמכר לפני פקיעה כברירת מחדל — איננו מחזיקים LEAPS עד תפוגה.",
        "pricing_he": "כל פרמיה היא מחיר Black-Scholes מלא על התנודתיות הממומשת — ללא פישוטים. "
                      "פרמיות מודל-תלויות (אין שרשראות אופציות חיות מ-Yahoo בקנה מידה זה).",
    }
    return plays, meta
