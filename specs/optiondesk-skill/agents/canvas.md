# CANVAS — Design & Presentation

**קובץ**: `backend/engine/canvas.py` NEW + `backend/templates/slide_deck.html`  
**Design System**: #16c75e (ירוק), #ef4f6b (אדום), #f5b740 (ענבר), #0a0e0c (רקע)  
**חובה**: 10 שקפים קבועים, Slide 10 = disclaimer בלבד, RTL עברית

## Build Mode

### canvas.py
```python
# engine/canvas.py
import os
from jinja2 import Environment, FileSystemLoader
TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), "../../templates")

def render(package) -> str:
    env = Environment(loader=FileSystemLoader(TEMPLATE_DIR))
    return env.get_template("slide_deck.html").render(package=package)

def render_pdf(package) -> bytes:
    from weasyprint import HTML
    return HTML(string=render(package)).write_pdf()
```

### 10 שקפים (לא לשנות)
| # | תוכן | מקור |
|---|------|-------|
| 1 | Executive Summary: ticker, strategy, regime, confidence | ATLAS |
| 2 | Macro Context: VIX, yield_curve, VRP, fed_stance | KEYNES |
| 3 | Technical Analysis: RSI, MACD, Bollinger | LENS |
| 4 | Options Strategy: legs, Greeks, cost, max_gain | SIGMA |
| 5 | Risk Assessment: kelly, position_size, stop_loss | GUARDIAN |
| 6 | Backtest Results: win_rate, Sharpe, drawdown, agreement | MAX |
| 7 | Event Calendar: earnings, ex-div, FOMC risks | RADAR |
| 8 | Client Suitability: suitable/unsuitable + explanation | COMPASS |
| 9 | Competitive Context: vs Bloomberg/ORATS/Quantcha | SCOUT |
| **10** | **Disclaimer + © EILON STERN** | **MANDATORY** |

### Acceptance Criteria
- [ ] HTML מכיל בדיוק 10 slides
- [ ] Slide 10 = disclaimer בלבד + EILON STERN
- [ ] `<html dir="rtl" lang="he">`
- [ ] Design System: #16c75e, #ef4f6b, #0a0e0c
- [ ] runtime < 15 שניות (HTML)

## Run Mode: `canvas ticker=<TICKER> [format=html|pdf]`
קרא canvas.py + templates/slide_deck.html, הצג preview של כל 10 שקפים.
