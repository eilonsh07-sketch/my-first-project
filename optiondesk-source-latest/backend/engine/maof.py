"""
maof.py — מנוע סורק אופציות מעו"ף על מדד ת"א-35 (TA-35) בלבד.

יש אופציות מעו"ף רק על מדד ת"א-35. המנוע:
  1. מושך ספוט ת"א-35 והיסטוריה יומית (Yahoo: TA35.TA).
  2. אומד תנודתיות:
       - σ עוגן = VTA35 (ה-VIX הישראלי, פרסום הבורסה). ברירת מחדל ~22.8%.
       - מתאם מבנה-זמן (term structure) לכל פקיעה לפי צורת התנודתיות הממומשת.
       - override ידני לכל אופציה (המשתמש יכול להזין IV מגלובס).
  3. בונה רשת מחירי-מימוש × פקיעות ומתמחר כל call ו-put ב-Black-Scholes-Merton
     מלא (r שקלי = 3.75%, q = דיבידנד ת"א-35 ≈ 2%) — ללא פישוטים.
  4. PoP מבוסס-היסטוריה: drift ריאלי (מנצח בתיקוף על מדד מפוזר — Brier 0.113,
     שגיאת כיול 0.013). מציג גם PoP ניטרלי-סיכון לצד זה לשקיפות.
  5. ציון משולב מאוזן (EV + PoP היסטורי + סיכון/Kelly) ובוחר את האופציה
     הטובה ביותר לרכישה — call או put.

הבסיס המדעי לבחירת drift: ראה maof_validation.py ו-maof_validation_results.json.
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta

import numpy as np

from . import pricing as P

# ---------------------------------------------------------------------------
# קבועי שוק (ישראל)
# ---------------------------------------------------------------------------
R_ILS = 0.0375          # ריבית חסרת-סיכון שקלית — בנק ישראל (הופחת ל-3.75% ב-25/05/2026)
Q_DIV_TA35 = 0.02       # תשואת דיבידנד ת"א-35 ≈ 2%
VTA35_DEFAULT = 0.228   # ערך VTA35 ברירת מחדל (ה-VIX הישראלי) — 22.8%
CONTRACT_MULT = 100     # מכפיל חוזה מעו"ף (₪ לנקודת מדד) — מוצג למשתמש
TRADING_DAYS = 252

# פרמטרי תיקוף שמנצחים על מדד מפוזר (מתוך מחקר התיקוף)
DRIFT_LOOKBACK_DAYS = 120   # חלון אמידת drift ריאלי
RV_LOOKBACK_DAYS = 60       # חלון תנודתיות ממומשת לתיקון מבנה-זמן
# הגבלת ה-drift הריאלי כדי שיודיע אך לא יטעה: drift קיצוני בחלון מגמתי
# מנפח אופציות עמוק-בתוך-הכסף. מגבילים לטווח ריאלי שנתי ±15% ומכווצים
# חצי לכיוון אפס (shrinkage) — שמרני, כמתחייב מדרישת 'שלא יטעה בהחלטה'.
DRIFT_CAP = 0.15            # תקרת/רצפת drift שנתי (±15%)
DRIFT_SHRINK = 0.5          # כיווץ לעבר 0 (חצי)

# מגבלות סינון (כמו בסורק האמריקאי, מותאם למדד)
MAX_OTM_PCT = 0.25          # מקסימום מרחק מחיר-מימוש מהספוט
MIN_PREMIUM = 0.05          # פרמיה מינימלית בנקודות מדד
MAX_SIGMA_MOVE = 2.5        # מקסימום סטיות-תקן עד נקודת איזון
N_MC = 12000                # מספר נתיבי מונטה-קרלו
SHORT_DTE_DAYS = 10         # מתחת ל-DTE זה (שבועי קרוב) מסמנים את ה-PoP כפחות-יציב


# ---------------------------------------------------------------------------
# אמידת תנודתיות ו-drift מההיסטוריה
# ---------------------------------------------------------------------------
def _realized_vol(close: np.ndarray, window: int) -> float:
    """תנודתיות ממומשת שנתית מתוך תשואות לוג יומיות."""
    if len(close) < window + 1:
        window = max(2, len(close) - 1)
    rets = np.diff(np.log(close[-(window + 1):]))
    if len(rets) < 2:
        return VTA35_DEFAULT
    return float(np.std(rets, ddof=1) * math.sqrt(TRADING_DAYS))


def _real_drift(close: np.ndarray, window: int = DRIFT_LOOKBACK_DAYS) -> float:
    """drift ריאלי שנתי — שיפוע התשואות הלוג על פני החלון.

    זהו ה'מנוף' החזוי שניצח בתיקוף על מדד ת"א-35 (לעומת drift ניטרלי-סיכון).
    מחושב מתשואת התקופה הכוללת, ממוצעת לשנה.
    """
    if len(close) < window + 1:
        window = max(2, len(close) - 1)
    seg = close[-(window + 1):]
    total_log_ret = math.log(seg[-1] / seg[0])
    years = len(seg[:-1]) / TRADING_DAYS
    if years <= 0:
        return 0.0
    raw = total_log_ret / years
    # כיווץ (shrinkage) לעבר אפס ואז הגבלה לטווח ריאלי — מונע מ-drift קיצוני
    # בחלון מגמתי לנפח אופציות עמוק-ITM ולהטעות את ההחלטה.
    shrunk = raw * DRIFT_SHRINK
    return float(max(-DRIFT_CAP, min(DRIFT_CAP, shrunk)))


def _term_adjusted_iv(anchor_iv: float, close: np.ndarray, dte: int) -> float:
    """מתאם את ה-IV העוגן (VTA35, ~30 יום) למבנה-זמן לכל פקיעה.

    VTA35 משקף IV ל-30 יום. לאופקים שונים מתקנים לפי היחס בין התנודתיות
    הממומשת קצרת-הטווח לארוכת-הטווח (proxy לשיפוע מבנה-הזמן). שמרני —
    התיקון מוגבל ל-±35% כדי לא להטעות.
    """
    if anchor_iv <= 0:
        anchor_iv = VTA35_DEFAULT
    rv_short = _realized_vol(close, 21)
    rv_long = _realized_vol(close, 63)
    if rv_short <= 0 or rv_long <= 0:
        return anchor_iv
    # שיפוע: אם קצר-טווח > ארוך-טווח → מבנה יורד (אופקים ארוכים זולים יותר)
    slope = rv_long / rv_short  # >1 כשטווח ארוך תנודתי יותר
    # אינטרפולציה לוגית סביב 30 יום
    horizon_factor = (dte / 30.0) ** (0.5 * math.log(max(slope, 1e-6)) / math.log(2))
    horizon_factor = max(0.65, min(1.35, horizon_factor))
    return float(anchor_iv * horizon_factor)


# ---------------------------------------------------------------------------
# PoP — שתי שיטות, זו מול זו (שקיפות)
# ---------------------------------------------------------------------------
def _pop_analytic(S, K, T, sigma, kind, drift):
    """P(תפוג בתוך הכסף) אנליטית = N(d2) לפי ה-drift הנתון.
    drift=R_ILS → ניטרלי-סיכון ; drift=μ ריאלי → מבוסס-היסטוריה."""
    if T <= 0 or sigma <= 0:
        return None
    d2 = (math.log(S / K) + (drift - Q_DIV_TA35 - 0.5 * sigma * sigma) * T) / (sigma * math.sqrt(T))
    return float(P.norm.cdf(d2)) if kind == "call" else float(P.norm.cdf(-d2))


# ---------------------------------------------------------------------------
# ציון משולב מאוזן לרכישה
# ---------------------------------------------------------------------------
def _combined_score(mc_early, ev_norm, pop_hist, sigma_move, liq=0.7):
    """ציון 0-100 לרכישת אופציית מעו"ף. שקלול מאוזן לפי דרישת המשתמש:

      ערך תוחלת (EV מנורמל לפרמיה) ..... 35   — מוביל; ההטיה החיובית האמיתית
      PoP מבוסס-היסטוריה (drift ריאלי) . 25   — הסטטיסטיקה שמנצחת בתיקוף
      יחס סיכון/סיכוי (Kelly) .......... 20   — גודל פוזיציה אופטימלי
      נזילות ........................... 12   — ספרד/OI (מוערך למדד)
      השגיוּת (sigma_move) ............. 8    — כמה סטיות-תקן עד איזון

    EV מוביל (כמו בסורק האמריקאי), אבל ה-PoP כאן מבוסס על drift ריאלי
    שהוכח בתיקוף ההיסטורי כמנבא הטוב ביותר על מדד ת"א-35 — ולכן מקבל
    משקל מהותי (25) ולא מוגבל ל-20 כמו במניות בודדות.
    """
    score = 0.0
    # EV מנורמל לפרמיה (35)
    score += 35 * max(0.0, min(1.0, (ev_norm + 0.5) / 1.5))
    # PoP מבוסס-היסטוריה (25)
    if pop_hist is not None:
        score += 25 * pop_hist
    else:
        score += 12.5
    # Kelly / סיכון-סיכוי (20)
    kelly = _kelly_from_mc(mc_early)
    score += 20 * min(1.0, kelly / 0.25)  # half-Kelly מנורמל לתקרה 25%
    # נזילות (12)
    score += 12 * liq
    # השגיות (8)
    if sigma_move is not None:
        score += 8 * max(0.0, 1.0 - min(sigma_move / MAX_SIGMA_MOVE, 1.0))
    else:
        score += 4.0
    return round(max(0.0, min(100.0, score)), 1), round(kelly, 4)


def _kelly_from_mc(mc):
    p = mc.get("prob_profit_early", mc.get("prob_profit", 0.0))
    ev = mc.get("expected_pnl_pct_early", mc.get("expected_pnl_pct", -1.0))
    if p <= 0 or p >= 1 or ev <= -0.99:
        return 0.0
    b = (ev + (1 - p)) / p
    if b <= 0:
        return 0.0
    f = (b * p - (1 - p)) / b
    return max(0.0, min(0.25, f * 0.5))  # half-Kelly capped 25%


# ---------------------------------------------------------------------------
# פקיעות מעו"ף — סדרות חודשיות (פקיעה ביום חמישי האחרון לפני סוף החודש)
# ---------------------------------------------------------------------------
def _last_thursday(year: int, month: int):
    """יום חמישי האחרון בחודש — מועד פקיעת מעו"ף החודשי."""
    if month == 12:
        nxt = datetime(year + 1, 1, 1)
    else:
        nxt = datetime(year, month + 1, 1)
    d = nxt - timedelta(days=1)
    while d.weekday() != 3:  # 3 = חמישי
        d -= timedelta(days=1)
    return d


def _upcoming_monthlies(today: datetime, n: int = 4):
    """n הפקיעות החודשיות הקרובות של מעו"ף (חמישי אחרון בחודש)."""
    out = []
    y, m = today.year, today.month
    while len(out) < n + 1:
        exp = _last_thursday(y, m)
        if exp.date() > today.date():
            out.append(exp)
        m += 1
        if m > 12:
            m = 1; y += 1
    return out[:n]


def _upcoming_thursdays(today: datetime, n: int = 6):
    """n ימי חמישי הקרובים — מועדי פקיעת מעו"ף השבועי (כל חמישי)."""
    out = []
    d = today
    # מתקדמים ליום החמישי הקרוב (לא כולל היום אם כבר עבר)
    while len(out) < n:
        d = d + timedelta(days=1)
        if d.weekday() == 3:  # חמישי
            out.append(datetime(d.year, d.month, d.day))
    return out


def _maof_expiries(today: datetime, n_weeks: int = 6, n_months: int = 4):
    """רשימת פקיעות מעו"ף משולבת: שבועיות (כל חמישי) + חודשיות (חמישי אחרון).

    מחזיר רשימת (datetime, type) כש-type הוא 'weekly' או 'monthly'.
    אם תאריך מופיע גם כשבועי וגם כחודשי (החמישי האחרון בחודש) — מסומן כחודשי
    (הפקיעה החודשית היא הנזילה והמשמעותית יותר).
    """
    monthlies = {e.date(): e for e in _upcoming_monthlies(today, n_months)}
    weeklies = {e.date(): e for e in _upcoming_thursdays(today, n_weeks)}
    merged = {}
    for dt, e in weeklies.items():
        merged[dt] = (e, "weekly")
    for dt, e in monthlies.items():
        merged[dt] = (e, "monthly")  # חודשי גובר על שבועי באותו תאריך
    return [merged[k] for k in sorted(merged.keys())]


# ---------------------------------------------------------------------------
# המנוע הראשי
# ---------------------------------------------------------------------------
def scan_maof(spot: float, close_hist: np.ndarray, *,
              anchor_iv: float | None = None,
              iv_override: float | None = None,
              strike_step_pct: float = 0.025,
              n_strikes: int = 9,
              today: datetime | None = None):
    """סורק את כל רשת אופציות מעו"ף (call+put) ומחזיר מדורג + הטובות ביותר.

    spot         — ערך מדד ת"א-35 הנוכחי
    close_hist   — מערך מחירי סגירה יומיים (לפחות ~130 ימים) לאמידת σ ו-drift
    anchor_iv    — IV עוגן (VTA35) כשבר עשרוני; ברירת מחדל VTA35_DEFAULT
    iv_override  — IV אחיד שמכריח על כל הרשת (מגלובס למשל); גובר על העוגן
    """
    today = today or datetime.now()
    anchor = float(anchor_iv) if anchor_iv else VTA35_DEFAULT
    mu_real = _real_drift(close_hist)
    rv60 = _realized_vol(close_hist, RV_LOOKBACK_DAYS)

    # שבועיות (כל חמישי) + חודשיות (חמישי אחרון)
    expiries = _maof_expiries(today, n_weeks=6, n_months=4)
    results = []

    for exp, exp_type in expiries:
        dte = (exp.date() - today.date()).days
        if dte <= 0:
            continue
        # ב-DTE זעיר (שבועי מאוד) ה-PoP ההיסטורי פחות יציב סטטיסטית — מסמנים
        short_dte = dte < SHORT_DTE_DAYS
        T = dte / 365.0
        # IV לפקיעה: override ידני > עוגן מתואם-מבנה-זמן
        if iv_override and iv_override > 0:
            sigma = float(iv_override)
            iv_source = "override ידני"
        else:
            sigma = _term_adjusted_iv(anchor, close_hist, dte)
            iv_source = f"VTA35 מתואם-זמן ({anchor*100:.1f}% → {sigma*100:.1f}%)"

        # רשת מחירי-מימוש סביב הספוט
        for j in range(-(n_strikes // 2), n_strikes // 2 + 1):
            K = round(spot * (1 + j * strike_step_pct))
            if K <= 0:
                continue
            otm_pct = abs(K - spot) / spot
            if otm_pct > MAX_OTM_PCT:
                continue

            for kind in ("call", "put"):
                premium = P.bs_price(spot, K, T, R_ILS, sigma, kind, Q_DIV_TA35)
                if premium < MIN_PREMIUM:
                    continue
                greeks = P.bs_greeks(spot, K, T, R_ILS, sigma, kind, Q_DIV_TA35)

                # PoP — שתי שיטות זו מול זו
                pop_neutral = _pop_analytic(spot, K, T, sigma, kind, R_ILS)
                pop_hist = _pop_analytic(spot, K, T, sigma, kind, mu_real)

                # מונטה-קרלו עם יציאה לפני פקיעה (ברירת מחדל: נמכרת לפני פקיעה)
                # drift ריאלי — השיטה שמנצחת בתיקוף על מדד מפוזר
                mc_early = P.monte_carlo_option_early(
                    spot, K, T, R_ILS, sigma, premium, kind=kind,
                    q=Q_DIV_TA35, mu=mu_real, n=N_MC, steps=max(20, min(dte, 60)))
                mc_term = P.monte_carlo_option(
                    spot, K, T, R_ILS, sigma, premium, kind=kind,
                    q=Q_DIV_TA35, mu=mu_real, n=N_MC)

                # EV מנורמל לפרמיה (מתוך התרחיש בו נמכרת לפני פקיעה)
                exp_max = mc_early.get("expected_max_value", premium)
                ev_norm = (exp_max - premium) / max(premium, 1e-9)

                # נקודת איזון ומרחק בסטיות-תקן
                if kind == "call":
                    breakeven = K + premium
                else:
                    breakeven = K - premium
                move_needed = abs(breakeven - spot) / spot
                sigma_move = move_needed / (sigma * math.sqrt(T)) if (sigma > 0 and T > 0) else None

                score, kelly = _combined_score(
                    {"prob_profit_early": mc_early.get("prob_hit_target_early", 0.0),
                     "expected_pnl_pct_early": ev_norm},
                    ev_norm, pop_hist, sigma_move)

                results.append({
                    "kind": kind,
                    "kind_he": "CALL (רכש)" if kind == "call" else "PUT (מכר)",
                    "strike": K,
                    "expiry": exp.strftime("%Y-%m-%d"),
                    "expiry_type": exp_type,
                    "expiry_type_he": "שבועי" if exp_type == "weekly" else "חודשי",
                    "short_dte": short_dte,
                    "dte": dte,
                    "premium": round(premium, 3),
                    "premium_ils": round(premium * CONTRACT_MULT, 1),
                    "iv": round(sigma, 4),
                    "iv_pct": round(sigma * 100, 2),
                    "iv_source": iv_source,
                    "moneyness_pct": round((K - spot) / spot * 100, 2),
                    "delta": round(greeks["delta"], 4),
                    "gamma": round(greeks["gamma"], 6),
                    "theta": round(greeks["theta"], 4),
                    "vega": round(greeks["vega"], 4),
                    "pop_historical": round(pop_hist, 4) if pop_hist is not None else None,
                    "pop_risk_neutral": round(pop_neutral, 4) if pop_neutral is not None else None,
                    "breakeven": round(breakeven, 2),
                    "sigma_move": round(sigma_move, 3) if sigma_move is not None else None,
                    "ev_norm": round(ev_norm, 4),
                    "expected_max_value": round(exp_max, 3),
                    "prob_profit_early": round(mc_early.get("prob_hit_target_early", 0.0), 4),
                    "expected_pnl_pct_hold": round(mc_term.get("expected_pnl_pct", 0.0), 4),
                    "kelly": kelly,
                    "score": score,
                })

    results.sort(key=lambda x: x["score"], reverse=True)
    best_call = next((r for r in results if r["kind"] == "call"), None)
    best_put = next((r for r in results if r["kind"] == "put"), None)
    best_overall = results[0] if results else None

    return {
        "spot": round(spot, 2),
        "anchor_iv_pct": round(anchor * 100, 2),
        "iv_override_pct": round(iv_override * 100, 2) if iv_override else None,
        "real_drift_annual_pct": round(mu_real * 100, 2),
        "realized_vol_60d_pct": round(rv60 * 100, 2),
        "r_ils_pct": round(R_ILS * 100, 2),
        "q_div_pct": round(Q_DIV_TA35 * 100, 2),
        "contract_mult": CONTRACT_MULT,
        "n_options": len(results),
        "n_weekly": sum(1 for r in results if r["expiry_type"] == "weekly"),
        "n_monthly": sum(1 for r in results if r["expiry_type"] == "monthly"),
        "best_overall": best_overall,
        "best_call": best_call,
        "best_put": best_put,
        "best_weekly": next((r for r in results if r["expiry_type"] == "weekly"), None),
        "best_monthly": next((r for r in results if r["expiry_type"] == "monthly"), None),
        "ranked": results[:50],
        "validation": {
            "method_he": "PoP מבוסס drift ריאלי — נבחר לאחר תיקוף היסטורי (walk-forward) על ת\"א-35",
            "brier": 0.113,
            "calib_err": 0.013,
            "note_he": "ה-drift הריאלי ניצח על מדד מפוזר (ת\"א-35). על מניות בודדות אמריקאיות נשארת שיטה ניטרלית-סיכון.",
        },
        "as_of": today.isoformat(),
        "note_he": "אופציות מעו\"ף קיימות רק על מדד ת\"א-35. תמחור Black-Scholes-Merton מלא (r שקלי, q דיבידנד). ברירת המחדל: האופציה נמכרת לפני פקיעה. לא ייעוץ השקעות.",
    }
