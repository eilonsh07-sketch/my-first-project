# Initial Product Audit — OptionDesk
**Date**: 2026-06-15
**Stage**: Post-clarify · Pre-plan
**Auditors**: SIGMA, MAX, GUARDIAN, KEYNES (simulated)

---

## SIGMA — ממצאים

### ✅ בסיס חזק
- `pricing.py` — BS מלא עם `q`, Vanna, Charm, American CRR (200 steps), `monte_carlo_option_early` עם BS repricing בכל צעד
- `implied_vol` — Newton + bisection fallback, robust
- Hard filters (anti-casino) מתועדים ומוצדקים

### 🚨 פערים קריטיים
- `strategies.py` — רק 3 אסטרטגיות: Long Call, Bull Spread, Ratio Spread. חסרים: Iron Condor, Covered Call, CSP, Straddle, LEAPS, Credit Spread, Protective Put. המוצר long-biased בלבד.
- `RISK_FREE = 0.045` — קבוע בקוד ב-scoring.py, strategies.py, pricing.py. לא מחובר ל-KEYNES/FRED.

### ⚠️ מפוקפק
- Bull Spread width = 8% מהמחיר — שרירותי, לא מוכח
- `target_return = 1.30` — +30% ברירת מחדל, ללא הצדקה
- `iv_source = "yahoo"` — מחרוזת ישנה אחרי מיגרציה ל-Polygon

### 🔬 MAX צריך לאמת
| פרמטר | ערך נוכחי |
|--------|-----------|
| `MAX_OTM_PCT` | 40% |
| `MAX_DTE` | 183 יום |
| `MIN_PREMIUM` | $0.10 |
| `target_return` | 1.30 |
| Bull Spread width | 8% |

---

## MAX — ממצאים

### ✅ בסיס חזק
- `_option_score()` — משקולות מתועדות עם הסבר הגיוני לכל משקל
- `cvar5` מחושב ב-MC — נכון סטטיסטית
- `_hold_to_expiry()` — לוגיקת שמירה/מכירה קיימת

### ⚠️ מפוקפק
- כיול משקולות: "160-option live sensitivity study" — ניתוח קורלציה, לא backtest. דרוש אימות על אלפי עסקאות היסטוריות.
- Monte Carlo drift: `mu=None` → risk-neutral (4.5%). הסתברויות אמיתיות דורשות real-world drift. מי מגדיר `mu`? לא תמיד מועבר.
- `_kelly()` — `b` מוערך מ-EV, לא מנתוני win/loss אמיתיים. Half-Kelly שמרני ונכון, אבל קלט לא מדויק.

### 🔬 משימות לאימות (סדר עדיפות)
1. Backtest Option Score — האם ציון גבוה מנבא תשואה גבוהה? (p-value)
2. בדיקת רגישות MAX_OTM_PCT (30%/40%/50%)
3. מקור real-world drift `mu` — ממוצע היסטורי? SPY return?

---

## GUARDIAN — ממצאים

### 🚨 קריטי
- `scenarios.py` — כל המודול עבור **ת"א-35 ישראלי**: VTA35, תרחישי 7.10, ירי איראני. **לא US options**. דורש כתיבה מחדש לשוק אמריקאי.
- אין תרחישי קיצון לשוק האמריקאי: crash -20%, VIX→60, ריבית +150bp
- אין portfolio-level risk — כל המערכת per-trade בלבד, ללא אגרגציה

### ⚠️ מפוקפק
- `RISK_FREE` קבוע — GUARDIAN לא מקבל ריבית חיה מ-KEYNES
- Liquidity score weights (50/30/20) — ללא כיול אמפירי
- אין VaR/max drawdown monitoring ברמת תיק

---

## KEYNES — ממצאים

### ✅ בסיס חזק
- `economist.py` ממוגרן ל-Polygon (I:VIX, SPY) + FRED (DGS10, DTB3, DFF) ✅
- VRP (IV-RV) מחושב ומפורש — בסיס תיאורטי מוצק
- סיווג משטר 4 רמות VIX + עקום תשואות — בסיס טוב

### 🚨 קריטי
- **KEYNES מנותק לחלוטין מ-scoring**: `scoring.py` לא מייבא ולא משתמש בשום דבר מ-`economist.py`. שני המודולים רצים במקביל ללא חיבור.
- דוגמה: VIX=45 → KEYNES: "הזדמנות למוכרי פרמיה" → scoring.py: ממשיך לתת ציון גבוה לקוני calls.

### ⚠️ מפוקפק
- `RISK_FREE = 0.045` בכל הקבצים — לא מחובר ל-`DFF`
- CPI/אינפלציה — לא קיים עדיין
- Regime לא מועבר ל-SIGMA וללנ-LENS

---

## סיכום עדיפויות

### 🚨 לתקן לפני בנייה
| # | ממצא | קובץ |
|---|------|------|
| 1 | `scenarios.py` — ישראלי, לא US | scenarios.py |
| 2 | KEYNES מנותק מ-scoring | economist.py ↔ scoring.py |
| 3 | `RISK_FREE` קבוע | scoring.py, strategies.py |
| 4 | אסטרטגיות חסרות (Iron Condor, CSP, Straddle...) | strategies.py |

### ⚠️ MAX יאמת בשבוע 2
- משקולות Option Score (35/20/15/10/12/8)
- `target_return`, `MAX_OTM_PCT`, `MAX_DTE`, Bull Spread width
- Real-world drift `mu`

### ✅ לא לגעת
- `pricing.py` כולו
- American pricing (CRR)
- `monte_carlo_option_early`
- Hard filters logic
