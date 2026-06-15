# פריסת ה-backend של OptionDesk (שלב אחרון)

ה-frontend כבר חי בכתובת קבועה:
**https://optiondesk-mocha.vercel.app**

נשאר רק לפרוס את ה-backend (מנוע החישובים + נתוני yfinance) לשרת קבוע ולחבר ביניהם.
ההמלצה: **Render** — תוכנית חינמית, פריסה ישירה מ-GitHub, תומך yfinance.

---

## שלב 1 — יצירת חשבון ופריסת ה-backend ב-Render (כ-4 דקות)

1. היכנס ל-https://render.com והירשם עם חשבון ה-GitHub שלך (eilonsh07-sketch).
2. לחץ **New +** → **Web Service**.
3. בחר את המאגר **optiondesk** (אם לא מופיע, אשר ל-Render גישה למאגר).
4. בהגדרות:
   - **Root Directory:** `backend`
   - **Runtime / Environment:** `Docker` (יזוהה אוטומטית מה-Dockerfile)
   - **Plan:** `Free`
   - **Health Check Path:** `/api/health`
5. תחת **Environment Variables** הוסף:
   - `ALLOWED_ORIGINS` = `https://optiondesk-mocha.vercel.app`
6. לחץ **Create Web Service**. הפריסה תיקח 3-5 דקות.
7. בסיום תקבל כתובת כמו `https://optiondesk-backend-xxxx.onrender.com`.
   בדוק שהיא חיה: פתח `https://<הכתובת>/api/health` — אמור להחזיר `{"ok":true,...}`.

> הערה: בתוכנית החינמית של Render השרת "נרדם" אחרי ~15 דקות חוסר שימוש,
> והקריאה הראשונה אחרי שינה לוקחת ~30 שניות. אחרי זה מהיר.

---

## שלב 2 — מסד נתונים ל-Watchlist (אופציונלי אך מומלץ)

אם אתה רוצה שה-Watchlist יישמר לצמיתות (ולא יימחק כשהשרת נרדם):

1. ב-Render: **New +** → **PostgreSQL** → תוכנית `Free` → **Create Database**.
2. העתק את ה-**Internal Database URL**.
3. חזור ל-Web Service → **Environment** → הוסף:
   - `DATABASE_URL` = ה-URL שהעתקת
4. שמור — השרת יופעל מחדש ויתחבר ל-Postgres אוטומטית.

ללא `DATABASE_URL` האפליקציה עדיין עובדת, אך ה-Watchlist זמני בלבד.

---

## שלב 3 — חיבור ה-frontend ל-backend

לאחר שתקבל את כתובת ה-backend, **שלח לי אותה כאן בצ'אט** ואני:
1. אגדיר את ה-frontend לדבר עם ה-backend (משתנה `VITE_API_BASE`).
2. אבנה מחדש ואפרוס שוב ל-Vercel.
3. אריץ QA מקצה לקצה לוודא שהכל עובד מהכתובת הקבועה.

זהו — מאותו רגע האפליקציה תהיה נגישה מכל מקום, כולל נייד, עם נתונים חיים.
