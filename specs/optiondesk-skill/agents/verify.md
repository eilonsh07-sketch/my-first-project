# VERIFY — Data Quality Gate

**קובץ**: `backend/engine/verify.py` NEW  
**Contract**: `DataQualityReport` (ראה contracts.py)  
**מתי רץ**: תמיד ראשון — ATLAS לא ממשיך אם נכשל

## Build Mode

### מה לממש
```python
# engine/verify.py
from .rates import get_risk_free   # F3 חייב להיות קיים קודם!
from .provider import PROVIDER

def run(ticker: str) -> DataQualityReport:
    issues = []
    info = PROVIDER.info_light(ticker)
    
    if _data_stale(info):          # > 15 דק' בשעות מסחר
        issues.append(f"נתוני {ticker} ישנים")
    
    iv = info.get("impliedVolatility", 0)
    if iv and 0 < iv < 0.05:       # MIN_VALID_IV
        issues.append(f"IV={iv:.4f} לא אמין (< 0.05)")
    
    hist = PROVIDER.history(ticker, "3mo")
    if hist is not None and _has_gap(hist):
        issues.append("פערים בהיסטוריה > 5 ימים")
    
    return DataQualityReport(
        passed=len(issues) == 0,
        issues=issues,
        risk_free_rate=get_risk_free(),
        data_freshness={ticker: str(info.get("regularMarketTime", "?"))}
    )
```

### תלויות (חייבות לקום קודם)
- `rates.py` (F3) — `get_risk_free()`
- `contracts.py` (Phase 1) — `DataQualityReport`

### Acceptance Criteria
- [ ] AAPL בשעות מסחר → `passed=True`
- [ ] ticker לא קיים → `passed=False`, issue ב-`issues`
- [ ] `risk_free_rate` תמיד מוחזר (fallback 0.045)
- [ ] runtime < 2 שניות

## Run Mode: `verify ticker=<TICKER>`
קרא verify.py, הרץ `run(ticker)`, הצג DataQualityReport.
