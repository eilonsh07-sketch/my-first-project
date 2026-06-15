# CLARITY — Explainability ⭐

**קובץ**: `backend/engine/clarity.py` NEW  
**Contract**: `ExplanationBundle` (ראה contracts.py)  
**API**: Claude Haiku (anthropic — כבר ב-requirements.txt)

## Build Mode

```python
# engine/clarity.py
import os, anthropic
from .contracts import AnalysisPackage, ExplanationBundle

_client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
MODEL = "claude-haiku-4-5-20251001"   # מהיר + זול

DISCLAIMER = (
    'הניתוח הנ"ל הינו עזר להחלטה בלבד ואינו מהווה ייעוץ השקעות. '
    'החלטת ביצוע ההשקעה נתונה לשיקול דעתו הבלעדי של היועץ המורשה.'
)

def explain(package: AnalysisPackage) -> ExplanationBundle:
    s = _summary(package)
    # 3 קריאות במקביל (threading)
    from concurrent.futures import ThreadPoolExecutor
    prompts = {
        "advisor":   f"הסבר טכני בעברית ליועץ השקעות. 3-4 משפטים מקצועיים. {s}",
        "client":    f"הסבר פשוט בעברית ללקוח, ללא ז'רגון. 2-3 משפטים. {s}",
        "regulator": f"Formal English regulatory summary, 3-4 sentences. {s}",
    }
    with ThreadPoolExecutor(max_workers=3) as ex:
        futures = {k: ex.submit(_call, v) for k, v in prompts.items()}
        results = {k: f.result() for k, f in futures.items()}
    
    return ExplanationBundle(
        advisor_layer=results["advisor"],
        client_layer=results["client"],
        regulator_layer=results["regulator"],
        key_risks=_risks(package),
        decision_support_disclaimer=DISCLAIMER
    )

def _call(prompt: str) -> str:
    msg = _client.messages.create(model=MODEL, max_tokens=512,
        messages=[{"role":"user","content":prompt}])
    return msg.content[0].text

def _summary(p): 
    return (f"מניה:{p['ticker']}, אסטרטגיה:{p['strategies']['preferred']}, "
            f"regime:{p['regime']['regime']}, win_rate:{p['backtest']['win_rate']:.0%}, "
            f"kelly:{p['risk']['kelly_fraction']:.1%}")

def _risks(p) -> list:
    r = []
    if p["events"].get("earnings_risk"): r.append("earnings < 14 ימים")
    if p["regime"]["regime"] == "extreme_fear": r.append("extreme fear regime")
    if p["risk"]["kelly_fraction"] > 0.15: r.append("גודל פוזיציה גבוה")
    return r
```

### כלל ברזל
`decision_support_disclaimer` חייב תמיד — לעולם לא None, לא "".

### Acceptance Criteria
- [ ] 3 שכבות תמיד מאוכלסות
- [ ] disclaimer לא ריק
- [ ] runtime < 10 שניות (3 קריאות במקביל)
- [ ] advisor_layer בעברית

## Run Mode: `clarity ticker=<T> strategy=<S> win_rate=<W> kelly=<K> regime=<R>`
בנה summary, הרץ `explain()`, הצג ExplanationBundle.
