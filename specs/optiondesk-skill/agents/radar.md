# RADAR — Timing & Events

**קובץ**: `backend/engine/radar.py` NEW  
**Contract**: `EventCalendar` (ראה contracts.py)  
**משפיע על**: SIGMA (מסנן אסטרטגיות לפני earnings/FOMC)

## Build Mode

```python
# engine/radar.py
from datetime import date, datetime
import yfinance as yf
from .contracts import EventCalendar

FOMC_2026 = [date(2026,1,28),date(2026,3,18),date(2026,4,29),date(2026,6,17),
             date(2026,7,29),date(2026,9,16),date(2026,10,28),date(2026,12,9)]

def get_events(ticker: str) -> EventCalendar:
    today = date.today()
    t = yf.Ticker(ticker)
    
    ed = _earnings(t, today)
    dte = (ed - today).days if ed else None
    
    xd = _ex_div(t, today)
    dtx = (xd - today).days if xd else None
    
    nf = min((f for f in FOMC_2026 if f >= today), default=None)
    dtf = (nf - today).days if nf else None
    
    e_risk  = dte is not None and dte < 14
    x_risk  = dtx is not None and dtx < 7
    f_risk  = dtf is not None and dtf < 7
    
    return EventCalendar(
        ticker=ticker,
        next_earnings=ed.isoformat() if ed else None, days_to_earnings=dte, earnings_risk=e_risk,
        next_ex_div=xd.isoformat() if xd else None,  days_to_ex_div=dtx,  ex_div_risk=x_risk,
        next_fomc=nf.isoformat() if nf else None,    days_to_fomc=dtf,    fomc_risk=f_risk,
        any_risk=e_risk or x_risk or f_risk
    )

def _earnings(t, today):
    try:
        dates = t.calendar.get("Earnings Date",[])
        future = [d.date() if hasattr(d,'date') else d for d in dates if hasattr(d,'date') and d.date() >= today or d >= today]
        return min(future) if future else None
    except: return None

def _ex_div(t, today):
    try:
        ts = t.info.get("exDividendDate")
        d = date.fromtimestamp(ts) if ts else None
        return d if d and d >= today else None
    except: return None
```

### Acceptance Criteria
- [ ] AAPL → `next_earnings` not None
- [ ] earnings < 14 ימים → `earnings_risk=True`
- [ ] FOMC < 7 ימים → `fomc_risk=True`

## Run Mode: `radar ticker=<TICKER>`
הרץ `get_events(ticker)`, הצג EventCalendar עם risk flags.
