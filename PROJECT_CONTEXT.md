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

## What to Build

A tool that helps an investment advisor evaluate options trades on US securities. Likely capabilities include:

- Options chain data display and filtering
- Greeks (delta, gamma, theta, vega) visualization
- Implied volatility analysis
- Risk/reward scenario modeling
- Market data integration (real-time or delayed)
- Trade idea comparison and tracking

All outputs must be framed as data and analysis for the advisor to interpret — not as buy/sell recommendations.

## Tech Decisions (To Be Made)

- Data provider (e.g. Polygon.io, Tradier, CBOE, Yahoo Finance)
- Frontend framework
- Backend / API layer
- Hosting / deployment target

## Spec-kit Workflow

This project uses spec-kit v0.10.2 for spec-driven development. New features follow the cycle:

```
speckit.clarify → speckit.specify → speckit.plan → speckit.tasks → speckit.implement
```

Or run the full workflow in one shot with the `speckit` workflow command.
