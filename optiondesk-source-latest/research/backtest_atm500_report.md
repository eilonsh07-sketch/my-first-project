# OptionDesk Backtest — ATM LEAPS ~500d
## גיליון תוצאות | Results Report
### כניסה: 8 יוני 2025 | Entry: 2025-06-08 | DTE: ~500 ימים | OTM: 0% (ATM)

---

<div dir="rtl">

## הערה מתודולוגית — אופציות LEAPS "עדיין חיות"

**מפתח:** אופציית LEAPS בת ~500 ימים שנקנתה ב-8 ביוני 2025 פוקעת בסביבות **21 באוקטובר 2026** — לאחר חלון הנתונים שלנו (8 ביוני 2026). לכן, בכל שלושת אופקי הערכה (3 חודש, 6 חודש, 12 חודש), האופציה **עדיין חיה** — אין החזקה עד לפקיעה בשום אופק.

**גישת התמחור (Approach A — מכירה לפני פקיעה):**
בכל אופק, האופציה מתומחרת מחדש לפי Black-Scholes עם:
- מחיר הסגירה הממשי של המניה ביום האופק
- תנודתיות ממומשת (60 ימי מסחר) עד ליום האופק
- זמן עד לפקיעה הנותר (T_remaining > 0 בכל אופק)

**אין הסתכלות קדימה:** כל נתוני הכניסה — מחיר, תנודתיות, ציונים טכניים — מסתיימים ב-8 ביוני 2025. נתוני היציאה נלקחים לאחר תאריך הסף בלבד.

| אופק | תאריך יציאה | T_remaining (שנים) |
|------|------------|-------------------|
| 3mo  | 2025-09-08 | ~1.118 |
| 6mo  | 2025-12-08 | ~0.868 |
| 12mo | 2026-06-08 | ~0.370 |

</div>

---

## Methodology Note — LEAPS Still-Alive Repricing

A ~500-day ATM call entered on 2025-06-08 expires approximately **2026-10-21**, which lies **beyond the data window** end of 2026-06-08. Therefore, at **all three evaluation horizons** (3-month, 6-month, 12-month), the option is still alive — no contract ever reaches expiry within the backtest window.

**Exit pricing (Approach A — sold before expiry by default):**  
At each horizon date, the option is repriced via Black-Scholes using:
- Actual stock close on the horizon date
- 60-day trailing realized volatility ending on the horizon date
- Remaining time to expiry (T_remaining ranges from 1.118yr at 3mo to 0.370yr at 12mo)

No intrinsic-only (Approach B / hold-to-expiry) calculation is used for any ticker at any horizon. This is fully consistent with how a practitioner would sell a LEAPS position mid-life.

---

## Benchmark — SPY

| Horizon | SPY S0 | SPY Close | SPY Return |
|---------|--------|-----------|------------|
| Entry   | 599.14 | —         | —          |
| 3mo     | —      | 648.83    | **+8.3%**  |
| 6mo     | —      | 683.63    | **+14.1%** |
| 12mo    | —      | 739.04    | **+23.4%** |

---

## Statistics — All 514 Tickers

| Horizon | N   | Hit-Rate | Mean Return | Median Return | Best       | Worst     | Beat SPY | Spearman ρ | p-value |
|---------|-----|----------|-------------|---------------|------------|-----------|----------|-----------|---------|
| 3mo     | 514 | **30.0%**  | -8.1%       | -19.9%        | +856.0%    | -83.2%    | ❌ No    | -0.014    | 0.749   |
| 6mo     | 514 | **33.9%**  | +2.5%       | -28.2%        | +994.0%    | -99.3%    | ❌ No    | **+0.152** | **0.001** |
| 12mo    | 514 | **41.2%**  | +77.6%      | -31.2%        | +9131.4%   | -100.0%   | ✅ Yes   | **+0.110** | **0.013** |

*Spearman ρ measures correlation between combined score and realized option return. Significant positive correlation at 6mo and 12mo confirms the scoring system has predictive value for LEAPS.*

---

## Statistics — Top 20 Picks (by Combined Score)

| Horizon | N  | Hit-Rate | Mean Return | Median Return | Best       | Worst   | SPY     | Beat SPY |
|---------|----|----------|-------------|---------------|------------|---------|---------|----------|
| 3mo     | 20 | **50.0%** | **+22.0%**  | **+9.0%**     | +165.6%    | -61.7%  | +8.3%   | ✅ Yes   |
| 6mo     | 20 | **60.0%** | **+118.1%** | **+34.0%**    | +700.3%    | -83.3%  | +14.1%  | ✅ Yes   |
| 12mo    | 20 | **65.0%** | **+419.8%** | **+157.6%**   | +2347.9%   | -91.1%  | +23.4%  | ✅ Yes   |

---

## Top-20 Trade Table

| # | Ticker | S0 ($) | Strike ($) | Entry Prem ($) | Score | 3mo Opt | 6mo Opt | 12mo Opt | 12mo Stock |
|---|--------|--------|-----------|----------------|-------|---------|---------|---------|-----------|
| 1 | L | 89.14 | 89.14 | 3.25 | 75.4 | -61.7% | +1.3% | +241.1% | +19.0% |
| 2 | GOOGL | 173.68 | 173.68 | 11.85 | 71.9 | +131.7% | +654.1% | +1267.7% | +109.5% |
| 3 | GOOG | 174.92 | 174.92 | 11.92 | 71.9 | +121.7% | +644.0% | +1232.3% | +106.7% |
| 4 | HLT | 252.81 | 252.81 | 21.38 | 69.2 | -27.3% | -28.3% | +239.8% | +34.8% |
| 5 | WST | 224.69 | 224.69 | 11.11 | 67.4 | +165.6% | +134.5% | +530.8% | +42.4% |
| 6 | LITE | 81.46 | 81.46 | 33.30 | 62.8 | +119.5% | +700.3% | +2347.9% | +999.1% |
| 7 | CASY | 444.04 | 444.04 | 13.51 | 62.6 | -29.3% | +193.3% | +1646.6% | +69.2% |
| 8 | EME | 488.82 | 488.82 | 58.34 | 62.5 | +51.0% | +142.2% | +406.9% | +68.4% |
| 9 | AVGO | 246.93 | 246.93 | 74.47 | 62.0 | +58.8% | +128.1% | +110.4% | +60.6% |
| 10 | ALNY | 300.83 | 300.83 | 87.47 | 62.0 | +102.9% | +66.6% | -72.0% | -2.8% |
| 11 | TKO | 165.94 | 165.94 | 33.85 | 61.5 | +54.3% | +41.7% | +22.9% | +22.0% |
| 12 | V | 370.22 | 370.22 | 62.08 | 61.5 | -56.2% | -83.3% | -91.1% | -13.7% |
| 13 | DRI | 217.53 | 217.53 | 37.61 | 61.4 | -54.9% | -77.0% | -83.1% | -9.8% |
| 14 | GEV | 485.00 | 485.00 | 70.44 | 61.4 | +29.9% | +55.4% | +451.4% | +92.5% |
| 15 | CCL | 24.28 | 24.28 | 7.73 | 60.8 | +25.4% | -34.8% | -33.8% | +11.2% |
| 16 | VST | 173.62 | 173.62 | 60.52 | 60.8 | -33.0% | -52.1% | -83.8% | -15.4% |
| 17 | HWM | 175.37 | 175.37 | 19.58 | 60.3 | -49.7% | -30.5% | +204.8% | +40.7% |
| 18 | FFIV | 295.43 | 295.43 | 57.27 | 60.2 | -7.3% | -61.8% | +88.5% | +34.1% |
| 19 | IBM | 268.87 | 268.87 | 49.38 | 60.2 | -43.8% | +26.2% | -10.9% | +4.5% |
| 20 | KMI | 28.14 | 28.14 | 4.98 | 60.2 | -57.9% | -58.3% | -19.6% | +11.2% |

---

## Sanity Check — NVDA & PLTR

### NVDA (S0 = $141.72, K = $141.72, Entry Premium = $42.43, σ_entry = 60.5%)

| Horizon | S_exit | T_remaining | Exit Value | Option Return | Stock Return | Notes |
|---------|--------|-------------|------------|---------------|--------------|-------|
| 3mo | $168.31 | 1.118 yr | $38.72 | **-8.8%** | +18.8% | LEAPS still alive; stock rose +18.8% but time value decay + vol reduction offset |
| 6mo | $185.55 | 0.868 yr | $54.91 | **+29.4%** | +30.9% | Stock up strongly; option tracks closely |
| 12mo | $208.51 | 0.370 yr | $69.97 | **+64.9%** | +47.1% | Option outperforms stock at 12mo ✅ |

**NVDA verdict:** Direction confirmed (stock +47% at 12mo → option +65%). LEAPS ATM has substantial time value at all horizons (T_remaining > 0 confirmed). The 3mo loss is expected: at 1.118yr remaining, high-vol ATM LEAPS is sensitive to vol contraction even when the stock rises modestly.

### PLTR (S0 = $127.72, K = $127.72, Entry Premium = $48.44, σ_entry = 79.8%)

| Horizon | S_exit | T_remaining | Exit Value | Option Return | Stock Return | Notes |
|---------|--------|-------------|------------|---------------|--------------|-------|
| 3mo | $156.10 | 1.118 yr | $47.31 | **-2.3%** | +22.2% | Vol crush on LEAPS; near-breakeven |
| 6mo | $181.49 | 0.868 yr | $66.50 | **+37.3%** | +42.1% | Strong stock move captures value |
| 12mo | $136.51 | 0.370 yr | $23.96 | **-50.5%** | +6.9% | Stock barely moved; theta eroded ATM LEAPS significantly |

**PLTR verdict:** Directional correctness at 6mo confirmed. At 12mo, PLTR stock gained only +6.9% — insufficient to overcome theta decay of a deep-in-time-value LEAPS, resulting in -50.5% option loss. This illustrates key LEAPS ATM risk: moderate stock moves are insufficient.

---

## ATM-500 vs ATM-270 Comparison (Top-20)

| Horizon | ATM-270 Hit | ATM-270 Mean | ATM-500 Hit | ATM-500 Mean | Verdict |
|---------|------------|-------------|------------|-------------|---------|
| 3mo     | 30%        | -8.2%       | **50%**    | **+22.0%**  | ATM-500 dominates |
| 6mo     | 30%        | +20.0%      | **60%**    | **+118.1%** | ATM-500 dominates |
| 12mo    | 40%        | +168.2%     | **65%**    | **+419.8%** | ATM-500 dominates |

**ATM-500 shows materially higher hit-rates and mean returns than ATM-270 at all horizons for the top-20 picks.** The longer DTE provides more time for directional thesis to play out while preserving substantial remaining time value at each evaluation point.

*Note: No OTM-500 (10% OTM, 500d) backtest file exists in this workspace. The closest comparison is ATM-270 (the prior 270d ATM run). By analogy with the 270d results — where ATM (0% OTM) already outperformed 10%-OTM at every horizon — ATM-500 is expected to further outperform any OTM-500 variant, as ATM starts in-the-money relative to the OTM strike while still carrying full LEAPS time value.*

---

## Spearman Score-vs-Return Correlation

| Horizon | ρ (All 514) | p-value | Significance |
|---------|------------|---------|--------------|
| 3mo     | -0.014     | 0.749   | None (noise at short horizon) |
| 6mo     | **+0.152** | **0.001** | Highly significant |
| 12mo    | **+0.110** | **0.013** | Significant |

The scoring system demonstrates statistically significant positive rank-correlation between combined score and realized return at 6-month and 12-month horizons. Higher-scored LEAPS tickers meaningfully outperform lower-scored ones at these time frames.

---

## Verdict

<div dir="rtl">

### פסיקה — LEAPS ATM ~500 ימים

**אופציות LEAPS ATM בנות ~500 יום מהוות את הוריאנט הפרפורמטיבי ביותר שנבדק עד כה.**

- **שיעור הצלחה:** 65% מתוך 20 הבחירות הטובות ביותר הרוויחו ב-12 חודש — לעומת 40% ל-ATM-270.
- **תשואה ממוצעת:** +419.8% ב-12 חודש לטופ-20, לעומת +168.2% ל-ATM-270 — פי 2.5.
- **ניצוח SPY:** הטופ-20 ניצח את SPY בכל שלושת האופקים (SPY: +8.3%, +14.1%, +23.4%).
- **כוח הניבוי:** מתאם ספירמן מובהק סטטיסטית ב-6 חודש (ρ=0.152, p=0.001) ו-12 חודש (ρ=0.110, p=0.013).

</div>

### Verdict — ATM LEAPS ~500-Day Options

**ATM LEAPS ~500-day options are the highest-performing variant backtested to date.**

**Strengths:**
- Top-20 hit-rate of **65%** at 12mo — up from 40% for ATM-270 and 40% for OTM-270
- Top-20 mean return of **+419.8%** at 12mo — more than 2.5× the ATM-270 result (+168.2%)
- Beats SPY at all three horizons for top-20: 3mo (+22.0% vs +8.3%), 6mo (+118.1% vs +14.1%), 12mo (+419.8% vs +23.4%)
- Statistically significant Spearman correlation at 6mo (ρ=+0.152, p=0.001) and 12mo (ρ=+0.110, p=0.013), confirming the scoring model's predictive value for LEAPS selection
- LEAPS time value is substantial at all evaluation horizons (T_remaining: 1.12yr → 0.87yr → 0.37yr), confirming the "still alive" repricing approach is appropriate

**Risks and cautions:**
- Broad universe (all 514 tickers) hit-rate is only 41.2% at 12mo with mean +77.6% — heavily skewed by a few extreme outliers (best: +9,131%). Median is -31.2%, meaning most LEAPS lose money.
- LEAPS ATM is highly sensitive to vol contraction at early horizons (see NVDA -8.8% at 3mo despite +18.8% stock move; PLTR -2.3% at 3mo despite +22.2% stock move).
- PLTR at 12mo lost -50.5% despite stock gaining +6.9% — moderate stock moves are insufficient to overcome LEAPS theta at this time scale.
- Premium costs are substantial (e.g., AVGO $74.47, ALNY $87.47), making position sizing critical.
- Entry premiums are model-implied via Black-Scholes (no real option chains available from yfinance); actual market premiums may differ.

**Overall rating: ✅ STRONG POSITIVE — ATM LEAPS ~500d is the recommended DTE for the OptionDesk strategy.** The 12mo evaluation is the natural measurement horizon for this product. Score-based selection (top-20) dramatically improves outcomes versus random selection.

---

## Parameters

| Parameter | Value |
|-----------|-------|
| Entry date | 2025-06-08 |
| Target DTE | 500 days |
| Approx expiry | 2026-10-21 |
| OTM% | 0.0% (ATM) |
| Risk-free rate | 4.5% |
| Entry sigma | 60-day realized vol trailing 2025-06-08 |
| Exit method | Approach A: BS reprice (all horizons, LEAPS still alive) |
| Universe | 515 tickers (514 scored) |
| RNG seed | 42 |
| Max workers | 6 |

---

*Report generated: 2026-06-08 | Script: backtest_atm500.py | Results: backtest_atm500_results.json*
