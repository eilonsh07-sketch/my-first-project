# Research Spec — "What would OptionDesk have suggested on 8.6.2025, and was it right one year later?"

## GOAL
Simulate the system with a HARD knowledge cutoff of **2025-06-08**, generate the option
trades it would have recommended that day, then evaluate them against the REAL data for
the following year (through **2026-06-08**). Produce success statistics and a verdict.

## NON-NEGOTIABLE: STRICT NO-LOOK-AHEAD (data leakage = invalid result)
Every input used to GENERATE recommendations must be knowable on/before 2025-06-08.
- Fetch prices with explicit dates: `yf.download(tkr, start=..., end="2025-06-09", auto_adjust=False)`
  (end is exclusive → includes 2025-06-08). NEVER use `period="1y"` for entry inputs
  (period is relative to TODAY = leakage).
- Entry spot S0 = actual close on 2025-06-08.
- Entry sigma = REALIZED volatility from trailing window ending 2025-06-08 (e.g. 60 trading
  days). This is the validated, best-calibrated vol source. NO future data.
- r = 0.045 (RISK_FREE in scoring.py) unless a better as-of-date value is trivially available.
- q = dividend yield from info (treat as ~static; acceptable).
- Fundamentals: only use what would have been reported by 2025-06-08. If unsure, mark the
  fundamental component as low-confidence; do NOT let it leak future earnings.

## ENTRY PRICING — Approach A (PRIMARY) + Approach B (CROSS-CHECK)
Historical option chains are NOT available from yfinance (it only serves current chains).
So we price entry honestly with the system's OWN real Black-Scholes engine:
- **Approach A (primary):** For each candidate contract, entry_premium = `bs_price(S0, K, T, r,
  sigma_entry, kind="call", q)` using 2025-06-08 inputs. Exit value at horizon = `bs_price(
  S_exit, K, T_remaining, r, sigma_exit, "call", q)` where S_exit = actual close on the exit
  date and sigma_exit = realized vol of the window ending the exit date (consistent entry/exit
  vol modeling). This honors the user's default "sold before expiry" rule.
- **Approach B (cross-check):** Restrict to contracts expiring on/before 2026-06-08; P&L =
  max(S_expiry_actual - K, 0) - entry_premium (hold to expiry, intrinsic only). Report
  separately as a validation lens.
- Honest caveat to state in report: entry premiums are MODEL-IMPLIED (no real bid/ask or IV
  smile). This is the only leak-free option available; document it plainly.

## UNIVERSE & SELECTION
- Universe: existing 515 names from `engine/universe.py` `universe("both")` (S&P500 + Nasdaq100).
  Membership as of 2025-06-08 is approximated by the current static list (acceptable; note it).
- Selection logic = the SHIPPING system, time-frozen. For each ticker:
  - Build technicals as-of cutoff from the leak-free price history → `momentum_score(tech)`.
  - For a representative long-CALL candidate per ticker: pick an expiry ~6–12 months out
    (target a real-ish DTE, e.g. ~180–365 days) and a strike near-to-moderately OTM
    (e.g. delta ~0.35–0.45, or ~5–15% OTM). Keep it deterministic and documented.
  - Price entry (Approach A), compute `evaluate_option(...)` → option_score, apply
    `fundamental_option_risk` multiplier, combine via `scan_score(...)` → final combined score.
- Recommendation set = TOP 20 by combined score (long calls). Also keep the FULL ranked list
  so we can test score-vs-return correlation across all names (Spearman), like ideas-validation.

## EVALUATION (the "success statistics")
Exit/evaluate at horizons: **3mo (2025-09-08), 6mo (2025-12-08), 12mo (2026-06-08)**.
For the top-20 and for the full ranked set compute, per horizon:
- Hit-rate = % of trades with positive return.
- Mean, median, best, worst return.
- A Sharpe-like ratio (mean/stdev of returns).
- **Benchmarks (a pick only "works" if it beats these):**
  - SPY total return over the same window.
  - Buying the UNDERLYING SHARES instead of the option, same window.
- **Predictive-power test:** Spearman correlation between the system's combined score and the
  realized option return across the full ranked set, per horizon. Positive & meaningful =
  the scoring actually predicted winners. Also compare top-decile vs bottom-decile mean return.

## ROBUSTNESS / RELIABILITY
- Wrap all yfinance calls with retry+backoff (2–3 tries); throttle workers (max ~6).
- If some tickers fail to fetch, proceed with whatever resolves (report coverage, e.g. 480/515).
- Cache fetched histories to /home/user/workspace/research/cache/ to allow safe restarts.
- Use a fixed RNG seed for any Monte Carlo so results are reproducible.
- VERIFY before claiming done: sanity-check a couple of trades by hand (e.g. a known mover like
  NVDA/PLTR) — does the computed return match the actual stock move direction?

## OUTPUTS (write to /home/user/workspace/optiondesk/research/)
1. `backtest_results.json` — full machine-readable: per-trade entries, exits at each horizon,
   returns, scores, benchmarks, correlations, coverage.
2. `backtest_8jun2025_report.md` — **Hebrew, RTL-friendly** research report:
   - Methodology + explicit leak-free guarantees + honest caveats.
   - Table of the 20 recommended trades (ticker, strike, expiry, entry premium, score, reason).
   - What actually happened at 3/6/12 months (returns, hit-rate).
   - Benchmark comparison (vs SPY, vs underlying).
   - Predictive-power verdict (Spearman, top-vs-bottom decile).
   - Clear bottom-line: did the system's recommendations work out-of-sample? Yes/No + numbers.
3. A short console summary of the headline numbers.

## REUSABLE FUNCTIONS (engine/)
- pricing.py: `bs_price(S,K,T,r,sigma,kind,q)`, `bs_greeks`, `implied_vol`,
  `monte_carlo_option(...)`, `prob_touch_target_price(...)`.
- scoring.py: `momentum_score(tech)`, `fundamental_option_risk(info,dte)`,
  `evaluate_option(opt,S,expiry,mu,realized_vol,target_return,...)`, `scan_score(...)`,
  RISK_FREE=0.045.
- technicals.py: `technical_summary`, `technical_scorecard`.
- universe.py: `universe("both")`, `membership(ticker)`.
- provider.py: prefer DIRECT `yf.download(start,end)` for leak-free history; provider.history
  uses relative period (do NOT use for entry inputs).

## DEFINITION OF DONE
A completed `backtest_results.json` + Hebrew `backtest_8jun2025_report.md` with a clear,
numbers-backed verdict on whether the time-frozen system's option recommendations beat the
benchmarks and whether higher scores predicted higher realized returns. Do not stop until both
files exist and the verdict is stated. If blocked, try alternatives (different DTE/strike rule,
smaller universe sample) rather than giving up — but document any compromise.
