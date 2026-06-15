# Implementation Plan: OptionDesk — Multi-Agent Architecture (v2)

**Branch**: `001-agent-architecture` | **Date**: 2026-06-15 | **Spec**: `specs/optiondesk-research-architecture.md`

**Input**: 13 agents defined in clarify phase + 4 critical audit findings from initial-audit-2026-06-15.md

**Deadline**: 2026-07-05 — פגישה עם סגן מנהל הסקטור, בנק מזרחי-טפחות

---

## Summary

OptionDesk v2 מוסיף שכבת 13 סוכנים AI מעל קוד ה-backend הקיים. ATLAS הוא ה-CEO — מנצח, לא מבצע. כל שאר הסוכנים מתמחים בתחום אחד ומדברים ביניהם דרך חוזי נתונים מוגדרים. **לפני** כל בנייה של סוכן חדש — מתקנים 4 ממצאי ביקורת קריטיים (Phase 0) שבלעדיהם הכל נבנה על בסיס שגוי.

---

## Technical Context

**Language/Version**: Python 3.12 (backend), React 18 + Vite (frontend)

**Primary Dependencies (existing)**: FastAPI, numpy, pandas, scipy, yfinance, anthropic, pricing.py (Black-Scholes — לא לגעת)

**New Dependencies (to add)**:
- `requests` — FRED API (ריבית דינמית)
- `anthropic` — כבר קיים ב-requirements; יופעל ב-CLARITY, CANVAS
- `jinja2` — תבניות HTML ל-CANVAS
- `weasyprint` — PDF generation ב-CANVAS (אלטרנטיבה: `playwright`)

**Storage**: SQLite/Postgres קיים דרך `store.py`. אין צורך במסד נוסף.

**Testing**: pytest (unit per agent) + integration test per data contract

**Target Platform**: Render (Docker) — backend. Vercel — frontend. לא משתנה.

**Performance Goals**:
- VERIFY: < 2 שניות (gate לפני כל backtest)
- KEYNES regime check: < 5 שניות (מחזיר cached regime עם TTL 30 דק')
- ATLAS full analysis: < 90 שניות (שוק סגור) / < 30 שניות (regime + LENS בלבד)
- CANVAS 10-slide deck: < 15 שניות

**Constraints**:
- `pricing.py` — אסור לגעת (BSM, Greeks, Monte Carlo — מאומת ועובד)
- כל output מסומן "decision-support only" — אין המלצות אוטומטיות
- ריבית חסרת סיכון חייבת להיות דינמית (audit finding #3)
- RISK_FREE קבוע = 0.045 אסור להישאר בקוד

**Scale/Scope**: יועץ בודד, יקום 515 מניות, ~50 ניתוחי אופציות ביום

---

## Architecture: 13 Agents — Skills & Tools

### Layer 0 — Infrastructure (מריץ תמיד ראשון)

| Agent | קובץ חדש | Skills | Tools / APIs | קלט → פלט |
|-------|----------|--------|-------------|-----------|
| **VERIFY** | `engine/verify.py` | Data validation, integrity checks | yfinance, Polygon, schema validation | כל בקשה → `DataQualityReport` |
| **ATLAS** | `engine/atlas.py` | Orchestration, agent dispatch | כל הסוכנים | user_request → `AnalysisPackage` |

### Layer 1 — Data & Macro (מריץ אחרי VERIFY)

| Agent | קובץ | Skills | Tools / APIs | קלט → פלט |
|-------|------|--------|-------------|-----------|
| **KEYNES** | `engine/economist.py` ← **enhance** | Macro regime, VRP, yield curve | FRED (free), yfinance (VIX, TNX, IRX) | ticker/date → `MacroRegime` |
| **MIKI** | `engine/research.py` ← **new** | Academic search, paper synthesis | WebSearch (Perplexity), arxiv, SSRN | research_query → `ResearchFindings` |
| **RADAR** | `engine/radar.py` ← **new** | Event calendar, catalyst detection | yfinance earnings, FRED FOMC calendar | ticker → `EventCalendar` |

### Layer 2 — Quantitative Core

| Agent | קובץ | Skills | Tools / APIs | קלט → פלט |
|-------|------|--------|-------------|-----------|
| **MAX** ⭐ | `engine/backtest.py` ← **enhance** | Backtesting, statistical validation, ALPHA/BETA dual-validator | `backtest.py` (existing), historical options data | strategy+params → `BacktestResult` |
| **SIGMA** ⭐ | `engine/strategies.py` ← **expand** | Options strategy selection, Greeks, multi-leg | `pricing.py` (existing), `strategies.py` (expanded) | market_data → `StrategyRecommendations` |
| **LENS** | `engine/technicals.py` ← **minor update** | Technical signals, confidence scoring | `technicals.py` (existing); confidence = MAX-validated only | ticker → `TechnicalSignal` |

### Layer 3 — Risk & Suitability

| Agent | קובץ חדש | Skills | Tools / APIs | קלט → פלט |
|-------|---------|--------|-------------|-----------|
| **GUARDIAN** ⭐ | `engine/guardian.py` | Kelly Criterion, position sizing, risk spectrum | `scoring.py` (existing), Kelly formula | strategy+account → `RiskAssessment` |
| **COMPASS** | `engine/compass.py` | Client risk profiling, regulatory suitability | rule-based (Mizrahi constraints) | client_profile → `SuitabilityReport` |
| **SCOUT** | `engine/scout.py` | Competitive intel, institutional comparison | WebSearch (יקרא לPERPLEXITY/WebSearch) | query → `CompetitiveInsights` |

### Layer 4 — Output

| Agent | קובץ חדש | Skills | Tools / APIs | קלט → פלט |
|-------|---------|--------|-------------|-----------|
| **CLARITY** ⭐ | `engine/clarity.py` | Explainability, 3-layer narrative | Claude API (anthropic — כבר ב-requirements) | analysis_package → `ExplanationBundle` |
| **CANVAS** | `engine/canvas.py` | 10-slide deck, HTML/PDF | Jinja2 templates, WeasyPrint/Playwright | explanation_bundle → `Presentation` |

---

## Data Contracts (ממשקי סוכנים)

כל סוכן מחזיר TypedDict. ATLAS הוא היחיד שמאגד.

```python
# engine/contracts.py — קובץ חדש, מגדיר את כל החוזים

class DataQualityReport(TypedDict):
    passed: bool
    issues: list[str]
    risk_free_rate: float        # מ-FRED, לשימוש כל הסוכנים
    data_freshness: dict         # ticker → last_updated timestamp

class MacroRegime(TypedDict):
    regime: Literal["low_vol_bull","mid_vol_neutral","high_vol_risk_off","extreme_fear"]
    vix: float
    yield_curve: float           # 10yr-2yr spread
    fed_stance: Literal["easing","neutral","tightening"]
    vrp: float                   # VIX - realized_vol_30d
    regime_multiplier: float     # 0.70–1.30 — מוזן ל-scoring.py (AUDIT F2)
    cached_at: str

class BacktestResult(TypedDict):
    strategy: str
    win_rate: float
    avg_return: float
    sharpe: float
    max_drawdown: float
    validated_params: dict       # הפרמטרים שMAX אימת
    confidence: float            # 0–1, מועבר ל-LENS
    alpha_beta_agreement: bool   # האם שני validators הסכימו

class StrategyRecommendations(TypedDict):
    strategies: list[dict]       # כל אסטרטגיה: type, legs, cost, max_gain, max_loss
    preferred: str               # ממליץ SIGMA לאחר סינון COMPASS+GUARDIAN
    event_adjusted: bool         # RADAR השפיע על הבחירה

class RiskAssessment(TypedDict):
    kelly_fraction: float        # אחוז מהחשבון לסיכון
    position_size_usd: float
    risk_level: Literal["conservative","moderate","aggressive"]
    max_loss_scenario: float
    stop_loss: float

class ExplanationBundle(TypedDict):
    advisor_layer: str           # עברית טכנית — ליועץ
    client_layer: str            # עברית פשוטה — ללקוח
    regulator_layer: str         # אנגלית פורמלית — לרגולטור
    key_risks: list[str]
    decision_support_disclaimer: str  # חובה בכל output

class AnalysisPackage(TypedDict):
    ticker: str
    regime: MacroRegime
    data_quality: DataQualityReport
    strategies: StrategyRecommendations
    risk: RiskAssessment
    technicals: dict             # מ-LENS
    events: dict                 # מ-RADAR
    explanation: ExplanationBundle
    presentation_url: str        # PDF/HTML מ-CANVAS
```

---

## Agent Interaction Flow

```
User Request (ticker + profile)
         │
         ▼
     ┌─────────┐
     │  ATLAS  │ ← CEO Orchestrator
     └────┬────┘
          │ dispatch parallel
    ┌─────┼──────────────────────┐
    ▼     ▼                      ▼
 VERIFY  KEYNES               RADAR
    │     │                      │
    │  MacroRegime           EventCalendar
    │     │                      │
    └──►  ATLAS  ◄───────────────┘
          │
    ┌─────┼─────────────┐
    ▼     ▼             ▼
  MIKI  SIGMA         LENS
    │     │             │
    │  Strategies   TechnicalSignal
    │ (COMPASS+GUARDIAN filter)
    │     │
    └──►  MAX ← ALPHA/BETA validators
          │
       BacktestResult
          │
          ▼
       GUARDIAN
          │
       RiskAssessment
          │
          ▼
       CLARITY
          │
       ExplanationBundle
          │
          ▼
       CANVAS → HTML/PDF Deck
          │
          ▼
       ATLAS → Final AnalysisPackage → User
```

**חוקי ה-flow:**
1. VERIFY תמיד ראשון — אם נכשל, ATLAS מחזיר שגיאה מיד
2. KEYNES + RADAR מריצים במקביל (לא תלויים אחד בשני)
3. SIGMA מקבל regime מ-KEYNES לפני שבוחר אסטרטגיות
4. MAX רץ רק אחרי SIGMA בחר אסטרטגיות (לא על כולן — רק על הנבחרות)
5. GUARDIAN + CLARITY יכולים לרוץ במקביל (שניהם מקבלים BacktestResult)
6. CANVAS תמיד אחרון

---

## Project Structure — קבצים חדשים/משופרים

```text
backend/
├── engine/
│   │── contracts.py          ← NEW: כל TypedDict contracts
│   │── rates.py              ← NEW: dynamic RISK_FREE from FRED (AUDIT F3)
│   │── verify.py             ← NEW: VERIFY agent
│   │── atlas.py              ← NEW: ATLAS orchestrator
│   │── guardian.py           ← NEW: GUARDIAN risk manager
│   │── compass.py            ← NEW: COMPASS client suitability
│   │── scout.py              ← NEW: SCOUT competitive intel
│   │── clarity.py            ← NEW: CLARITY explainability
│   │── canvas.py             ← NEW: CANVAS presentation
│   │── research.py           ← NEW: MIKI research intelligence
│   │── radar.py              ← NEW: RADAR timing & events
│   │
│   │── economist.py          ← ENHANCE: add regime_multiplier output (AUDIT F2)
│   │── scoring.py            ← PATCH: use rates.get_risk_free() + read regime_multiplier (AUDIT F2, F3)
│   │── strategies.py         ← EXPAND: Iron Condor, CSP, Covered Call, Straddle, LEAPS (AUDIT F4)
│   │── scenarios.py          ← REWRITE: US options scenarios only (AUDIT F1)
│   │── backtest.py           ← ENHANCE: ALPHA/BETA dual validators
│   │── technicals.py         ← MINOR: confidence bounded by MAX results
│   │
│   │── pricing.py            ← DO NOT TOUCH (BSM perfect)
│   └── ...existing files unchanged
│
├── templates/                ← NEW: Jinja2 HTML templates for CANVAS
│   ├── slide_deck.html
│   └── report_one_pager.html
│
└── app.py                    ← ADD: /api/agents/* endpoints

specs/001-agent-architecture/
├── plan.md                   ← THIS FILE
├── contracts.md              ← TypedDict specs (human-readable)
└── tasks.md                  ← Phase breakdown (יוצר /speckit.tasks)
```

---

## Phase 0 — Critical Audit Fixes (חייב לסיים לפני Phase 1)

אלה 4 ממצאי הביקורת שחוסמים בנייה נכונה של כל הסוכנים.

### F1 — `scenarios.py` Rewrite (TA-35 → US)

**בעיה**: הקובץ הנוכחי בנוי סביב מדד TA-35 ואירועים ישראליים (גאופוליטיקה, בנק ישראל).  
**פתרון**: כתיבה מחדש מלאה ל-US options scenarios:

```python
# US scenarios to implement:
US_SCENARIOS = {
    "fed_rate_shock":    {"iv_jump": +0.40, "spot_move": -0.05},  # פד מעלה בהפתעה
    "earnings_beat":     {"iv_crush": -0.50, "spot_move": +0.08}, # Beat + IV crush
    "earnings_miss":     {"iv_spike": +0.30, "spot_move": -0.12}, # Miss
    "vix_spike":         {"iv_jump": +0.80, "spot_move": -0.15},  # VIX > 30
    "sector_rotation":   {"iv_mild": +0.15, "spot_move": -0.04},  # rotation out
    "black_swan":        {"iv_jump": +2.00, "spot_move": -0.30},  # 2020-style crash
}
```

**Owner**: SIGMA  
**Test**: כל 6 תרחישים מחזירים BS repricing תקין דרך `pricing.py` (לא לגעת)

---

### F2 — KEYNES → `scoring.py` Integration

**בעיה**: `economist.py` מחשב regime אבל `scoring.py` לא קורא אותו בכלל — שני עולמות מנותקים.  
**פתרון**: 2 שינויים קטנים עם השפעה גדולה:

```python
# economist.py — הוסף פונקציה:
def get_regime_multiplier(regime: str) -> float:
    return {
        "low_vol_bull":       1.15,  # קל יותר למצוא הזדמנויות
        "mid_vol_neutral":    1.00,  # baseline
        "high_vol_risk_off":  0.85,  # להיות שמרניים יותר
        "extreme_fear":       0.70,  # כמעט כל הזדמנות נדחית
    }.get(regime, 1.00)

# scoring.py — בפונקציית evaluate_option():
from .economist import get_regime_multiplier, classify_regime
regime_data = classify_regime()  # cached 30 min
multiplier = get_regime_multiplier(regime_data["regime"])
final_score = base_score * multiplier  # מוזרק לסוף החישוב
```

**Owner**: KEYNES + MAX (MAX יוודא שהמשקל הזה הגיוני בבדיקה היסטורית)

---

### F3 — Dynamic RISK_FREE from FRED

**בעיה**: `RISK_FREE = 0.045` מוקשת ב-`scoring.py`, `strategies.py`, `backtest.py`, `maof.py`.  
**פתרון**: קובץ חדש `rates.py` עם cache TTL 60 דקות:

```python
# engine/rates.py — NEW
import urllib.request, json
from functools import lru_cache
from datetime import datetime

_cache: dict = {}

def get_risk_free() -> float:
    """13-week T-bill rate from FRED (free, no API key). 
    Falls back to 0.045 if unavailable. Cache 60 min."""
    now = datetime.utcnow()
    if _cache.get("ts") and (now - _cache["ts"]).seconds < 3600:
        return _cache["rate"]
    try:
        url = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=DTB3"
        with urllib.request.urlopen(url, timeout=5) as r:
            lines = r.read().decode().strip().split("\n")
            last = lines[-1].split(",")
            rate = float(last[1]) / 100.0
        _cache.update({"rate": rate, "ts": now})
        return rate
    except Exception:
        return _cache.get("rate", 0.045)  # graceful fallback
```

**שינויים נדרשים לאחר יצירת rates.py**:
- `scoring.py:17` — `RISK_FREE = 0.045` → `from .rates import get_risk_free; RISK_FREE = get_risk_free()`
- `strategies.py:13` — אותו דבר
- `backtest.py` — כל מקום שמשתמש ב-RISK_FREE הקשיח
- `maof.py` — כל מקום שמשתמש ב-RISK_FREE הקשיח

**Owner**: VERIFY (VERIFY יאמת שהריבית עדכנית בכל ריצה)

---

### F4 — `strategies.py` Expansion

**בעיה**: רק 3 אסטרטגיות. Iron Condor, CSP, Covered Call, Straddle, LEAPS חסרים לחלוטין.  
**פתרון**: הוסף לפונקציה `build_strategy()` הקיימת:

```python
# strategies.py — build_strategy() additions:

if strategy == "iron_condor":
    # Short OTM Call + Long further OTM Call + Short OTM Put + Long further OTM Put
    width = max(1, round(S * 0.05))
    return [
        {"K": atm + width,     "kind": "call", "qty": -1},  # short call
        {"K": atm + 2*width,   "kind": "call", "qty": +1},  # long call (protection)
        {"K": atm - width,     "kind": "put",  "qty": -1},  # short put
        {"K": atm - 2*width,   "kind": "put",  "qty": +1},  # long put (protection)
    ]

if strategy == "cash_secured_put":  # CSP
    return [{"K": round(S * 0.95), "kind": "put", "qty": -1}]

if strategy == "covered_call":
    # הנחה: המשתמש מחזיק 100 מניות (delta=1 implicit)
    return [{"K": round(S * 1.05), "kind": "call", "qty": -1}]

if strategy == "straddle":
    return [
        {"K": atm, "kind": "call", "qty": 1},
        {"K": atm, "kind": "put",  "qty": 1},
    ]

if strategy == "leaps":
    # LEAPS = long call עם DTE > 183 (מוגדר ב-scoring.py)
    return [{"K": round(S * 0.90), "kind": "call", "qty": 1}]
```

**Owner**: SIGMA  
**Test**: כל אסטרטגיה עוברת `pnl_curve()` ומחזירה breakeven תקין

---

## Phase 1 — Infrastructure (שבוע 1, אחרי Phase 0)

### 1.1 — `contracts.py` (NEW)
כל ה-TypedDict schemas מה-section "Data Contracts" למעלה — קובץ אחד, אמת יחידה.

### 1.2 — `rates.py` (NEW)
כבר מוגדר ב-F3 למעלה. נוצר כחלק מ-Phase 0.

### 1.3 — VERIFY Agent (`verify.py`)
גורם לריצה אוטומטית לפני כל backtest:
- בודק freshness של נתוני מחיר (לא ישנים מ-15 דקות בשעות מסחר)
- בודק שIV > MIN_VALID_IV (0.05) — כבר קיים ב-scoring.py, מרכז כאן
- בודק רצף תאריכים בהיסטוריה (אין gaps > 5 ימים)
- מחזיר `DataQualityReport` עם `risk_free_rate` מ-`rates.py`

### 1.4 — ATLAS Skeleton (`atlas.py`)
בשלב זה: רק ה-orchestration flow. לא AI. Pure Python coordinator:
```python
def analyze(ticker: str, client_profile: dict, flags: dict) -> AnalysisPackage:
    quality = VERIFY.run(ticker)
    if not quality["passed"]: return error_package(quality)
    regime  = KEYNES.classify_regime()
    events  = RADAR.get_events(ticker)
    strategies = SIGMA.recommend(ticker, regime, events)
    backtest   = MAX.validate(strategies, ticker)
    risk       = GUARDIAN.assess(backtest, client_profile)
    technicals = LENS.signals(ticker, confidence=backtest["confidence"])
    explanation = CLARITY.explain(AnalysisPackage(...))
    canvas_url  = CANVAS.render(explanation)
    return AnalysisPackage(...)
```

---

## Phase 2 — Quantitative Core (שבוע 1–2)

### 2.1 — KEYNES Enhancement
`economist.py` כבר קיים עם VIX, yield curve, VRP. להוסיף:
- `get_regime_multiplier(regime) -> float` (מוגדר ב-F2)
- Fed stance detection מ-FRED (`FEDFUNDS` series)
- TTL cache 30 דקות (כרגע אין cache)
- החזרת `MacroRegime` TypedDict מ-contracts.py

### 2.2 — MAX Enhancement (ALPHA/BETA dual validators)
`backtest.py` קיים. להוסיף:
- **ALPHA validator**: מריץ backtest על in-sample (2022–2024)
- **BETA validator**: מריץ cross-validation על out-of-sample (2021, 2025)
- שניהם חייבים להסכים (win_rate deviation < 10%) → `alpha_beta_agreement: True`
- אם לא מסכימים → ATLAS מסמן "low confidence"

### 2.3 — SIGMA Completion
`strategies.py` כבר מורחב ב-F4. SIGMA מוסיף logic של בחירה:
```python
def recommend(ticker, regime, events) -> StrategyRecommendations:
    # בוחר אסטרטגיות מתאימות לפי:
    # - regime (low_vol → iron_condor; high_vol → straddle)
    # - events (לפני earnings → avoid short gamma)
    # - COMPASS profile (conservative → CSP/covered_call בלבד)
```

---

## Phase 3 — Intelligence Layer (שבוע 2)

### 3.1 — MIKI (`research.py`)
- מחפש ספרות אקדמית על אסטרטגיה שנבחרה ב-SIGMA
- WebSearch/Perplexity — ניתן להפעיל דרך Claude API tools
- מחזיר 3+ מקורות עם הצעות פרמטרים מבוססות ספרות
- ממצאים → MAX (MAX יוודא אם הפרמטרים שMIKI הציע מאומתים בבדיקה)

### 3.2 — LENS (minor update)
`technicals.py` קיים ועובד. שינוי אחד בלבד:
```python
# confidence now bounded by MAX's backtest confidence
def signals(ticker, confidence: float = 1.0) -> TechnicalSignal:
    raw = technical_summary(ticker)
    return {**raw, "confidence": min(raw["confidence"], confidence)}
```

### 3.3 — GUARDIAN (`guardian.py`)
Kelly Criterion + risk spectrum:
```python
def assess(backtest: BacktestResult, account_size: float, profile: dict) -> RiskAssessment:
    w = backtest["win_rate"]
    r = backtest["avg_return"]  # reward/risk ratio
    kelly = w - (1 - w) / r if r > 0 else 0
    half_kelly = kelly / 2     # conservative standard: half-Kelly
    
    risk_multiplier = {"conservative": 0.5, "moderate": 1.0, "aggressive": 1.5}
    final_fraction = half_kelly * risk_multiplier.get(profile["risk_level"], 1.0)
    return RiskAssessment(kelly_fraction=final_fraction, ...)
```

### 3.4 — COMPASS (`compass.py`)
Rule-based (לא AI). מסנן אסטרטגיות לא מתאימות:
```python
CONSERVATIVE_ALLOWED = ["cash_secured_put", "covered_call", "bull_spread"]
MODERATE_ALLOWED     = CONSERVATIVE_ALLOWED + ["long_call", "iron_condor"]
AGGRESSIVE_ALLOWED   = MODERATE_ALLOWED + ["ratio_spread", "straddle", "leaps"]

def filter_strategies(strategies: list, profile: dict) -> list:
    allowed = globals()[f"{profile['risk_level'].upper()}_ALLOWED"]
    return [s for s in strategies if s["type"] in allowed]
```

---

## Phase 4 — Context & Events (שבוע 2)

### 4.1 — RADAR (`radar.py`)
```python
def get_events(ticker: str) -> EventCalendar:
    earnings_date = _fetch_earnings(ticker)   # yfinance .calendar
    ex_div_date   = _fetch_ex_div(ticker)     # yfinance .info["exDividendDate"]
    fomc_dates    = _fetch_fomc()             # FRED / hardcoded 2025-2026 calendar
    days_to_earnings = (earnings_date - date.today()).days if earnings_date else None
    return EventCalendar(
        days_to_earnings=days_to_earnings,
        earnings_risk=days_to_earnings < 14 if days_to_earnings else False,
        ex_div_risk=...,
        next_fomc=...,
        fomc_risk=days_to_fomc < 7 if days_to_fomc else False
    )
```

### 4.2 — SCOUT (`scout.py`)
מחקר תחרותי — מריץ WebSearch (Claude API tool) על:
- "institutional options screening tools [year]"
- "Bloomberg ORATS Quantcha comparison"
- מחזיר `CompetitiveInsights` — משמש בעיקר ל-CANVAS (הצגה בבנק)

---

## Phase 5 — Output Layer (שבוע 2–3)

### 5.1 — CLARITY (`clarity.py`)
שלוש שכבות הסבר בנפרד — שימוש ב-Claude API:
```python
ADVISOR_PROMPT  = "הסבר טכני בעברית ליועץ השקעות מנוסה: {analysis}"
CLIENT_PROMPT   = "הסבר פשוט בעברית ללקוח, ללא ז'רגון: {analysis}"
REGULATOR_PROMPT = "Formal English explanation for regulatory documentation: {analysis}"

def explain(package: AnalysisPackage) -> ExplanationBundle:
    # Parallel API calls
    return ExplanationBundle(
        advisor_layer=claude(ADVISOR_PROMPT, package),
        client_layer=claude(CLIENT_PROMPT, package),
        regulator_layer=claude(REGULATOR_PROMPT, package),
        decision_support_disclaimer=REQUIRED_DISCLAIMER  # חובה תמיד
    )
```

### 5.2 — CANVAS (`canvas.py`)
10 שקפים קבועים (לפי התחייבות מ-project_commitments.md):

| # | שקף | תוכן |
|---|-----|-------|
| 1 | Executive Summary | מניה, ציון, regime מאקרו |
| 2 | Macro Context | KEYNES — VIX, yield curve, VRP |
| 3 | Technical Analysis | LENS — MACD, RSI, Bollinger |
| 4 | Options Strategy | SIGMA — אסטרטגיה מומלצת, Greeks |
| 5 | Risk Assessment | GUARDIAN — Kelly, max loss, stop-loss |
| 6 | Backtest Results | MAX — win rate, Sharpe, drawdown |
| 7 | Event Calendar | RADAR — earnings, ex-div, FOMC |
| 8 | Client Suitability | COMPASS — מתאים/לא מתאים + הסבר |
| 9 | Competitive Context | SCOUT — השוואה לכלים מוסדיים |
| 10 | Disclaimer | חובה: decision-support only |

---

## Phase 6 — Orchestration (שבוע 3)

### 6.1 — ATLAS Full (`atlas.py`)
הפוך מה-skeleton ל-orchestrator מלא:
- parallel dispatch (asyncio.gather לכל סוכני Layer 1)
- error handling per agent (אם MIKI נכשל — ממשיכים; אם VERIFY נכשל — עוצרים)
- context aggregation ל-AnalysisPackage
- endpoint חדש ב-app.py: `POST /api/agents/analyze`

### 6.2 — Frontend integration
טאב חדש ב-App.jsx: "ניתוח מלא" — שולח ל-`/api/agents/analyze` ומציג את ה-CANVAS deck

---

## Build Order Summary

```
Week 1:  Phase 0 (F1+F2+F3+F4) → Phase 1 (contracts + rates + VERIFY + ATLAS skeleton)
Week 2:  Phase 2 (KEYNES+MAX+SIGMA) → Phase 3 (MIKI+LENS+GUARDIAN+COMPASS)
         Phase 4 (RADAR+SCOUT)
Week 3:  Phase 5 (CLARITY+CANVAS) → Phase 6 (ATLAS full + Frontend)
Demo:    2026-07-05 — פגישה עם סגן מנהל הסקטור
```

---

## Deliverables for 2026-07-05 Demo

| מה | מי | status |
|----|-----|--------|
| MIKI: 3+ מקורות + הצעות פרמטרים | MIKI | ⏳ |
| MAX: baseline על 100+ מניות | MAX | ⏳ |
| CANVAS: מצגת 10 שקפים | CANVAS | ⏳ |
| הדגמה חיה: ניתוח מניה אחת מקצה לקצה | ATLAS | ⏳ |

---

## Constitution Gates

1. ✅ Decision-support only — כל output כולל disclaimer. CLARITY מחויב לכלול `decision_support_disclaimer`
2. ✅ Secrets ב-.env בלבד — FRED API (free, אין key). Claude API key ב-`ANTHROPIC_API_KEY` (כבר ב-.env)
3. ✅ Push to GitHub בכל milestone — Phase 0 → push. Phase 2 → push. Phase 5 → push.
4. ✅ No .claude/ בתוך הפרויקט — כל הסוכנים ב-backend/engine/ בלבד
5. ✅ pricing.py לא נגעים — כל הסוכנים יורשים דרכו, לא מחליפים אותו

---

*מסמך זה מכסה את Phase 0 (תיקונים קריטיים) ו-Phases 1–6 (13 הסוכנים). השלב הבא: `/speckit.tasks` — פירוק כל phase למשימות ממוספרות עם acceptance criteria.*
