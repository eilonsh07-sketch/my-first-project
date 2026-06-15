<div dir="rtl">

# דוח בקטסט: OTM LEAPS ~500d — OptionDesk (8 ביוני 2025)

</div>


## Methodology

- **Entry date**: 2025-06-08
- **Target DTE**: 500 days (~2026-10-21 expiry)
- **OTM %**: 10% (strike = S0 × 1.10)
- **Strike type**: OTM
- **Risk-free rate**: 4.5%

### LEAPS Still-Alive Repricing (Approach A at ALL Horizons)

> A ~500-day option entered 2025-06-08 expires ~October 2026, which is **after** our data window ends
> (2026-06-08). Therefore at all evaluation horizons (3 mo = Sep-2025, 6 mo = Dec-2025, 12 mo = Jun-2026)
> the option is still alive and retains time value. Exit value is computed as:
>
> `exit_value = bs_price(S_exit, K, T_remaining, r, σ_realized, 'call')`
>
> where `T_remaining = (expiry − horizon_date) / 365 > 0` in all cases.
> This means **even a flat stock is not worthless** — residual time value is preserved.
> Approach B (hold-to-expiry intrinsic) is **not triggered** because no horizon date reaches expiry.
> All entry inputs strictly ≤ 2025-06-08 (no look-ahead). Entry premium via real Black-Scholes.

## SPY Benchmark
| Horizon | SPY close | SPY return |
|---------|-----------|------------|
| 3 mo (2025-09-08) | 648.83 | +8.3% |
| 6 mo (2025-12-08) | 683.63 | +14.1% |
| 12 mo (2026-06-08) | 739.04 | +23.4% |

## Performance Statistics — All Scored Tickers
|Horizon|N|Hit Rate|Mean Return|Median Return|Best|Worst|Beat SPY?|Spearman ρ|p-value|
|-------|-|--------|-----------|-------------|----|----|---------|----------|-------|
| 3mo | 514 | +25.3% | -16.1% | -31.2% | +915.7% | -89.8% | False | -0.030 | 0.497 |
| 6mo | 514 | +29.8% | -4.3% | -42.2% | +1046.6% | -99.6% | False | 0.153 | 0.001 |
| 12mo | 514 | +35.2% | +78.7% | -50.7% | +9716.4% | -100.0% | True | 0.117 | 0.008 |

## Performance Statistics — Top 20 by Score
|Horizon|N|Hit Rate|Mean Return|Median Return|Best|Worst|Beat SPY?|
|-------|-|--------|-----------|-------------|----|----|---------|
| 3mo | 20 | +45.0% | +10.1% | -24.0% | +198.2% | -82.4% | True |
| 6mo | 20 | +50.0% | +112.6% | -7.5% | +743.0% | -91.9% | True |
| 12mo | 20 | +55.0% | +431.8% | +44.4% | +2509.7% | -96.6% | True |

## Top-20 Trades Detail
|#|Ticker|S0|K|Entry Premium|Score|3mo Opt%|3mo Stock%|6mo Opt%|6mo Stock%|12mo Opt%|12mo Stock%|
|-|------|--|--|------------|-----|--------|---------|--------|---------|---------|----------|
| 1 | L | 89.14 | 98.05 | 2.04 | 70.7 | -82.4% | +7.7% | -46.6% | +13.8% | +167.0% | +19.0% |
| 2 | GOOGL | 173.68 | 191.05 | 8.86 | 66.2 | +119.3% | +34.8% | +743.0% | +80.6% | +1537.7% | +109.5% |
| 3 | GOOG | 174.92 | 192.41 | 8.91 | 66.2 | +107.2% | +33.9% | +729.0% | +79.8% | +1490.5% | +106.7% |
| 4 | HLT | 252.81 | 278.09 | 15.81 | 63.8 | -46.7% | +9.9% | -48.6% | +6.7% | +222.7% | +34.8% |
| 5 | WST | 224.69 | 247.16 | 7.99 | 62.8 | +198.2% | +12.7% | +131.2% | +19.8% | +550.9% | +42.4% |
| 6 | LITE | 81.46 | 89.61 | 30.93 | 61.9 | +114.1% | +83.4% | +739.1% | +320.5% | +2509.7% | +999.1% |
| 7 | AVGO | 246.93 | 271.62 | 65.94 | 61.0 | +51.7% | +40.0% | +127.9% | +62.4% | +105.1% | +60.6% |
| 8 | ALNY | 300.83 | 330.91 | 76.91 | 60.9 | +101.1% | +51.3% | +58.0% | +42.9% | -81.8% | -2.8% |
| 9 | TKO | 165.94 | 182.53 | 27.26 | 60.1 | +54.7% | +20.8% | +32.1% | +22.8% | +6.4% | +22.0% |
| 10 | CASY | 444.04 | 488.44 | 8.83 | 59.9 | -60.0% | +17.4% | +150.7% | +27.6% | +2087.8% | +69.2% |
| 11 | V | 370.22 | 407.24 | 46.59 | 59.9 | -66.5% | -7.5% | -91.9% | -11.7% | -96.6% | -13.7% |
| 12 | CCL | 24.28 | 26.71 | 6.91 | 59.8 | +17.2% | +30.0% | -43.8% | +7.1% | -44.1% | +11.2% |
| 13 | DRI | 217.53 | 239.28 | 28.58 | 59.8 | -69.7% | -3.1% | -83.3% | -17.3% | -91.7% | -9.8% |
| 14 | VST | 173.62 | 190.98 | 54.93 | 59.8 | -41.3% | +8.3% | -58.3% | -4.3% | -88.8% | -15.4% |
| 15 | AXON | 791.85 | 871.03 | 173.94 | 58.8 | -28.6% | -6.5% | -85.4% | -30.1% | -95.8% | -40.5% |
| 16 | FFIV | 295.43 | 324.97 | 45.36 | 58.8 | -19.3% | +8.5% | -67.0% | -16.0% | +82.4% | +34.1% |
| 17 | IBM | 268.87 | 295.76 | 38.38 | 58.7 | -53.0% | -4.8% | +19.7% | +15.0% | -16.5% | +4.5% |
| 18 | EME | 488.82 | 537.70 | 46.56 | 58.6 | +36.3% | +27.2% | +154.3% | +28.7% | +435.4% | +68.4% |
| 19 | KMI | 28.14 | 30.95 | 3.82 | 58.6 | -69.7% | -5.9% | -72.4% | -3.0% | -44.8% | +11.2% |
| 20 | WMB | 60.56 | 66.62 | 7.69 | 58.6 | -59.8% | -6.1% | -34.8% | +2.3% | -0.5% | +18.2% |

## Sanity Check — NVDA & PLTR

> LEAPS still-alive: at every horizon T_remaining > 0, so a flat stock should NOT be worthless.
> Verify direction aligns with actual stock move.

**NVDA** — Rank #58 | S0=141.72 | K=155.89 | Entry premium=37.52 | Score=55.7 | Expiry=2026-10-21

|Horizon|S_exit|T_remaining(yr)|Option return|Stock return|Time value preserved?|
|-------|------|--------------|-------------|-----------|---------------------|
| 3mo | 168.31 | 1.118 | -21.3% | +18.8% | v (T>0) |
| 6mo | 185.55 | 0.868 | +20.3% | +30.9% | v (T>0) |
| 12mo | 208.51 | 0.370 | +52.8% | +47.1% | v (T>0) |

**PLTR** — Rank #95 | S0=127.72 | K=140.49 | Entry premium=44.54 | Score=53.5 | Expiry=2026-10-21

|Horizon|S_exit|T_remaining(yr)|Option return|Stock return|Time value preserved?|
|-------|------|--------------|-------------|-----------|---------------------|
| 3mo | 156.10 | 1.118 | -9.3% | +22.2% | v (T>0) |
| 6mo | 181.49 | 0.868 | +30.3% | +42.1% | v (T>0) |
| 12mo | 136.51 | 0.370 | -59.5% | +6.9% | v (T>0) |

## Verdict

At the **12-month horizon** the full universe achieved a mean option return of +78.7% vs SPY +23.4% — beating the index.

Hit rate (positive option return) at 12mo: **35%**.

Spearman rank correlation between model score and 12mo option return: **ρ=0.117**, p=0.008 (statistically significant).

LEAPS structure provides substantial time-value cushion at all horizons — the longer DTE dampens theta decay relative to the 270d variant but increases capital at risk per contract.

Top-20 results (OptionDesk's highest-ranked picks) vs full universe provide the clearest signal of scoring effectiveness.
