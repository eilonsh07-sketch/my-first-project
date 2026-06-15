"""
market.py — "מצב שוק" market overview.
All data is free (yfinance via PROVIDER): S&P 500 (SPY), 11 sector ETFs, VIX.
Plus a rules-based economic-events calendar (NFP / CPI / FOMC) — no paid API.
All textual labels are produced in Hebrew here in code (no LLM needed).
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from concurrent.futures import ThreadPoolExecutor

# 11 SPDR sector ETFs → Hebrew sector names
SECTORS = [
    ("XLK", "טכנולוגיה"),
    ("XLF", "פיננסים"),
    ("XLV", "בריאות"),
    ("XLY", "צריכה מחזורית"),
    ("XLP", "צריכה בסיסית"),
    ("XLE", "אנרגיה"),
    ("XLI", "תעשייה"),
    ("XLB", "חומרי גלם"),
    ("XLU", "תשתיות (יוטיליטיס)"),
    ("XLRE", "נדל\"ן"),
    ("XLC", "תקשורת"),
]


def _sma(closes, n):
    if closes is None or len(closes) < n:
        return None
    return float(sum(closes[-n:]) / n)


def _closes_from_hist(hist):
    """Extract a plain list of closing prices from the provider history DataFrame."""
    try:
        s = hist["Close"].dropna()
        return [float(x) for x in s.tolist()]
    except Exception:
        return []


def _trend_label(price, sma50, sma200):
    """Hebrew trend label + tone from price vs moving averages."""
    if price is None or sma50 is None:
        return "לא ידוע", "warn"
    if sma200 is not None:
        if price > sma50 > sma200:
            return "מגמת עלייה חזקה", "good"
        if price > sma200 and price > sma50:
            return "חיובי", "good"
        if price < sma50 < sma200:
            return "מגמת ירידה", "bad"
        if price < sma200:
            return "חלש · מתחת לממוצע 200", "bad"
    if price > sma50:
        return "חיובי", "good"
    return "חלש", "bad"


def _vix_label(v):
    if v is None:
        return "לא ידוע", "warn", "—"
    if v < 14:
        return "רגוע", "good", "תנודתיות נמוכה — אופציות זולות יחסית (טוב לקנייה)"
    if v < 20:
        return "נורמלי", "good", "תנודתיות ממוצעת"
    if v < 28:
        return "מתוח", "warn", "תנודתיות מוגברת — אופציות מתייקרות"
    return "פחד", "bad", "תנודתיות גבוהה — אופציות יקרות (טוב למכירה, סיכון גבוה)"


# ── Economic events: rules-based calendar (no paid API) ──────────────────────
def _first_friday(y, m):
    d = date(y, m, 1)
    return d + timedelta(days=(4 - d.weekday()) % 7)


def _nth_weekday(y, m, weekday, n):
    """n-th given weekday (0=Mon) of month m."""
    d = date(y, m, 1)
    first = d + timedelta(days=(weekday - d.weekday()) % 7)
    return first + timedelta(weeks=n - 1)


def _next_nfp(today):
    """Non-Farm Payrolls — released first Friday of each month, 08:30 ET."""
    f = _first_friday(today.year, today.month)
    if f < today:
        ny, nm = (today.year + (today.month == 12)), (today.month % 12 + 1)
        f = _first_friday(ny, nm)
    return f


def _next_cpi(today):
    """CPI — mid-month (US BLS typically ~10th-14th). We approximate as the
    second Wednesday, a robust mid-month proxy that updates automatically."""
    c = _nth_weekday(today.year, today.month, 2, 2)  # 2nd Wednesday
    if c < today:
        ny, nm = (today.year + (today.month == 12)), (today.month % 12 + 1)
        c = _nth_weekday(ny, nm, 2, 2)
    return c


# FOMC meeting dates are published by the Fed ~yearly. Known 2026 decision days
# (second day of each meeting). Extend this list each year.
FOMC_2026 = [
    date(2026, 1, 28), date(2026, 3, 18), date(2026, 4, 29), date(2026, 6, 17),
    date(2026, 7, 29), date(2026, 9, 16), date(2026, 11, 4), date(2026, 12, 16),
]
FOMC_2027 = [
    date(2027, 1, 27), date(2027, 3, 17), date(2027, 4, 28), date(2027, 6, 16),
    date(2027, 7, 28), date(2027, 9, 22), date(2027, 11, 3), date(2027, 12, 15),
]


def _next_fomc(today):
    for d in FOMC_2026 + FOMC_2027:
        if d >= today:
            return d
    return None


def _event_row(name_he, d, today, note):
    if d is None:
        return None
    days = (d - today).days
    if days <= 2:
        tone, urgency = "bad", "השבוע — שים לב"
    elif days <= 7:
        tone, urgency = "warn", "בשבוע הקרוב"
    else:
        tone, urgency = "default", "בקרוב"
    return {
        "name_he": name_he,
        "date": d.isoformat(),
        "days_away": days,
        "tone": tone,
        "urgency_he": urgency,
        "note_he": note,
    }


def economic_events():
    today = date.today()
    rows = [
        _event_row("דוח תעסוקה (NFP)", _next_nfp(today), today,
                   "נתוני שוק העבודה בארה\"ב — מזיז שווקים חזק"),
        _event_row("מדד המחירים לצרכן (CPI)", _next_cpi(today), today,
                   "אינפלציה — משפיע ישירות על ציפיות הריבית"),
        _event_row("החלטת ריבית (FOMC)", _next_fomc(today), today,
                   "הפדרל ריזרב — ההחלטה הכי משמעותית לשווקים"),
    ]
    rows = [r for r in rows if r]
    rows.sort(key=lambda r: r["days_away"])
    return rows


def _one_quote_hist(provider, ticker):
    """Fetch quote + 1y history for a single ticker (used in parallel)."""
    try:
        q = provider.quote(ticker)
    except Exception:
        q = None
    try:
        hist = provider.history(ticker, period="1y", interval="1d")
        closes = _closes_from_hist(hist)
    except Exception:
        closes = []
    return ticker, q, closes


def build_overview(provider):
    """Assemble the full market overview. Fetches SPY + 11 sectors + VIX in
    parallel for speed. Returns a JSON-serializable dict with Hebrew labels."""
    tickers = ["SPY", "^VIX"] + [s[0] for s in SECTORS]
    results = {}
    with ThreadPoolExecutor(max_workers=10) as ex:
        for tk, q, closes in ex.map(lambda t: _one_quote_hist(provider, t), tickers):
            results[tk] = (q, closes)

    # ── S&P 500 (SPY) ──
    spy_q, spy_closes = results.get("SPY", (None, []))
    spy_price = (spy_q or {}).get("price")
    spy_sma50 = _sma(spy_closes, 50)
    spy_sma200 = _sma(spy_closes, 200)
    spy_label, spy_tone = _trend_label(spy_price, spy_sma50, spy_sma200)
    sp500 = {
        "price": spy_price,
        "change_pct": (spy_q or {}).get("change_pct"),
        "label_he": spy_label,
        "tone": spy_tone,
        "above_sma50": (spy_price is not None and spy_sma50 is not None and spy_price > spy_sma50),
        "above_sma200": (spy_price is not None and spy_sma200 is not None and spy_price > spy_sma200),
    }

    # ── VIX ──
    vix_q, _ = results.get("^VIX", (None, []))
    vix_val = (vix_q or {}).get("price")
    vlabel, vtone, vnote = _vix_label(vix_val)
    vix = {
        "value": vix_val,
        "change_pct": (vix_q or {}).get("change_pct"),
        "label_he": vlabel,
        "tone": vtone,
        "note_he": vnote,
    }

    # ── Sectors: rank by daily change ──
    sectors = []
    for tk, name in SECTORS:
        q, _ = results.get(tk, (None, []))
        if not q:
            continue
        chg = q.get("change_pct")
        sectors.append({
            "ticker": tk,
            "name_he": name,
            "change_pct": chg,
            "tone": "good" if (chg or 0) > 0.2 else "bad" if (chg or 0) < -0.2 else "warn",
        })
    sectors.sort(key=lambda s: (s["change_pct"] if s["change_pct"] is not None else -999), reverse=True)

    # Overall breadth read from sectors
    up = sum(1 for s in sectors if (s["change_pct"] or 0) > 0)
    total = len(sectors) or 1
    breadth_pct = round(100 * up / total)
    if breadth_pct >= 70:
        breadth_label, breadth_tone = "רחב — רוב הסקטורים עולים", "good"
    elif breadth_pct >= 45:
        breadth_label, breadth_tone = "מעורב", "warn"
    else:
        breadth_label, breadth_tone = "חלש — רוב הסקטורים יורדים", "bad"

    return {
        "as_of": datetime.utcnow().isoformat() + "Z",
        "sp500": sp500,
        "vix": vix,
        "sectors": sectors,
        "breadth": {"up": up, "total": total, "pct": breadth_pct,
                    "label_he": breadth_label, "tone": breadth_tone},
        "events": economic_events(),
    }
