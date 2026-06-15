"""
american_pricing.py — תמחור אופציות אמריקאיות (זכות מימוש מוקדם).

שני מנועים, ללא קיצורי דרך:
  1. binomial_crr  — מודל Cox-Ross-Rubinstein (עץ בינומי וקטורי, NumPy).
                     המנוע הראשי לתמחור אמריקאי — מהיר, יציב, חסכוני בזיכרון.
  2. lsm_price     — Least Squares Monte Carlo (Longstaff-Schwartz).
                     בדיקת-הצלבה (cross-validation) מול CRR וטיפול בתרחישים מורכבים.

עקרונות:
  * דיבידנד נתמך בשתי צורות: תשואה רציפה q, או דיבידנדים בדידים (cash) בתאריכים.
  * המימוש המוקדם מחושב באינדוקציה לאחור: בכל צומת/צעד משווים בין הערך הפנימי
    (Intrinsic) לערך ההמתנה (Continuation) ובוחרים במקסימום.
  * early_exercise_premium = מחיר אמריקאי − מחיר אירופאי (Black-Scholes).
    זו בדיוק התוספת שמודל אירופאי מפספס.

הערה: כל המתמטיקה כאן ניטרלת-סיכון (risk-neutral) לצורך *תמחור* הוגן של החוזה.
ה-drift הריאלי (mu) של ה-PoP נשאר בנפרד ב-pricing.py / scoring.py.
"""
from __future__ import annotations

import math
from typing import Optional, Sequence, Tuple

import numpy as np

from .pricing import bs_price


# ---------------------------------------------------------------------------
# עזר: דיבידנדים בדידים -> ערך נוכחי שמורד ממחיר המניה (escrowed dividend model)
# ---------------------------------------------------------------------------
def _pv_discrete_dividends(
    S0: float,
    T: float,
    r: float,
    dividends: Optional[Sequence[Tuple[float, float]]],
) -> float:
    """ערך נוכחי של דיבידנדים בדידים שייפלו בתוך חיי האופציה.

    dividends: רשימת (t_years, amount) — זמן בשנים מהיום עד האקס-דיבידנד, וסכום למניה.
    מחזיר את סכום הערכים הנוכחיים (מהוון בריבית r).
    """
    if not dividends:
        return 0.0
    pv = 0.0
    for t_div, amt in dividends:
        if amt and 0.0 < t_div <= T:
            pv += float(amt) * math.exp(-r * float(t_div))
    return pv


# ---------------------------------------------------------------------------
# 1. מודל בינומי Cox-Ross-Rubinstein (CRR) — וקטורי
# ---------------------------------------------------------------------------
def binomial_crr(
    S, K, T, r, sigma, kind="call", q=0.0, steps=200,
    american=True, dividends=None,
):
    """תמחור אופציה במודל CRR.

    S, K  — מחיר נכס הבסיס ומחיר המימוש.
    T     — זמן לפקיעה בשנים.
    r     — ריבית חסרת-סיכון (רציפה).
    sigma — תנודתיות שנתית.
    kind  — "call" / "put".
    q     — תשואת דיבידנד רציפה (אם אין דיבידנדים בדידים).
    steps — מספר צעדי זמן בעץ (ברירת מחדל 200 -> דיוק גבוה).
    american — True למימוש מוקדם בכל צומת; False לאירופאי (לבדיקה מול BS).
    dividends — רשימת (t_years, amount) לדיבידנדים בדידים. אם ניתנים, q מתעלמים.

    מחזיר את מחיר האופציה (per share).
    """
    S = float(S); K = float(K); T = float(T)
    sigma = max(float(sigma), 1e-9)
    steps = max(int(steps), 1)

    if T <= 0:
        return max(S - K, 0.0) if kind == "call" else max(K - S, 0.0)

    # אם יש דיבידנדים בדידים — מורידים את הערך הנוכחי שלהם ממחיר הבסיס (escrowed model),
    # ומתמחרים את "החלק התנודתי" של המניה. זו השיטה הסטנדרטית לעצים בינומיים.
    use_discrete = bool(dividends)
    if use_discrete:
        pv_div = _pv_discrete_dividends(S, T, r, dividends)
        S_eff = max(S - pv_div, 1e-9)
        q_eff = 0.0
    else:
        S_eff = S
        q_eff = float(q)

    dt = T / steps
    u = math.exp(sigma * math.sqrt(dt))
    d = 1.0 / u
    disc = math.exp(-r * dt)
    # הסתברות ניטרלת-סיכון (כולל דיבידנד רציף q_eff)
    a = math.exp((r - q_eff) * dt)
    p = (a - d) / (u - d)
    # הגנה נומרית: אם p יוצא מחוץ ל-[0,1] (steps נמוך / sigma קטן) — מצמצמים
    p = min(max(p, 0.0), 1.0)

    # מחירי הבסיס בפקיעה: S_eff * u^j * d^(steps-j), j=0..steps  (וקטורי)
    j = np.arange(steps + 1)
    ST = S_eff * (u ** j) * (d ** (steps - j))

    if kind == "call":
        values = np.maximum(ST - K, 0.0)
    else:
        values = np.maximum(K - ST, 0.0)

    # אינדוקציה לאחור — וקטורית על פני כל צעד
    for i in range(steps - 1, -1, -1):
        # ערך ההמתנה (continuation) המהוון
        values = disc * (p * values[1:] + (1.0 - p) * values[:-1])
        if american:
            # מחירי הבסיס בצעד i
            j = np.arange(i + 1)
            S_i = S_eff * (u ** j) * (d ** (i - j))
            # אם יש דיבידנדים בדידים — מוסיפים בחזרה את ה-PV שעוד לא חולק עד צעד i
            if use_discrete:
                t_i = i * dt
                pv_future = _pv_discrete_dividends(S, T, r,
                    [(td, amt) for (td, amt) in dividends if td > t_i])
                # ה-PV של דיבידנדים שכבר חולקו לפני t_i כבר לא רלוונטי למחיר;
                # מוסיפים בחזרה רק את אלו שעדיין צפויים (escrowed) כדי לקבל את מחיר המניה האמיתי
                S_real = S_i + pv_future
            else:
                S_real = S_i
            if kind == "call":
                exercise = np.maximum(S_real - K, 0.0)
            else:
                exercise = np.maximum(K - S_real, 0.0)
            values = np.maximum(values, exercise)

    return float(values[0])


# ---------------------------------------------------------------------------
# 2. Least Squares Monte Carlo (Longstaff-Schwartz)
# ---------------------------------------------------------------------------
def lsm_price(
    S, K, T, r, sigma, kind="put", q=0.0, n=10000, steps=50,
    dividends=None, seed=43, poly_degree=2,
):
    """תמחור אופציה אמריקאית בשיטת LSM (Longstaff-Schwartz).

    מריצים n מסלולי GBM, ומבצעים אינדוקציה לאחור: בכל צעד, על המסלולים
    שנמצאים בתוך הכסף (ITM), מבצעים רגרסיה של ערך-ההמתנה המהוון על פולינום של
    מחיר הבסיס, ומשווים מול הערך הפנימי כדי להחליט על מימוש מוקדם.

    מחזיר את מחיר האופציה (per share).

    הערה: LSM מדויק במיוחד ל-PUTs אמריקאיות; ל-CALLs ללא דיבידנד המימוש המוקדם
    אף פעם לא אופטימלי (המחיר = אירופאי), וזה משמש בדיקת שפיות.
    """
    S = float(S); K = float(K); T = float(T)
    sigma = max(float(sigma), 1e-9)
    if T <= 0:
        return max(S - K, 0.0) if kind == "call" else max(K - S, 0.0)

    n = int(n); steps = max(int(steps), 1)
    dt = T / steps
    disc = math.exp(-r * dt)
    rng = np.random.default_rng(seed)

    # ערך נוכחי של דיבידנדים בדידים -> מורידים מ-S ההתחלתי (escrowed), q=0
    if dividends:
        pv_div = _pv_discrete_dividends(S, T, r, dividends)
        S_start = max(S - pv_div, 1e-9)
        q_eff = 0.0
    else:
        S_start = S
        q_eff = float(q)

    drift = (r - q_eff - 0.5 * sigma * sigma) * dt
    vol = sigma * math.sqrt(dt)

    # יצירת מסלולי מחיר: מטריצה (steps+1, n). שומרים רק את העמודה הנוכחית כדי
    # לחסוך זיכרון? — LSM זקוק לכל המסלולים לרגרסיה, אבל נשמור float32 לחיסכון.
    logS = np.full(n, math.log(S_start), dtype=np.float64)
    paths = np.empty((steps + 1, n), dtype=np.float32)
    paths[0] = S_start
    for t in range(1, steps + 1):
        logS = logS + drift + vol * rng.standard_normal(n)
        paths[t] = np.exp(logS)

    # תזרים: מתחילים מהערך הפנימי בפקיעה
    if kind == "call":
        cashflow = np.maximum(paths[-1] - K, 0.0).astype(np.float64)
    else:
        cashflow = np.maximum(K - paths[-1], 0.0).astype(np.float64)

    # אינדוקציה לאחור מ-steps-1 עד 1 (לא מממשים ב-t=0)
    for t in range(steps - 1, 0, -1):
        St = paths[t].astype(np.float64)
        if kind == "call":
            intrinsic = St - K
        else:
            intrinsic = K - St
        itm = intrinsic > 0.0
        cashflow *= disc  # היוון התזרים העתידי צעד אחד אחורה
        if not np.any(itm):
            continue
        X = St[itm]
        Y = cashflow[itm]  # ערך ההמתנה המהוון בפועל לאורך כל מסלול ITM
        # רגרסיה: ניבוי ערך ההמתנה כפולינום של מחיר הבסיס (Least Squares)
        try:
            coeffs = np.polyfit(X, Y, poly_degree)
            continuation = np.polyval(coeffs, X)
        except (np.linalg.LinAlgError, ValueError):
            continuation = Y
        ex_val = intrinsic[itm]
        # החלטת מימוש: היכן שהערך הפנימי גבוה מערך ההמתנה החזוי -> ממשים עכשיו
        exercise_now = ex_val > continuation
        idx = np.where(itm)[0][exercise_now]
        cashflow[idx] = ex_val[exercise_now]

    # התזרים כבר מהוון עד t=1; היוון אחרון לצעד t=0
    price = float(np.mean(cashflow) * disc)
    return max(price, 0.0)


# ---------------------------------------------------------------------------
# 3. ממשק אחיד: מחיר אמריקאי + פרמיית מימוש מוקדם מול אירופאי
# ---------------------------------------------------------------------------
def american_price(
    S, K, T, r, sigma, kind="call", q=0.0, dividends=None,
    method="crr", steps=200, n=10000,
):
    """מחזיר dict עם המחיר האמריקאי, האירופאי, ופרמיית המימוש המוקדם.

    method: "crr" (ברירת מחדל, מהיר) או "lsm".
    """
    euro = bs_price(S, K, T, r, sigma, kind, q=q if not dividends else 0.0)
    # אם יש דיבידנדים בדידים, גם האירופאי צריך להתחשב בהם (escrowed)
    if dividends:
        pv_div = _pv_discrete_dividends(float(S), float(T), float(r), dividends)
        euro = bs_price(max(float(S) - pv_div, 1e-9), K, T, r, sigma, kind, q=0.0)

    if method == "lsm":
        amer = lsm_price(S, K, T, r, sigma, kind, q=q, n=n,
                         steps=min(steps, 60), dividends=dividends)
    else:
        amer = binomial_crr(S, K, T, r, sigma, kind, q=q, steps=steps,
                            american=True, dividends=dividends)

    # המחיר האמריקאי לעולם לא נמוך מהאירופאי (זכות נוספת). מצמצמים רעש מספרי.
    amer = max(amer, euro)
    premium = amer - euro
    return {
        "american": amer,
        "european": euro,
        "early_exercise_premium": premium,
        "early_exercise_premium_pct": (premium / euro * 100.0) if euro > 1e-9 else 0.0,
        "method": method,
        "steps": steps if method == "crr" else min(steps, 60),
    }


# ---------------------------------------------------------------------------
# 4. שכבת החלטה: "רק כשמשתלם" — מתי בכלל להפעיל את המנוע האמריקאי
# ---------------------------------------------------------------------------
def should_use_american(
    S, K, kind, q=0.0, dividends=None,
    atm_band=0.05, deep_itm_band=0.15, div_yield_floor=0.005,
):
    """מחזיר (bool, reason_he). מפעילים את התמחור האמריקאי רק כאשר פער המימוש
    המוקדם עשוי להיות משמעותי, כדי לשמור על מהירות הסורק וזיכרון Render:

      * מניה שמחלקת דיבידנד מהותי (q מעל הרצפה, או דיבידנדים בדידים) — CALLs.
      * אופציה קרובה לכסף (ATM, בתוך atm_band).
      * אופציה עמוק בתוך הכסף (Deep ITM, מעבר ל-deep_itm_band) — בעיקר PUTs.
    אחרת — Black-Scholes האירופאי מספיק (ומהיר).
    """
    S = float(S); K = float(K)
    has_div = bool(dividends) or (q is not None and float(q) >= div_yield_floor)

    moneyness = (K - S) / S if kind == "call" else (S - K) / S  # >0 = OTM
    dist = abs(S - K) / S

    # קרוב לכסף
    if dist <= atm_band:
        return True, "אופציה קרובה לכסף (ATM) — פער המימוש המוקדם עשוי להיות מהותי"

    # עמוק בתוך הכסף
    in_the_money = (S > K) if kind == "call" else (S < K)
    if in_the_money and dist >= deep_itm_band:
        if kind == "put":
            return True, "PUT עמוק בתוך הכסף — מימוש מוקדם לרוב אופטימלי (ערך זמן שלילי)"
        if has_div:
            return True, "CALL עמוק בתוך הכסף על מניית דיבידנד — סיכון מימוש לפני אקס-דיבידנד"

    # דיבידנד מהותי על CALL
    if kind == "call" and has_div:
        return True, "CALL על מניית דיבידנד — מימוש מוקדם אפשרי לפני אקס-דיבידנד"

    return False, "אירופאי (Black-Scholes) מספיק — פער מימוש מוקדם זניח"
