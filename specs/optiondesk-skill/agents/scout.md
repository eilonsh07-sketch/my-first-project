# SCOUT — Competitive Intelligence

**קובץ**: `backend/engine/scout.py` NEW  
**Contract**: `CompetitiveInsights` (ראה contracts.py)  
**מטרה עיקרית**: Slide 9 ב-CANVAS — להראות לבנק שאנחנו מכירים את הנוף המוסדי

## Build Mode

```python
# engine/scout.py
import os, json, re, anthropic
from .contracts import CompetitiveInsights

_client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
MODEL = "claude-haiku-4-5-20251001"

PROMPT = """Compare institutional options analysis tools for strategy: {strategy}
Tools: Bloomberg ORATS, Quantcha, Barchart Options, OptionDesk (Hebrew RTL, Mizrahi-Tefahot Bank).
Return JSON only:
{{"tools":[{{"name":"..","signal_quality":"1-5","cost":"..","differentiator":".."}}],
  "optiondesk_advantage":"..","gap_to_close":"..","summary_for_slide":".."}}"""

def search(strategy: str) -> CompetitiveInsights:
    msg = _client.messages.create(model=MODEL, max_tokens=800,
        tools=[{"type":"web_search","name":"web_search"}],
        messages=[{"role":"user","content":PROMPT.format(strategy=strategy)}])
    raw = msg.content[0].text
    try:
        data = json.loads(re.search(r'\{.*\}', raw, re.DOTALL).group())
    except Exception:
        data = {"tools":[],"optiondesk_advantage":raw[:200],"gap_to_close":"N/A",
                "summary_for_slide":"OptionDesk — ניתוח כמותי מוסדי בעברית"}
    return CompetitiveInsights(strategy=strategy, **data)
```

### Acceptance Criteria
- [ ] `tools_compared` ≥ 2 כלים
- [ ] `optiondesk_advantage` מזכיר Hebrew/RTL/Mizrahi
- [ ] `summary_for_slide` מוכן לשימוש ישיר ב-CANVAS

## Run Mode: `scout strategy=<STRATEGY>`
הרץ `search(strategy)`, הצג CompetitiveInsights.
