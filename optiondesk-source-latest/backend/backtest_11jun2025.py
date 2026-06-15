"""
\u05d1\u05d3\u05d9\u05e7\u05d4 \u05d0\u05d7\u05d5\u05e8\u05d4 (no look-ahead \u05de\u05d7\u05de\u05d9\u05e8 \u05de\u05dc\u05d0): \u05d0\u05d9\u05dc\u05d5 \u05d4\u05de\u05d5\u05d3\u05dc \u05d4\u05d9\u05d4 \u05de\u05e6\u05dc\u05d9\u05d7 \u05e2\u05dc \u05db\u05e0\u05d9\u05e1\u05d4 11/06/2025.
\u05dc\u05db\u05dc \u05de\u05e0\u05d9\u05d4: 6 \u05e7\u05d5\u05de\u05d1\u05d9\u05e0\u05e6\u05d9\u05d5\u05ea = {ATM, ITM, OTM} \u00d7 {\u05e7\u05e6\u05e8\u05d4 ~45\u05d9, \u05d0\u05e8\u05d5\u05db\u05d4 ~365\u05d9}.
\u05dc\u05db\u05dc \u05e7\u05d5\u05de\u05d1\u05d9\u05e0\u05e6\u05d9\u05d4: \u05ea\u05d5\u05e6\u05d0\u05d4 \u05d1\u05e9\u05ea\u05d9 \u05d0\u05e1\u05d8\u05e8\u05d8\u05d2\u05d9\u05d5\u05ea \u05d9\u05e6\u05d9\u05d0\u05d4 \u2014 \u05de\u05db\u05d9\u05e8\u05d4 \u05de\u05d5\u05e7\u05d3\u05de\u05ea \u05d5\u05d4\u05d7\u05d6\u05e7\u05d4 \u05e2\u05d3 \u05e4\u05e7\u05d9\u05e2\u05d4.

\u05ea\u05de\u05d7\u05d5\u05e8: CRR \u05d0\u05de\u05e8\u05d9\u05e7\u05d0\u05d9 \u05de\u05dc\u05d0 (engine.american_pricing). \u05ea\u05e0\u05d5\u05d3\u05ea\u05d9\u05d5\u05ea = \u05e8\u05d9\u05d0\u05dc\u05d9\u05d6\u05d3 \u05e2\u05d3 \u05d4\u05db\u05e0\u05d9\u05e1\u05d4 \u05d1\u05dc\u05d1\u05d3.
\u05db\u05dc \u05d4\u05d0\u05d5\u05e4\u05e6\u05d9\u05d5\u05ea \u05d4\u05df CALLs (\u05dc\u05d5\u05e0\u05d2). r=0.045.
"""
import sys, json, math
import datetime as dt
sys.path.insert(0, '.')
import numpy as np
from engine.provider import YahooProvider
from engine.american_pricing import binomial_crr, american_price
from engine.pricing import bs_price

R = 0.045
ENTRY = dt.date(2025, 6, 11)
TICKERS = ["MSFT", "SMCI", "MRVL", "AAPL", "NVDA", "IONQ", "QBTS", "SPY", "QQQ"]
SHORT_DAYS = 45
LONG_DAYS = 365
MONEYNESS = {"ATM": 0.0, "ITM": -0.10, "OTM": +0.10}  # strike offset for CALL: ITM strike below spot, OTM above

prov = YahooProvider()


def realized_vol(closes):
    """\u05ea\u05e0\u05d5\u05d3\u05ea\u05d9\u05d5\u05ea \u05e9\u05e0\u05ea\u05d9\u05ea \u05de\u05ea\u05e9\u05d5\u05d0\u05d5\u05ea \u05dc\u05d5\u05d2\u05d9\u05ea \u05d9\u05d5\u05de\u05d9\u05d5\u05ea (annualized)."""
    closes = np.asarray(closes, dtype=float)
    rets = np.diff(np.log(closes))
    if len(rets) < 5:
        return 0.30
    return float(np.std(rets, ddof=1) * math.sqrt(252))


def nearest_trading_row(df, target_date):
    """\u05de\u05d7\u05d6\u05d9\u05e8 (date, close) \u05e9\u05dc \u05d9\u05d5\u05dd \u05d4\u05de\u05e1\u05d7\u05e8 \u05d4\u05e7\u05e8\u05d5\u05d1 \u05d1\u05d9\u05d5\u05ea\u05e8 \u05d1-/\u05d0\u05d7\u05e8\u05d9 target_date."""
    idx_dates = [d.date() if hasattr(d, 'date') else d for d in df.index]
    best_i = None
    for i, d in enumerate(idx_dates):
        if d >= target_date:
            best_i = i
            break
    if best_i is None:
        best_i = len(idx_dates) - 1  # \u05d0\u05d7\u05e8\u05d9 \u05d4\u05e1\u05d5\u05e3 \u2192 \u05d9\u05d5\u05dd \u05d0\u05d7\u05e8\u05d5\u05df \u05d6\u05de\u05d9\u05df
    return idx_dates[best_i], float(df['Close'].iloc[best_i]), (best_i >= len(idx_dates) - 1)


results = []
meta = {}

for tk in TICKERS:
    try:
        df = prov.history(tk, period='2y', interval='1d')
    except Exception as e:
        print(f"[{tk}] history error: {e}")
        continue
    if df is None or len(df) < 60:
        print(f"[{tk}] insufficient data")
        continue

    idx_dates = [d.date() if hasattr(d, 'date') else d for d in df.index]

    # --- \u05db\u05e0\u05d9\u05e1\u05d4: \u05de\u05d7\u05d9\u05e8 \u05d1-11/06/2025 ---
    entry_date, S0, _ = nearest_trading_row(df, ENTRY)
    # \u05ea\u05e0\u05d5\u05d3\u05ea\u05d9\u05d5\u05ea \u05e8\u05d9\u05d0\u05dc\u05d9\u05d6\u05d3 \u2014 \u05e8\u05e7 \u05e0\u05ª\u05d5\u05e0\u05d9\u05dd \u05e2\u05d3 \u05d4\u05db\u05e0\u05d9\u05e1\u05d4 (no look-ahead)
    entry_i = idx_dates.index(entry_date)
    hist_closes = df['Close'].iloc[max(0, entry_i - 252):entry_i + 1].values
    sigma = realized_vol(hist_closes)

    # \u05d3\u05d9\u05d1\u05d9\u05d3\u05e0\u05d3 \u05e8\u05e6\u05d9\u05e3 (continuous q) \u2014 \u05de\u05d4\u05e1\u05db\u05d5\u05dd \u05d4\u05d3\u05d9\u05d1\u05d9\u05d3\u05e0\u05d3\u05d9\u05dd \u05d1-12 \u05d7\u05d5\u05d3\u05e9\u05d9\u05dd \u05e9\u05dc\u05e4\u05e0\u05d9 \u05d4\u05db\u05e0\u05d9\u05e1\u05d4
    div_12m = float(df['Dividends'].iloc[max(0, entry_i - 252):entry_i + 1].sum())
    q = (div_12m / S0) if S0 > 0 else 0.0

    meta[tk] = {"entry_date": str(entry_date), "S0": round(S0, 2),
                "sigma": round(sigma, 4), "q": round(q, 4)}
    print(f"[{tk}] entry {entry_date} S0={S0:.2f} sigma={sigma:.3f} q={q:.4f}")

    for horizon_name, horizon_days in [("\u05e7\u05e6\u05e8\u05d4", SHORT_DAYS), ("\u05d0\u05e8\u05d5\u05db\u05d4", LONG_DAYS)]:
        T0 = horizon_days / 365.0
        expiry_date = entry_date + dt.timedelta(days=horizon_days)
        # \u05e0\u05e7\u05d5\u05d3\u05ea \u05d9\u05e6\u05d9\u05d0\u05d4 \u05de\u05d5\u05e7\u05d3\u05de\u05ea = \u05d7\u05e6\u05d9 \u05d4\u05d3\u05e8\u05da
        exit_date = entry_date + dt.timedelta(days=horizon_days // 2)

        for mny_name, off in MONEYNESS.items():
            # CALL strike: ATM=S0, ITM=S0*0.90 (strike \u05de\u05ª\u05d7\u05ª \u05dc\u05de\u05d7\u05d9\u05e8 \u2192 \u05d1\u05ª\u05d5\u05da \u05d4\u05db\u05e1\u05e3), OTM=S0*1.10
            K = round(S0 * (1.0 + off), 2)

            # \u05e4\u05e8\u05de\u05d9\u05d9\u05ª \u05db\u05e0\u05d9\u05e1\u05d4 \u2014 CRR \u05d0\u05de\u05e8\u05d9\u05e7\u05d0\u05d9
            entry_prem = binomial_crr(S0, K, T0, R, sigma, "call", q=q, steps=200, american=True)
            if entry_prem < 0.01:
                entry_prem = 0.01

            # --- \u05de\u05d7\u05d9\u05e8\u05d9 \u05d1\u05e1\u05d9\u05e1 \u05d1\u05e0\u05e7\u05d5\u05d3\u05d5\u05ª \u05d4\u05d9\u05e6\u05d9\u05d0\u05d4 \u05d5\u05d4\u05e4\u05e7\u05d9\u05e2\u05d4 (\u05e0\u05ª\u05d5\u05e0\u05d9 \u05e9\u05d5\u05e7 \u05d0\u05de\u05d9\u05ª\u05d9\u05d9\u05dd) ---
            ex_date, S_exit, exit_past_end = nearest_trading_row(df, exit_date)
            ep_date, S_exp, exp_past_end = nearest_trading_row(df, expiry_date)

            # \u05d6\u05de\u05df \u05e9\u05e0\u05d5\u05ª\u05e8 \u05d1\u05d9\u05e6\u05d9\u05d0\u05d4 \u05d4\u05de\u05d5\u05e7\u05d3\u05de\u05ª
            days_elapsed_exit = (ex_date - entry_date).days
            T_exit = max((horizon_days - days_elapsed_exit) / 365.0, 1e-4)

            # \u05ª\u05e0\u05d5\u05d3\u05ª\u05d9\u05d5\u05ª \u05d1\u05d9\u05e6\u05d9\u05d0\u05d4 = \u05e8\u05d9\u05d0\u05dc\u05d9\u05d6\u05d3 \u05e2\u05d3 \u05d9\u05d5\u05dd \u05d4\u05d9\u05e6\u05d9\u05d0\u05d4 (\u05de\u05d7\u05de\u05d9\u05e8: \u05dc\u05dc\u05d0 \u05d4\u05e6\u05e6\u05d4 \u05e7\u05d3\u05d9\u05de\u05d4)
            try:
                exit_i = idx_dates.index(ex_date)
                sigma_exit = realized_vol(df['Close'].iloc[max(0, exit_i - 252):exit_i + 1].values)
            except ValueError:
                sigma_exit = sigma

            # --- \u05d0\u05e1\u05d8\u05e8\u05d8\u05d2\u05d9\u05d4 1: \u05de\u05db\u05d9\u05e8\u05d4 \u05de\u05d5\u05e7\u05d3\u05de\u05ª (CRR \u05d1\u05e0\u05e7\u05d5\u05d3\u05ª \u05d4\u05d9\u05e6\u05d9\u05d0\u05d4) ---
            exit_val_early = binomial_crr(S_exit, K, T_exit, R, sigma_exit, "call", q=q, steps=200, american=True)
            ret_early = (exit_val_early - entry_prem) / entry_prem

            # --- \u05d0\u05e1\u05d8\u05e8\u05d8\u05d2\u05d9\u05d4 2: \u05d4\u05d7\u05d6\u05e7\u05d4 \u05e2\u05d3 \u05e4\u05e7\u05d9\u05e2\u05d4 (\u05e2\u05e8\u05da \u05e4\u05e0\u05d9\u05de\u05d9) ---
            exit_val_exp = max(S_exp - K, 0.0)
            ret_exp = (exit_val_exp - entry_prem) / entry_prem

            results.append({
                "ticker": tk, "moneyness": mny_name, "horizon": horizon_name,
                "horizon_days": horizon_days,
                "S0": round(S0, 2), "strike": K, "sigma_entry": round(sigma, 4),
                "entry_premium": round(entry_prem, 3),
                "S_exit": round(S_exit, 2), "exit_date": str(ex_date),
                "exit_val_early": round(exit_val_early, 3),
                "ret_early_pct": round(ret_early * 100, 1),
                "S_expiry": round(S_exp, 2), "expiry_used": str(ep_date),
                "expiry_partial": bool(exp_past_end),  # True = \u05d4\u05e4\u05e7\u05d9\u05e2\u05d4 \u05d1\u05e2\u05ª\u05d9\u05d3 (\u05d0\u05d9\u05df \u05e2\u05d3\u05d9\u05d9\u05df \u05e0\u05ª\u05d5\u05e0\u05d9\u05dd \u05de\u05dc\u05d0\u05d9\u05dd)
                "exit_val_expiry": round(exit_val_exp, 3),
                "ret_expiry_pct": round(ret_exp * 100, 1),
            })

with open('backtest_results_11jun2025.json', 'w') as f:
    json.dump({"meta": meta, "results": results,
               "params": {"entry": str(ENTRY), "r": R, "short_days": SHORT_DAYS,
                          "long_days": LONG_DAYS, "moneyness": MONEYNESS}}, f, indent=2)

print(f"\n=== {len(results)} rows written ===")
