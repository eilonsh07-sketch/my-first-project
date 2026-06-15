"""
base.py — Abstract interface for historical options data.

Both SyntheticBSProvider and PolygonOptionsProvider implement this contract.
The Experimental Researcher only ever calls methods defined here — so swapping
the data source requires zero changes to the backtesting logic.
"""
from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class HistoricalOptionContract:
    """One option contract's data on a specific historical date."""
    ticker: str
    as_of_date: str          # YYYY-MM-DD — the date we're pricing as of
    expiry: str              # YYYY-MM-DD
    strike: float
    kind: str                # 'call' | 'put'
    mid: Optional[float]     # mid price (bid+ask)/2  — None if synthetic
    bid: Optional[float]
    ask: Optional[float]
    iv: Optional[float]      # implied volatility (annualized)
    delta: Optional[float]
    open_interest: Optional[int]
    volume: Optional[int]
    underlying_price: float  # spot price on as_of_date
    data_source: str         # 'polygon' | 'synthetic_bs'
    synthetic: bool          # True if price is BS-reconstructed, not a real trade


@dataclass
class BacktestUniverse:
    """The set of options to evaluate on a given historical date."""
    ticker: str
    as_of_date: str
    spot: float
    contracts: list[HistoricalOptionContract] = field(default_factory=list)


class HistoricalOptionsProvider(ABC):
    """
    Abstract base: fetch historical options data for the Experimental Researcher.

    All dates are YYYY-MM-DD strings. Providers must be safe to call in a tight
    loop (500 tickers × many dates) — implement caching and rate-limiting inside.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable provider name, e.g. 'Polygon.io' or 'Synthetic BS'."""

    @property
    @abstractmethod
    def is_synthetic(self) -> bool:
        """True if prices are reconstructed (not real market trades)."""

    @abstractmethod
    def options_chain_on_date(
        self,
        ticker: str,
        as_of_date: str,
        expiry: str,
    ) -> list[HistoricalOptionContract]:
        """
        Return all option contracts for `ticker` expiring on `expiry`,
        priced as of `as_of_date`.

        Returns empty list if data unavailable (do not raise).
        """

    @abstractmethod
    def stock_price_on_date(self, ticker: str, date: str) -> Optional[float]:
        """Closing price of the underlying on the given date. None if unavailable."""

    @abstractmethod
    def stock_history(self, ticker: str, start: str, end: str) -> list[dict]:
        """
        Daily OHLCV for `ticker` from `start` to `end` (inclusive, YYYY-MM-DD).
        Each dict: {'date': str, 'open': float, 'high': float, 'low': float,
                    'close': float, 'volume': int}
        """

    def available_expiries_on_date(self, ticker: str, as_of_date: str) -> list[str]:
        """
        Return expiry dates available for `ticker` as of `as_of_date`.
        Default implementation returns [] — override in providers that can enumerate.
        """
        return []
