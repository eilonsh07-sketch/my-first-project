# OptionDesk — מסמך העברה מלא (Handoff)

> מסמך זה מתאר את אפליקציית **OptionDesk** במלואה: לוגיקה, פונקציונליות, עיצוב, ארכיטקטורה, API, משתני סביבה, חיבורים, פריסה (deployment), ומצב נוכחי.
> מטרתו: לאפשר לצ'אט אחר (או מפתח אחר) להבין את כל המערכת ולהמשיך **בדיוק מהנקודה שבה עצרנו** — ללא הקשר קודם.
> **עודכן לאחרונה:** 8 ביוני 2026. **גרסה:** 1.0. **קומיט אחרון:** `c736dec`.

---

## 0. תקציר מנהלים (קרא קודם)

**OptionDesk** היא אפליקציית ווב פרטית לניתוח כמותי של מניות ואופציות, בנויה עבור משקיע/אנליסט אחד (יועץ השקעות בבנק מזרחי-טפחות, תל אביב). כל הממשק וכל התקשורת **בעברית, RTL**.

- **Frontend:** React 18 + Vite + Tailwind, פרוס ב-Vercel: `https://optiondesk-mocha.vercel.app`
- **Backend:** FastAPI (Python 3.12) + מנוע כמותי, פרוס ב-Render (Docker): `https://optiondesk.onrender.com`
- **קוד:** ריפו פרטי ב-GitHub: `https://github.com/eilonsh07-sketch/optiondesk` (ענף `master`)
- **מקור נתונים:** Yahoo Finance דרך `yfinance` (ללא מפתח API)
- **שער כניסה (Gate):** קוד גישה `0804`. חתימה בתחתית: `EILON STERN`.
- **10 טאבים** ב-RTL: מצב שוק · אופציות · מחקר · החברה · שורה תחתונה · דירוג מניות · **רעיונות השקעה** · מעקב · שוק ישראלי · מידע למשתמש

### מנדטים קריטיים של המשתמש (לשמר תמיד, מילה במילה)
1. **תמחור Black-Scholes אמיתי, ללא קיצורי דרך / פישוטים** — חל גם על ה-backtest.
2. **הנחת מסחר ברירת-מחדל:** אופציות **נמכרות לפני פקיעה**; לסמן מקרים נדירים של החזקה-עד-פקיעה.
3. **לעולם לא לומר "cron" למשתמש** — לומר **"משימה חוזרת"**. תמיד `confirm_action` לפני יצירת משימה חוזרת.
4. **כל חישוב/דירוג חייב להתבסס על סטטיסטיקת הצלחה** ("חשוב שהחישוב התבסס על סטטיסטיקה של הצלחה") — בוחרים את מה שמנבא הכי טוב לפי בדיקת היסטוריה, לא לפי אינטואיציה.
5. **מקור IV למעו"ף:** "מה שמומלץ אבל שלא יטעה בקבלת החלטה".
6. **כל התקשורת וכל ה-UI בעברית (RTL).**

---

## 1. ארכיטקטורה כללית

```
┌─────────────────────────────┐         HTTPS          ┌──────────────────────────────┐
│  Frontend (React/Vite)      │  ───────────────────▶  │  Backend (FastAPI / Python)  │
│  Vercel                     │   fetch JSON           │  Render (Docker)             │
│  optiondesk-mocha.vercel.app│  ◀───────────────────  │  optiondesk.onrender.com     │
│                             │                        │                              │
│  - Gate (קוד 0804)          │                        │  engine/  (מנוע כמותי)        │
│  - 10 טאבים RTL             │                        │  - pricing (Black-Scholes)   │
│  - api.js (לקוח HTTP)       │                        │  - scoring / technicals      │
└─────────────────────────────┘                        │  - fundamentals / ideas      │
                                                        │  - maof / scenarios          │
                                                        │  - store (watchlist SQLite/PG)│
                                                        └──────────────┬───────────────┘
                                                                       │ yfinance
                                                                       ▼
                                                              ┌─────────────────┐
                                                              │  Yahoo Finance  │
                                                              └─────────────────┘
```

- ה-Frontend **לא** מחזיק לוגיקה כמותית — הוא צורך JSON מה-backend בלבד.
- כל החישובים (Black-Scholes, מונטה-קרלו, ציונים, סריקות) קורים ב-backend.
- אין מסד נתונים חיצוני חובה: רשימת מעקב (watchlist) נשמרת ב-`store.py` (SQLite מקומי, או Postgres אם `DATABASE_URL` מוגדר).

---

## 2. Backend — מבנה ולוגיקה

נתיב שורש ב-Render: `backend/`. נקודת כניסה: `app.py` (FastAPI). מנוע: `backend/engine/`.

### 2.1 קבצי המנוע (`backend/engine/`)

| קובץ | תפקיד |
|---|---|
| `pricing.py` | **Black-Scholes-Merton אמיתי** (price, greeks, implied vol), מונטה-קרלו, מונטה-קרלו עם יציאה מוקדמת, הסתברות נגיעה במחיר יעד. ללא פישוטים. `_d1_d2`, `bs_price`, `bs_greeks`, `implied_vol`, `monte_carlo_option`, `monte_carlo_option_early`, `prob_touch_target_price`. |
| `scoring.py` | מנוע ציונים לאופציות ולמניות. `RISK_FREE=0.045`. `momentum_score(tech)`, `fundamental_option_risk`, `scan_score(...)`, `evaluate_option(...)`. פילטרים: `MIN_PREMIUM=0.10`, `MAX_OTM_PCT=0.40`, `MIN_VALID_IV=0.05`. |
| `technicals.py` | אינדיקטורים טכניים: MACD, Bollinger, RSI, ממוצעים נעים. `technical_summary`, `technical_scorecard`. |
| `fundamentals.py` | ניתוח פונדמנטלי. `long_term_score(info,tech,cagr_3y)` → score/axes/label/note/metrics. `dcf_fair_value(info,fin)` → upside. `multiples_summary`. |
| `provider.py` | שכבת גישה ל-Yahoo דרך `yfinance` + מטמון. `info_light(ticker)` (רק `t.info`, זול), גרסה מלאה עם העשרת דוחות. מפתחות מטמון: `infolight:`, וכו'. |
| `ideas.py` | **סורק רעיונות השקעה** (ראה §2.4). |
| `universe.py` | יקום המניות: S&P 500 + נאסד"ק-100 (515 ייחודיות). `universe(name)`, `membership(ticker)`. נירמול טיקרים לפורמט Yahoo (BRK.B→BRK-B). |
| `maof.py` | סורק אופציות מעו"ף (TA-35) — Black-Scholes מלא, PoP מבוסס היסטוריה. אקספיריות חודשיות + שבועיות (כל יום חמישי). |
| `scenarios.py` | מודול תרחישים גאופוליטיים למעו"ף: תמחור-מחדש BSM תחת קפיצות IV היסטוריות. |
| `market.py` | תמונת מצב שוק כללית. |
| `backtest.py` | בדיקה היסטורית של אסטרטגיות אופציות לאורך ~3 שנים. |
| `spreads.py` / `strategies.py` | מרווחים ואסטרטגיות מרובות-רגליים. |
| `store.py` | אחסון רשימת מעקב + היסטוריית מעקב (SQLite מקומי / Postgres). |

### 2.2 נקודות קצה API (כל הנתיבים תחת `/api`)

| Method | Path | תיאור |
|---|---|---|
| GET | `/api/health` | בריאות: `{"ok":true,"provider":"yahoo"}` |
| POST | `/api/backtest` | בדיקה היסטורית של אסטרטגיה |
| GET | `/api/market` | תמונת מצב שוק |
| GET | `/api/quote/{ticker}?leaps=true` | ציטוט + שרשרת אופציות |
| POST | `/api/scan` | סורק אופציות לפי ציון משולב |
| GET | `/api/research/{ticker}` | מחקר טכני/פונדמנטלי על מניה |
| GET | `/api/company/{ticker}` | נתוני חברה |
| POST | `/api/strategy` | ניתוח אסטרטגיית אופציה בודדת |
| POST | `/api/compare` | השוואת חוזים |
| POST | `/api/analyze` | ניתוח מקיף (שורה תחתונה) |
| POST | `/api/distribution` | התפלגות מונטה-קרלו |
| POST | `/api/whatif` | תרחישי מחיר/זמן/תנודתיות |
| POST | `/api/rank` | דירוג רשימת מניות |
| GET/POST | `/api/watchlist` | רשימת מעקב (קריאה/הוספה) |
| DELETE | `/api/watchlist/{id}` | מחיקה מרשימת מעקב |
| GET | `/api/watchlist/{id}/history` | היסטוריית מעקב |
| POST | `/api/watchlist/{id}/track` | רישום נקודת מעקב |
| POST | `/api/alerts/check` | בדיקת התראות |
| GET | `/api/israel/index/{index_id}` | אינדקס ישראלי (TA35/TA90/TA125) |
| GET | `/api/israel/maof` | סורק אופציות מעו"ף |
| GET | `/api/israel/maof/scenarios` | תרחישים גאופוליטיים למעו"ף |
| GET | `/api/ideas?universe=&min_score=&limit=&refresh=` | **סורק רעיונות השקעה** |

### 2.3 תלויות (`requirements.txt`)
```
fastapi, uvicorn[standard], pydantic, numpy, pandas, scipy, yfinance, anthropic, psycopg[binary]
```

### 2.4 סורק "רעיונות השקעה" — `engine/ideas.py` (התוספת האחרונה)

המטרה: לדרג **מניות מעניינות לקנייה** (לא אופציות) על פני יקום של 515 מניות, לפי ציון אטרקטיביות משוקלל 0–100.

**ארבעת רכיבי הציון ומשקליהם (נבחרו לפי תיקוף היסטורי — ראה §4):**
```python
WEIGHTS = {
  "technical":      0.30,   # מומנטום טכני
  "fundamental":    0.20,   # איכות פונדמנטלית (קנייה-החזקה)
  "distortion":     0.15,   # עיוות מחיר (DCF + יעד אנליסטים) — קונטרני, משקל נמוך + דגל אזהרה
  "iv_opportunity": 0.35,   # הזדמנות תנודתיות גלומה זולה — המנבא החיובי העקבי ביותר
}
```

**פונקציות מפתח:**
- `distortion_score(info,tech)` — משלב upside מ-DCF + upside מיעדי אנליסטים, כל אחד מוגבל ב-`_cap()` לטווח [−0.90, +1.00] (מתקן פיצוצי DCF כמו WDAY 199%). ממפה upside מ-−30%→0 עד +50%→100.
- `iv_opportunity_score(info,tech)` — פרוקסי **בלי** שליפת שרשראות אופציות: משטר תנודתיות ממומשת + יחס IV/RV ( vol זול = תגמול).
- `evaluate_ticker(ticker,provider,idx_hist,weights)` — מחשב את כל הרכיבים, מנרמל מחדש משקלים על רכיבים זמינים, מחזיר שורה עם score/components/fundamental_axes/distortion/iv_opportunity/`reason_he`/membership. עטוף ב-`_fetch_with_retry` (2 ניסיונות, backoff) למניעת חניקת Yahoo.
- `_reason_he()` — שורת הסבר אחת בעברית של 2-3 המניעים העיקריים.
- `scan_universe(provider, universe_name, max_workers=6)` — `ThreadPoolExecutor` (הופחת מ-12 ל-6 למניעת throttling).
- מחלקת `IdeasScanner` — סריקת רקע בתהליכון, מטמון TTL 1800 שניות לפי יקום; מחזיר status `building`|`ready` + תוצאות חלקיות.

**תיקון אחרון (קומיט `479bcdd`):** `_fresh()` הוגן מפני `KeyError: 'fetched_at'` כשמצב = `building`. ראה §4.

---

## 3. Frontend — מבנה, טאבים ועיצוב

נתיב שורש: `frontend/`. נבנה עם Vite. נפרס ב-Vercel.

### 3.1 קבצי מקור (`frontend/src/`)
- `main.jsx` — נקודת כניסה.
- `App.jsx` — שלד ה-app, ניווט טאבים, ניתוב.
- `api.js` — לקוח HTTP (`export const api = {...}`). פתרון בסיס API (ראה §5.3).
- `ui.jsx` — רכיבי UI לשימוש חוזר: `fmt`, `Card`, `Stat`, `Badge`, `ScoreRing`, `Bar`, `Spinner`, `Empty`, `ErrorBox`, `scoreTone`, `InfoTip`.
- `Gate.jsx` — מסך כניסה (קוד 0804).
- `hooks.js`, `pwa.jsx` (התקנת PWA), `index.css`.
- `tabs/` — קומפוננטת לכל טאב (ראה למטה).

### 3.2 מבנה הטאבים (`App.jsx`)

10 טאבים ראשיים (RTL, מימין לשמאל):

| # | id | תווית | קומפוננטה |
|---|---|---|---|
| 1 | `market` | מצב שוק | `Market.jsx` |
| 2 | `options` | אופציות | תת-טאבים: `Scanner` / `Strategy` / `WhatIf` / `Backtest` |
| 3 | `research` | מחקר | `Research.jsx` |
| 4 | `company` | החברה | `Company.jsx` |
| 5 | `bottomline` | שורה תחתונה | `BottomLine.jsx` |
| 6 | `ranking` | דירוג מניות | `Ranking.jsx` |
| 7 | `ideas` | **רעיונות השקעה** | `Ideas.jsx` |
| 8 | `tracker` | מעקב | `Tracker.jsx` |
| 9 | `israel` | שוק ישראלי | `Israel.jsx` (תת-טאבים: tech / maof) |
| 10 | `info` | מידע למשתמש | `UserInfo.jsx` |

**תת-טאבים של "אופציות" (טאב 2):**
- `scanner` — סורק אופציות לפי ציון משולב
- `strategy` — ניתוח אופציה בודדת
- `whatif` — תרחישי מחיר/זמן/תנודתיות
- `backtest` — מבחן היסטורי (איך האסטרטגיה התנהגה ב-3 שנים)

**`NO_TICKER_TABS`** (טאבים שלא דורשים בחירת מניה): `market, info, compare, ranking, ideas, tracker, israel`.

### 3.3 טאב "רעיונות השקעה" — `Ideas.jsx` (~323 שורות, התוספת האחרונה)
- בורר יקום: `both` (S&P 500 + נאסד"ק) / `sp500` / `nasdaq100`.
- סינון ציון מינימלי: הכול / +50 / +60 / +70.
- שורת משקלים (chips): טכני 30% · פונדמנטלי 20% · עיוות מחיר 15% · הזדמנות IV 35%.
- **באנר אזהרה כתום** על רכיב עיוות-המחיר הקונטרני.
- בר התקדמות (polls כל 4 שניות בזמן `status=building`, עד 515 מניות).
- לוח מדורג: `MiniRing` + `ScorePill` לכל רכיב + `reason_he`.
- לחיצה על שורה פותחת פאנל: צירים פונדמנטליים (bars) + פרטי עיוות/DCF + טכני/IV.

### 3.4 עיצוב (Design System)
- **ערכת צבעים:** primary `#16c75e` (ירוק), danger `#ef4f6b` (אדום), amber `#f5b740` (כתום-אזהרה), רקע `#0a0e0c` (כהה).
- **RTL מלא**, גופן עברי. כל הטקסטים בעברית.
- כרטיסים כהים, טבעות ציון (ScoreRing), בארים, badges.
- PWA: ניתן להתקנה (manifest + service worker), עם תמיכת safe-area למובייל.
- חתימה בתחתית: `© EILON STERN · כל הזכויות שמורות`. כיתוב: "OptionDesk · נתונים מ-Yahoo Finance · תמחור Black-Scholes ו-Monte Carlo · לא ייעוץ השקעות בלבד".

---

## 4. תיקוף סטטיסטי (מנדט "סטטיסטיקת הצלחה")

לפי דרישת המשתמש, **כל דירוג חייב להתבסס על מה שבאמת ניבא תשואה היסטורית** — לא על אינטואיציה.

### 4.1 תיקוף סורק הרעיונות (`backend/ideas_validation.py`, `ideas_validation_results.json`, `ideas_weights_final.json`, `ideas_design.md`)

**שיטה:** דגימה של ~118 מניות, חישוב כל רכיב נכון לתאריך עבר (ללא look-ahead), קורלציית Spearman מול תשואה קדימה על פני 4 אופקים (3/6/9/12 חודשים).

**ממצאים (Spearman ממוצע על פני האופקים):**
| רכיב | Spearman ממוצע | מסקנה |
|---|---|---|
| `iv_opportunity` | **+0.1995** | המנבא החיובי העקבי ביותר בכל האופקים → משקל גבוה (אבל מוגבל כי זה פרוקסי) |
| `technical` | **+0.1008** | חזק, שיא +0.40 באופק 6 חודשים |
| `fundamental` | **+0.0073** | ~ניטרלי; נשמר לעדשת קנייה-החזקה |
| `distortion` | **−0.2231** | **קונטרני!** "זול מול ערך הוגן" התת-ביצע בכל אופק → משקל נמוך + דגל אזהרה ב-UI |

**משקלים סופיים שהוחלו:** technical 0.30, fundamental 0.20, distortion 0.15, iv_opportunity 0.35 (נקבעו בשיקול דעת על בסיס הממצאים — IV מוגבל כי פרוקסי, distortion נמוך עם אזהרה).

### 4.2 תיקוף PoP למעו"ף (`backend/maof_validation.py`, `maof_validation_results.json`)
- שיטה: walk-forward, sigma=realized 60d, mu=trailing 120d, אופקים 10/21/42 יום, moneyness ±6/3/0%.
- מסקנה: **real-drift analytic PoP** הכי טוב-מכויל (calib_err הנמוך ביותר ל-TA35: 0.0134). analytic == MC (אותו log-normal).

---

## 5. פריסה (Deployment), משתני סביבה וחיבורים

### 5.1 Backend (Render)
- **URL:** `https://optiondesk.onrender.com`
- שירות: Render free tier, Docker, auto-deploy מענף `master` ב-GitHub. שורש: `backend`. Service ID: `srv-d8i233ernols73b9abug`.
- **חשוב:** free tier **נרדם אחרי ~15 דק'**; cold start 30-50 שניות. סריקת ideas של 515 שמות לוקחת ~3-5 דק' בריצה ראשונה.
- בריאות: `GET /api/health` → `{"ok":true,"provider":"yahoo"}`.
- Dockerfile: `python:3.12-slim`, מתקין requirements, מריץ `uvicorn app:app --host 0.0.0.0 --port ${PORT}`. Render מזריק `$PORT`.

### 5.2 Frontend (Vercel)
- **URL:** `https://optiondesk-mocha.vercel.app`
- Vercel scope: `eilon-stern-s-projects`, חשבון `eilonsh07-1000`.
- שער כניסה: קוד `0804`.

### 5.3 משתני סביבה
**Frontend (build-time):**
- `VITE_API_BASE` — כתובת ה-backend. **חובה** לבנות עם `VITE_API_BASE="https://optiondesk.onrender.com"` לפני פריסה ל-Vercel.
- סדר פתרון בסיס API ב-`api.js`: (1) `VITE_API_BASE` (production) → (2) `__PORT_8000__` (פרוקסי Perplexity) → (3) `http://localhost:8000` (פיתוח מקומי).
- Timeout ברירת מחדל לבקשות: 90 שניות (120 שניות ל-backtest ול-ideas) — כי Render מתעורר משינה.

**Backend (אופציונלי):**
- `PORT` — מוזרק ע"י Render (ברירת מחדל 8000 מקומית).
- `DATABASE_URL` — אם מוגדר, `store.py` משתמש ב-Postgres; אחרת SQLite מקומי.
- `ANTHROPIC_API_KEY` — `anthropic` ב-requirements (אם נעשה שימוש ב-LLM; כרגע לא חובה לפעולה הבסיסית).

### 5.4 חיבורים חיצוניים (Connectors בשימוש בעבודה)
- **GitHub** (ריפו פרטי) — push דרך `api_credentials=["github"]`. דגלי קומיט: `-c user.email="optiondesk@local" -c user.name="OptionDesk"`.
- **Vercel** — פריסה דרך `api_credentials=["vercel"]`.
- **finance** (connector) — לנתוני שוק בעת עבודה.
- **מקור נתוני המניות בפועל:** Yahoo Finance דרך `yfinance` (ללא מפתח, ללא connector).

### 5.5 GitHub
- **Repo:** `https://github.com/eilonsh07-sketch/optiondesk` (פרטי), ענף `master`.
- **קומיט אחרון:** `c736dec` (feat: Investment Ideas tab).
- היסטוריית קומיטים אחרונה:
  - `c736dec` — טאב רעיונות השקעה (frontend)
  - `479bcdd` — תיקון `_fresh` (KeyError fetched_at)
  - `b8e16b8` — סורק רעיונות (backend + משקלים מתוקפים)
  - `463d058` — אופציות מעו"ף שבועיות (כל יום חמישי)
  - `abc109f` — שלב 3: תרחישים גאופוליטיים למעו"ף
  - `bcc7133` — שלב 2: סורק אופציות מעו"ף TA-35
  - `2059c56` — שלב 1: טאב שוק ישראלי

---

## 6. פקודות פריסה ופיתוח (Runbook)

### 6.1 בניית Frontend ופריסה ל-Vercel
```bash
cd frontend && VITE_API_BASE="https://optiondesk.onrender.com" npm run build
cd dist && rm -f vercel.json
DEP=$(npx vercel deploy --prod --yes --token $VERCEL_TOKEN | grep -oE "https://dist-[a-z0-9-]+\.vercel\.app" | head -1)
npx vercel alias set "$DEP" optiondesk-mocha.vercel.app --token $VERCEL_TOKEN
# api_credentials=["vercel"]
```
- `frontend/dist` ב-gitignore → לעשות commit רק ל-src + public.

### 6.2 Backend — push ל-GitHub (Render בונה מחדש אוטומטית)
```bash
cd /home/user/workspace/optiondesk
git add <files>
git -c user.email="optiondesk@local" -c user.name="OptionDesk" commit -m "<msg>"
git push origin master   # api_credentials=["github"]
# פולינג על /api/<endpoint> עד שהשדה החדש מופיע = הבנייה עלתה
```

### 6.3 אימות מקומי
```bash
# backend על :8077
cd backend && python -m uvicorn app:app --host 0.0.0.0 --port 8077   # log: /tmp/od_backend.log
# frontend dist על :8078 (בנה עם VITE_API_BASE="http://localhost:8077")
cd frontend/dist && python -m http.server 8078
```

### 6.4 בניית גיבוי קוד מקור (zip)
```bash
cd /home/user/workspace/optiondesk && rm -f optiondesk-v1.0-source.zip
zip -rq optiondesk-v1.0-source.zip backend frontend/src frontend/public frontend/index.html \
  frontend/package.json frontend/vite.config.js frontend/tailwind.config.js \
  frontend/postcss.config.js -x "*/node_modules/*" -x "*/__pycache__/*" -x "*/dist/*" -x "*.pyc"
```

### 6.5 בדיקה חיה ב-Playwright (js_repl)
```js
chromium.launch({ args:['--no-sandbox','--disable-dev-shm-usage','--disable-gpu'] })
// שער: למלא input עם '0804' + Enter
```

---

## 7. מצב נוכחי (היכן עצרנו)

### ✅ הושלם
- שלבים 1-3 של השוק הישראלי: טאב שוק ישראלי, סורק מעו"ף TA-35 (BSM מלא, PoP מבוסס היסטוריה), תרחישים גאופוליטיים, אופציות מעו"ף שבועיות (86 שבועיות + 72 חודשיות חיות).
- **סורק "רעיונות השקעה" — חי ומלא:** יקום 515 מניות, 4 רכיבים משוקללים (משקלים שנבחרו בתיקוף היסטורי), באנר אזהרה קונטרני, טאב RTL חדש (טאב 7). נפרס ב-Vercel ואומת חי מול backend חי ב-Render (נאסד"ק-100 השלים 101/101). תוקן באג `fetched_at`. קוד מקור (frontend + backend) דחוף ל-GitHub. גיבוי zip עודכן.

### ⏳ נותר / נדחה
- **שלב 4: אופציות מט"ח (FX options)** — מודל **Garman-Kohlhagen**, עם **קלט ידני**. **טרם התחיל.** זה השלב הבא הפתוח.

---

## 8. נכסים משותפים (assets — לעדכן באותו שם)
- `optiondesk/frontend/dist` — build הפרונטאנד
- `optiondesk-source` (zip, CODE_FILE) — גיבוי קוד מקור מלא
- `optiondesk-blueprint` (md, DOC_FILE) — מסמך תכנון
- `optiondesk-strategy-memo` (md, DOC_FILE) — מזכר אסטרטגיה
- `OPTIONDESK_HANDOFF.md` (מסמך זה) — העברה מלאה

---

## 9. מלכודות ידועות (Gotchas)
- **באג מרכאות עברי:** `ת"א` / `מעו"ף` בתוך f-strings של Python או attributes של JSX שוברים פירוק — להשתמש במרכאות בודדות או לנסח מחדש.
- **חניקת Yahoo:** סריקות גדולות → `max_workers=6` + `_fetch_with_retry` (2 ניסיונות + backoff).
- **פיצוצי DCF:** upside חייב להיות מוגבל ב-`_cap()` לטווח [−0.90, +1.00] (אחרת WDAY מקבל 199%).
- **Render cold start:** הבקשה הראשונה אחרי 15 דק' שינה לוקחת 30-50 שניות → timeouts ב-api.js נדיבים (90-120 שניות).
- **`status=building`:** הקצה `/api/ideas` מחזיר תוצאות חלקיות עם `status=building`; ה-UI עושה polling עד `ready`.

---

*נכתב כמסמך העברה עצמאי. צ'אט/מפתח חדש שיקרא אותו אמור להבין את כל המערכת ולהמשיך משלב 4 (אופציות מט"ח, Garman-Kohlhagen, קלט ידני) — או כל בקשה אחרת של המשתמש — תוך שמירה על המנדטים בסעיף 0.*
