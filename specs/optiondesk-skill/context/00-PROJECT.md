# OptionDesk — Project Context

## מה זה
כלי **decision-support** לניתוח אופציות על US securities, עבור יועץ השקעות בבנק מזרחי-טפחות.
הכלי מציג ניתוח ונתונים — לעולם לא מקבל החלטות או ממליץ אוטומטית.

## 6 חוקי ברזל (לעולם לא לפרוץ)
1. **Decision-support בלבד** — כל output חייב לכלול disclaimer. אין המלצות אוטומטיות.
2. **Secrets ב-.env בלבד** — ANTHROPIC_API_KEY, מפתחות API — לא בקוד, לא בצאט.
3. **Push לGitHub בכל milestone** — `https://github.com/eilonsh07-sketch/my-first-project`
4. **אין .claude/ בתוך הפרויקט** — כל skills/plugins גלובליים ב-`C:\Users\yuval\.claude\`
5. **pricing.py — אסור לגעת** — BSM, Greeks, Monte Carlo — מאומת ועובד, לא לשנות.
6. **MAX Gate — שום ציון לא מוצג לפני אימות** — כל ציון מספרי (85/100) וכל סבירות (68%) שמוצגים למשתמש חייבים להתבסס על מודל ש-MAX הוכיח out-of-sample. ציון ללא גיבוי סטטיסטי = אסור להציג.

## חזון ואסטרטגיית פריסה
**שלב 1 (נוכחי):** הכלי נבנה לשימוש אישי של היועץ — הוא משתמש בו בעצמו, מוכיח שהוא מייצר edge אמיתי, ורק אז מציגו להנהלה ומתאים לשימוש רחב יותר.

**מה הכלי מציג:**
- ציונים מספריים (85/100) לכל אסטרטגיה וסטאפ
- סבירויות מבוססות-נתונים ("68% win-rate היסטורי על הסטאפ הזה")
- תרחישי תשואה: best / base / worst case עם סכומים בדולרים
- סריקת בוקר: רשימה מדורגת של רעיונות לסחר

**העיקרון:** שום ציון לא מגיע ל-UI לפני שעבר דרך MAX ואומת. CLARITY לא מייצרת מספרים — היא מסבירה מספרים ש-MAX הוכיח.

## Stack
- **Backend**: Python 3.12, FastAPI, uvicorn (Render/Docker)
- **Frontend**: React 18 + Vite + Tailwind (Vercel)
- **Data**: Polygon.io (primary), yfinance (fallback)
- **AI**: Claude API — `anthropic` package (כבר ב-requirements.txt)
- **Storage**: SQLite (local) / Postgres (production via DATABASE_URL)

## קוד קיים — אל תשנה ללא סיבה
```
backend/engine/
├── pricing.py          ← SACRED (BSM, Greeks, MC)
├── scoring.py          ← patch only (RISK_FREE + regime_multiplier)
├── technicals.py       ← minor update (confidence bounding)
├── fundamentals.py     ← unchanged
├── provider.py         ← unchanged
├── backtest.py         ← enhance (ALPHA/BETA validators)
├── strategies.py       ← expand (5 new strategies)
├── economist.py        ← enhance (regime_multiplier + MacroRegime)
└── scenarios.py        ← REWRITE (TA-35 → US scenarios)
```

## מיקומים
- **קוד backend**: `c:\Users\yuval\Desktop\my-first-project\my-first-project\optiondesk-source-latest\backend\`
- **Plan**: `c:\Users\yuval\Desktop\my-first-project\my-first-project\specs\001-agent-architecture\plan.md`
- **Skills**: `C:\Users\yuval\.claude\skills\optiondesk\`
- **GitHub repo**: `https://github.com/eilonsh07-sketch/my-first-project` (branch: master)

## דד-ליין
**2026-07-05** — פגישה עם סגן מנהל הסקטור, בנק מזרחי-טפחות.
צריך: MIKI (3+ מקורות), MAX (baseline 100+ מניות), CANVAS (10 שקפים), הדגמה חיה.
