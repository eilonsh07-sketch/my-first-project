# OptionDesk — Build Status

**עדכון אחרון**: 2026-06-15  
**עדכן קובץ זה** בסיום כל משימה — זה ה-"מוח" של הפרויקט.

---

## Phase 0 — Critical Fixes

- [ ] **F1** — `scenarios.py` → US options (6 תרחישים)
- [ ] **F2** — `economist.py` → `get_regime_multiplier()` + `scoring.py` integration
- [ ] **F3** — `rates.py` NEW → `get_risk_free()` dynamic from FRED
- [ ] **F4** — `strategies.py` → iron_condor, CSP, covered_call, straddle, leaps

---

## Phase 1 — Infrastructure

- [ ] **contracts.py** — כל TypedDicts (12 classes)
- [ ] **verify.py** — VERIFY agent
- [ ] **atlas.py** skeleton — orchestration flow (ללא async מלא)

---

## Phase 2 — Quantitative Core

- [ ] **economist.py** ENHANCE — MacroRegime TypedDict, cache 30min, fed_stance
- [ ] **backtest.py** ENHANCE — ALPHA/BETA validators, dynamic risk_free
- [ ] **strategies.py** EXPAND — recommend() + 8 אסטרטגיות + scenarios.py rewrite

---

## Phase 3 — Intelligence Layer

- [ ] **research.py** — MIKI (web_search + ResearchFindings)
- [ ] **technicals.py** MINOR — LENS confidence bounding (`signals()` wrapper)
- [ ] **guardian.py** — GUARDIAN (Kelly formula)
- [ ] **compass.py** — COMPASS (rule-based strategy filter)

---

## Phase 4 — Context & Events

- [ ] **radar.py** — RADAR (earnings + ex-div + FOMC 2026)
- [ ] **scout.py** — SCOUT (competitive intel)

---

## Phase 5 — Output Layer

- [ ] **clarity.py** — CLARITY (3 layers, Claude API, Haiku model)
- [ ] **canvas.py** + `templates/slide_deck.html` — CANVAS (10 slides RTL)

---

## Phase 6 — Full Orchestration

- [ ] **atlas.py** COMPLETE — async dispatch, error handling per agent
- [ ] **app.py** ADD — `POST /api/agents/analyze`
- [ ] **Frontend** — "ניתוח מלא" tab

---

## Demo Milestones

- [ ] MIKI הריץ חיפוש על iron_condor → ≥ 3 מקורות
- [ ] MAX הריץ baseline על ≥ 100 מניות
- [ ] CANVAS יצר 10-slide deck ל-AAPL
- [ ] ATLAS ניתח AAPL מקצה לקצה בפחות מ-90 שניות

---

## כיצד לעדכן
כשמסיימים משימה: שנה `- [ ]` ל-`- [x]` + הוסף תאריך:
```
- [x] **F3** — rates.py ✅ 2026-06-16
```
