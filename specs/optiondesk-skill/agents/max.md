# MAX — Quantitative Validation ⭐

**קובץ**: `backend/engine/backtest.py` ENHANCE  
**Contract**: `BacktestResult` (ראה contracts.py)  
**Demo**: baseline על ≥ 100 מניות עד 2026-07-05

## Build Mode

### מה לשנות ב-backtest.py
```python
from .rates import get_risk_free   # החלף כל RISK_FREE = 0.045

def validate(strategy: str, ticker: str) -> BacktestResult:
    rf = get_risk_free()
    
    # ALPHA: in-sample 2022-2024
    alpha = _run_backtest(strategy, ticker, ("2022-01-01","2024-12-31"), rf)
    
    # BETA: out-of-sample cross-validation
    beta_periods = [("2021-01-01","2021-12-31"), ("2025-01-01","2025-05-31")]
    beta = _aggregate([_run_backtest(strategy, ticker, p, rf) for p in beta_periods])
    
    agreement = abs(alpha["win_rate"] - beta["win_rate"]) < 0.10
    confidence = alpha["win_rate"] * (0.9 if not agreement else 1.0)
    
    return BacktestResult(
        strategy=strategy, win_rate=alpha["win_rate"],
        avg_return=alpha["avg_return"], sharpe=alpha["sharpe"],
        max_drawdown=alpha["max_drawdown"],
        validated_params={"risk_free": rf},
        confidence=confidence, alpha_beta_agreement=agreement
    )
```

### grep & fix
```bash
grep -n "RISK_FREE\|= 0\.045" backend/engine/backtest.py
# החלף כל מופע
```

### Acceptance Criteria
- [ ] `RISK_FREE = 0.045` לא קיים יותר בקובץ
- [ ] `alpha_beta_agreement` מחושב ומוחזר
- [ ] AAPL + bull_spread: win_rate > 0.5, confidence > 0
- [ ] runtime < 30 שניות

## Run Mode: `max ticker=<TICKER> strategy=<STRATEGY>`
קרא backtest.py, הרץ `validate(strategy, ticker)`, הצג BacktestResult.

**אסטרטגיות**: long_call, bull_spread, ratio_spread, iron_condor, cash_secured_put, covered_call, straddle, leaps
