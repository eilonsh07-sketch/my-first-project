"""
technicals.py — Technical indicators & chart-pattern detection.
Pure numpy/pandas. Input: pandas DataFrame with columns Open, High, Low, Close, Volume.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def _series(df, col="Close"):
    return df[col].astype(float)


def rsi(df, period=14):
    close = _series(df)
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    rs = gain / loss.replace(0, np.nan)
    out = 100 - (100 / (1 + rs))
    return out


def macd(df, fast=12, slow=26, signal=9):
    close = _series(df)
    ema_fast = close.ewm(span=fast, adjust=False).mean()
    ema_slow = close.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    hist = macd_line - signal_line
    return macd_line, signal_line, hist


def bollinger(df, period=20, mult=2.0):
    close = _series(df)
    mid = close.rolling(period).mean()
    std = close.rolling(period).std()
    upper = mid + mult * std
    lower = mid - mult * std
    width = (upper - lower) / mid
    return upper, mid, lower, width


def obv(df):
    close = _series(df)
    vol = df["Volume"].astype(float)
    direction = np.sign(close.diff().fillna(0))
    return (direction * vol).cumsum()


def vwap(df):
    typical = (df["High"] + df["Low"] + df["Close"]) / 3.0
    vol = df["Volume"].astype(float)
    return (typical * vol).cumsum() / vol.cumsum()


def atr(df, period=14):
    high = df["High"].astype(float)
    low = df["Low"].astype(float)
    close = _series(df)
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr.rolling(period).mean()


def adx(df, period=14):
    """Average Directional Index — trend STRENGTH (not direction). Returns (adx, +DI, -DI) series."""
    high = df["High"].astype(float)
    low = df["Low"].astype(float)
    close = _series(df)
    up_move = high.diff()
    down_move = -low.diff()
    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)
    prev_close = close.shift(1)
    tr = pd.concat([high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1).max(axis=1)
    atr_s = tr.ewm(alpha=1 / period, adjust=False).mean()
    plus_di = 100 * pd.Series(plus_dm, index=df.index).ewm(alpha=1 / period, adjust=False).mean() / atr_s.replace(0, np.nan)
    minus_di = 100 * pd.Series(minus_dm, index=df.index).ewm(alpha=1 / period, adjust=False).mean() / atr_s.replace(0, np.nan)
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    adx_s = dx.ewm(alpha=1 / period, adjust=False).mean()
    return adx_s, plus_di, minus_di


def stochastic(df, k_period=14, d_period=3):
    """Stochastic oscillator %K and %D (0-100). Momentum / overbought-oversold."""
    high = df["High"].astype(float)
    low = df["Low"].astype(float)
    close = _series(df)
    lowest = low.rolling(k_period).min()
    highest = high.rolling(k_period).max()
    k = 100 * (close - lowest) / (highest - lowest).replace(0, np.nan)
    d = k.rolling(d_period).mean()
    return k, d


def ichimoku(df):
    """Ichimoku Cloud components. Returns dict of latest values + price-vs-cloud position."""
    high = df["High"].astype(float)
    low = df["Low"].astype(float)
    close = _series(df)
    if len(close) < 52:
        return None
    tenkan = (high.rolling(9).max() + low.rolling(9).min()) / 2          # conversion
    kijun = (high.rolling(26).max() + low.rolling(26).min()) / 2         # base
    span_a = ((tenkan + kijun) / 2)                                      # leading span A
    span_b = (high.rolling(52).max() + low.rolling(52).min()) / 2        # leading span B
    last = float(close.iloc[-1])
    a = _f(span_a.iloc[-1]); b = _f(span_b.iloc[-1])
    cloud_top = max(a, b) if (a is not None and b is not None) else None
    cloud_bot = min(a, b) if (a is not None and b is not None) else None
    if cloud_top is None:
        position = None
    elif last > cloud_top:
        position = "above"   # bullish — above the cloud
    elif last < cloud_bot:
        position = "below"   # bearish — below the cloud
    else:
        position = "inside"  # neutral / in the cloud
    return {
        "tenkan": _f(tenkan.iloc[-1]), "kijun": _f(kijun.iloc[-1]),
        "span_a": a, "span_b": b,
        "cloud_top": cloud_top, "cloud_bottom": cloud_bot,
        "position": position,
        "tk_cross": bool(_f(tenkan.iloc[-1]) and _f(kijun.iloc[-1]) and tenkan.iloc[-1] > kijun.iloc[-1]),
    }


def support_resistance(df, lookback=120, n_levels=3):
    """Detect horizontal support/resistance from swing highs/lows via local extrema clustering."""
    seg = df.tail(lookback)
    highs = seg["High"].astype(float).values
    lows = seg["Low"].astype(float).values
    close = float(_series(df).iloc[-1])
    piv_high, piv_low = [], []
    w = 3
    for i in range(w, len(seg) - w):
        if highs[i] == max(highs[i - w:i + w + 1]):
            piv_high.append(highs[i])
        if lows[i] == min(lows[i - w:i + w + 1]):
            piv_low.append(lows[i])

    def cluster(levels, tol=0.015):
        levels = sorted(levels)
        clusters = []
        for lv in levels:
            if clusters and abs(lv - clusters[-1][-1]) / clusters[-1][-1] <= tol:
                clusters[-1].append(lv)
            else:
                clusters.append([lv])
        # rank by touch count
        ranked = sorted(clusters, key=len, reverse=True)
        return [round(float(np.mean(c)), 2) for c in ranked]

    res = [r for r in cluster(piv_high) if r > close][:n_levels]
    sup = [s for s in cluster(piv_low) if s < close][:n_levels]
    res_sorted = sorted(res)
    sup_sorted = sorted(sup, reverse=True)
    return {
        "resistance": res_sorted,
        "support": sup_sorted,
        "nearest_resistance": res_sorted[0] if res_sorted else None,
        "nearest_support": sup_sorted[0] if sup_sorted else None,
    }


def fibonacci_levels(df, lookback=120):
    """Fibonacci retracement levels from the most recent significant swing high/low."""
    seg = _series(df).tail(lookback)
    if len(seg) < 20:
        return None
    hi = float(seg.max()); lo = float(seg.min())
    hi_idx = seg.idxmax(); lo_idx = seg.idxmin()
    rng = hi - lo
    if rng <= 0:
        return None
    uptrend = seg.index.get_loc(hi_idx) > seg.index.get_loc(lo_idx)
    ratios = [0.236, 0.382, 0.5, 0.618, 0.786]
    if uptrend:
        # retracements measured down from the high
        levels = {f"{int(r*1000)/10}%": round(hi - r * rng, 2) for r in ratios}
    else:
        levels = {f"{int(r*1000)/10}%": round(lo + r * rng, 2) for r in ratios}
    close = float(_series(df).iloc[-1])
    # nearest fib level to current price
    nearest = min(levels.items(), key=lambda kv: abs(kv[1] - close))
    return {
        "swing_high": round(hi, 2), "swing_low": round(lo, 2),
        "direction": "up" if uptrend else "down",
        "levels": levels,
        "nearest_level": nearest[0], "nearest_price": nearest[1],
    }


def moving_averages(df):
    close = _series(df)
    return {
        "ma20": float(close.rolling(20).mean().iloc[-1]) if len(close) >= 20 else None,
        "ma50": float(close.rolling(50).mean().iloc[-1]) if len(close) >= 50 else None,
        "ma150": float(close.rolling(150).mean().iloc[-1]) if len(close) >= 150 else None,
        "ma200": float(close.rolling(200).mean().iloc[-1]) if len(close) >= 200 else None,
    }


def realized_vol(df, window=30):
    """Annualized realized volatility from daily log returns."""
    close = _series(df)
    logret = np.log(close / close.shift(1)).dropna()
    if len(logret) < 5:
        return None
    w = min(window, len(logret))
    return float(logret.tail(w).std() * np.sqrt(252))


def beta(stock_df, index_df):
    """Beta of stock vs index using daily returns."""
    s = np.log(_series(stock_df) / _series(stock_df).shift(1)).dropna()
    m = np.log(_series(index_df) / _series(index_df).shift(1)).dropna()
    joined = pd.concat([s, m], axis=1, join="inner").dropna()
    if len(joined) < 20:
        return None
    cov = np.cov(joined.iloc[:, 0], joined.iloc[:, 1])
    var_m = cov[1, 1]
    if var_m == 0:
        return None
    return float(cov[0, 1] / var_m)


def relative_strength(stock_df, index_df, lookback=252):
    """Performance of stock vs index over lookback period (ratio of returns)."""
    s = _series(stock_df)
    m = _series(index_df)
    n = min(lookback, len(s) - 1, len(m) - 1)
    if n < 20:
        return None
    s_ret = s.iloc[-1] / s.iloc[-n] - 1
    m_ret = m.iloc[-1] / m.iloc[-n] - 1
    return {"stock_return": float(s_ret), "index_return": float(m_ret),
            "outperformance": float(s_ret - m_ret)}


# ---------------------------------------------------------------------------
# Chart pattern detection (heuristic, transparent)
# ---------------------------------------------------------------------------
def detect_patterns(df):
    """Detect simple, well-known chart patterns. Returns list of {name, confidence, note}."""
    patterns = []
    close = _series(df)
    if len(close) < 60:
        return patterns
    highs = df["High"].astype(float)
    lows = df["Low"].astype(float)

    recent = close.tail(60)
    x = np.arange(len(recent))

    # Trend channel (rising / falling) via linear regression on closes
    slope, intercept = np.polyfit(x, recent.values, 1)
    resid = recent.values - (slope * x + intercept)
    rel_slope = slope * len(recent) / recent.mean()
    band = resid.std() / recent.mean()
    if abs(rel_slope) > 0.04 and band < 0.06:
        if slope > 0:
            patterns.append({"name": "תעלה עולה", "name_en": "Rising Channel",
                             "confidence": min(0.9, 0.5 + abs(rel_slope)),
                             "note": "מחיר עולה בתעלה יציבה"})
        else:
            patterns.append({"name": "תעלה יורדת", "name_en": "Falling Channel",
                             "confidence": min(0.9, 0.5 + abs(rel_slope)),
                             "note": "מחיר יורד בתעלה — זהירות"})

    # Bull flag: strong run-up then tight consolidation
    if len(close) >= 40:
        runup = close.iloc[-20] / close.iloc[-40] - 1
        consol = close.tail(15)
        consol_range = (consol.max() - consol.min()) / consol.mean()
        consol_slope = np.polyfit(np.arange(len(consol)), consol.values, 1)[0]
        if runup > 0.12 and consol_range < 0.08 and consol_slope <= 0:
            patterns.append({"name": "דגל שורי", "name_en": "Bull Flag",
                             "confidence": min(0.85, 0.5 + runup),
                             "note": "ריצה חזקה ואז דשדוש — המשך אפשרי כלפי מעלה"})

    # Cup and handle: U-shape recovery then small dip
    if len(close) >= 60:
        seg = close.tail(60).values
        left = seg[:20].mean(); bottom = seg[20:40].min(); right = seg[40:55].mean()
        handle = seg[55:]
        if (bottom < left * 0.92 and right > left * 0.97 and
                handle.min() > bottom * 1.05 and handle[-1] < right):
            patterns.append({"name": "ספל וידית", "name_en": "Cup & Handle",
                             "confidence": 0.65,
                             "note": "תבנית היפוך שורית קלאסית"})

    return patterns


def technical_summary(df, index_df=None):
    """Compute all indicators and return a structured summary for the latest bar."""
    close = _series(df)
    last = float(close.iloc[-1])
    rsi_v = rsi(df)
    macd_line, sig_line, hist = macd(df)
    up, mid, low, width = bollinger(df)
    obv_s = obv(df)
    vwap_s = vwap(df)
    atr_s = atr(df)
    mas = moving_averages(df)
    rv = realized_vol(df, 30)

    # NEW advanced indicators
    adx_s, plus_di, minus_di = adx(df)
    stoch_k, stoch_d = stochastic(df)
    ich = ichimoku(df)
    sr = support_resistance(df)
    fib = fibonacci_levels(df)

    ma20 = mas["ma20"]
    overextended = bool(ma20 and (last - ma20) / ma20 > 0.15)

    # OBV trend (last 20 bars)
    obv_trend = None
    if len(obv_s.dropna()) > 20:
        recent_obv = obv_s.dropna().tail(20)
        obv_trend = "עולה" if recent_obv.iloc[-1] > recent_obv.iloc[0] else "יורד"

    patterns = detect_patterns(df)
    rs = relative_strength(df, index_df) if index_df is not None else None
    b = beta(df, index_df) if index_df is not None else None

    return {
        "price": last,
        "rsi": _f(rsi_v.iloc[-1]),
        "macd": _f(macd_line.iloc[-1]),
        "macd_signal": _f(sig_line.iloc[-1]),
        "macd_hist": _f(hist.iloc[-1]),
        "macd_bullish": bool(_f(hist.iloc[-1]) and hist.iloc[-1] > 0),
        "bb_upper": _f(up.iloc[-1]),
        "bb_mid": _f(mid.iloc[-1]),
        "bb_lower": _f(low.iloc[-1]),
        "bb_width": _f(width.iloc[-1]),
        "bb_position": _f((last - low.iloc[-1]) / (up.iloc[-1] - low.iloc[-1])) if _f(up.iloc[-1]) else None,
        "obv_trend": obv_trend,
        "vwap": _f(vwap_s.iloc[-1]),
        "above_vwap": bool(_f(vwap_s.iloc[-1]) and last > vwap_s.iloc[-1]),
        "atr": _f(atr_s.iloc[-1]),
        "atr_pct": _f(atr_s.iloc[-1] / last) if _f(atr_s.iloc[-1]) else None,
        "ma20": ma20, "ma50": mas["ma50"], "ma150": mas["ma150"], "ma200": mas["ma200"],
        "above_ma20": bool(ma20 and last > ma20),
        "above_ma50": bool(mas["ma50"] and last > mas["ma50"]),
        "above_ma150": bool(mas["ma150"] and last > mas["ma150"]),
        "above_ma200": bool(mas["ma200"] and last > mas["ma200"]),
        "overextended": overextended,
        "realized_vol": rv,
        "beta": b,
        "relative_strength": rs,
        "patterns": patterns,
        # --- advanced indicators ---
        "adx": _f(adx_s.iloc[-1]),
        "plus_di": _f(plus_di.iloc[-1]),
        "minus_di": _f(minus_di.iloc[-1]),
        "stoch_k": _f(stoch_k.iloc[-1]),
        "stoch_d": _f(stoch_d.iloc[-1]),
        "ichimoku": ich,
        "support_resistance": sr,
        "fibonacci": fib,
    }


def _rate(signal):
    """Map a -2..+2 signal to a Hebrew rating + tone for the UI."""
    if signal >= 2:
        return "חזק חיובי", "good", signal
    if signal == 1:
        return "חיובי", "good", signal
    if signal == 0:
        return "ניטרלי", "warn", signal
    if signal == -1:
        return "שלילי", "bad", signal
    return "חזק שלילי", "bad", signal


def technical_scorecard(tech, currency="$"):
    """Build a per-indicator scorecard from a technical_summary() dict.
    Each row: {name_he, value, rating, tone, signal (-2..+2), on_chart, note}.
    Returns {rows, total (0-100), grade_he}.
    `currency` is the symbol used in price-bearing notes (default "$" for US
    stocks; pass "\u20aa" for Israeli indices/securities)."""
    cur = currency
    rows = []
    last = tech.get("price")

    # RSI
    rsi_v = tech.get("rsi")
    if rsi_v is not None:
        if rsi_v < 30:
            sig, note = 1, "מכירת יתר — פוטנציאל תיקון מעלה"
        elif rsi_v > 70:
            sig, note = -1, "קניית יתר — סיכון לתיקון"
        elif 45 <= rsi_v <= 65:
            sig, note = 1, "אזור בריא למגמה עולה"
        else:
            sig, note = 0, "ניטרלי"
        r, tone, s = _rate(sig)
        rows.append({"name_he": "RSI (14)", "value": round(rsi_v, 1), "rating": r,
                     "tone": tone, "signal": s, "on_chart": True, "note": note})

    # MACD
    mh = tech.get("macd_hist")
    if mh is not None:
        sig = 1 if tech.get("macd_bullish") else -1
        note = "היסטוגרמה חיובית — מומנטום עולה" if sig > 0 else "היסטוגרמה שלילית — מומנטום יורד"
        r, tone, s = _rate(sig)
        rows.append({"name_he": "MACD", "value": round(mh, 3), "rating": r,
                     "tone": tone, "signal": s, "on_chart": True, "note": note})

    # ADX — trend strength + direction via DI
    adx_v = tech.get("adx")
    if adx_v is not None:
        pdi, mdi = tech.get("plus_di") or 0, tech.get("minus_di") or 0
        if adx_v >= 25:
            dir_up = pdi > mdi
            sig = 2 if dir_up else -2
            note = f"מגמה חזקה ({'עולה' if dir_up else 'יורדת'}) — ADX מעל 25"
        elif adx_v >= 20:
            dir_up = pdi > mdi
            sig = 1 if dir_up else -1
            note = f"מגמה מתפתחת ({'עולה' if dir_up else 'יורדת'})"
        else:
            sig = 0
            note = "מגמה חלשה / דשדוש — ADX מתחת ל-20"
        r, tone, s = _rate(sig)
        rows.append({"name_he": "ADX (עוצמת מגמה)", "value": round(adx_v, 1), "rating": r,
                     "tone": tone, "signal": s, "on_chart": True, "note": note})

    # Stochastic
    sk = tech.get("stoch_k")
    if sk is not None:
        sd = tech.get("stoch_d") or sk
        if sk < 20:
            sig, note = 1, "מכירת יתר — איתות קנייה אפשרי"
        elif sk > 80:
            sig, note = -1, "קניית יתר — סיכון להיחלשות"
        else:
            sig = 1 if sk > sd else (-1 if sk < sd else 0)
            note = "%K מעל %D — מומנטום חיובי" if sig > 0 else ("%K מתחת %D — מומנטום שלילי" if sig < 0 else "ניטרלי")
        r, tone, s = _rate(sig)
        rows.append({"name_he": "Stochastic", "value": round(sk, 1), "rating": r,
                     "tone": tone, "signal": s, "on_chart": True, "note": note})

    # Ichimoku cloud position
    ich = tech.get("ichimoku")
    if ich and ich.get("position"):
        pos = ich["position"]
        if pos == "above":
            sig, note = 2, "מחיר מעל הענן — מגמה שורית"
        elif pos == "below":
            sig, note = -2, "מחיר מתחת לענן — מגמה דובית"
        else:
            sig, note = 0, "מחיר בתוך הענן — חוסר החלטיות"
        r, tone, s = _rate(sig)
        rows.append({"name_he": "Ichimoku (ענן)", "value": {"above": "מעל הענן", "below": "מתחת לענן", "inside": "בתוך הענן"}[pos],
                     "rating": r, "tone": tone, "signal": s, "on_chart": True, "note": note})

    # Bollinger position
    bbp = tech.get("bb_position")
    if bbp is not None:
        if bbp > 0.95:
            sig, note = -1, "ברצועה העליונה — מתוח, סיכון תיקון"
        elif bbp < 0.05:
            sig, note = 1, "ברצועה התחתונה — פוטנציאל ריבאונד"
        else:
            sig, note = 0, "בתוך הרצועות — נורמלי"
        r, tone, s = _rate(sig)
        rows.append({"name_he": "Bollinger", "value": f"{round(bbp*100)}%", "rating": r,
                     "tone": tone, "signal": s, "on_chart": True, "note": note})

    # Moving-average stack
    ma_above = sum(1 for k in ("above_ma20", "above_ma50", "above_ma150", "above_ma200") if tech.get(k))
    ma_total = sum(1 for k in ("ma20", "ma50", "ma150", "ma200") if tech.get(k) is not None)
    if ma_total:
        frac = ma_above / ma_total
        if frac >= 0.75:
            sig, note = 2, f"מעל {ma_above}/{ma_total} ממוצעים נעים — מבנה שורי"
        elif frac >= 0.5:
            sig, note = 1, f"מעל {ma_above}/{ma_total} ממוצעים נעים"
        elif frac <= 0.25:
            sig, note = -2, f"מתחת לרוב הממוצעים הנעים — מבנה דובי"
        else:
            sig, note = -1, f"מעורב — מעל {ma_above}/{ma_total} ממוצעים"
        r, tone, s = _rate(sig)
        rows.append({"name_he": "ממוצעים נעים", "value": f"{ma_above}/{ma_total}", "rating": r,
                     "tone": tone, "signal": s, "on_chart": True, "note": note})

    # OBV / volume trend
    obv_t = tech.get("obv_trend")
    if obv_t:
        sig = 1 if obv_t == "עולה" else -1
        r, tone, s = _rate(sig)
        rows.append({"name_he": "OBV (זרימת נפח)", "value": obv_t, "rating": r,
                     "tone": tone, "signal": s, "on_chart": False,
                     "note": "נפח תומך במגמה" if sig > 0 else "נפח נגד המגמה"})

    # Support / resistance proximity
    sr = tech.get("support_resistance")
    if sr and last:
        ns, nr = sr.get("nearest_support"), sr.get("nearest_resistance")
        sig, note = 0, "ללא רמות קרובות מובהקות"
        if ns and nr:
            dist_s = (last - ns) / last
            dist_r = (nr - last) / last
            if dist_s < 0.03:
                sig, note = 1, f"קרוב לתמיכה {cur}{ns} — אזור כניסה פוטנציאלי"
            elif dist_r < 0.03:
                sig, note = -1, f"קרוב להתנגדות {cur}{nr} — ייתכן בלימה"
            else:
                note = f"תמיכה {cur}{ns} / התנגדות {cur}{nr}"
        elif ns:
            note = f"תמיכה קרובה {cur}{ns}"
        elif nr:
            note = f"התנגדות קרובה {cur}{nr}"
        r, tone, s = _rate(sig)
        rows.append({"name_he": "תמיכה / התנגדות", "value": note, "rating": r,
                     "tone": tone, "signal": s, "on_chart": True, "note": note})

    # Fibonacci proximity
    fib = tech.get("fibonacci")
    if fib and fib.get("nearest_level"):
        lvl, px = fib["nearest_level"], fib.get("nearest_price")
        sig = 0
        note = f"רמת פיבונאצ'י קרובה {lvl} ({cur}{px})"
        r, tone, s = _rate(sig)
        rows.append({"name_he": "Fibonacci", "value": f"{lvl} ({cur}{px})", "rating": r,
                     "tone": tone, "signal": s, "on_chart": True, "note": note})

    # Aggregate score 0-100 (signals are -2..+2)
    if rows:
        raw = sum(rr["signal"] for rr in rows)
        max_raw = 2 * len(rows)
        total = round(50 + 50 * raw / max_raw) if max_raw else 50
        total = max(0, min(100, total))
    else:
        total = 50
    if total >= 70:
        grade = "טכני חיובי חזק"
    elif total >= 58:
        grade = "טכני חיובי"
    elif total >= 42:
        grade = "טכני ניטרלי"
    elif total >= 30:
        grade = "טכני חלש"
    else:
        grade = "טכני שלילי"
    return {"rows": rows, "total": total, "grade_he": grade}


def _f(v):
    try:
        if v is None or (isinstance(v, float) and np.isnan(v)):
            return None
        return float(v)
    except Exception:
        return None
