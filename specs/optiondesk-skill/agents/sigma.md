# SIGMA — Options Specialist ⭐

**קובץ**: `backend/engine/strategies.py` EXPAND  
**Contract**: `StrategyRecommendations` (ראה contracts.py)  
**גם בבעלות**: F4 (5 אסטרטגיות חסרות) + F1 (scenarios.py rewrite)

## Build Mode

### F4 — הוסף ל-build_strategy()
```python
# strategies.py — החלף RISK_FREE = 0.045 ב:
from .rates import get_risk_free

if strategy == "iron_condor":
    w = max(1, round(S * 0.05))
    return [{"K": atm+w,"kind":"call","qty":-1},{"K": atm+2*w,"kind":"call","qty":1},
            {"K": atm-w,"kind":"put","qty":-1},{"K": atm-2*w,"kind":"put","qty":1}]
if strategy == "cash_secured_put":
    return [{"K": round(S*0.95), "kind":"put","qty":-1}]
if strategy == "covered_call":
    return [{"K": round(S*1.05), "kind":"call","qty":-1}]
if strategy == "straddle":
    return [{"K": atm,"kind":"call","qty":1},{"K": atm,"kind":"put","qty":1}]
if strategy == "leaps":
    return [{"K": round(S*0.90),"kind":"call","qty":1}]
```

### F1 — scenarios.py rewrite (ראה 03-AUDIT.md לקוד)
החלף TA-35 scenarios ב-6 US scenarios.

### recommend() — לוגיקת בחירה
```python
REGIME_PREFERRED = {
    "low_vol_bull":      ["iron_condor","covered_call","cash_secured_put"],
    "mid_vol_neutral":   ["bull_spread","long_call","iron_condor"],
    "high_vol_risk_off": ["straddle","cash_secured_put","bull_spread"],
    "extreme_fear":      ["cash_secured_put"],
}
def recommend(ticker, regime, events, client_profile) -> StrategyRecommendations:
    candidates = REGIME_PREFERRED.get(regime["regime"], ["bull_spread"])
    if events.get("earnings_risk"):
        candidates = [s for s in candidates if s not in ["iron_condor","ratio_spread"]]
    ...
```

### Acceptance Criteria
- [ ] 8 אסטרטגיות עוברות `pnl_curve()` ללא שגיאה
- [ ] `scenarios.py` — אין TA-35, יש 6 US scenarios
- [ ] `recommend()` מסנן iron_condor כשearn_risk=True

## Run Mode: `sigma ticker=<TICKER> [regime=<REGIME>] [events=earnings|clean]`
קרא strategies.py, הרץ `recommend()`, הצג top-3 אסטרטגיות + preferred.
