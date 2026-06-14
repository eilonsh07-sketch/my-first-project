"""
economist.py — Economist Agent: macro regime classification and VRP analysis.

All data sources are FREE (yfinance + FRED public API).
No API key required. Designed to provide economic context for:
  1. The Experimental Researcher (which macro regime do each backtest periods belong to?)
  2. The bank presentation (professional economic framing of the strategy)

Macro Regime Classification:
  VIX level + Yield curve shape + Fed policy stance → regime label
  Regimes: "low_vol_bull" | "mid_vol_neutral" | "high_vol_risk_off" | "extreme_fear"

VRP (Volatility Risk Premium):
  IV (VIX) vs realized vol (SPY 30-day) → is options market cheap or expensive?
  Positive VRP = options overpriced = seller's edge (literature strongly supports this)
  Negative VRP = options cheap = buyer's edge (rarer, occurs before major moves)
"""
from __future__ import annotations

import math
import json
import ssl
import urllib.request
import urllib.parse
from datetime import datetime, date, timedelta
from typing import Optional

try:
    import certifi
    _SSL_CTX = ssl.create_default_context(cafile=certifi.where())
except Exception:
    _SSL_CTX = ssl.create_default_context()

# ─────────────────────────────────────────────────────────────────────────────
# VIX Regime Thresholds (CBOE standard + empirical research)
# ─────────────────────────────────────────────────────────────────────────────
VIX_THRESHOLDS = {
    "low":     (0,  15),    # calm, complacent market
    "mid":     (15, 25),    # normal uncertainty
    "high":    (25, 35),    # elevated fear, risk-off
    "extreme": (35, 999),   # crisis/panic (2008, 2020 levels)
}

# Yield curve: spread between 10yr and 2yr (TNX - IRX proxy)
# Positive = normal (longer yields higher = growth expectations)
# Negative = inverted = recession warning
CURVE_THRESHOLDS = {
    "steep":    0.01,    # >100bps spread → growth regime
    "flat":     0.00,    # near zero → transition
    "inverted": -999,    # negative → recession warning
}


def _fetch_polygon_series(ticker: str, period: str = "1y") -> list[dict]:
    """Daily close series from Polygon (stock or index like I:VIX)."""
    try:
        from engine.provider import PROVIDER
        df = PROVIDER.history(ticker, period)
        if df is None or len(df) == 0:
            return []
        return [
            {"date": ts.strftime("%Y-%m-%d"), "close": float(row["Close"])}
            for ts, row in df.iterrows()
        ]
    except Exception:
        return []


def _fetch_fred_series(series_id: str, tail_days: int = 365) -> list[dict]:
    """Latest N data points from FRED public CSV (no API key needed)."""
    try:
        url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"
        req = urllib.request.Request(url, headers={"User-Agent": "OptionDesk/1.0"})
        with urllib.request.urlopen(req, timeout=10, context=_SSL_CTX) as r:
            content = r.read().decode("utf-8")
        lines = [l for l in content.strip().split("\n") if l and not l.startswith("DATE")]
        result = []
        for line in lines[-tail_days:]:
            parts = line.split(",")
            if len(parts) >= 2 and parts[1].strip() not in (".", ""):
                result.append({"date": parts[0].strip(), "close": float(parts[1].strip())})
        return result
    except Exception:
        return []


def _realized_vol_30d(series: list[dict]) -> Optional[float]:
    """30-day trailing realized volatility (annualized) from a close-price series."""
    if len(series) < 32:
        return None
    closes = [r["close"] for r in series[-32:]]
    returns = [math.log(closes[i] / closes[i - 1]) for i in range(1, len(closes))]
    tail = returns[-30:]
    mean = sum(tail) / len(tail)
    variance = sum((r - mean) ** 2 for r in tail) / len(tail)
    return math.sqrt(variance * 252)


def _fetch_fred_rate(series_id: str = "DFF") -> Optional[float]:
    """
    Fetch a FRED series (latest value). Uses the public CSV endpoint — no API key.
    DFF = Effective Federal Funds Rate (daily)
    """
    try:
        url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"
        req = urllib.request.Request(url, headers={"User-Agent": "OptionDesk/1.0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            content = r.read().decode("utf-8")
        lines = [l for l in content.strip().split("\n") if l and not l.startswith("DATE")]
        if not lines:
            return None
        last = lines[-1].split(",")
        if len(last) >= 2 and last[1].strip() not in (".", ""):
            return float(last[1].strip()) / 100.0
    except Exception:
        return None
    return None


def _classify_vix(vix: float) -> tuple[str, str]:
    """Return (regime_key, hebrew_label)."""
    if vix >= 35:
        return "extreme_fear", "פאניקה / משבר (VIX ≥35)"
    if vix >= 25:
        return "high_vol_risk_off", "פחד גבוה / risk-off (VIX 25–35)"
    if vix >= 15:
        return "mid_vol_neutral", "אי-ודאות נורמלית (VIX 15–25)"
    return "low_vol_bull", "רגיעה / שוק שורי (VIX <15)"


def _classify_curve(spread_10_2: Optional[float]) -> tuple[str, str]:
    if spread_10_2 is None:
        return "unknown", "לא ידוע"
    if spread_10_2 > 0.005:
        return "normal", f"תלולה (ספרד 10yr-2yr: +{spread_10_2*100:.0f}bps) — ציפיות צמיחה"
    if spread_10_2 < -0.001:
        return "inverted", f"הפוכה (ספרד 10yr-2yr: {spread_10_2*100:.0f}bps) — אזהרת מיתון"
    return "flat", "שטוחה (ספרד אפסי) — מעבר"


def _vrp_signal(vix_current: float, rv_30d: Optional[float]) -> dict:
    """
    Volatility Risk Premium: VIX (implied) vs 30-day realized vol (SPY).
    VRP = IV - RV: positive = options overpriced = sellers have edge
    Academic reference: Carr & Wu (2009), Bollerslev et al. (2009)
    """
    if rv_30d is None:
        return {"vrp": None, "signal": "unknown", "he_label": "לא זמין — אין היסטוריה מספיקה"}

    vrp = vix_current / 100.0 - rv_30d
    vrp_pct = vrp * 100

    if vrp > 0.03:
        signal = "overpriced"
        label = f"אופציות יקרות — VRP={vrp_pct:+.1f}% — יתרון למוכר"
    elif vrp > 0.005:
        signal = "fair"
        label = f"אופציות במחיר הוגן — VRP={vrp_pct:+.1f}%"
    elif vrp > -0.02:
        signal = "cheap"
        label = f"אופציות זולות — VRP={vrp_pct:+.1f}% — יתרון לקונה"
    else:
        signal = "very_cheap"
        label = f"אופציות זולות מאד — VRP={vrp_pct:+.1f}% — שוק לפני מהלך גדול?"

    return {
        "vix_iv": round(vix_current / 100.0, 4),
        "realized_vol_30d": round(rv_30d, 4),
        "vrp": round(vrp, 4),
        "vrp_pct": round(vrp_pct, 2),
        "signal": signal,
        "he_label": label,
    }


def _strategy_implications(vix_regime: str, curve_regime: str, vrp_signal: str) -> list[str]:
    """Translate macro regime into options strategy implications (Hebrew)."""
    implications = []

    if vix_regime == "low_vol_bull":
        implications.append("VIX נמוך → פרמיות אופציות זולות יחסית → עדיפות לאסטרטגיות LONG (קנייה)")
        implications.append("סיכון: VIX נמוך מדי עלול להוביל לפיצוץ חד — הגן עם OTM puts")
    elif vix_regime == "mid_vol_neutral":
        implications.append("VIX נורמלי → מחיר הוגן לאופציות → בחר עסקאות לפי ניתוח פרטני")
    elif vix_regime == "high_vol_risk_off":
        implications.append("VIX גבוה → פרמיות יקרות → שקול אסטרטגיות SHORT vol (מכירת פרמיה)")
        implications.append("סיכון: VIX יכול להמשיך לעלות — הגבל גודל פוזיציה")
    elif vix_regime == "extreme_fear":
        implications.append("VIX קיצוני → פאניקה → הזדמנות לכתיבת פרמיה גבוהה, אך סיכון זנב קיצוני")

    if curve_regime == "inverted":
        implications.append("עקום הפוך → אזהרת מיתון → הגבל אקספוזיציה מחזורית, העדף defensive")
    elif curve_regime == "normal":
        implications.append("עקום תלול → ציפיות צמיחה → פוזיציות מחזוריות אפשריות")

    if vrp_signal == "overpriced":
        implications.append("VRP חיובי → היסטורית: מוכרי אופציות מרוויחים. שקול כתיבה מכוסה")
    elif vrp_signal in ("cheap", "very_cheap"):
        implications.append("VRP שלילי → אופציות זולות → עדיפות לקניית אופציות, מהלך גדול אפשרי")

    return implications


def macro_regime_report() -> dict:
    """
    Main entry point: fetch all macro data and return a structured regime report.
    Suitable for the Orchestrator to pass to any agent needing economic context.
    """
    as_of = date.today().isoformat()

    # VIX (implied vol of S&P 500 options — the market's fear gauge)
    vix_series = _fetch_polygon_series("I:VIX", "1y")
    vix_current = vix_series[-1]["close"] if vix_series else None

    # SPY for realized vol computation
    spy_series = _fetch_polygon_series("SPY", "3mo")
    rv_30d = _realized_vol_30d(spy_series)

    # Yield curve: 10yr (DGS10) and 3-month T-bill (DTB3) from FRED
    tnx_series = _fetch_fred_series("DGS10", 365)
    irx_series = _fetch_fred_series("DTB3", 365)
    tnx = (tnx_series[-1]["close"] / 100.0) if tnx_series else None
    irx = (irx_series[-1]["close"] / 100.0) if irx_series else None
    curve_spread = (tnx - irx) if (tnx and irx) else None

    # Fed funds rate (FRED public API, no key)
    fed_rate = _fetch_fred_rate("DFF")

    # VIX history for context (52-week range)
    vix_52w_high = max((r["close"] for r in vix_series), default=None) if vix_series else None
    vix_52w_low = min((r["close"] for r in vix_series), default=None) if vix_series else None
    vix_1y_avg = (sum(r["close"] for r in vix_series) / len(vix_series)) if vix_series else None
    vix_rank = None
    if vix_current and vix_52w_high and vix_52w_low and vix_52w_high > vix_52w_low:
        vix_rank = (vix_current - vix_52w_low) / (vix_52w_high - vix_52w_low)

    # Classifications
    vix_regime_key, vix_regime_he = _classify_vix(vix_current) if vix_current else ("unknown", "לא זמין")
    curve_regime_key, curve_regime_he = _classify_curve(curve_spread)
    vrp = _vrp_signal(vix_current, rv_30d) if vix_current else {"signal": "unknown", "he_label": "לא זמין"}

    # Fed stance
    if fed_rate is not None:
        if fed_rate > 0.04:
            fed_stance = "הידוק (ריבית גבוהה) — לחץ על הערכות שווי"
        elif fed_rate > 0.015:
            fed_stance = "ניטרלי"
        else:
            fed_stance = "מרחיב (ריבית נמוכה) — תמיכה בנכסי סיכון"
    else:
        fed_stance = "לא זמין"

    implications = _strategy_implications(vix_regime_key, curve_regime_key, vrp.get("signal", "unknown"))

    return {
        "as_of": as_of,
        "agent": "Economist Agent v1",
        "data_sources": ["Polygon.io (I:VIX, SPY)", "FRED public API (DGS10, DTB3, DFF)"],
        "vix": {
            "current": round(vix_current, 2) if vix_current else None,
            "52w_high": round(vix_52w_high, 2) if vix_52w_high else None,
            "52w_low": round(vix_52w_low, 2) if vix_52w_low else None,
            "1y_avg": round(vix_1y_avg, 2) if vix_1y_avg else None,
            "rank_52w": round(vix_rank, 3) if vix_rank is not None else None,
            "regime": vix_regime_key,
            "regime_he": vix_regime_he,
        },
        "yield_curve": {
            "rate_10yr": round(tnx * 100, 2) if tnx else None,
            "rate_short": round(irx * 100, 2) if irx else None,
            "spread_bps": round(curve_spread * 10000, 0) if curve_spread is not None else None,
            "regime": curve_regime_key,
            "regime_he": curve_regime_he,
        },
        "fed": {
            "funds_rate_pct": round(fed_rate * 100, 2) if fed_rate else None,
            "stance_he": fed_stance,
        },
        "vrp": vrp,
        "spy_realized_vol_30d": round(rv_30d, 4) if rv_30d else None,
        "overall_regime": f"{vix_regime_key} / {curve_regime_key}",
        "strategy_implications_he": implications,
        "presentation_summary_he": (
            f"משטר שוק נוכחי: {vix_regime_he}. "
            f"עקום תשואות: {curve_regime_he}. "
            f"פד: {fed_stance}. "
            f"VRP: {vrp.get('he_label', 'לא זמין')}."
        ),
    }


if __name__ == "__main__":
    report = macro_regime_report()
    print(json.dumps(report, ensure_ascii=False, indent=2))
