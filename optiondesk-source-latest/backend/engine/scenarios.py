"""
scenarios.py — מודול תרחישים גיאופוליטיים לאופציות מעו"ף (ת"א-35).

מתמחר מחדש אופציה תחת הלם גיאופוליטי: שילוב של (א) זעזוע מחיר למדד ת"א-35
ו-(ב) קפיצת תנודתיות גלומה (VTA35). שתי הכוחות האלה הם מה שמשפיע על מחזיק
אופציה באירוע גיאופוליטי. כל התרחישים מכוילים על קפיצות IV היסטוריות אמיתיות
(ראה geopolitical_research.md ו-geopolitical_empirical_results.json).

תמחור Black-Scholes-Merton מלא — ללא פישוטים (r שקלי, q דיבידנד).
ברירת המחדל: האופציה נמכרת באירוע (לא מוחזקת לפקיעה).
"""
from __future__ import annotations

from datetime import datetime

from . import pricing as P
from .maof import R_ILS, Q_DIV_TA35, CONTRACT_MULT, VTA35_DEFAULT

# ---------------------------------------------------------------------------
# תרחישי הלם מכוילים על אירועים היסטוריים אמיתיים (2020-2025)
# spot_shock — שינוי מיידי במדד ת"א-35 (שבר עשרוני, שלילי=ירידה)
# vta35_to   — רמת VTA35 (IV) שאליה קופצת התנודתיות (נקודות = אחוזים)
# ---------------------------------------------------------------------------
SCENARIOS = [
    {
        "id": "calm",
        "name_he": "רגוע (מצב נוכחי)",
        "desc_he": "ללא אירוע — תמחור לפי השוק הנוכחי",
        "spot_shock": 0.0,
        "vta35_to": None,          # נשאר ברמת ה-IV הנוכחית
        "example_he": "מצב בסיס להשוואה",
        "tone": "good",
    },
    {
        "id": "mild",
        "name_he": "מתון",
        "desc_he": "מבצע מוגבל / ירי רקטות מקומי ללא פריצת מלחמה",
        "spot_shock": -0.025,      # -2.5%
        "vta35_to": 0.21,          # VTA35 → 21
        "example_he": "דמוי מבצע שומר חומות (מאי 2021)",
        "tone": "warn",
    },
    {
        "id": "moderate",
        "name_he": "מתון-חמור",
        "desc_he": "מתקפת ירי ישירה מאיראן שמיורטת ברובה",
        "spot_shock": -0.05,       # -5%
        "vta35_to": 0.26,          # VTA35 → 26
        "example_he": "אפריל 2024 / אוקטובר 2024 (ירי איראני)",
        "tone": "warn",
    },
    {
        "id": "severe",
        "name_he": "חמור",
        "desc_he": "פרוץ מלחמה מפתיעה, אי-ודאות קיצונית",
        "spot_shock": -0.085,      # -8.5%
        "vta35_to": 0.30,          # VTA35 → 30 (שיא גיאופוליטי 7.10)
        "example_he": "7 באוקטובר 2023 (קפיצת VTA35 של ~110%)",
        "tone": "bad",
    },
    {
        "id": "extreme",
        "name_he": "קיצוני (Tail Risk)",
        "desc_he": "פגיעה רחבה בתשתיות / משבר מערכתי",
        "spot_shock": -0.18,       # -18%
        "vta35_to": 0.50,          # VTA35 → 50
        "example_he": "ללא תקדים גיאופוליטי ישראלי (COVID הגיע ל-85)",
        "tone": "bad",
    },
    {
        "id": "relief",
        "name_he": "הקלה / 'חיסון'",
        "desc_he": "השוק 'מתמחר מראש' וקופץ למרות הסלמה",
        "spot_shock": 0.03,        # +3%
        "vta35_to": 0.20,          # VTA35 → 20 (יורד עם הוודאות)
        "example_he": "יוני 2025 (ת\"א-35 +5.2% בשבוע מלחמה!)",
        "tone": "good",
    },
]


def _years_to_expiry(expiry_str: str, today: datetime | None = None) -> float:
    today = today or datetime.now()
    exp = datetime.strptime(expiry_str, "%Y-%m-%d")
    return max((exp.date() - today.date()).days, 0) / 365.0


def price_option_under_scenarios(spot: float, strike: float, expiry: str, kind: str,
                                 current_iv: float, entry_premium: float | None = None,
                                 today: datetime | None = None,
                                 expiry_type: str | None = None):
    """מתמחר אופציה בודדת תחת כל התרחישים.

    spot          — מדד ת"א-35 נוכחי
    strike        — מחיר מימוש
    expiry        — תאריך פקיעה 'YYYY-MM-DD'
    kind          — 'call' / 'put'
    current_iv    — IV נוכחי (שבר עשרוני)
    entry_premium — פרמיית כניסה; אם None, מחושבת BSM לפי ה-IV הנוכחי

    מחזיר לכל תרחיש: ספוט הלם, IV הלם, פרמיה חדשה, רווח/הפסד מהכניסה.
    הזמן לפקיעה מתקצר ביום מסחר אחד תחת ההלם (אירוע מתרחש מחר).
    """
    today = today or datetime.now()
    T0 = _years_to_expiry(expiry, today)
    if entry_premium is None:
        entry_premium = P.bs_price(spot, strike, T0, R_ILS, current_iv, kind, Q_DIV_TA35)
    entry_premium = max(entry_premium, 1e-6)

    # ההלם מתרחש "מחר" → יום מסחר אחד פחות לפקיעה
    T1 = max(T0 - (1.0 / 365.0), 1e-6)

    rows = []
    for sc in SCENARIOS:
        shocked_spot = spot * (1 + sc["spot_shock"])
        shocked_iv = sc["vta35_to"] if sc["vta35_to"] is not None else current_iv
        new_premium = P.bs_price(shocked_spot, strike, T1, R_ILS, shocked_iv, kind, Q_DIV_TA35)
        new_greeks = P.bs_greeks(shocked_spot, strike, T1, R_ILS, shocked_iv, kind, Q_DIV_TA35)
        pnl = new_premium - entry_premium
        pnl_pct = (new_premium / entry_premium - 1.0)
        rows.append({
            "id": sc["id"],
            "name_he": sc["name_he"],
            "desc_he": sc["desc_he"],
            "example_he": sc["example_he"],
            "tone": sc["tone"],
            "spot_shock_pct": round(sc["spot_shock"] * 100, 1),
            "shocked_spot": round(shocked_spot, 1),
            "vta35_to_pct": round(shocked_iv * 100, 1),
            "iv_jump_pct": round((shocked_iv / current_iv - 1) * 100, 1) if current_iv > 0 else None,
            "new_premium": round(new_premium, 3),
            "new_premium_ils": round(new_premium * CONTRACT_MULT, 1),
            "pnl": round(pnl, 3),
            "pnl_ils": round(pnl * CONTRACT_MULT, 1),
            "pnl_pct": round(pnl_pct * 100, 1),
            "new_delta": round(new_greeks["delta"], 4),
        })

    return {
        "option": {
            "kind": kind,
            "kind_he": "CALL (רכש)" if kind == "call" else "PUT (מכר)",
            "strike": strike,
            "expiry": expiry,
            "expiry_type": expiry_type,
            "expiry_type_he": ("שבועי" if expiry_type == "weekly" else "חודשי") if expiry_type else None,
            "current_iv_pct": round(current_iv * 100, 2),
            "entry_premium": round(entry_premium, 3),
            "entry_premium_ils": round(entry_premium * CONTRACT_MULT, 1),
            "dte": int(round(T0 * 365)),
        },
        "spot": round(spot, 1),
        "r_ils_pct": round(R_ILS * 100, 2),
        "q_div_pct": round(Q_DIV_TA35 * 100, 2),
        "vta35_default_pct": round(VTA35_DEFAULT * 100, 1),
        "scenarios": rows,
        "as_of": today.isoformat(),
        "note_he": ("תרחישים מכוילים על קפיצות IV היסטוריות אמיתיות של VTA35 (ה-VIX הישראלי) "
                    "באירועים גיאופוליטיים 2020-2025. כל אירוע משלב זעזוע מחיר למדד ת\"א-35 "
                    "וקפיצת תנודתיות גלומה. תמחור Black-Scholes-Merton מלא. "
                    "הנחה: האופציה נמכרת באירוע, לא מוחזקת לפקיעה. לא ייעוץ השקעות."),
        "insight_he": ("תובנה היסטורית: מאז 7.10.2023 השוק הישראלי 'התחסן' — מתקפות איראניות "
                       "שמיורטות גרמו לנזק קטן מהצפוי, ולעיתים אף לעליות (יוני 2025). "
                       "PUT מגן מפני זעזוע מחיר, אך קפיצת ה-IV מנפחת גם CALL וגם PUT."),
    }
