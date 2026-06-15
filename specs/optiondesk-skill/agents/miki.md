# MIKI — Research Intelligence

**קובץ**: `backend/engine/research.py` NEW  
**Contract**: `ResearchFindings` (ראה contracts.py)  
**Demo**: ≥ 3 מקורות + פרמטרים מוכחים עד 2026-07-05

## Build Mode

```python
# engine/research.py
import os, json, re, anthropic
from .contracts import ResearchFindings

_client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
MODEL = "claude-sonnet-4-6"   # MIKI צריך יכולת חיפוש + סינתזה

PROMPT = """חוקר שוקי אופציות. חפש ספרות אקדמית על: {query}
החזר JSON בלבד:
{{"sources": [{{"title":"..","year":..,"journal":"..","finding":".."}}],
  "key_findings": [".."],
  "suggested_params": {{"dte": int, "otm_pct": float, "target_profit": float}},
  "literature_verdict": "supports|against|neutral|inconclusive"}}
מינימום 3 מקורות. SSRN, Journal of Finance, Journal of Derivatives, Risk."""

def search(query: str, strategy: str = None) -> ResearchFindings:
    full = f"{strategy} options strategy {query}" if strategy else query
    msg = _client.messages.create(model=MODEL, max_tokens=1024,
        tools=[{"type":"web_search","name":"web_search"}],
        messages=[{"role":"user","content":PROMPT.format(query=full)}])
    raw = msg.content[0].text
    try:
        data = json.loads(re.search(r'\{.*\}', raw, re.DOTALL).group())
    except Exception:
        data = {"sources":[],"key_findings":[raw[:500]],"suggested_params":{},"literature_verdict":"inconclusive"}
    return ResearchFindings(query=full, **data)
```

### Demo Deliverable (SC-005)
על `iron_condor` + `tech stocks`:
- ≥ 3 מקורות עם citations
- `suggested_params`: DTE, otm_pct, target_profit
- `literature_verdict`: "supports"

### Acceptance Criteria
- [ ] `search("iron condor")` → `len(sources) >= 3`
- [ ] `suggested_params` מכיל DTE + otm_pct
- [ ] runtime < 30 שניות

## Run Mode: `miki strategy=<S> [query=<Q>]`
הרץ `search()`, הצג ResearchFindings עם citations.
