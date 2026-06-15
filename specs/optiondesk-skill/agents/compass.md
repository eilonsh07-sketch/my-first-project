# COMPASS — Client Suitability

**קובץ**: `backend/engine/compass.py` NEW  
**Contract**: `SuitabilityReport` (ראה contracts.py)  
**הערה**: Rule-based בלבד — ללא AI, ללא LLM

## Build Mode

```python
# engine/compass.py
from .contracts import SuitabilityReport

CONSERVATIVE = ["cash_secured_put","covered_call","bull_spread"]
MODERATE     = CONSERVATIVE + ["long_call","iron_condor"]
AGGRESSIVE   = MODERATE    + ["ratio_spread","straddle","leaps"]

ALLOWED = {"conservative":CONSERVATIVE, "moderate":MODERATE, "aggressive":AGGRESSIVE}

WHY = {
    "cash_secured_put": "מכירת PUT מגובה במזומן — הכנסה שוטפת, סיכון מוגבל",
    "covered_call":     "מכירת CALL על מניה מוחזקת — הגנה חלקית",
    "bull_spread":      "ספריד עולה — תקרת רווח + סיכון ידועים",
    "long_call":        "קנית CALL — סיכון מוגבל לפרמיה",
    "iron_condor":      "Iron Condor — הכנסה בשוק רגוע, סיכון מוגבל",
    "ratio_spread":     "Ratio Spread — סיכון בלתי מוגבל בקצוות",
    "straddle":         "Straddle — רווח מתנודתיות, עלות גבוהה",
    "leaps":            "LEAPS — טווח ארוך, הון גדול נדרש",
}

def filter_strategies(strategies: list, client_profile: dict) -> SuitabilityReport:
    lvl     = client_profile.get("risk_level", "moderate")
    allowed = ALLOWED.get(lvl, MODERATE)
    suitable   = [s for s in strategies if s in allowed]
    unsuitable = [s for s in strategies if s not in allowed]
    return SuitabilityReport(
        risk_level=lvl,
        suitable=suitable, unsuitable=unsuitable,
        explanations={s: WHY.get(s,"") for s in strategies},
        recommended=suitable[0] if suitable else None,
        regulatory_note=f"סינון לפי פרופיל {lvl} — בנק מזרחי-טפחות"
    )
```

### Acceptance Criteria
- [ ] conservative → רק 3 אסטרטגיות
- [ ] aggressive → כל 8
- [ ] `regulatory_note` מכיל "מזרחי-טפחות"

## Run Mode: `compass strategies=<s1,s2,...> risk=<LEVEL>`
הרץ `filter_strategies()`, הצג SuitabilityReport.
