# OptionDesk — Data Contracts (TypedDicts)

**קובץ**: `backend/engine/contracts.py` (NEW — צריך לייצר)  
**כלל**: כל TypedDict מוגדר פה ורק פה. כל סוכן מייבא מ-contracts.py.

```python
# engine/contracts.py
from typing import TypedDict, Optional, Literal

class DataQualityReport(TypedDict):
    passed: bool
    issues: list[str]
    risk_free_rate: float          # מ-FRED, מועבר לכל סוכן שצריך
    data_freshness: dict           # {ticker: timestamp}

class MacroRegime(TypedDict):
    regime: Literal["low_vol_bull","mid_vol_neutral","high_vol_risk_off","extreme_fear"]
    vix: float
    yield_curve: float             # 10yr - 2yr spread
    fed_stance: Literal["easing","neutral","tightening"]
    vrp: float                     # VIX minus SPY realized_vol_30d
    regime_multiplier: float       # 0.70–1.15 → מוזרק לscoring.py
    cached_at: str

class BacktestResult(TypedDict):
    strategy: str
    win_rate: float
    avg_return: float              # reward/risk ratio (e.g. 1.8x)
    sharpe: float
    max_drawdown: float
    validated_params: dict         # {"risk_free": float, "alpha_period": tuple}
    confidence: float              # 0–1, מועבר לLENS
    alpha_beta_agreement: bool     # ALPHA vs BETA validators agree

class StrategyRecommendations(TypedDict):
    strategies: list[dict]         # top 3: [{type, legs, regime_fit}]
    preferred: str                 # top pick after COMPASS + events filter
    event_adjusted: bool           # האם RADAR השפיע על הבחירה

class RiskAssessment(TypedDict):
    kelly_fraction: float          # אחוז מהחשבון (0–0.20 max)
    position_size_usd: float
    risk_level: str
    max_loss_scenario: float       # worst case בדולרים
    stop_loss: float               # 50% of position (אופציות standard)

class TechnicalSignal(TypedDict):
    ticker: str
    rsi: Optional[float]
    macd_signal: str               # "bullish" | "bearish" | "neutral"
    bollinger_position: str        # "above" | "below" | "middle"
    trend: str                     # "up" | "down" | "sideways"
    confidence: float              # = min(lens_raw, MAX.confidence)
    raw_confidence: float          # LENS's own assessment (before bounding)
    summary_he: str

class SuitabilityReport(TypedDict):
    risk_level: str
    suitable: list[str]
    unsuitable: list[str]
    explanations: dict             # {strategy: reason}
    recommended: Optional[str]
    regulatory_note: str           # "סינון לפי פרופיל X — מזרחי-טפחות"

class CompetitiveInsights(TypedDict):
    strategy: str
    tools_compared: list[dict]     # [{name, signal_quality, cost, differentiator}]
    optiondesk_advantage: str
    gap_to_close: str
    summary_for_slide: str         # לslide 9 ב-CANVAS

class ResearchFindings(TypedDict):
    query: str
    sources: list[dict]            # [{title, year, journal, finding}]
    key_findings: list[str]
    suggested_params: dict         # {dte: int, otm_pct: float, ...}
    literature_verdict: str        # "supports" | "against" | "neutral" | "inconclusive"

class EventCalendar(TypedDict):
    ticker: str
    next_earnings: Optional[str]   # ISO date
    days_to_earnings: Optional[int]
    earnings_risk: bool            # True אם < 14 ימים
    next_ex_div: Optional[str]
    days_to_ex_div: Optional[int]
    ex_div_risk: bool              # True אם < 7 ימים
    next_fomc: Optional[str]
    days_to_fomc: Optional[int]
    fomc_risk: bool                # True אם < 7 ימים
    any_risk: bool                 # OR of all risks

class ExplanationBundle(TypedDict):
    advisor_layer: str             # עברית טכנית — ליועץ
    client_layer: str              # עברית פשוטה — ללקוח
    regulator_layer: str           # אנגלית פורמלי — לרגולטור
    key_risks: list[str]
    decision_support_disclaimer: str  # MANDATORY — תמיד מלא

class AnalysisPackage(TypedDict):   # ATLAS assembles this
    ticker: str
    data_quality: DataQualityReport
    regime: MacroRegime
    strategies: StrategyRecommendations
    backtest: BacktestResult
    risk: RiskAssessment
    technicals: TechnicalSignal
    suitability: SuitabilityReport
    events: EventCalendar
    research: Optional[ResearchFindings]
    competitive: Optional[CompetitiveInsights]
    explanation: ExplanationBundle
    presentation_url: Optional[str]
```
