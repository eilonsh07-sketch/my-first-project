# OptionDesk — Build Plan

**Full plan**: `specs/001-agent-architecture/plan.md`

## לוח זמנים
```
שבוע 1 (עד 2026-06-22): Phase 0 + Phase 1
שבוע 2 (עד 2026-06-29): Phase 2 + Phase 3 + Phase 4
שבוע 3 (עד 2026-07-05): Phase 5 + Phase 6 + דמו
```

## Phase 0 — Critical Fixes (בלוקר: חייב לסיים ראשון)
- F1: `scenarios.py` → US options rewrite
- F2: `economist.py` + `scoring.py` → regime_multiplier integration
- F3: `rates.py` NEW → dynamic RISK_FREE from FRED
- F4: `strategies.py` → 5 אסטרטגיות חסרות

## Phase 1 — Infrastructure
- `contracts.py` NEW — כל TypedDicts
- `rates.py` NEW — חלק מF3
- `verify.py` NEW — VERIFY agent
- `atlas.py` skeleton — ATLAS orchestrator (skeleton)

## Phase 2 — Quantitative Core
- `economist.py` ENHANCE — KEYNES (TTL cache, fed_stance, MacroRegime TypedDict)
- `backtest.py` ENHANCE — MAX (ALPHA/BETA validators, dynamic risk_free)
- `strategies.py` EXPAND — SIGMA (8 אסטרטגיות + recommend())

## Phase 3 — Intelligence Layer
- `research.py` NEW — MIKI (web_search + ResearchFindings)
- `technicals.py` MINOR — LENS (confidence bounding)
- `guardian.py` NEW — GUARDIAN (Kelly Criterion)
- `compass.py` NEW — COMPASS (rule-based suitability filter)

## Phase 4 — Context & Events
- `radar.py` NEW — RADAR (earnings + ex-div + FOMC)
- `scout.py` NEW — SCOUT (competitive intelligence)

## Phase 5 — Output Layer
- `clarity.py` NEW — CLARITY (3 layers via Claude API)
- `canvas.py` NEW + `templates/` — CANVAS (10 slides HTML/PDF)

## Phase 6 — Full Orchestration
- `atlas.py` COMPLETE — ATLAS full (async dispatch, all agents)
- `app.py` ADD — `POST /api/agents/analyze` endpoint
- Frontend tab — "ניתוח מלא" → ATLAS

## Demo Deliverables (2026-07-05)
| מה | מי | סטטוס |
|----|-----|--------|
| MIKI: 3+ מקורות + פרמטרים | MIKI | ⏳ |
| MAX: baseline על 100+ מניות | MAX | ⏳ |
| CANVAS: מצגת 10 שקפים | CANVAS | ⏳ |
| הדגמה חיה: ניתוח AAPL מקצה לקצה | ATLAS | ⏳ |
