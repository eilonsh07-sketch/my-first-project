"""
data_providers — abstract historical options data layer for the Experimental Researcher.

The existing engine.provider (yfinance) handles *live* data for the UI.
This package handles *historical* data for backtesting — the key scientific layer.

Resolution order:
  1. POLYGON_API_KEY set → PolygonOptionsProvider (real bid/ask/IV per contract)
  2. No key          → SyntheticBSProvider (BS reconstruction from stock prices — free)

Usage:
    from engine.data_providers import get_historical_provider
    provider = get_historical_provider()
    chain = provider.options_chain_on_date("AAPL", "2023-06-16", "2023-03-15")
"""
from __future__ import annotations
import os

from .base import HistoricalOptionsProvider
from .synthetic_bs import SyntheticBSProvider


def get_historical_provider() -> HistoricalOptionsProvider:
    """Return the best available historical options data provider."""
    key = os.environ.get("POLYGON_API_KEY", "").strip()
    if key:
        from .polygon_provider import PolygonOptionsProvider
        return PolygonOptionsProvider(api_key=key)
    return SyntheticBSProvider()


__all__ = ["get_historical_provider", "HistoricalOptionsProvider"]
