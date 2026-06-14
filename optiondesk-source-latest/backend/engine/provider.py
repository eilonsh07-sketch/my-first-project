"""
provider.py — Modular market-data provider abstraction.
Current implementation: YahooProvider (yfinance). Designed so a paid provider
(Polygon/Tradier/Finnhub) can be dropped in later by implementing the same interface.

Includes a lightweight TTL cache to avoid hammering Yahoo on every debounce.
"""
from __future__ import annotations

import os
import json
import ssl
import time
import threading
import math
import urllib.request
import urllib.parse
from datetime import datetime, date, timezone, timedelta

import numpy as np
import pandas as pd

try:
    import certifi
    _SSL_CTX = ssl.create_default_context(cafile=certifi.where())
except Exception:
    _SSL_CTX = ssl.create_default_context()

try:
    import yfinance as yf
    _HAS_YF = True
except ImportError:
    _HAS_YF = False

# --- Browser-impersonation session ------------------------------------------
# Yahoo Finance blocks/rate-limits requests from datacenter IPs (Render, etc.)
# by TLS-fingerprint + User-Agent. yfinance's default `requests` session gets
# 429'd / returns empty data on cloud hosts even though it works locally.
# curl_cffi with impersonate="chrome" mimics a real Chrome TLS handshake and
# defeats the block. We build ONE shared session and hand it to every
# yf.Ticker so all calls go through the impersonated client.
try:
    from curl_cffi import requests as _curl_requests
    _HAS_CURL = True
except Exception:  # curl_cffi missing -> fall back to yfinance default
    _curl_requests = None
    _HAS_CURL = False

# curl_cffi sessions are NOT thread-safe: sharing one across a ThreadPoolExecutor
# (used by the parallel option-chain scan) makes concurrent requests hang. We
# therefore keep one impersonation session PER THREAD via thread-local storage.
_TLS = threading.local()


def _get_session():
    """Return this thread's curl_cffi impersonation session (lazily created)."""
    if not _HAS_CURL:
        return None
    sess = getattr(_TLS, "session", None)
    if sess is None:
        sess = _curl_requests.Session(impersonate="chrome")
        _TLS.session = sess
    return sess


def _refresh_session():
    """Drop this thread's session so the next call rebuilds it (new cookies/crumb)
    after a Yahoo block."""
    if not _HAS_CURL:
        return None
    _TLS.session = None
    return _get_session()


_CACHE = {}
_CACHE_LOCK = threading.Lock()
# Hard cap so a long-running process (or a 515-name scan that fetches
# quote+history+info per ticker ≈ 1500 entries) can't grow the cache without
# bound — that was leaking memory and tripping Render's 512MB limit. When the
# cap is hit we drop expired entries first, then the oldest, keeping RSS flat.
_CACHE_MAX = 900
_CACHE_DEFAULT_TTL = 1800  # used only for opportunistic expiry-based eviction


def _cache_get(key, ttl):
    with _CACHE_LOCK:
        item = _CACHE.get(key)
        if item and (time.time() - item[0]) < ttl:
            return item[1]
    return None


def _evict_locked():
    """Caller must hold _CACHE_LOCK. Trim the cache back under the cap by first
    dropping stale entries, then the oldest by timestamp."""
    if len(_CACHE) <= _CACHE_MAX:
        return
    now = time.time()
    # 1) drop anything older than the default TTL
    stale = [k for k, (ts, _) in _CACHE.items() if now - ts > _CACHE_DEFAULT_TTL]
    for k in stale:
        _CACHE.pop(k, None)
    # 2) if still over, evict oldest until ~10% headroom
    if len(_CACHE) > _CACHE_MAX:
        target = int(_CACHE_MAX * 0.9)
        for k, _ in sorted(_CACHE.items(), key=lambda kv: kv[1][0])[: len(_CACHE) - target]:
            _CACHE.pop(k, None)


def _cache_set(key, value):
    with _CACHE_LOCK:
        _CACHE[key] = (time.time(), value)
        _evict_locked()


def _cache_purge_ticker(ticker):
    """Drop the heavy per-ticker scan artifacts (history DataFrame + info dict)
    from the cache once a ticker has been evaluated. During a 515-name scan
    these would otherwise pile up and blow past Render's 512MB free-tier limit.
    Quotes are tiny and kept (they back the fast single-ticker quote path)."""
    ticker = (ticker or "").upper().strip()
    with _CACHE_LOCK:
        for k in [k for k in _CACHE
                  if k.startswith(f"hist:{ticker}:")
                  or k == f"info:{ticker}"
                  or k == f"infolight:{ticker}"]:
            _CACHE.pop(k, None)


def _safe(v):
    """Convert numpy/pandas scalars to JSON-safe Python floats; NaN->None."""
    try:
        if v is None:
            return None
        if isinstance(v, (np.floating, float)):
            f = float(v)
            return None if math.isnan(f) else f
        if isinstance(v, (np.integer, int)):
            return int(v)
        return v
    except Exception:
        return None


class DataProvider:
    """Interface. Implement these to add a new provider."""
    name = "base"

    def quote(self, ticker): raise NotImplementedError
    def history(self, ticker, period="1y", interval="1d"): raise NotImplementedError
    def info(self, ticker): raise NotImplementedError
    def expirations(self, ticker): raise NotImplementedError
    def option_chain(self, ticker, expiry): raise NotImplementedError


class YahooProvider(DataProvider):
    name = "yahoo"

    def __init__(self, quote_ttl=20, info_ttl=600, chain_ttl=60, hist_ttl=900):
        self.quote_ttl = quote_ttl
        self.info_ttl = info_ttl
        self.chain_ttl = chain_ttl
        self.hist_ttl = hist_ttl

    def _ticker(self, ticker):
        sess = _get_session()
        if sess is not None:
            return yf.Ticker(ticker.upper().strip(), session=sess)
        return yf.Ticker(ticker.upper().strip())

    def quote(self, ticker):
        ticker = ticker.upper().strip()
        key = f"quote:{ticker}"
        cached = _cache_get(key, self.quote_ttl)
        if cached:
            return cached
        # First attempt; if Yahoo blocked us (empty data), rebuild the
        # impersonation session once and retry before giving up.
        try:
            return self._quote_once(ticker, key)
        except ValueError:
            _refresh_session()
            return self._quote_once(ticker, key)

    def _quote_once(self, ticker, key):
        t = self._ticker(ticker)
        fi = {}
        try:
            fi = dict(t.fast_info)
        except Exception:
            pass
        # IMPORTANT: yfinance's fast_info.previousClose is unreliable — it can be
        # misaligned by a session (e.g. it returned 133.89 for PLTR while the
        # true prior regular close was 141.70, flipping a -4.4% day into +1.2%).
        # Prefer Yahoo's authoritative, session-aligned .info fields and only
        # fall back to fast_info / history if they're missing.
        price = _safe(fi.get("lastPrice")) or _safe(fi.get("last_price"))
        prev = None
        info = {}
        try:
            info = t.info or {}
        except Exception:
            info = {}
        rmp = _safe(info.get("regularMarketPrice"))
        rmpc = (_safe(info.get("regularMarketPreviousClose"))
                or _safe(info.get("previousClose")))
        if rmp is not None:
            price = rmp  # the regular-session price (stable across pre/post market)
        if rmpc is not None:
            prev = rmpc
        # Fallbacks if .info was unavailable.
        if prev is None:
            prev = _safe(fi.get("regularMarketPreviousClose"))
        if price is None or prev is None:
            # last resort: derive both from daily history
            try:
                h = t.history(period="5d")
                if len(h):
                    if price is None:
                        price = _safe(h["Close"].iloc[-1])
                    if prev is None and len(h) > 1:
                        prev = _safe(h["Close"].iloc[-2])
            except Exception:
                pass
        if price is None:
            raise ValueError(f"לא נמצא מחיר עבור הטיקר '{ticker}'")
        out = {
            "ticker": ticker,
            "price": price,
            "previous_close": prev,
            "change": _safe(price - prev) if (price and prev) else None,
            "change_pct": _safe((price / prev - 1) * 100) if (price and prev) else None,
            "year_high": _safe(fi.get("yearHigh")) or _safe(fi.get("year_high")),
            "year_low": _safe(fi.get("yearLow")) or _safe(fi.get("year_low")),
            "currency": fi.get("currency"),
            "exchange": fi.get("exchange"),
            "as_of": datetime.now(timezone.utc).isoformat(),
            "provider": self.name,
        }
        _cache_set(key, out)
        return out

    def history(self, ticker, period="1y", interval="1d"):
        ticker = ticker.upper().strip()
        key = f"hist:{ticker}:{period}:{interval}"
        cached = _cache_get(key, self.hist_ttl)
        if cached is not None:
            return cached
        t = self._ticker(ticker)
        h = t.history(period=period, interval=interval, auto_adjust=False)
        if h is None or len(h) == 0:
            raise ValueError(f"אין נתוני היסטוריה עבור '{ticker}'")
        _cache_set(key, h)
        return h

    def info(self, ticker):
        ticker = ticker.upper().strip()
        key = f"info:{ticker}"
        cached = _cache_get(key, self.info_ttl)
        if cached is not None:
            return cached
        t = self._ticker(ticker)
        info = {}
        try:
            info = dict(t.info)
        except Exception:
            info = {}
        # Enrich with statement-derived fields that .info often omits
        info = self._enrich_financials(t, info)
        _cache_set(key, info)
        return info

    def info_light(self, ticker):
        """Fast info: plain Yahoo .info WITHOUT pulling cashflow/balance-sheet/
        financials statements. Used by the universe scanner where statement
        enrichment (3-4 extra round-trips per ticker) would make a 515-name scan
        far too slow. Cached separately. long_term_score / distortion degrade
        gracefully on the fields .info omits."""
        ticker = ticker.upper().strip()
        key = f"infolight:{ticker}"
        cached = _cache_get(key, self.info_ttl)
        if cached is not None:
            return cached
        t = self._ticker(ticker)
        try:
            info = dict(t.info)
        except Exception:
            info = {}
        _cache_set(key, info)
        return info

    def dividend_params(self, ticker, T=2.0):
        """מחזיר פרמטרי דיבידנד לתמחור אמריקאי, 'לפי זמינות':
          { 'q': continuous_yield_or_0,
            'dividends': [(t_years, amount), ...] | None,
            'source': 'discrete' | 'yield' | 'none' }
        מעדיף דיבידנדים בדידים (מדויק למימוש מוקדם) אם זמינים,
        אחרת נופל בחזרה לתשואה רציפה. קשור היטב ל-512MB — משתמש
        ב-info המטמון ובסדרת דיבידנדים קטנה בלבד."""
        ticker = ticker.upper().strip()
        key = f"div:{ticker}"
        cached = _cache_get(key, self.info_ttl)
        if cached is not None:
            return cached
        import math as _math
        result = {"q": 0.0, "dividends": None, "source": "none"}
        try:
            info = self.info_light(ticker)
        except Exception:
            info = {}
        # תשואה רציפה (fallback) — Yahoo dividendYield לעיתים באחוזים, לעיתים כשבר (0-1)
        dy = info.get("dividendYield")
        try:
            dy = float(dy) if dy is not None else None
        except (TypeError, ValueError):
            dy = None
        if dy is not None and dy > 0:
            # Yahoo מחזיר לעיתים 1.8 (אחוזים) ולעיתים 0.018; מנרמלים
            q_cont = dy / 100.0 if dy > 1.0 else dy
            result["q"] = float(q_cont)
            result["source"] = "yield"
        # דיבידנדים בדידים — משליכים את התשלומים האחרונים קדימה לאורך T
        try:
            t = self._ticker(ticker)
            divs = t.dividends  # pandas Series, index=ex-date
            if divs is not None and len(divs) >= 2:
                recent = divs.tail(8)
                # תדירות ממוצעת בין תשלומים (בשנים)
                idx = recent.index
                gaps = [(idx[i] - idx[i-1]).days for i in range(1, len(idx))]
                avg_gap_days = sum(gaps) / len(gaps) if gaps else 91.0
                avg_gap_yr = max(avg_gap_days / 365.0, 1e-3)
                last_amt = float(recent.iloc[-1])
                last_date = idx[-1]
                import datetime as _dt
                now = _dt.datetime.now(last_date.tzinfo) if getattr(last_date, "tzinfo", None) else _dt.datetime.now()
                # משליכים תשלומים עתידיים עד אופק T
                future = []
                t_next = (last_date - now).days / 365.0 + avg_gap_yr
                while 0 < t_next <= T and len(future) < 16:
                    future.append((float(t_next), last_amt))
                    t_next += avg_gap_yr
                if future and last_amt > 0:
                    result["dividends"] = future
                    result["source"] = "discrete"
        except Exception:
            pass
        _cache_set(key, result)
        return result

    def _enrich_financials(self, t, info):
        """Pull FCF, total assets, retained earnings, EBIT, working capital
        from the financial statements when .info lacks them."""
        try:
            cf = t.cashflow
            if cf is not None and not cf.empty:
                col = cf.columns[0]
                fcf = None
                if "Free Cash Flow" in cf.index:
                    fcf = cf.loc["Free Cash Flow", col]
                else:
                    ocf = cf.loc["Operating Cash Flow", col] if "Operating Cash Flow" in cf.index else None
                    capex = cf.loc["Capital Expenditure", col] if "Capital Expenditure" in cf.index else None
                    if ocf is not None and capex is not None:
                        fcf = ocf + capex  # capex is negative
                if fcf is not None and not info.get("freeCashflow"):
                    info["freeCashflow"] = _safe(fcf)
        except Exception:
            pass
        try:
            bs = t.balance_sheet
            if bs is not None and not bs.empty:
                col = bs.columns[0]
                def gb(*names):
                    for n in names:
                        if n in bs.index:
                            return _safe(bs.loc[n, col])
                    return None
                ta = gb("Total Assets")
                if ta and not info.get("totalAssets"):
                    info["totalAssets"] = ta
                re = gb("Retained Earnings")
                if re and not info.get("retainedEarnings"):
                    info["retainedEarnings"] = re
                ca = gb("Current Assets", "Total Current Assets")
                cl = gb("Current Liabilities", "Total Current Liabilities")
                if ca and cl:
                    info["_workingCapital"] = ca - cl
                if cl is not None:
                    info["_currentLiabilities"] = cl
                # Real book equity for ROIC denominator (avoid marketCap proxy)
                eq = gb("Stockholders Equity", "Total Stockholder Equity",
                        "Total Stockholders Equity", "Common Stock Equity")
                if eq is not None:
                    info["_bookEquity"] = eq
                cash = gb("Cash And Cash Equivalents",
                          "Cash Cash Equivalents And Short Term Investments",
                          "Cash And Cash Equivalents And Short Term Investments")
                if cash is not None:
                    info["_cash"] = cash
        except Exception:
            pass
        try:
            fin = t.financials
            if fin is not None and not fin.empty:
                col = fin.columns[0]
                if "EBIT" in fin.index and not info.get("_ebit"):
                    info["_ebit"] = _safe(fin.loc["EBIT", col])
                elif "Operating Income" in fin.index and not info.get("_ebit"):
                    info["_ebit"] = _safe(fin.loc["Operating Income", col])
        except Exception:
            pass
        return info

    def expirations(self, ticker):
        ticker = ticker.upper().strip()
        key = f"exps:{ticker}"
        cached = _cache_get(key, self.chain_ttl)
        if cached is not None:
            return cached
        t = self._ticker(ticker)
        try:
            exps = list(t.options)
        except Exception:
            exps = []
        _cache_set(key, exps)
        return exps

    def option_chain(self, ticker, expiry):
        ticker = ticker.upper().strip()
        key = f"chain:{ticker}:{expiry}"
        cached = _cache_get(key, self.chain_ttl)
        if cached is not None:
            return cached
        # Under concurrent scans (ThreadPoolExecutor) a freshly-created yf.Ticker
        # must first fetch the option-expirations metadata before it can return a
        # chain. When many threads hit Yahoo simultaneously some metadata calls
        # get throttled and come back empty, so option_chain() raises
        # "Expiration ... cannot be found. Available expirations are: []".
        # We retry a couple of times with a fresh impersonation session +
        # tiny jittered backoff, which lets the metadata populate.
        last_err = None
        for attempt in range(3):
            try:
                t = self._ticker(ticker)
                ch = t.option_chain(expiry)
                calls = self._chain_to_records(ch.calls, "call")
                puts = self._chain_to_records(ch.puts, "put")
                out = {"calls": calls, "puts": puts}
                _cache_set(key, out)
                return out
            except Exception as e:
                last_err = e
                # Rebuild this thread's session and wait a touch before retrying.
                _refresh_session()
                time.sleep(0.4 + 0.3 * attempt)
        raise last_err

    @staticmethod
    def _chain_to_records(df, kind):
        recs = []
        for _, row in df.iterrows():
            recs.append({
                "contract": row.get("contractSymbol"),
                "strike": _safe(row.get("strike")),
                "last": _safe(row.get("lastPrice")),
                "bid": _safe(row.get("bid")),
                "ask": _safe(row.get("ask")),
                "mid": _safe(((row.get("bid") or 0) + (row.get("ask") or 0)) / 2)
                        if (row.get("bid") or row.get("ask")) else _safe(row.get("lastPrice")),
                "iv": _safe(row.get("impliedVolatility")),
                "volume": _safe(row.get("volume")) or 0,
                "open_interest": _safe(row.get("openInterest")) or 0,
                "in_the_money": bool(row.get("inTheMoney")),
                "kind": kind,
            })
        return recs


def _sic_to_sector(sic_code: int, sic_desc: str) -> str:
    c, d = int(sic_code or 0), (sic_desc or "").lower()
    if 6000 <= c < 7000: return "Financial Services"
    if 4900 <= c < 5000: return "Utilities"
    if 6510 <= c < 6560: return "Real Estate"
    if any(x in d for x in ("pharma", "drug", "biotech", "medical", "hospital", "health")):
        return "Healthcare"
    if 8000 <= c < 8100: return "Healthcare"
    if any(x in d for x in ("computer", "software", "semiconductor", "data processing", "internet", "electronic")):
        return "Technology"
    if 7370 <= c < 7380: return "Technology"
    if any(x in d for x in ("telecom", "telephone", "cable", "broadcast", "media", "entertainment", "communication")):
        return "Communication Services"
    if 4800 <= c < 4900: return "Communication Services"
    if 1300 <= c < 1400 or any(x in d for x in ("oil", "gas", "petroleum", "energy")):
        return "Energy"
    if any(x in d for x in ("food", "beverage", "tobacco", "household", "personal care")):
        return "Consumer Defensive"
    if 2000 <= c < 2200: return "Consumer Defensive"
    if any(x in d for x in ("retail", "apparel", "automotive", "hotel", "restaurant", "gaming")):
        return "Consumer Cyclical"
    if 5000 <= c < 6000: return "Consumer Cyclical"
    if 1000 <= c < 1500 or any(x in d for x in ("mining", "mineral", "chemical", "paper", "metal")):
        return "Basic Materials"
    return "Industrials"


def _polygon_get(path: str, params: dict, api_key: str) -> dict:
    p = dict(params)
    p["apiKey"] = api_key
    url = f"https://api.polygon.io{path}?{urllib.parse.urlencode(p)}"
    req = urllib.request.Request(url, headers={"User-Agent": "OptionDesk/1.0"})
    with urllib.request.urlopen(req, timeout=15, context=_SSL_CTX) as r:
        return json.loads(r.read().decode())


def _period_days(period: str) -> int:
    return {"1d": 1, "5d": 5, "1mo": 30, "3mo": 90, "6mo": 180,
            "1y": 365, "2y": 730, "3y": 1095, "5y": 1825}.get(period, 365)


class PolygonLiveProvider(DataProvider):
    """Live market data via Polygon.io — replaces YahooProvider."""
    name = "polygon"

    def __init__(self, api_key: str,
                 quote_ttl=20, info_ttl=600, chain_ttl=60, hist_ttl=900):
        self._key = api_key
        self.quote_ttl = quote_ttl
        self.info_ttl = info_ttl
        self.chain_ttl = chain_ttl
        self.hist_ttl = hist_ttl

    def _get(self, path: str, params: dict | None = None) -> dict:
        return _polygon_get(path, params or {}, self._key)

    # ------------------------------------------------------------------ quote
    def quote(self, ticker: str) -> dict:
        ticker = ticker.upper().strip()
        key = f"quote:{ticker}"
        cached = _cache_get(key, self.quote_ttl)
        if cached:
            return cached

        data = self._get(f"/v2/snapshot/locale/us/markets/stocks/tickers/{ticker}")
        snap = data.get("ticker") or data.get("results") or {}
        day = snap.get("day") or {}
        prev = snap.get("prevDay") or {}

        price = (_safe(snap.get("lastTrade", {}).get("p"))
                 or _safe(snap.get("last", {}).get("price"))
                 or _safe(day.get("c")))
        prev_close = _safe(prev.get("c"))

        # 52-week range — use a cached 1y history call if already fetched
        year_high = year_low = None
        try:
            h = self.history(ticker, "1y")
            if h is not None and len(h):
                year_high = float(h["High"].max())
                year_low = float(h["Low"].min())
        except Exception:
            pass

        if price is None:
            raise ValueError(f"לא נמצא מחיר עבור הטיקר '{ticker}'")

        out = {
            "ticker": ticker,
            "price": price,
            "previous_close": prev_close,
            "change": _safe(price - prev_close) if (price and prev_close) else None,
            "change_pct": _safe((price / prev_close - 1) * 100) if (price and prev_close) else None,
            "year_high": year_high,
            "year_low": year_low,
            "currency": "USD",
            "exchange": snap.get("T", ""),
            "as_of": datetime.now(timezone.utc).isoformat(),
            "provider": self.name,
        }
        _cache_set(key, out)
        return out

    # --------------------------------------------------------------- history
    def history(self, ticker: str, period: str = "1y", interval: str = "1d"):
        ticker = ticker.upper().strip()
        key = f"hist:{ticker}:{period}:{interval}"
        cached = _cache_get(key, self.hist_ttl)
        if cached is not None:
            return cached

        span_map = {"1d": ("1", "day"), "1wk": ("1", "week"), "1mo": ("1", "month")}
        mult, span = span_map.get(interval, ("1", "day"))
        today = date.today()
        from_date = (today - timedelta(days=_period_days(period))).strftime("%Y-%m-%d")
        to_date = today.strftime("%Y-%m-%d")

        data = self._get(
            f"/v2/aggs/ticker/{ticker}/range/{mult}/{span}/{from_date}/{to_date}",
            {"adjusted": "true", "sort": "asc", "limit": 5000},
        )
        results = data.get("results") or []
        if not results:
            raise ValueError(f"אין נתוני היסטוריה עבור '{ticker}'")

        rows = [{
            "Date": datetime.utcfromtimestamp(r["t"] / 1000),
            "Open": float(r.get("o", 0)),
            "High": float(r.get("h", 0)),
            "Low": float(r.get("l", 0)),
            "Close": float(r.get("c", 0)),
            "Volume": int(r.get("v", 0)),
        } for r in results]

        df = pd.DataFrame(rows).set_index("Date")
        df.index = pd.DatetimeIndex(df.index)
        _cache_set(key, df)
        return df

    # ------------------------------------------------------------------- info
    def info(self, ticker: str) -> dict:
        ticker = ticker.upper().strip()
        key = f"info:{ticker}"
        cached = _cache_get(key, self.info_ttl)
        if cached is not None:
            return cached

        result: dict = {}

        # 1. Reference ticker (name, sector, shares, market cap)
        try:
            ref = self._get(f"/v3/reference/tickers/{ticker}")
            r = ref.get("results") or {}
            result["shortName"] = r.get("name")
            result["longBusinessSummary"] = r.get("description")
            result["exchange"] = r.get("primary_exchange")
            result["currency"] = "USD"
            shares = r.get("weighted_shares_outstanding") or r.get("share_class_shares_outstanding")
            result["sharesOutstanding"] = shares
            result["marketCap"] = r.get("market_cap")
            result["sector"] = _sic_to_sector(int(r.get("sic_code") or 0), r.get("sic_description") or "")
            result["industry"] = r.get("sic_description")
        except Exception:
            pass

        # 2. Current price for ratio computation
        price = None
        try:
            q = self.quote(ticker)
            price = q.get("price")
            result["currentPrice"] = price
            if result.get("marketCap") is None and price and result.get("sharesOutstanding"):
                result["marketCap"] = price * result["sharesOutstanding"]
        except Exception:
            pass

        # 3. Financial statements (latest 2 annual periods)
        try:
            fin_data = self._get("/vX/reference/financials", {
                "ticker": ticker, "timeframe": "annual",
                "limit": 2, "sort": "period_of_report_date", "order": "desc",
            })
            fin_results = fin_data.get("results") or []
            if fin_results:
                def _fv(section, period_idx, *keys):
                    fs = ((fin_results[period_idx] if period_idx < len(fin_results) else {})
                          .get("financials") or {}).get(section) or {}
                    for k in keys:
                        if k in fs and fs[k].get("value") is not None:
                            return float(fs[k]["value"])
                    return None

                IS, BS, CF = "income_statement", "balance_sheet", "cash_flow_statement"

                rev   = _fv(IS, 0, "revenues", "net_revenues", "revenue_from_contract_with_customer_excluding_assessed_tax")
                gp    = _fv(IS, 0, "gross_profit")
                oi    = _fv(IS, 0, "operating_income_loss", "income_from_operations")
                ni    = _fv(IS, 0, "net_income_loss", "net_income_loss_attributable_to_parent")
                eps   = _fv(IS, 0, "diluted_earnings_per_share", "basic_earnings_per_share")

                ta    = _fv(BS, 0, "assets")
                ca    = _fv(BS, 0, "current_assets")
                cl    = _fv(BS, 0, "current_liabilities")
                ltd   = _fv(BS, 0, "long_term_debt", "long_term_debt_and_capital_lease_obligations")
                ret   = _fv(BS, 0, "retained_earnings_accumulated_deficit", "retained_earnings")
                eq    = _fv(BS, 0, "equity", "stockholders_equity", "equity_attributable_to_parent")
                cash  = _fv(BS, 0, "cash_and_cash_equivalents_at_carrying_value",
                             "cash_and_cash_equivalents", "cash_and_cash_equivalents_and_short_term_investments")

                ocf   = _fv(CF, 0, "net_cash_flow_from_operating_activities",
                             "net_cash_provided_by_used_in_operating_activities")
                capex = _fv(CF, 0, "capital_expenditure",
                             "payments_to_acquire_property_plant_and_equipment")
                fcf   = ((ocf + capex) if (ocf is not None and capex is not None)
                         else ocf)  # capex is typically negative

                rev_p = _fv(IS, 1, "revenues", "net_revenues", "revenue_from_contract_with_customer_excluding_assessed_tax")
                ni_p  = _fv(IS, 1, "net_income_loss", "net_income_loss_attributable_to_parent")

                result.update({
                    "totalRevenue": rev, "freeCashflow": fcf,
                    "totalDebt": ltd, "totalCash": cash, "totalAssets": ta,
                    "retainedEarnings": ret, "_bookEquity": eq, "_cash": cash,
                    "_currentLiabilities": cl, "_ebit": oi,
                    "_workingCapital": ((ca - cl) if (ca and cl) else None),
                })

                mcap   = result.get("marketCap")
                shares = result.get("sharesOutstanding")

                def _ratio(n, d): return _safe(n / d) if (n is not None and d and d != 0) else None

                if rev:
                    result["grossMargins"]                  = _ratio(gp, rev)
                    result["operatingMargins"]              = _ratio(oi, rev)
                    result["profitMargins"]                 = _ratio(ni, rev)
                    result["priceToSalesTrailing12Months"]  = _ratio(mcap, rev)
                if eq and eq > 0:
                    result["returnOnEquity"]  = _ratio(ni, eq)
                    result["debtToEquity"]    = _safe((ltd or 0) / eq * 100)
                    result["priceToBook"]     = _ratio(mcap, eq)
                if ta and ta > 0:
                    result["returnOnAssets"]  = _ratio(ni, ta)
                if ca and cl and cl > 0:
                    result["currentRatio"]    = _ratio(ca, cl)
                # trailingPE: prefer computed EPS from financials, fallback to Polygon EPS field
                if price:
                    eps_calc = (ni / shares) if (ni and shares and shares > 0) else None
                    denom = eps_calc or eps
                    if denom and denom > 0:
                        result["trailingPE"] = _safe(price / denom)
                # YoY growth
                result["revenueGrowth"]  = _ratio(rev - rev_p, abs(rev_p)) if (rev and rev_p) else None
                result["earningsGrowth"] = (_ratio(ni - ni_p, abs(ni_p))
                                             if (ni is not None and ni_p) else None)
        except Exception:
            pass

        # 4. Dividend yield
        try:
            dp = self.dividend_params(ticker)
            if dp.get("q"):
                result["dividendYield"] = dp["q"]
        except Exception:
            pass

        # 5. Beta from 2-year price regression vs SPY
        try:
            result["beta"] = self.beta(ticker)
        except Exception:
            pass

        # Fields not available from Polygon (set to None for graceful degradation)
        result.setdefault("forwardPE", None)
        result.setdefault("pegRatio", None)
        result.setdefault("shortPercentOfFloat", None)
        result.setdefault("shortRatio", None)

        _cache_set(key, result)
        return result

    # -------------------------------------------------------------- info_light
    def info_light(self, ticker: str) -> dict:
        ticker = ticker.upper().strip()
        key = f"infolight:{ticker}"
        cached = _cache_get(key, self.info_ttl)
        if cached is not None:
            return cached
        result: dict = {}
        try:
            ref = self._get(f"/v3/reference/tickers/{ticker}")
            r = ref.get("results") or {}
            result["shortName"]       = r.get("name")
            result["marketCap"]       = r.get("market_cap")
            result["sharesOutstanding"] = (r.get("weighted_shares_outstanding")
                                           or r.get("share_class_shares_outstanding"))
            result["sector"]   = _sic_to_sector(int(r.get("sic_code") or 0), r.get("sic_description") or "")
            result["industry"] = r.get("sic_description")
        except Exception:
            pass
        try:
            dp = self.dividend_params(ticker)
            if dp.get("q"):
                result["dividendYield"] = dp["q"]
        except Exception:
            pass
        _cache_set(key, result)
        return result

    # --------------------------------------------------------- dividend_params
    def dividend_params(self, ticker: str, T: float = 2.0) -> dict:
        ticker = ticker.upper().strip()
        key = f"div:{ticker}"
        cached = _cache_get(key, self.info_ttl)
        if cached is not None:
            return cached

        result = {"q": 0.0, "dividends": None, "source": "none"}
        try:
            data = self._get("/v3/reference/dividends",
                             {"ticker": ticker, "limit": 12,
                              "sort": "ex_dividend_date", "order": "desc"})
            divs = [d for d in (data.get("results") or [])
                    if d.get("dividend_type") in ("CD", None)]
            if len(divs) >= 2:
                dates = []
                for d in divs[:8]:
                    try:
                        dates.append(datetime.strptime(d["ex_dividend_date"], "%Y-%m-%d").date())
                    except Exception:
                        pass
                if dates:
                    gaps = [(dates[i] - dates[i + 1]).days for i in range(len(dates) - 1)]
                    avg_gap = sum(gaps) / len(gaps) if gaps else 91.0
                    last_amt = float(divs[0].get("cash_amount") or 0)
                    annual = last_amt * (365.0 / max(avg_gap, 1))
                    try:
                        price = self.quote(ticker).get("price") or 0
                        if price > 0:
                            result["q"] = annual / price
                            result["source"] = "yield"
                    except Exception:
                        pass
                    # Discrete schedule for American pricing
                    now = date.today()
                    avg_yr = avg_gap / 365.0
                    t_next = (dates[0] - now).days / 365.0 + avg_yr
                    future = []
                    while 0 < t_next <= T and len(future) < 16:
                        future.append((float(t_next), last_amt))
                        t_next += avg_yr
                    if future and last_amt > 0:
                        result["dividends"] = future
                        result["source"] = "discrete"
        except Exception:
            pass
        _cache_set(key, result)
        return result

    # ------------------------------------------------------------ expirations
    def expirations(self, ticker: str) -> list:
        ticker = ticker.upper().strip()
        key = f"exps:{ticker}"
        cached = _cache_get(key, self.chain_ttl)
        if cached is not None:
            return cached
        try:
            data = self._get("/v3/reference/options/contracts", {
                "underlying_ticker": ticker,
                "as_of": date.today().strftime("%Y-%m-%d"),
                "expired": "false", "limit": 1000,
                "sort": "expiration_date", "order": "asc",
            })
            exps = sorted({r["expiration_date"]
                           for r in (data.get("results") or [])
                           if "expiration_date" in r})
            _cache_set(key, exps)
            return exps
        except Exception:
            return []

    # ------------------------------------------------------------ option_chain
    def option_chain(self, ticker: str, expiry: str) -> dict:
        ticker = ticker.upper().strip()
        key = f"chain:{ticker}:{expiry}"
        cached = _cache_get(key, self.chain_ttl)
        if cached is not None:
            return cached

        data = self._get(f"/v3/snapshot/options/{ticker}", {
            "expiration_date": expiry, "limit": 250,
            "sort": "strike_price", "order": "asc",
        })
        calls, puts = [], []
        for r in (data.get("results") or []):
            d    = r.get("details") or {}
            g    = r.get("greeks") or {}
            q_d  = r.get("last_quote") or {}
            day  = r.get("day") or {}
            lt   = r.get("last_trade") or {}

            bid = _safe(q_d.get("bid") or q_d.get("B"))
            ask = _safe(q_d.get("ask") or q_d.get("A"))
            mid = _safe(r.get("fair_market_value"))
            if mid is None and bid is not None and ask is not None:
                mid = (bid + ask) / 2

            rec = {
                "contract":      d.get("ticker"),
                "strike":        _safe(d.get("strike_price")),
                "last":          _safe(lt.get("price") or day.get("close")),
                "bid":           bid,
                "ask":           ask,
                "mid":           mid,
                "iv":            _safe(r.get("implied_volatility")),
                "volume":        int(_safe(day.get("volume")) or 0),
                "open_interest": int(_safe(r.get("open_interest")) or 0),
                "in_the_money":  bool(r.get("in_the_money", False)),
                "kind":          d.get("contract_type", "call"),
                "delta":         _safe(g.get("delta")),
                "gamma":         _safe(g.get("gamma")),
                "theta":         _safe(g.get("theta")),
                "vega":          _safe(g.get("vega")),
            }
            (puts if d.get("contract_type") == "put" else calls).append(rec)

        out = {"calls": calls, "puts": puts}
        _cache_set(key, out)
        return out

    # -------------------------------------------------------------------- beta
    def beta(self, ticker: str, benchmark: str = "SPY", period: str = "2y") -> float | None:
        """OLS beta: cov(stock, benchmark) / var(benchmark) over `period` daily returns."""
        key = f"beta:{ticker}:{benchmark}:{period}"
        cached = _cache_get(key, 86400)  # 24-hour cache
        if cached is not None:
            return cached
        try:
            sh = self.history(ticker, period)
            bh = self.history(benchmark, period)
            combined = pd.concat([sh["Close"].rename("s"), bh["Close"].rename("b")],
                                 axis=1).dropna()
            if len(combined) < 60:
                return None
            sr = combined["s"].pct_change().dropna()
            br = combined["b"].pct_change().dropna()
            combined2 = pd.concat([sr, br], axis=1).dropna()
            cov = np.cov(combined2.iloc[:, 0].values, combined2.iloc[:, 1].values)
            beta_val = float(cov[0, 1] / cov[1, 1])
            beta_val = round(max(-3.0, min(5.0, beta_val)), 3)
            _cache_set(key, beta_val)
            return beta_val
        except Exception:
            return None


# Default provider instance — Polygon when key is set, Yahoo as fallback
_POLYGON_KEY = os.environ.get("POLYGON_API_KEY", "").strip()
if _POLYGON_KEY:
    PROVIDER: DataProvider = PolygonLiveProvider(_POLYGON_KEY)
elif _HAS_YF:
    PROVIDER: DataProvider = YahooProvider()
else:
    raise RuntimeError("No data provider available: set POLYGON_API_KEY or install yfinance")
