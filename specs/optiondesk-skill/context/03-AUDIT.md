# OptionDesk — Audit Findings (Phase 0)

**חייבים לסיים לפני Phase 1.** בלי זה, כל הסוכנים נבנים על בסיס שגוי.

---

## F1 — `scenarios.py` → US options (SIGMA owns this)

**בעיה**: הקובץ בנוי סביב TA-35 ואירועים ישראליים.  
**פתרון**: כתיבה מחדש מלאה.

```python
# engine/scenarios.py — REWRITE
US_SCENARIOS = {
    "fed_rate_shock":    {"iv_delta": +0.40, "spot_pct": -0.05},
    "earnings_beat":     {"iv_delta": -0.50, "spot_pct": +0.08},
    "earnings_miss":     {"iv_delta": +0.30, "spot_pct": -0.12},
    "vix_spike":         {"iv_delta": +0.80, "spot_pct": -0.15},
    "sector_rotation":   {"iv_delta": +0.15, "spot_pct": -0.04},
    "black_swan":        {"iv_delta": +2.00, "spot_pct": -0.30},
}
def reprice_scenario(name, S, K, T, iv_base, kind):
    from .pricing import bs_price      # pricing.py — לא לשנות!
    from .rates import get_risk_free
    sc = US_SCENARIOS[name]
    return bs_price(S*(1+sc["spot_pct"]), K, T, get_risk_free(), iv_base*(1+sc["iv_delta"]), kind)
```

**Status**: ⏳ לא התחיל

---

## F2 — KEYNES → `scoring.py` integration (KEYNES owns this)

**בעיה**: `economist.py` מחשב regime אבל `scoring.py` לא קורא אותו — מנותקים.  
**פתרון**:

```python
# economist.py — הוסף:
def get_regime_multiplier(regime: str) -> float:
    return {"low_vol_bull": 1.15, "mid_vol_neutral": 1.00,
            "high_vol_risk_off": 0.85, "extreme_fear": 0.70}.get(regime, 1.00)

# scoring.py — בסוף evaluate_option(), לפני return:
from .economist import classify_regime, get_regime_multiplier
regime_data = _get_cached_regime()   # cache 30 min
final_score = base_score * get_regime_multiplier(regime_data["regime"])
```

**Status**: ⏳ לא התחיל

---

## F3 — Dynamic RISK_FREE from FRED (VERIFY owns this)

**בעיה**: `RISK_FREE = 0.045` קשיח ב-scoring.py, strategies.py, backtest.py, maof.py.  
**פתרון**: קובץ חדש `engine/rates.py`:

```python
# engine/rates.py — NEW
_cache = {}
def get_risk_free() -> float:
    from datetime import datetime
    import urllib.request
    now = datetime.utcnow()
    if _cache.get("ts") and (now - _cache["ts"]).seconds < 3600:
        return _cache["rate"]
    try:
        url = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=DTB3"
        with urllib.request.urlopen(url, timeout=5) as r:
            rate = float(r.read().decode().strip().split("\n")[-1].split(",")[1]) / 100
        _cache.update({"rate": rate, "ts": now})
        return rate
    except Exception:
        return _cache.get("rate", 0.045)
```

**אחרי rates.py — grep ותקן**:
```bash
grep -rn "RISK_FREE\|= 0\.045" backend/engine/
# החלף כל מופע ב: from .rates import get_risk_free; RISK_FREE = get_risk_free()
```

**Status**: ⏳ לא התחיל

---

## F4 — `strategies.py` Expansion (SIGMA owns this)

**בעיה**: רק 3 אסטרטגיות. חסרים: iron_condor, CSP, covered_call, straddle, leaps.  
**פתרון**: הוסף ל-`build_strategy()`:

| אסטרטגיה | legs |
|-----------|------|
| `iron_condor` | -OTM_call +OTM2_call -OTM_put +OTM2_put |
| `cash_secured_put` | -0.95*S put |
| `covered_call` | -1.05*S call (הנחה: מחזיק מניה) |
| `straddle` | +ATM_call +ATM_put |
| `leaps` | +0.90*S call, DTE > 183 |

**Status**: ⏳ לא התחיל
