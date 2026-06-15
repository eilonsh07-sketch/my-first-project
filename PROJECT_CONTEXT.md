# Project Context

## What This Is

An options-trading **decision-support tool** for US securities, built for an investment advisor at **Mizrahi-Tefahot Bank**. The tool surfaces analysis, signals, and data to help the advisor make better-informed decisions — it does not make or automate investment recommendations.

## Owner

- **Role:** Investment advisor
- **Organization:** Mizrahi-Tefahot Bank
- **Market:** US securities (options)

## Core Rules

1. **Decision-support only.** This tool assists human judgment — it never makes, automates, or presents output as investment advice. Regulatory compliance requires a human in the loop at every decision point.

2. **Secrets stay in `.env`.** All API keys, tokens, and credentials go in the `.env` file exclusively. Never hardcode them, never paste them in chat, never commit them to GitHub. The `.gitignore` already protects `.env`.

3. **Push to GitHub whenever something works.** Commit and push at each meaningful milestone — don't let working progress sit only on the local machine.

4. **Everything global, no project-level `.claude` folder.** Plugins, skills, and preferences live in `C:\Users\yuval\.claude\` and apply across all projects. Never create a `.claude/` folder inside this project directory.

5. **Perplexity prototype is a skeleton reference only.** A zipped Perplexity-generated prototype exists as a starting-point reference. The goal is to rebuild it to a significantly higher standard — not to preserve or port it as-is.

## Vision & Deployment Strategy

**Phase 1 (current):** Build the tool for personal use — the advisor uses it himself, validates that it generates real edge, and tracks whether it improves actual decisions. Only after proving personal value does he present it to management and adapt for broader use.

**What the tool must display:**
- Numerical scores (e.g. 85/100) for each strategy and setup
- Data-based probabilities (e.g. "68% historical win-rate on this setup")
- Return scenarios: best / base / worst case with dollar amounts
- Morning scan: a ranked list of trade ideas for the day

All outputs framed as data-based analysis for the advisor's judgment — the final decision is always his.

**The MAX Gate (critical integrity rule):**
Every score and probability shown to the user MUST be backed by evidence that MAX has validated scientifically — out-of-sample testing, walk-forward validation, statistical significance. A score of "85" without MAX validation is a pretty number with no foundation. No score is displayed to the user before MAX has proven it predicts correctly.

## What to Build

A **multi-agent decision-support system** for US options analysis. The architecture is 13 specialized agents orchestrated by a CEO agent (ATLAS), each with a defined role, a typed input/output contract, and a clear position in the pipeline.

### Architecture: 13 Agents in 4 Layers

| Layer | Agents | Role |
|-------|--------|------|
| 0 — Infrastructure | ATLAS, VERIFY | ATLAS orchestrates; VERIFY gates data quality before any analysis |
| 1 — Data & Macro | KEYNES, MIKI, RADAR | Macro regime (VIX/yield curve/VRP), academic research, earnings/FOMC calendar |
| 2 — Quant Core | MAX, SIGMA, LENS | MAX validates all scores out-of-sample; SIGMA selects strategies by regime; LENS provides technical signals bounded by MAX confidence |
| 3 — Risk & Suitability | GUARDIAN, COMPASS, SCOUT | Kelly-based position sizing; client risk-profile filtering; competitive context vs. Bloomberg/ORATS |
| 4 — Output | CLARITY, CANVAS | 3-layer explanations (advisor/client/regulator); 10-slide Hebrew RTL presentation |

### Shared Persistent Context

All agents read from a shared context directory (`specs/optiondesk-skill/context/`), backed by GitHub. No copy-pasting between sessions — any agent invoked via `/optiondesk` has immediate access to the full project state, all contracts, and the live build checklist (`BUILD_STATUS.md`).

### Two Usage Modes

**1. On-demand analysis** — advisor enters a ticker + client risk profile:
```
/optiondesk atlas ticker=AAPL profile=moderate
```
Full pipeline: VERIFY → KEYNES+RADAR+MIKI (parallel) → SIGMA → MAX → GUARDIAN → LENS → COMPASS → SCOUT → CLARITY → CANVAS

**2. Morning scan** — ATLAS scans a watchlist and returns a ranked list of trade ideas for the day, each with a MAX-validated score.

### What the Output Contains

Every analysis package produced by ATLAS includes:
- Strategy recommendation with a numerical score (e.g. 85/100) — computed by `scoring.py`, validated out-of-sample by MAX
- Win-rate and confidence — from MAX backtest (ALPHA + BETA validators must agree, diff < 10%)
- Return scenarios: best / base / worst case with dollar amounts
- Risk assessment: Kelly-sized position, max drawdown, Greeks exposure
- Client suitability note (COMPASS filter)
- 10-slide CANVAS presentation in Hebrew RTL, exportable to PDF
- Mandatory disclaimer on every output

### What Is Not Built

- No trade execution, no order routing, no automation
- No buy/sell recommendations — all framing is "data and analysis for advisor judgment"
- No scores displayed without MAX validation (the MAX Gate rule)

## Tech Stack (Decided)

| Component | Technology |
|-----------|-----------|
| Backend | Python 3.12, FastAPI, uvicorn |
| Frontend | React 18 + Vite + Tailwind CSS |
| Data (primary) | Polygon.io |
| Data (fallback) | yfinance |
| Risk-free rate | FRED DTB3 API — dynamic, TTL 1h (no hardcoded 0.045) |
| AI / LLM | Claude API — Haiku model (CLARITY explanations, MIKI/SCOUT research) |
| Presentation | Jinja2 + WeasyPrint → HTML/PDF (CANVAS) |
| Storage | SQLite (local) / Postgres (production via `DATABASE_URL`) |
| Deployment | Render (backend) / Vercel (frontend) |
| Version control | GitHub — `https://github.com/eilonsh07-sketch/my-first-project` |

## Spec-kit Workflow

This project uses spec-kit v0.10.2 for spec-driven development. New features follow the cycle:

```
speckit.clarify → speckit.specify → speckit.plan → speckit.tasks → speckit.implement
```

Or run the full workflow in one shot with the `speckit` workflow command.
