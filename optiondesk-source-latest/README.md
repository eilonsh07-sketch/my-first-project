# OptionDesk — מחשבון החלטות השקעה כמותי

אפליקציית RTL בעברית לניתוח מניות ואופציות: תמחור Black-Scholes אמיתי, יוונים מלאים,
סימולציית Monte-Carlo (10,000 תרחישים), ניתוח טכני ופנדמנטלי, וציון אופציה/מומנטום.

## מבנה הפרויקט

```
optiondesk/
├── backend/            FastAPI · Python 3.12 · נתונים מ-yfinance
│   ├── app.py          כל ה-endpoints
│   ├── requirements.txt
│   └── engine/         pricing, scoring, technicals, fundamentals,
│                       strategies, spreads, provider, store
└── frontend/           Vite + React 18 + Tailwind 3 + Recharts (RTL)
    ├── package.json
    └── src/
        ├── App.jsx, api.js, hooks.js, ui.jsx
        └── tabs/        Scanner, Research, Company, Strategy, WhatIf,
                         Pipeline, BottomLine, Ranking, Tracker, Compare, HowItWorks
```

## הרצה מקומית

### Backend (פורט 8000)

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python3 -m uvicorn app:app --host 0.0.0.0 --port 8000
```

בדיקת בריאות: http://localhost:8000/api/health → `{"ok":true,"provider":"yahoo"}`

### Frontend (פורט 5173)

```bash
cd frontend
npm install
npm run dev          # פיתוח
npm run build        # build לפרודקשן -> dist/
```

ב-`src/api.js` כתובת ה-API נופלת אוטומטית ל-`http://localhost:8000` כשמריצים מקומית.

## מסד נתונים (Watchlist / Tracker)

`engine/store.py` הוא pluggable:
- ברירת מחדל: SQLite (קובץ `backend/optiondesk.db`, נוצר אוטומטית).
- אם מוגדר משתנה סביבה `DATABASE_URL` (postgres://...) → משתמש ב-Postgres דרך psycopg.

## ששת השיפורים

1. מעקב והתראות (טאב "מעקב") — שמירה במסד נתונים + snapshots יומיים + sparkline.
2. התראות בוקר — `POST /api/alerts/check` סורק את הרשימה ומחזיר פריטים שחצו סף.
3. ניתוח What-If חי — סליידרים עם עדכון מיידי של תמחור והסתברויות.
4. היסטוגרמת התפלגות Monte-Carlo — 10,000 תרחישים עם קווי איזון/יעד.
5. סורק מורחב — קולים, פוטים, Bull Call Spread, Bear Put Spread.
6. דירוג מניות לטווח ארוך — השוואה לפי ציון Buy-and-Hold (איכות/צמיחה/תמחור/מגמה).

## עקרונות

- מודל התמחור הוא Black-Scholes אמיתי, ללא פישוטים.
- הנחת ברירת המחדל: האופציות נסחרות ונמכרות לפני פקיעה; המערכת מסמנת מקרים נדירים
  שבהם שווה להחזיק עד פקיעה.
- נתונים מ-Yahoo Finance. אינו ייעוץ השקעות.
