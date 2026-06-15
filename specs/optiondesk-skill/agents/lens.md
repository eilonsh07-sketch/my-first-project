# LENS — Technical Signals

**קובץ**: `backend/engine/technicals.py` MINOR UPDATE  
**Contract**: `TechnicalSignal` (ראה contracts.py)  
**כלל**: `final_confidence = min(lens_raw, MAX.confidence)` — LENS לא יתבע יותר ממה שMAX הוכיח

## Build Mode

### שינוי יחיד — הוסף wrapper לtechnicals.py
```python
# technicals.py — הוסף בסוף הקובץ:
from .contracts import TechnicalSignal

def signals(ticker: str, confidence: float = 1.0) -> TechnicalSignal:
    """LENS entry point. confidence = MAX.confidence (bounding)."""
    raw = technical_summary(ticker)
    sc  = technical_scorecard(raw)
    lens_raw = sc.get("confidence", 0.5)
    return TechnicalSignal(
        ticker=ticker,
        rsi=raw.get("rsi"),
        macd_signal=raw.get("macd_signal", "neutral"),
        bollinger_position=raw.get("bb_position", "middle"),
        trend=raw.get("trend", "sideways"),
        confidence=min(lens_raw, confidence),   # ← THE KEY RULE
        raw_confidence=lens_raw,
        summary_he=sc.get("summary_he", "")
    )
```

### Acceptance Criteria
- [ ] `signals("AAPL", confidence=0.5)` → `final_confidence ≤ 0.5`
- [ ] `raw_confidence` נשמר בoutput
- [ ] ללא שינויים לפונקציות קיימות ב-technicals.py

## Run Mode: `lens ticker=<TICKER> [confidence=<0-1>]`
קרא technicals.py, הרץ `signals(ticker, confidence)`, הצג TechnicalSignal.
