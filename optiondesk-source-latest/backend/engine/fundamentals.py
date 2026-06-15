"""
fundamentals.py — Fundamental valuation: multiples, DCF, ROIC vs WACC, Altman Z-Score.
Inputs come from the data provider (yfinance .info + financial statements).
All functions degrade gracefully when data is missing.
"""
from __future__ import annotations

import math


def _g(d, *keys):
    """Get first non-None value among keys."""
    for k in keys:
        v = d.get(k)
        if v is not None:
            return v
    return None


def multiples_summary(info):
    """Extract & label valuation multiples and key fundamentals."""
    pe = _g(info, "trailingPE")
    fwd_pe = _g(info, "forwardPE")
    peg = _g(info, "pegRatio", "trailingPegRatio")
    ps = _g(info, "priceToSalesTrailing12Months")
    pb = _g(info, "priceToBook")
    fcf = _g(info, "freeCashflow")
    mcap = _g(info, "marketCap")
    p_fcf = (mcap / fcf) if (mcap and fcf and fcf > 0) else None

    return {
        "pe": pe,
        "forward_pe": fwd_pe,
        "peg": peg,
        "ps": ps,
        "pb": pb,
        "p_fcf": p_fcf,
        "gross_margin": _g(info, "grossMargins"),
        "operating_margin": _g(info, "operatingMargins"),
        "profit_margin": _g(info, "profitMargins"),
        "roe": _g(info, "returnOnEquity"),
        "roa": _g(info, "returnOnAssets"),
        "revenue_growth": _g(info, "revenueGrowth"),
        "earnings_growth": _g(info, "earningsGrowth"),
        "total_cash": _g(info, "totalCash"),
        "total_debt": _g(info, "totalDebt"),
        "current_ratio": _g(info, "currentRatio"),
        "quick_ratio": _g(info, "quickRatio"),
        "debt_to_equity": _g(info, "debtToEquity"),
        "short_percent_float": _g(info, "shortPercentOfFloat"),
        "short_ratio": _g(info, "shortRatio"),
        "beta": _g(info, "beta"),
        "dividend_yield": _g(info, "dividendYield"),
        "sector": _g(info, "sector"),
        "industry": _g(info, "industry"),
    }


def dcf_fair_value(info, fin):
    """
    Two-stage FCF DCF. Returns fair value per share + assumptions.
    fin: dict with optional 'fcf', 'shares', and growth estimates.
    Uses conservative defaults when inputs missing.
    """
    fcf = _g(info, "freeCashflow")
    shares = _g(info, "sharesOutstanding")
    if not fcf or not shares or fcf <= 0:
        return {"fair_value": None, "reason": "אין FCF חיובי / נתוני מניות — DCF לא ישים"}

    # Growth assumptions
    g_high = _g(info, "earningsGrowth") or _g(info, "revenueGrowth") or 0.10
    g_high = max(min(float(g_high), 0.30), 0.0)   # cap 0-30%
    g_terminal = 0.025                              # long-run GDP-ish
    wacc = _wacc(info)
    discount = wacc or 0.09

    years_high = 5
    pv = 0.0
    cf = fcf
    for t in range(1, years_high + 1):
        cf *= (1 + g_high)
        pv += cf / ((1 + discount) ** t)

    # Terminal value (Gordon growth)
    terminal_cf = cf * (1 + g_terminal)
    tv = terminal_cf / (discount - g_terminal)
    pv += tv / ((1 + discount) ** years_high)

    cash = _g(info, "totalCash") or 0
    debt = _g(info, "totalDebt") or 0
    equity_value = pv + cash - debt
    fair = equity_value / shares

    return {
        "fair_value": float(fair),
        "wacc": discount,
        "growth_stage1": g_high,
        "growth_terminal": g_terminal,
        "fcf_base": float(fcf),
        "current_price": _g(info, "currentPrice"),
        "upside": float(fair / _g(info, "currentPrice") - 1) if _g(info, "currentPrice") else None,
    }


def _wacc(info):
    """Rough WACC estimate from beta (CAPM cost of equity) blended with cost of debt."""
    beta = _g(info, "beta") or 1.0
    rf = 0.045          # risk-free
    erp = 0.05          # equity risk premium
    cost_equity = rf + beta * erp
    debt = _g(info, "totalDebt") or 0
    mcap = _g(info, "marketCap") or 0
    total = debt + mcap
    if total <= 0:
        return cost_equity
    cost_debt = 0.05 * (1 - 0.21)   # after-tax
    w_e = mcap / total
    w_d = debt / total
    return w_e * cost_equity + w_d * cost_debt


def roic_vs_wacc(info):
    """ROIC vs WACC — management efficiency. ROIC = NOPAT / invested capital.

    Invested capital uses REAL book values from the financial statements
    (book equity + total debt − excess cash), not the market-cap proxy that
    used to inflate the denominator and depress ROIC. Falls back to operating
    invested capital (total assets − current liabilities) and finally to the
    old market-cap proxy only when book data is entirely missing.
    """
    op_margin = _g(info, "operatingMargins")
    revenue = _g(info, "totalRevenue")
    ebit = _g(info, "_ebit")
    debt = _g(info, "totalDebt") or 0

    # ---- Invested capital, best basis available ----
    book_eq = _g(info, "_bookEquity")
    if book_eq is None:
        book = _g(info, "bookValue")
        shares = _g(info, "sharesOutstanding")
        if book and shares:
            book_eq = book * shares
    cash = _g(info, "_cash") or 0
    total_assets = _g(info, "totalAssets")
    cur_liab = _g(info, "_currentLiabilities")

    basis = None
    invested = None
    if book_eq and book_eq > 0:
        # Standard financing-side invested capital: equity + debt − excess cash
        invested = book_eq + debt - cash
        basis = "book"          # הון בספרים
    elif total_assets and cur_liab is not None:
        # Operating-side invested capital
        invested = total_assets - cur_liab
        basis = "operating"     # נכסים תפעוליים
    else:
        equity_proxy = _g(info, "marketCap")
        if equity_proxy:
            invested = equity_proxy + debt
            basis = "market_proxy"  # קירוב לפי שווי שוק

    if ebit is None and op_margin and revenue:
        ebit = op_margin * revenue
    if not ebit or not invested or invested <= 0:
        return {"roic": None, "wacc": _wacc(info), "spread": None,
                "reason": "נתונים חסרים לחישוב ROIC"}

    nopat = ebit * (1 - 0.21)
    roic = nopat / invested
    wacc = _wacc(info)
    spread = roic - wacc
    creates_value = spread > 0

    # ---- Cyclical context: high beta + negative spread is normal mid/trough ----
    beta = _g(info, "beta") or 1.0
    cyclical = (beta is not None and beta >= 1.3)
    basis_he = {"book": "הון בספרים (דוחות)",
                "operating": "נכסים תפעוליים (דוחות)",
                "market_proxy": "קירוב לפי שווי שוק"}.get(basis, "")
    note_he = None
    if not creates_value:
        if cyclical:
            note_he = ("מרווח שלילי נפוץ בחברות ציקליות (β גבוה) בתחתית או אמצע "
                       "מחזור — ה-WACC מנופח ע\"י תנודתיות וה-ROIC מבוסס רווחיות "
                       "תקופתית נוכחית, לא שיא המחזור. עשוי להתהפך לחיובי בשיא.")
        else:
            note_he = ("התשואה על ההון המושקע נמוכה כרגע מעלות ההון. "
                       "שווה לבדוק מגמה רב-שנתית לפני מסקנה על איכות ההנהלה.")
    else:
        note_he = "ההנהלה מייצרת תשואה מעל עלות ההון — סימן לאיכות הקצאת הון."

    return {"roic": roic, "wacc": wacc, "spread": spread,
            "creates_value": bool(creates_value),
            "invested_capital": float(invested),
            "basis": basis, "basis_he": basis_he,
            "cyclical": bool(cyclical), "beta": float(beta),
            "note_he": note_he}


def altman_z(info, balance=None):
    """
    Altman Z-Score for bankruptcy risk.
    Z = 1.2*A + 1.4*B + 3.3*C + 0.6*D + 1.0*E
    Uses approximations from .info when full balance sheet unavailable.
    Zones: >2.99 safe, 1.81-2.99 grey, <1.81 distress.
    """
    total_assets = _g(info, "totalAssets")
    mcap = _g(info, "marketCap")
    total_debt = _g(info, "totalDebt")
    revenue = _g(info, "totalRevenue")
    retained = _g(info, "retainedEarnings")
    working_capital = _g(info, "_workingCapital")
    ebit = _g(info, "_ebit")

    op_margin = _g(info, "operatingMargins")
    if ebit is None and op_margin and revenue:
        ebit = op_margin * revenue

    if not total_assets:
        return {"z_score": None, "zone": None, "reason": "אין סך נכסים — Altman-Z לא ישים"}

    A = (working_capital / total_assets) if (working_capital is not None) else 0.05
    B = (retained / total_assets) if (retained and total_assets) else 0.0
    C = (ebit / total_assets) if (ebit and total_assets) else 0.0
    D = (mcap / total_debt) if (mcap and total_debt and total_debt > 0) else 4.0
    E = (revenue / total_assets) if (revenue and total_assets) else 0.5

    z = 1.2 * A + 1.4 * B + 3.3 * C + 0.6 * D + 1.0 * E
    if z > 2.99:
        zone = "בטוח"
    elif z >= 1.81:
        zone = "אפור"
    else:
        zone = "מצוקה"
    return {"z_score": float(z), "zone": zone,
            "components": {"A": A, "B": B, "C": C, "D": D, "E": E}}


def sector_comparison(info, sector_pe=None):
    """Compare the stock's P/E to a typical sector multiple."""
    pe = _g(info, "trailingPE")
    if not pe:
        return {"relative": None, "note": "אין P/E"}
    bench = sector_pe or _DEFAULT_SECTOR_PE.get(_g(info, "sector"), 22.0)
    return {
        "pe": pe,
        "sector_pe": bench,
        "premium_discount": float(pe / bench - 1),
        "verdict": "יקר מהסקטור" if pe > bench * 1.1 else ("זול מהסקטור" if pe < bench * 0.9 else "בקו הסקטור"),
    }


_DEFAULT_SECTOR_PE = {
    "Technology": 30.0, "Healthcare": 24.0, "Financial Services": 14.0,
    "Consumer Cyclical": 22.0, "Communication Services": 20.0,
    "Industrials": 20.0, "Energy": 12.0, "Utilities": 18.0,
    "Consumer Defensive": 21.0, "Real Estate": 30.0, "Basic Materials": 16.0,
}


def _clip(x, lo, hi):
    return max(lo, min(hi, x))


def _score_linear(v, lo, hi):
    """Map v from [lo,hi] to [0,100], clipped. If lo>hi, lower v scores higher."""
    if v is None:
        return None
    if lo == hi:
        return 50.0
    if lo < hi:
        return _clip((v - lo) / (hi - lo) * 100.0, 0.0, 100.0)
    # inverted: lower is better
    return _clip((lo - v) / (lo - hi) * 100.0, 0.0, 100.0)


def _avg(vals):
    vals = [x for x in vals if x is not None]
    return (sum(vals) / len(vals)) if vals else None


def long_term_score(info, tech=None, cagr_3y=None):
    """
    Balanced long-term (3+ year) BUY-AND-HOLD attractiveness score for the
    UNDERLYING STOCK (not options). 0-100, weighted across four axes:
      - Quality  (35%): ROE, ROIC-vs-WACC spread, margins, financial health (debt, Altman-Z)
      - Growth   (25%): revenue & earnings growth, 3y price CAGR
      - Value    (25%): P/E, PEG, P/FCF, P/S vs sector — cheaper = better
      - Trend    (15%): above 200-day MA, relative strength vs S&P 500
    Returns the composite, per-axis sub-scores, the raw metrics, and a Hebrew verdict.
    Degrades gracefully: axes with no data are dropped and weights renormalized.
    """
    mult = multiples_summary(info)
    roic = roic_vs_wacc(info)
    z = altman_z(info)
    sector = sector_comparison(info)
    tech = tech or {}

    # ---------- QUALITY ----------
    q_parts = []
    roe = mult.get("roe")
    if roe is not None:
        q_parts.append(("ROE", _score_linear(roe, 0.05, 0.30)))       # 5%→0, 30%→100
    spread = roic.get("spread")
    if spread is not None:
        q_parts.append(("ROIC-WACC", _score_linear(spread, -0.02, 0.10)))
    om = mult.get("operating_margin")
    if om is not None:
        q_parts.append(("שולי תפעול", _score_linear(om, 0.05, 0.35)))
    gm = mult.get("gross_margin")
    if gm is not None:
        q_parts.append(("שולי גולמי", _score_linear(gm, 0.20, 0.65)))
    d2e = mult.get("debt_to_equity")
    if d2e is not None:
        # yfinance debtToEquity is in percent (e.g. 150 = 1.5x). Lower is better.
        q_parts.append(("חוב/הון", _score_linear(d2e, 200.0, 20.0)))
    zscore = z.get("z_score")
    if zscore is not None:
        q_parts.append(("Altman-Z", _score_linear(zscore, 1.81, 4.0)))
    quality = _avg([s for _, s in q_parts])

    # ---------- GROWTH ----------
    g_parts = []
    rg = mult.get("revenue_growth")
    if rg is not None:
        g_parts.append(("צמיחת הכנסות", _score_linear(rg, 0.0, 0.25)))
    eg = mult.get("earnings_growth")
    if eg is not None:
        g_parts.append(("צמיחת רווח", _score_linear(eg, 0.0, 0.30)))
    if cagr_3y is not None:
        g_parts.append(("CAGR מחיר 3ש", _score_linear(cagr_3y, 0.0, 0.20)))
    growth = _avg([s for _, s in g_parts])

    # ---------- VALUE (cheaper = higher score) ----------
    v_parts = []
    pe = mult.get("pe") or mult.get("forward_pe")
    if pe is not None and pe > 0:
        bench = _DEFAULT_SECTOR_PE.get(mult.get("sector"), 22.0)
        # at half sector PE → 100, at 2x sector PE → 0
        v_parts.append(("P/E מול סקטור", _score_linear(pe / bench, 2.0, 0.5)))
    peg = mult.get("peg")
    if peg is not None and peg > 0:
        v_parts.append(("PEG", _score_linear(peg, 3.0, 0.8)))   # <1 great, >3 poor
    pfcf = mult.get("p_fcf")
    if pfcf is not None and pfcf > 0:
        v_parts.append(("P/FCF", _score_linear(pfcf, 50.0, 12.0)))
    ps = mult.get("ps")
    if ps is not None and ps > 0:
        v_parts.append(("P/S", _score_linear(ps, 15.0, 1.0)))
    value = _avg([s for _, s in v_parts])

    # ---------- TREND ----------
    t_parts = []
    if tech.get("above_ma200") is not None:
        t_parts.append(("מעל ממוצע 200", 100.0 if tech.get("above_ma200") else 25.0))
    rs = tech.get("relative_strength")
    if isinstance(rs, dict):
        sr = rs.get("stock_return")
        mr = rs.get("index_return")
        if sr is not None and mr is not None:
            t_parts.append(("חוזק יחסי מול S&P", _score_linear(sr - mr, -0.20, 0.20)))
    trend = _avg([s for _, s in t_parts])

    # ---------- COMPOSITE (renormalized weights over available axes) ----------
    base_w = {"quality": 0.35, "growth": 0.25, "value": 0.25, "trend": 0.15}
    axes = {"quality": quality, "growth": growth, "value": value, "trend": trend}
    avail = {k: v for k, v in axes.items() if v is not None}
    composite = None
    if avail:
        wsum = sum(base_w[k] for k in avail)
        composite = sum(axes[k] * base_w[k] for k in avail) / wsum

    # ---------- VERDICT ----------
    if composite is None:
        label, tone = "נתונים לא מספיקים", "warn"
    elif composite >= 75:
        label, tone = "כדאי לטווח ארוך", "good"
    elif composite >= 60:
        label, tone = "איכותי — להחזיק/לצבור", "good"
    elif composite >= 45:
        label, tone = "בינוני — לבחון נקודת כניסה", "warn"
    else:
        label, tone = "חלש להשקעה ארוכת-טווח", "avoid"

    # nuance: great quality but expensive
    note = None
    if composite is not None and quality is not None and value is not None:
        if quality >= 70 and value < 40:
            note = "עסק איכותי אך התמחור מתוח כרגע — שווה להמתין לתיקון או לצבור בהדרגה (DCA)."
        elif quality < 45 and value >= 65:
            note = "זול יחסית אך איכות עסקית חלשה — מלכודת ערך אפשרית, להיזהר."
        elif composite >= 70:
            note = "שילוב חיובי של איכות, צמיחה ותמחור — מתאים לליבת תיק ארוך-טווח."

    return {
        "score": round(composite, 1) if composite is not None else None,
        "label": label,
        "tone": tone,
        "note": note,
        "axes": {
            "quality": round(quality, 1) if quality is not None else None,
            "growth": round(growth, 1) if growth is not None else None,
            "value": round(value, 1) if value is not None else None,
            "trend": round(trend, 1) if trend is not None else None,
        },
        "weights": {"quality": 35, "growth": 25, "value": 25, "trend": 15},
        "metrics": {
            "roe": roe, "roic_spread": spread, "operating_margin": om,
            "gross_margin": gm, "debt_to_equity": d2e, "altman_z": zscore,
            "revenue_growth": rg, "earnings_growth": eg, "cagr_3y": cagr_3y,
            "pe": pe, "peg": peg, "p_fcf": pfcf, "ps": ps,
            "sector_pe": _DEFAULT_SECTOR_PE.get(mult.get("sector"), 22.0),
            "above_ma200": tech.get("above_ma200"),
            "dividend_yield": mult.get("dividend_yield"),
        },
    }
