"""
synthetic_bs.py — Free historical options provider via BS reconstruction.

No API key required. Uses yfinance for stock price history and reconstructs
option prices using Black-Scholes with historical realized vol as the IV proxy.

Limitations (documented for scientific transparency):
  - IV is realized-vol-based, not actual market implied vol → VRP effect missing
  - Bid/ask spread is estimated (not real) → liquidity scores are approximate
  - Greeks computed from BS formula, not market-observed
  - This is what the existing backtest.py already does

When to upgrade to Polygon: when we need to study VRP, real spread costs,
or detect IV crush around earnings with actual data.
"""
from __future__ import annotations

import math
from datetime import datetime, date, timedelta
from typing import Optional

from .base import HistoricalOptionsProvider, HistoricalOptionContract

# These match the live engine so experiments are comparable
RISK_FREE = 0.045
MIN_IV = 0.05


def _bs_price(S: float, K: float, T: float, r: float, sigma: float, kind: str) -> float:
    if T <= 0 or sigma <= 0 or S <= 0 or K <= 0:
        return 0.0
    d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)

    def _ncdf(x):
        return 0.5 * (1.0 + math.erf(x / math.sqrt(2)))

    if kind == "call":
        return S * _ncdf(d1) - K * math.exp(-r * T) * _ncdf(d2)
    return K * math.exp(-r * T) * _ncdf(-d2) - S * _ncdf(-d1)


def _realized_vol(closes: list[float], window: int = 30) -> float:
    if len(closes) < 2:
        return 0.25
    returns = [math.log(closes[i] / closes[i - 1]) for i in range(1, len(closes))]
    tail = returns[-window:]
    if not tail:
        return 0.25
    mean = sum(tail) / len(tail)
    variance = sum((r - mean) ** 2 for r in tail) / len(tail)
    return max(MIN_IV, math.sqrt(variance * 252))


class SyntheticBSProvider(HistoricalOptionsProvider):
    """
    Historical options data reconstructed from stock prices + Black-Scholes.
    Free, no API key, works out of the box. Scientific caveat: IV = realized vol proxy.
    """

    def __init__(self, vol_window: int = 30):
        self._vol_window = vol_window
        self._price_cache: dict[str, dict] = {}

    @property
    def name(self) -> str:
        return "Synthetic BS (Polygon + Black-Scholes)"

    @property
    def is_synthetic(self) -> bool:
        return True

    def _fetch_history(self, ticker: str) -> dict:
        if ticker not in self._price_cache:
            try:
                from engine.provider import PROVIDER
                hist = PROVIDER.history(ticker, "5y")
                if hist is None or len(hist) == 0:
                    self._price_cache[ticker] = {}
                    return {}
                records = {}
                for ts, row in hist.iterrows():
                    d = ts.strftime("%Y-%m-%d")
                    records[d] = {
                        "date": d,
                        "open": float(row["Open"]),
                        "high": float(row["High"]),
                        "low": float(row["Low"]),
                        "close": float(row["Close"]),
                        "volume": int(row.get("Volume", 0)),
                    }
                self._price_cache[ticker] = records
            except Exception:
                self._price_cache[ticker] = {}
        return self._price_cache[ticker]

    def stock_price_on_date(self, ticker: str, date_str: str) -> Optional[float]:
        hist = self._fetch_history(ticker)
        rec = hist.get(date_str)
        if rec:
            return rec["close"]
        # Try nearest prior trading day
        dt = datetime.strptime(date_str, "%Y-%m-%d").date()
        for i in range(1, 6):
            d = (dt - timedelta(days=i)).strftime("%Y-%m-%d")
            if d in hist:
                return hist[d]["close"]
        return None

    def stock_history(self, ticker: str, start: str, end: str) -> list[dict]:
        hist = self._fetch_history(ticker)
        return [v for k, v in sorted(hist.items()) if start <= k <= end]

    def options_chain_on_date(
        self,
        ticker: str,
        as_of_date: str,
        expiry: str,
    ) -> list[HistoricalOptionContract]:
        hist = self._fetch_history(ticker)
        if not hist:
            return []

        # Get spot on as_of_date
        spot = self.stock_price_on_date(ticker, as_of_date)
        if spot is None:
            return []

        # Compute realized vol from prior 60 days
        dates_before = sorted(d for d in hist if d <= as_of_date)
        closes_before = [hist[d]["close"] for d in dates_before[-60:]]
        sigma = _realized_vol(closes_before, self._vol_window)

        # Time to expiry
        try:
            exp_dt = datetime.strptime(expiry, "%Y-%m-%d").date()
            as_of_dt = datetime.strptime(as_of_date, "%Y-%m-%d").date()
            dte = (exp_dt - as_of_dt).days
        except Exception:
            return []

        if dte <= 0:
            return []

        T = dte / 365.0

        # Generate strikes: ±5% to ±40% OTM in 2.5% steps
        contracts = []
        for pct in range(-40, 45, 5):
            K = round(spot * (1 + pct / 100.0), 2)
            if K <= 0:
                continue
            for kind in ("call", "put"):
                price = _bs_price(spot, K, T, RISK_FREE, sigma, kind)
                if price < 0.01:
                    continue
                # Estimate a spread (wider for OTM, tighter for ATM)
                otm_factor = abs(pct) / 40.0
                spread_pct = 0.05 + otm_factor * 0.20
                bid = round(price * (1 - spread_pct / 2), 4)
                ask = round(price * (1 + spread_pct / 2), 4)
                contracts.append(HistoricalOptionContract(
                    ticker=ticker,
                    as_of_date=as_of_date,
                    expiry=expiry,
                    strike=K,
                    kind=kind,
                    mid=round(price, 4),
                    bid=bid,
                    ask=ask,
                    iv=sigma,
                    delta=None,
                    open_interest=None,
                    volume=None,
                    underlying_price=spot,
                    data_source="synthetic_bs",
                    synthetic=True,
                ))

        return contracts
