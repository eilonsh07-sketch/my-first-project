# OptionDesk — Project Context

## מה זה
כלי **decision-support** לניתוח אופציות על US securities, עבור יועץ השקעות בבנק מזרחי-טפחות.
הכלי מציג ניתוח ונתונים — לעולם לא מקבל החלטות או ממליץ אוטומטית.

## 5 חוקי ברזל (לעולם לא לפרוץ)
1. **Decision-support בלבד** — כל output חייב לכלול disclaimer. אין המלצות אוטומטיות.
2. **Secrets ב-.env בלבד** — ANTHROPIC_API_KEY, מפתחות API — לא בקוד, לא בצאט.
3. **Push לGitHub בכל milestone** — `https://github.com/eilonsh07-sketch/my-first-project`
4. **אין .claude/ בתוך הפרויקט** — כל skills/plugins גלובליים ב-`C:\Users\yuval\.claude\`
5. **pricing.py — אסור לגעת** — BSM, Greeks, Monte Carlo — מאומת ועובד, לא לשנות.

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
