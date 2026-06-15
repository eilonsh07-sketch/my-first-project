"""Investment-Ideas scanner.

Scans a stock universe (S&P 500 + Nasdaq-100) and ranks each name by a weighted
0-100 attractiveness score for BUYING THE STOCK (not an option). Five components,
per the user's spec:

  1. technical      - SC.momentum_score(tech)           (0-100)
  2. fundamental    - F.long_term_score(info, tech)      (0-100)
  3. price distortion - DCF/analyst upside vs market price -> mispricing score
  4. iv opportunity - cheap implied vol vs realized (long-premium edge) -> proxy
  5. weighted       - the composite, weights chosen by historical validation

DESIGN FOR SCALE
- 515 tickers; per ticker we fetch quote + 1y history + light info + index history.
- Heavy financial-statement enrichment is SKIPPED in the universe scan (too slow
  at 515 names); long_term_score degrades gracefully on missing axes and uses the
  valuation fields .info provides directly.
- Network round-trips are the slow part, so fetches run in a ThreadPoolExecutor.
- A failed ticker is skipped, never fatal.
- Results are cached with an as-of timestamp; the scan can run in a background
  thread while the API serves status + partial results.
"""

from __future__ import annotations
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

from . import scoring as SC
from . import fundamentals as F
from . import technicals as T
from .universe import universe, membership

INDEX = "^GSPC"  # S&P 500 for relative-strength / beta

# --- component weights (CHOSEN BY HISTORICAL VALIDATION; see ideas_validation.py) ---
# Validated over 4 forward horizons (3/6/9/12 months, ~118 names each):
#   iv_opportunity: most consistent POSITIVE predictor (Spearman +0.17..+0.24) -> top
#       weight, but capped (it's a vol proxy, not real option chains).
#   technical:      strong predictor, peaks at 6mo (Spearman up to +0.40).
#   fundamental:    ~neutral short-term; kept for the buy-and-hold lens at modest weight.
#   distortion:     historically CONTRARIAN/negative (Spearman ~-0.22 every horizon) -
#       'cheap vs fair value' lagged. Kept as a low-weight informational sub-score and
#       FLAGGED in the UI so it doesn't mislead the decision.
WEIGHTS = {
    "technical": 0.30,
    "fundamental": 0.20,
    "distortion": 0.15,
    "iv_opportunity": 0.35,
}

# Per the validation, a HIGH distortion score (looks very cheap) has historically
# NOT predicted outperformance. Surface a caution flag when distortion is the main
# thing carrying a name.
DISTORTION_CAUTION = True

# ---------------------------------------------------------------- distortion --
def distortion_score(info, tech):
    """0-100 mispricing score: how cheap is the stock vs its intrinsic/analyst value.

    Blends two independent value anchors when available:
      - DCF upside  (fair_value / price - 1)
      - Analyst mean target upside (targetMeanPrice / price - 1)
    Higher upside (cheaper vs value) -> higher score. Returns score + the raw
    upside figures for display. Degrades gracefully if one anchor is missing.
    """
    price = F._g(info, "currentPrice") or F._g(info, "regularMarketPrice")
    anchors = []
    dcf_up = None
    analyst_up = None

    # DCF anchor (uses freeCashflow from .info if present). A two-stage DCF can
    # blow up (e.g. +200% upside) when FCF spikes or WACC-g is tiny; that's a model
    # artifact, not a real signal, so we CAP each anchor to a sane band before use.
    def _cap(u):
        return max(-0.90, min(1.00, float(u)))

    try:
        dcf = F.dcf_fair_value(info, {})
        if dcf.get("upside") is not None:
            dcf_up = _cap(dcf["upside"])
            anchors.append(dcf_up)
    except Exception:
        pass

    # Analyst-target anchor
    tgt = F._g(info, "targetMeanPrice")
    if tgt and price:
        analyst_up = _cap(float(tgt) / float(price) - 1.0)
        anchors.append(analyst_up)

    if not anchors:
        return {"score": None, "dcf_upside": None, "analyst_upside": None,
                "blended_upside": None}

    blended = sum(anchors) / len(anchors)
    # Map upside to 0-100: -30% upside -> 0, +50% upside -> 100, 0% -> ~37.5
    score = _lin(blended, -0.30, 0.50)
    return {
        "score": round(score, 1),
        "dcf_upside": round(dcf_up, 4) if dcf_up is not None else None,
        "analyst_upside": round(analyst_up, 4) if analyst_up is not None else None,
        "blended_upside": round(blended, 4),
    }


# ------------------------------------------------------------ iv opportunity --
def iv_opportunity_score(info, tech):
    """0-100 'cheap options' proxy WITHOUT fetching option chains (too slow at scale).

    Long-premium edge is biggest when implied vol is LOW relative to the stock's
    own realized vol and there is real movement potential. We proxy implied vol
    with the .info field when present, else fall back to a realized-vol regime
    read. Lower IV-vs-RV (options look underpriced) AND meaningful realized vol
    (the stock actually moves) -> higher score.
    """
    rv = (tech or {}).get("realized_vol")
    # Yahoo sometimes exposes an at-the-money-ish IV proxy; not always present.
    iv = F._g(info, "impliedVolatility")

    if rv is None:
        return {"score": None, "realized_vol": None, "iv_vs_rv": None}

    # A stock that doesn't move offers little long-premium opportunity.
    move_factor = _lin(rv, 0.12, 0.55)   # 12% RV -> 0, 55% RV -> 100

    if iv:
        iv = float(iv)
        ratio = iv / rv if rv > 0 else 1.0
        # ratio < 1 => IV below realized => options look cheap => reward
        cheap_factor = _lin(ratio, 1.4, 0.7)  # 1.4x -> 0, 0.7x -> 100
        score = 0.55 * cheap_factor + 0.45 * move_factor
        iv_vs_rv = round(ratio, 3)
    else:
        # No IV: lean on the movement regime alone (mild signal)
        score = 0.6 * move_factor + 20.0  # keep mid-ish so it doesn't dominate
        iv_vs_rv = None

    return {"score": round(max(0.0, min(100.0, score)), 1),
            "realized_vol": round(rv, 4),
            "iv_vs_rv": iv_vs_rv}


# --------------------------------------------------------------------- helper --
def _lin(v, lo, hi):
    """Linear map v in [lo,hi] -> [0,100], clamped. Supports inverted ranges."""
    if v is None:
        return None
    if hi == lo:
        return 50.0
    x = (v - lo) / (hi - lo)
    return max(0.0, min(100.0, x * 100.0))


def _cagr_3y(hist):
    try:
        closes = hist["Close"].dropna()
        if len(closes) < 30:
            return None
        first, last = float(closes.iloc[0]), float(closes.iloc[-1])
        yrs = len(closes) / 252.0
        if first <= 0 or yrs <= 0:
            return None
        return (last / first) ** (1.0 / yrs) - 1.0
    except Exception:
        return None


# ------------------------------------------------------ per-ticker evaluation --
def _fetch_with_retry(fn, *args, retries=2, base_delay=0.8):
    """Yahoo throttles bursty parallel access; a transient failure usually clears
    on a short backoff. Retry a fetch a couple of times before giving up."""
    last = None
    for attempt in range(retries + 1):
        try:
            return fn(*args)
        except Exception as e:  # noqa: BLE001 - transient network/throttle
            last = e
            if attempt < retries:
                time.sleep(base_delay * (attempt + 1))
    raise last


def evaluate_ticker(ticker, provider, idx_hist=None, weights=None):
    """Compute all components + the weighted score for one ticker. Returns a row
    dict, or None on failure."""
    weights = weights or WEIGHTS
    try:
        q = _fetch_with_retry(provider.quote, ticker)
        S = q.get("price")
        if not S:
            return None
        hist = _fetch_with_retry(provider.history, ticker, "1y")
        info_fn = provider.info_light if hasattr(provider, "info_light") else provider.info
        info = _fetch_with_retry(info_fn, ticker)
        tech = T.technical_summary(hist, idx_hist)

        tech_score = SC.momentum_score(tech)
        lt = F.long_term_score(info, tech, cagr_3y=_cagr_3y(hist))
        fund_score = lt.get("score")
        dist = distortion_score(info, tech)
        ivo = iv_opportunity_score(info, tech)

        # Weighted composite over AVAILABLE components (renormalize weights).
        comps = {
            "technical": tech_score,
            "fundamental": fund_score,
            "distortion": dist.get("score"),
            "iv_opportunity": ivo.get("score"),
        }
        avail = {k: v for k, v in comps.items() if v is not None}
        if not avail:
            return None
        wsum = sum(weights[k] for k in avail)
        composite = sum(comps[k] * weights[k] for k in avail) / wsum

        return {
            "ticker": ticker,
            "name": info.get("longName") or info.get("shortName") or ticker,
            "membership": membership(ticker),
            "sector": info.get("sector"),
            "price": round(float(S), 2),
            "change_pct": q.get("change_pct"),
            "score": round(composite, 1),
            "components": {k: (round(v, 1) if v is not None else None) for k, v in comps.items()},
            "fundamental_axes": lt.get("axes"),
            "fundamental_verdict": lt.get("label"),
            "fundamental_note": lt.get("note"),
            "distortion": dist,
            "iv_opportunity": ivo,
            "rsi": tech.get("rsi"),
            "macd_bullish": tech.get("macd_bullish"),
            "above_ma200": tech.get("above_ma200"),
            "reason_he": _reason_he(comps, dist, ivo, tech, lt),
        }
    except Exception:
        return None
    finally:
        # Free the heavy per-ticker artifacts (1y history DataFrame + info dict)
        # immediately so a 515-name scan keeps memory flat instead of holding
        # 500+ DataFrames at once (which OOM-killed the Render free tier).
        try:
            from engine.provider import _cache_purge_ticker
            _cache_purge_ticker(ticker)
        except Exception:
            pass


def _reason_he(comps, dist, ivo, tech, lt):
    """One-line Hebrew rationale: the strongest 2-3 drivers behind the score."""
    bits = []
    t = comps.get("technical")
    f = comps.get("fundamental")
    d = comps.get("distortion")
    iv = comps.get("iv_opportunity")
    if t is not None and t >= 65:
        bits.append("מומנטום טכני חזק")
    elif t is not None and t <= 35:
        bits.append("חולשה טכנית")
    if f is not None and f >= 65:
        bits.append("פונדמנטלי איכותי")
    elif f is not None and f <= 35:
        bits.append("פונדמנטלי חלש")
    up = dist.get("blended_upside")
    if up is not None and up >= 0.15:
        bits.append(f"נסחרת ~{round(up*100)}%- מתחת לערך ההוגן")
    elif up is not None and up <= -0.10:
        bits.append(f"נסחרת מעל הערך ההוגן ({round(up*100)}%)")
    if iv is not None and iv >= 65:
        bits.append("תנודתיות גלומה זולה — הזדמנות אופציות long")
    if not bits:
        bits.append("פרופיל מאוזן")
    return " · ".join(bits[:3])


# ---------------------------------------------------------- universe scanner --
def scan_universe(provider, universe_name="both", weights=None, max_workers=2,
                  progress=None):
    """Scan the whole universe in parallel. `progress` is an optional callable
    invoked as progress(done, total). Returns (rows_sorted, scanned, total)."""
    tickers = universe(universe_name)
    total = len(tickers)
    try:
        idx_hist = provider.history(INDEX, "1y")
    except Exception:
        idx_hist = None

    import gc
    rows = []
    done = 0
    # Gentler concurrency: Yahoo throttles bursts AND each parallel worker holds a
    # full 1y history DataFrame + curl_cffi session in memory at once. 3 workers
    # keeps the transient memory footprint well under Render's 512MB free-tier
    # limit (6 workers peaked ~600MB and got the service OOM-killed).
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futs = {ex.submit(evaluate_ticker, t, provider, idx_hist, weights): t
                for t in tickers}
        for fut in as_completed(futs):
            done += 1
            try:
                r = fut.result()
                if r:
                    rows.append(r)
            except Exception:
                pass
            # Periodically reclaim the transient pandas/numpy buffers so peak RSS
            # stays flat across the long scan instead of climbing monotonically.
            if done % 50 == 0:
                gc.collect()
            if progress:
                try:
                    progress(done, total)
                except Exception:
                    pass

    del futs
    gc.collect()
    rows.sort(key=lambda r: r["score"], reverse=True)
    return rows, len(rows), total


# ---------------------------------------------------- cached async scan state --
class IdeasScanner:
    """Holds a cached scan + runs refreshes in a background thread so the API can
    return status + partial/last-good results immediately."""

    def __init__(self, provider, ttl_seconds=1800):
        self.provider = provider
        self.ttl = ttl_seconds
        self._lock = threading.Lock()
        self._state = {}  # keyed by universe_name

    def _fresh(self, st):
        if not st:
            return False
        fa = st.get("fetched_at")
        if fa is None:
            return False
        return (time.time() - fa) < self.ttl

    def get(self, universe_name="both", refresh=False, weights=None):
        with self._lock:
            st = self._state.get(universe_name)
            running = bool(st and st.get("status") == "building")
            need = refresh or not self._fresh(st)
            if need and not running:
                # start a fresh background scan; keep any prior results visible
                st = st or {}
                st.update({
                    "status": "building",
                    "started_at": time.time(),
                    "done": 0, "total": len(universe(universe_name)),
                })
                self._state[universe_name] = st
                th = threading.Thread(
                    target=self._run, args=(universe_name, weights), daemon=True)
                th.start()
            st = self._state.get(universe_name) or {"status": "building",
                                                     "done": 0, "total": 0}
        return self._snapshot(universe_name)

    def _run(self, universe_name, weights):
        def prog(done, total):
            with self._lock:
                s = self._state.get(universe_name)
                if s:
                    s["done"], s["total"] = done, total
        try:
            rows, scanned, total = scan_universe(
                self.provider, universe_name, weights=weights, progress=prog)
            with self._lock:
                self._state[universe_name] = {
                    "status": "ready",
                    "rows": rows,
                    "scanned": scanned,
                    "total": total,
                    "fetched_at": time.time(),
                    "as_of": datetime.now(timezone.utc).isoformat(),
                    "done": total,
                }
        except Exception as e:
            with self._lock:
                s = self._state.get(universe_name) or {}
                s["status"] = "error"
                s["error"] = str(e)
                self._state[universe_name] = s

    def _snapshot(self, universe_name):
        with self._lock:
            st = self._state.get(universe_name) or {}
            return {
                "status": st.get("status", "building"),
                "rows": st.get("rows", []),
                "scanned": st.get("scanned", 0),
                "total": st.get("total", 0),
                "done": st.get("done", 0),
                "as_of": st.get("as_of"),
                "error": st.get("error"),
            }
