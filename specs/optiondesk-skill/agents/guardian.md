# GUARDIAN — Risk Manager ⭐

**קובץ**: `backend/engine/guardian.py` NEW  
**Contract**: `RiskAssessment` (ראה contracts.py)

## Build Mode

```python
# engine/guardian.py
RISK_MULTIPLIERS = {"conservative":0.50, "moderate":1.00, "aggressive":1.50}
MAX_POSITION_PCT = {"conservative":0.05, "moderate":0.10, "aggressive":0.20}

def assess(backtest: BacktestResult, client_profile: dict) -> RiskAssessment:
    w  = backtest["win_rate"]
    r  = backtest["avg_return"]       # reward/risk ratio
    acc = client_profile.get("account_size_usd", 100_000)
    lvl = client_profile.get("risk_level", "moderate")
    
    kelly_full  = w - (1-w)/r if r > 0 else 0
    kelly_half  = max(0, kelly_full / 2)
    kelly_adj   = kelly_half * RISK_MULTIPLIERS.get(lvl, 1.0)
    kelly_final = min(kelly_adj, MAX_POSITION_PCT.get(lvl, 0.10))
    
    # Extra caution: low MAX confidence → halve again
    if backtest.get("confidence", 1.0) < 0.5:
        kelly_final /= 2
    
    position = acc * kelly_final
    return RiskAssessment(
        kelly_fraction=round(kelly_final,4),
        position_size_usd=round(position,0),
        risk_level=lvl,
        max_loss_scenario=round(position * abs(backtest["max_drawdown"]),0),
        stop_loss=round(position * 0.50, 0)
    )
```

### כלל ברזל
- Kelly שלילי → fraction=0
- Conservative: לעולם לא > 5% מהחשבון
- GUARDIAN מציג — החלטה היא של היועץ

### Acceptance Criteria
- [ ] Kelly formula: `f* = w - (1-w)/r`
- [ ] Conservative cap: ≤ 5%
- [ ] Kelly שלילי → fraction=0
- [ ] confidence < 0.5 → fraction /= 2

## Run Mode: `guardian win_rate=<W> avg_return=<R> account=<USD> risk=<LEVEL>`
הרץ `assess()`, הצג RiskAssessment.
