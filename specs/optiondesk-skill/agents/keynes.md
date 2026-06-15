# KEYNES — Macro Economist

**קובץ**: `backend/engine/economist.py` ENHANCE  
**Contract**: `MacroRegime` (ראה contracts.py)  
**בבעלות**: F2 (regime_multiplier → scoring.py)

## Build Mode

### שינויים ב-economist.py

**הוסף `get_regime_multiplier()`** (F2 — חיבור לscoring.py):
```python
REGIME_MULTIPLIERS = {
    "low_vol_bull":      1.15,
    "mid_vol_neutral":   1.00,
    "high_vol_risk_off": 0.85,
    "extreme_fear":      0.70,
}
def get_regime_multiplier(regime: str) -> float:
    return REGIME_MULTIPLIERS.get(regime, 1.00)
```

**שדרג `classify_regime()` להחזיר MacroRegime TypedDict**:
```python
def classify_regime() -> MacroRegime:
    vix    = _get_vix()
    curve  = _get_yield_curve()
    vrp    = _get_vrp()        # VIX - SPY_realized_vol_30d
    fed    = _get_fed_stance() # FEDFUNDS from FRED
    regime = _determine_regime(vix, curve)
    return MacroRegime(regime=regime, vix=vix, yield_curve=curve,
                       fed_stance=fed, vrp=vrp,
                       regime_multiplier=get_regime_multiplier(regime),
                       cached_at=datetime.utcnow().isoformat())
```

**הוסף TTL cache 30 דקות** (כרגע אין):
```python
_regime_cache = {"data": None, "ts": None}
def classify_regime_cached() -> MacroRegime:
    from datetime import datetime
    now = datetime.utcnow()
    if _regime_cache["ts"] and (now - _regime_cache["ts"]).seconds < 1800:
        return _regime_cache["data"]
    data = classify_regime()
    _regime_cache.update({"data": data, "ts": now})
    return data
```

**עדכן scoring.py** (F2 — אחרי economist.py מוכן):
```python
# scoring.py — בסוף evaluate_option(), לפני return:
from .economist import classify_regime_cached, get_regime_multiplier
try:
    regime = classify_regime_cached()
    final_score = base_score * regime["regime_multiplier"]
except Exception:
    final_score = base_score   # fallback: אל תשבור scoring
```

### Acceptance Criteria
- [ ] `get_regime_multiplier("extreme_fear")` = 0.70
- [ ] `classify_regime()` מחזיר MacroRegime TypedDict מלא
- [ ] Cache: 2 קריאות תוך 30 דק' → אותו object
- [ ] scoring.py מכיל import מ-economist ומפעיל multiplier

## Run Mode: `keynes run`
קרא economist.py, הרץ `classify_regime()`, הצג MacroRegime.
