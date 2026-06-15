"""
scoring.py — Decision engine.
- Hard anti-casino filters (lottery, OTM distance, DTE horizon, liquidity)
- Per-option evaluation: BS pricing, Greeks, IV rank, MC, EV, POP, breakeven, Kelly
- Option Score (math/pricing/MC) and Momentum Score (technicals/patterns/RS)
- Final blended verdict
"""
from __future__ import annotations

import math
from datetime import datetime, date

from .pricing import bs_price, bs_greeks, implied_vol, monte_carlo_option, monte_carlo_option_early, prob_touch_target_price
from .american_pricing import american_price, should_use_american
from .fundamentals import altman_z

RISK_FREE = 0.045

# --- Hard rules (anti-casino) ---
MIN_PREMIUM = 0.10          # no lottery tickets cheaper than $0.10
MAX_OTM_PCT = 0.40          # block options > 40% OTM
MAX_DTE = 183               # no expiries beyond ~6 months
MAX_SIGMA_MOVE = 2.5        # ATR/target filter: reject > 2.5 std-dev required moves
MIN_VALID_IV = 0.05         # Yahoo IV below this is broken (e.g. 0.00001 off-hours,
                            # or fragments like 0.016/0.031 for illiquid strikes).
                            # Real equity IV is virtually never < 5% annualized, so
                            # below this we fall back to a BS-inverted IV from last price.

DTE_BUCKETS = [(7, 30), (31, 60), (61, 120), (121, 183)]
# Extended buckets used when LEAPS (>6 months) are allowed
LEAPS_BUCKETS = [(7, 30), (31, 60), (61, 120), (121, 183), (184, 365), (366, 1000)]


def dte_bucket(dte):
    for lo, hi in LEAPS_BUCKETS:
        if lo <= dte <= hi:
            return f"{lo}-{hi}"
    if dte < 7:
        return "<7"
    return "366+"


def years_to_expiry(expiry_str):
    exp = datetime.strptime(expiry_str, "%Y-%m-%d").date()
    dte = (exp - date.today()).days
    return max(dte, 0) / 365.0, dte


def iv_rank(current_iv, iv_history):
    """IV Rank & percentile vs trailing IV proxy (we use realized-vol band as proxy
    when option-IV history unavailable). iv_history is (low, high, series-percentile)."""
    if not iv_history or current_iv is None:
        return None, None
    lo, hi = iv_history
    if hi <= lo:
        return None, None
    rank = (current_iv - lo) / (hi - lo)
    return max(0.0, min(1.0, rank)), None


def passes_hard_filters(opt, S, dte, otm_pct, premium, max_dte=MAX_DTE):
    """Return (passed: bool, reasons: list[str]).
    max_dte caps the expiry horizon; raise it to allow LEAPS (>6 months)."""
    reasons = []
    if premium is None or premium < MIN_PREMIUM:
        reasons.append(f"פרמיה < ${MIN_PREMIUM} (לוטו)")
    if otm_pct > MAX_OTM_PCT:
        reasons.append(f"OTM > {int(MAX_OTM_PCT*100)}%")
    if dte > max_dte:
        if max_dte <= MAX_DTE:
            reasons.append("פקיעה > 6 חודשים")
        else:
            reasons.append(f"פקיעה > {round(max_dte/30)} חודשים")
    if dte < 1:
        reasons.append("פקיעה היום/עבר")
    return (len(reasons) == 0), reasons


def liquidity_score(opt):
    """0-1 liquidity quality from bid-ask spread %, OI, volume."""
    bid = opt.get("bid") or 0
    ask = opt.get("ask") or 0
    mid = opt.get("mid") or opt.get("last") or 0
    oi = opt.get("open_interest") or 0
    vol = opt.get("volume") or 0
    spread_pct = ((ask - bid) / mid) if (mid and ask and bid) else 1.0
    s_spread = max(0.0, 1.0 - min(spread_pct / 0.25, 1.0))  # 0% spread=1, 25%+=0
    s_oi = min(oi / 500.0, 1.0)
    s_vol = min(vol / 100.0, 1.0)
    score = 0.5 * s_spread + 0.3 * s_oi + 0.2 * s_vol
    return score, {"spread_pct": spread_pct, "oi": oi, "volume": vol}


def evaluate_option(opt, S, expiry, mu=None, realized_vol=None, target_return=1.30,
                    target_price=None, n_mc=10000, iv_band=None, max_dte=MAX_DTE,
                    early_exit=True, div_params=None, american=True):
    """
    Full evaluation of a single option contract.
    mu: real-world annualized drift for the underlying (for MC); defaults risk-neutral.
    realized_vol: stock's realized vol (for IV-vs-RV comparison).
    iv_band: (low_iv, high_iv) for IV-rank computation.
    """
    T, dte = years_to_expiry(expiry)
    K = opt["strike"]
    kind = opt["kind"]
    sigma = opt.get("iv")
    premium = opt.get("mid") or opt.get("last")

    # --- IV source resolution -------------------------------------------------
    # Yahoo often returns a broken IV (~0.00001) when the market is closed or for
    # illiquid strikes, which would zero-out Monte Carlo (POP / targets / EV).
    # When the provider IV is missing or below MIN_VALID_IV, invert Black-Scholes
    # on the last traded price to recover a usable IV. This is exactly what a
    # broker does. The computed IV is flagged so the UI can mark it as derived
    # rather than a live quote. A valid provider IV is NEVER overwritten.
    iv_source = "yahoo"
    last_px = opt.get("last")
    if (sigma is None or sigma < MIN_VALID_IV) and last_px and T > 0:
        calc = implied_vol(last_px, S, K, T, RISK_FREE, kind)
        if calc and calc >= MIN_VALID_IV:
            sigma = calc
            iv_source = "computed"
        else:
            iv_source = "none"
    elif sigma is None or sigma < MIN_VALID_IV:
        iv_source = "none"

    # Distance from money
    if kind == "call":
        otm_pct = max(0.0, (K - S) / S)
    else:
        otm_pct = max(0.0, (S - K) / S)

    passed, fail_reasons = passes_hard_filters(opt, S, dte, otm_pct, premium, max_dte=max_dte)

    # Theoretical price & IV consistency
    theo = None
    edge = None
    american_info = None
    if sigma and premium and T > 0:
        theo = bs_price(S, K, T, RISK_FREE, sigma, kind)
        edge = premium - theo  # positive = market price above model (overpriced)

        # --- תמחור אמריקאי (זכות מימוש מוקדם) — 'רק כשמשתלם' --------------
        # BS האירופאי נשאר הפילטר המהיר (חסם תחתון). המנוע האמריקאי (CRR)
        # רץ רק כאשר פער המימוש המוקדם עשוי להיות מהותי: דיבידנד/ATM/Deep-ITM.
        if american:
            q = (div_params or {}).get("q", 0.0)
            divs = (div_params or {}).get("dividends")
            use_amer, reason_he = should_use_american(S, K, kind, q=q, dividends=divs)
            if use_amer:
                try:
                    ap = american_price(S, K, T, RISK_FREE, sigma, kind, q=q,
                                        dividends=divs, method="crr", steps=200)
                    american_info = {
                        "american_price": ap["american"],
                        "european_price": ap["european"],
                        "early_exercise_premium": ap["early_exercise_premium"],
                        "early_exercise_premium_pct": ap["early_exercise_premium_pct"],
                        "reason_he": reason_he,
                        "dividend_source": (div_params or {}).get("source", "none"),
                        "method": "crr",
                    }
                    # כאשר המימוש המוקדם מהותי, השוואת השוק מול מודל צריכה להיעשות
                    # מול המחיר האמריקאי (הנכון לחוזה האמריקאי), לא מול האירופאי.
                    if ap["american"] > 0:
                        theo = ap["american"]
                        edge = premium - theo
                except Exception:
                    american_info = None

    greeks = bs_greeks(S, K, T, RISK_FREE, sigma or 0.5, kind) if T > 0 else None

    # Breakeven & required move
    if kind == "call":
        breakeven = K + (premium or 0)
    else:
        breakeven = K - (premium or 0)
    req_move_pct = (breakeven - S) / S if kind == "call" else (S - breakeven) / S

    # Required move in std-devs (ATR/sigma filter)
    sigma_move = None
    if sigma and T > 0:
        expected_sd = sigma * math.sqrt(T)
        sigma_move = abs(math.log(breakeven / S)) / expected_sd if expected_sd > 0 else None

    # Liquidity
    liq, liq_detail = liquidity_score(opt)

    # IV rank & RV comparison
    ivr, _ = iv_rank(sigma, iv_band)
    iv_vs_rv = (sigma / realized_vol) if (sigma and realized_vol) else None

    # Monte Carlo (only if it passed structural sanity)
    mc = None
    if sigma and premium and T > 0 and premium >= MIN_PREMIUM:
        mc = monte_carlo_option(S, K, T, RISK_FREE, sigma, premium, kind,
                                target_return=target_return, n=n_mc, mu=mu)
        # Early-exit variant: probability the option's MARKET VALUE (incl. time
        # value) reaches the target at any point before expiry — matches the
        # "trade and sell before expiry" assumption. Uses fewer steps for speed.
        # Skipped during bulk scan (early_exit=False) and computed only for the
        # top results to avoid running a path sim on hundreds of options.
        if early_exit:
            early = monte_carlo_option_early(S, K, T, RISK_FREE, sigma, premium, kind,
                                             target_return=target_return,
                                             n=min(n_mc, 4000), steps=40, mu=mu)
            mc["prob_hit_target_early"] = early["prob_hit_target_early"]
            mc["expected_max_value"] = early["expected_max_value"]

    # Target-price probability
    tp = None
    if target_price and sigma and T > 0:
        tp = prob_touch_target_price(S, target_price, T, RISK_FREE, sigma, mu=mu)

    option_score = _option_score(mc, edge, theo, premium, liq, sigma_move, ivr, iv_vs_rv) if passed else 0.0

    # Kelly fraction for position sizing
    kelly = _kelly(mc) if mc else None

    # Hold-to-expiry vs trade-out recommendation
    hold = _hold_to_expiry(S, K, kind, dte, premium, theo, greeks, sigma, mc)

    return {
        "contract": opt.get("contract"),
        "kind": kind,
        "strike": K,
        "expiry": expiry,
        "dte": dte,
        "dte_bucket": dte_bucket(dte),
        "premium": premium,
        "theo_price": theo,           # מחיר תיאורטי: אמריקאי אם הופעל, אחרת אירופאי (BS)
        "edge": edge,                 # premium - theo
        "american": american_info,    # None אם המימוש המוקדם זניח (BS מספיק)
        "mispricing_pct": (edge / theo) if (edge is not None and theo) else None,
        "iv": sigma,
        "iv_source": iv_source,       # "yahoo" | "computed" | "none"
        "iv_rank": ivr,
        "iv_vs_rv": iv_vs_rv,
        "otm_pct": otm_pct,
        "breakeven": breakeven,
        "required_move_pct": req_move_pct,
        "sigma_move": sigma_move,
        "greeks": greeks,
        "liquidity": liq,
        "liquidity_detail": liq_detail,
        "monte_carlo": mc,
        "target_prob": tp,
        "kelly": kelly,
        "passed_filters": passed,
        "fail_reasons": fail_reasons,
        "option_score": option_score,
        "hold_to_expiry": hold,
    }


def _option_score(mc, edge, theo, premium, liq, sigma_move, ivr, iv_vs_rv):
    """0-100 Option Score for an option BUYER. Rebalanced weights:

      EV (normalized by premium) ...... 35   — the true expectancy edge (LEADS)
      Probability of profit ........... 20   — POP alone is misleading, so capped
      IV Rank (cheap vol = good) ...... 15   — For a long-premium buyer, a LOW
                                              IV-rank means options are historically
                                              cheap → a strong buyer's edge.
      IV vs RV (option not too rich) .. 10   — cheap relative to realized movement
      Liquidity ....................... 12   — executable spread / OI / volume
      Reachability (sigma_move) ....... 8    — how many std-devs to break even

    Rationale: for an option BUYER the #1 structural predictor is EXPECTANCY
    (EV), supported by volatility cheapness (IV Rank + IV-vs-RV). POP alone is
    misleading — a high-POP option is usually deep ITM and EXPENSIVE (high
    probability, poor payoff) — so POP is capped at 20.

    Calibration note (from a 160-option live sensitivity study): an earlier
    20-pt IV-Rank weight made IV-Rank the single highest-correlated driver of
    the total score (r=+0.67 > EV r=+0.56), partially DOUBLE-COUNTING the
    separate IV-vs-RV cheapness term. IV-Rank was reduced 20→15 and the freed
    5 pts returned to EV (30→35) so expectancy LEADS while volatility
    cheapness (IV Rank 15 + IV/RV 10 = 25) remains a strong but non-dominant
    edge.
    """
    if not mc:
        return 0.0
    score = 0.0

    # Expected value normalized by premium (35) — the expectancy edge, LEADS
    ev_norm = mc["expected_pnl"] / max(premium, 0.01)
    score += 35 * max(0.0, min(1.0, (ev_norm + 0.5) / 1.5))

    # Probability of profit (20) — capped: POP alone overstates deep-ITM options
    score += 20 * mc["prob_profit"]

    # IV Rank (15): for a BUYER, LOW rank = cheap vol = good. Reward = 1 - rank.
    # When IV-rank can't be computed (no band) fall back to the IV-vs-RV signal,
    # and if neither is available give a neutral half-credit so the option is not
    # unfairly punished for a data gap.
    if ivr is not None:
        score += 15 * (1.0 - ivr)
    elif iv_vs_rv is not None:
        # cheap if IV ≲ RV; map iv_vs_rv 0.7→1.0 (full) .. 1.5→0.0 (rich)
        score += 15 * max(0.0, min(1.0, (1.5 - iv_vs_rv) / 0.8))
    else:
        score += 7.5

    # IV vs RV — option not too rich relative to realized movement (10)
    if iv_vs_rv is not None:
        score += 10 * max(0.0, 1.0 - max(0.0, (iv_vs_rv - 1.0)))
    else:
        score += 5.0

    # Liquidity (12)
    score += 12 * liq

    # Reachability: lower sigma_move is better (8)
    if sigma_move is not None:
        score += 8 * max(0.0, 1.0 - min(sigma_move / MAX_SIGMA_MOVE, 1.0))
    else:
        score += 4.0

    return round(max(0.0, min(100.0, score)), 1)


def _kelly(mc):
    """Kelly fraction from MC win prob and payoff odds. Conservative (half-Kelly)."""
    p = mc["prob_profit"]
    if p <= 0 or p >= 1:
        return 0.0
    # b = avg win / avg loss magnitude — approximate from EV decomposition
    # Use prob_total_loss as worst case; payoff ratio from expected pnl
    if mc["expected_pnl_pct"] <= -0.99:
        return 0.0
    # Approximate odds b from EV: EV = p*b - (1-p); solve b = (EV + (1-p))/p
    ev = mc["expected_pnl_pct"]
    b = (ev + (1 - p)) / p
    if b <= 0:
        return 0.0
    f = (b * p - (1 - p)) / b
    return round(max(0.0, min(0.25, f * 0.5)), 4)  # half-Kelly, capped 25%


def _hold_to_expiry(S, K, kind, dte, premium, theo, greeks, sigma, mc):
    """
    Default trading assumption: the option will be TRADED and SOLD BEFORE expiry.
    This function flags the rarer case where holding to expiry is the better plan.

    A buyer benefits from holding to expiry when:
      - The option is deep ITM (mostly intrinsic value, little time premium to lose),
      - Theta decay as a fraction of premium is low,
      - There is meaningful runway (not about to expire worthless),
    Otherwise the recommendation is to SELL BEFORE EXPIRY to capture remaining
    time value and avoid accelerating theta decay / pin risk near expiration.
    Returns dict {recommend: 'hold'|'sell', confidence, reasons[], he_label, he_note}.
    """
    reasons = []
    if premium is None or premium <= 0 or S <= 0:
        return {"recommend": "sell", "confidence": 0.5, "reasons": ["חסר נתוני תמחור"],
                "he_label": "למכור לפני פקיעה", "he_note": "ברירת מחדל — לסגור את העסקה לפני הפקיעה."}

    # Intrinsic value
    intrinsic = max(0.0, (S - K)) if kind == "call" else max(0.0, (K - S))
    time_value = max(0.0, premium - intrinsic)
    tv_frac = time_value / premium if premium else 1.0          # 0 = all intrinsic
    intrinsic_frac = intrinsic / premium if premium else 0.0

    # Moneyness
    itm_pct = (S - K) / S if kind == "call" else (K - S) / S    # >0 means ITM
    deep_itm = itm_pct > 0.10

    # Theta burden as fraction of premium (daily)
    theta = abs(greeks.get("theta")) if (greeks and greeks.get("theta") is not None) else None
    theta_frac = (theta / premium) if (theta and premium) else None

    hold_score = 0
    if deep_itm:
        hold_score += 2
        reasons.append("אופציה עמוק בתוך הכסף (ITM) — רוב הערך פנימי")
    if intrinsic_frac >= 0.7:
        hold_score += 1
        reasons.append("ערך פנימי גבוה — פרמיית זמן נמוכה לאיבוד")
    if tv_frac <= 0.20:
        hold_score += 1
        reasons.append("פרמיית זמן נמוכה (≤20%) — מעט להפסיד בהמתנה")
    if theta_frac is not None and theta_frac < 0.005:
        hold_score += 1
        reasons.append("שחיקת תיטא יומית זניחה יחסית לפרמיה")
    if dte and dte < 14:
        # near expiry: prefer to close to avoid pin/gamma risk unless fully intrinsic
        if not deep_itm:
            hold_score -= 2
            reasons.append("קרוב לפקיעה ולא עמוק ITM — סיכון שחיקה ופין")

    if hold_score >= 3:
        return {"recommend": "hold", "confidence": min(0.9, 0.55 + 0.1 * hold_score),
                "reasons": reasons,
                "he_label": "שווה להמתין לפקיעה",
                "he_note": "האופציה עמוקה בתוך הכסף עם מעט ערך זמן לאיבוד — החזקה עד פקיעה סבירה."}
    return {"recommend": "sell", "confidence": min(0.9, 0.55 + 0.08 * (3 - hold_score)),
            "reasons": reasons or ["ערך זמן משמעותי — עדיף לסגור לפני שחיקת התיטא"],
            "he_label": "למכור לפני פקיעה",
            "he_note": "הנחת המסחר: לממש את הרווח ולצאת לפני שהתיטא מאיצה את שחיקת ערך הזמן."}


def momentum_score(tech):
    """0-100 Momentum Score from technical summary."""
    if not tech:
        return 0.0
    score = 0.0
    # Trend: above moving averages (30)
    ma_pts = sum([tech.get("above_ma20", False), tech.get("above_ma50", False),
                  tech.get("above_ma150", False), tech.get("above_ma200", False)])
    score += 30 * (ma_pts / 4.0)
    # MACD (15)
    if tech.get("macd_bullish"):
        score += 15
    # RSI sweet spot 45-70 (15)
    rsi = tech.get("rsi")
    if rsi is not None:
        if 45 <= rsi <= 70:
            score += 15
        elif 40 <= rsi < 45 or 70 < rsi <= 78:
            score += 8
        elif rsi > 78:
            score += 2  # overbought
    # Relative strength vs index (15)
    rs = tech.get("relative_strength")
    if rs and rs.get("outperformance") is not None:
        score += 15 * max(0.0, min(1.0, (rs["outperformance"] + 0.1) / 0.4))
    # Volume / smart money OBV (10)
    if tech.get("obv_trend") == "עולה":
        score += 7
    if tech.get("above_vwap"):
        score += 3
    # Patterns (10)
    for p in tech.get("patterns", []):
        if p.get("name_en") in ("Bull Flag", "Cup & Handle", "Rising Channel"):
            score += 5
        elif p.get("name_en") == "Falling Channel":
            score -= 5
    # Overextended penalty (-5)
    if tech.get("overextended"):
        score -= 5

    # --- advanced indicators (rebalanced into existing 100-pt frame) ---
    # ADX trend-strength gate: strong confirmed up-trend rewarded, strong down-trend penalized
    adx_v = tech.get("adx")
    if adx_v is not None:
        pdi, mdi = tech.get("plus_di") or 0, tech.get("minus_di") or 0
        if adx_v >= 25:
            score += 6 if pdi > mdi else -6
        elif adx_v >= 20:
            score += 3 if pdi > mdi else -3
    # Ichimoku cloud position
    ich = tech.get("ichimoku")
    if ich and ich.get("position") == "above":
        score += 5
    elif ich and ich.get("position") == "below":
        score -= 5
    # Stochastic momentum
    sk = tech.get("stoch_k")
    if sk is not None:
        sd = tech.get("stoch_d") or sk
        if sk < 20:
            score += 3            # oversold bounce potential
        elif sk > 80:
            score -= 3            # overbought
        elif sk > sd:
            score += 2            # bullish %K/%D cross
    return round(max(0.0, min(100.0, score)), 1)


def fundamental_option_risk(info, dte=None):
    """
    Focused fundamental layer for OPTIONS (not buy-and-hold).

    Rationale (professional): for the short-to-mid-dated options the user trades,
    classic valuation (P/E, growth) is largely IMMATERIAL to the option's price —
    what moves the option is volatility, momentum and flow. So we DELIBERATELY do
    NOT push full valuation into the score. Instead we capture only the two
    fundamental facts that ARE material to pricing an option:

      1. EARNINGS BEFORE EXPIRY  -> a scheduled report inside the option's life
         means an IV crush + gap risk. This is the single most material
         fundamental input to an option. We flag it (caller can also fetch the
         date) and apply a small risk haircut because the long-premium buyer is
         exposed to post-earnings IV collapse.
      2. FINANCIAL DISTRESS  -> a company with a fragile balance sheet / burning
         cash (low Altman-Z) carries tail/gap risk. We apply a mild penalty.
         A healthy balance sheet gets NO inflated bonus (we don't reward strong
         fundamentals for a short option — that would distort the score).

    Returns a dict with a `multiplier` in roughly [0.85, 1.0] to scale the
    option score, plus the reasons and the distress zone for display.
    """
    reasons = []
    mult = 1.0

    # --- Financial distress (Altman-Z) as a downside-only filter ---
    z = altman_z(info)
    zone = z.get("zone")
    zscore = z.get("z_score")
    if zone == "מצוקה":
        mult *= 0.90
        reasons.append("מצב פיננסי שברירי (Altman-Z במצוקה) — סיכון זנב/גאפ")
    elif zone == "אפור":
        mult *= 0.96
        reasons.append("מצב פיננסי בינוני (Altman-Z אפור)")

    # --- Cash burn: negative FCF on a small/heavily-levered name adds tail risk ---
    fcf = info.get("freeCashflow")
    d2e = info.get("debtToEquity")
    if fcf is not None and fcf < 0 and (d2e or 0) > 150:
        mult *= 0.95
        reasons.append("שריפת מזומנים עם מינוף גבוה — סיכון נוסף")

    return {
        "multiplier": round(mult, 4),
        "reasons": reasons,
        "distress_zone": zone,
        "altman_z": round(zscore, 2) if zscore is not None else None,
    }


def earnings_before_expiry(earnings_ts, dte):
    """Return (flag, days_to_earnings, note) — is there a scheduled earnings report
    within the option's remaining life? This is the most material fundamental
    input to an option (IV crush + gap risk for the long-premium buyer)."""
    if not earnings_ts or not dte:
        return False, None, None
    try:
        # accept unix ts (seconds) or YYYY-MM-DD
        if isinstance(earnings_ts, (int, float)):
            ed = datetime.utcfromtimestamp(float(earnings_ts)).date()
        else:
            ed = datetime.strptime(str(earnings_ts)[:10], "%Y-%m-%d").date()
    except Exception:
        return False, None, None
    d2e = (ed - date.today()).days
    if 0 <= d2e <= dte:
        return True, d2e, f"דוח רווחים בעוד {d2e} ימים (לפני הפקיעה) — צפו לקריסת IV וסיכון גאפ"
    return False, d2e, None


def scan_score(option_score, momentum_score, fund_multiplier=1.0,
               earnings_flag=False, weights=(0.6, 0.4)):
    """
    Composite ranking score for the SCANNER. Blends the option's own quality with
    the stock's technical momentum (same 60/40 frame as final_verdict), then
    applies the focused fundamental option-risk multiplier and a small earnings
    haircut. This is what the scanner sorts by, so a strong option on a stock
    with strong momentum AND sound fundamentals ranks highest.
    """
    w_opt, w_mom = weights
    base = w_opt * option_score + w_mom * (momentum_score or 0.0)
    score = base * (fund_multiplier or 1.0)
    if earnings_flag:
        score *= 0.93  # IV-crush / gap risk haircut when earnings fall before expiry
    return round(max(0.0, min(100.0, score)), 1)


def backtest_multiplier(backtest_score):
    """Map a 0-100 historical-backtest score to a VALIDATION MULTIPLIER in
    [0.85, 1.10], centered so that a neutral backtest (50) leaves the score
    unchanged (×1.00).

      backtest 100 → ×1.10   (strong historical confirmation)
      backtest  50 → ×1.00   (neutral)
      backtest   0 → ×0.85   (history says this strategy failed)

    WHY A MULTIPLIER, NOT A THIRD ADDITIVE WEIGHT:
    The backtest result is itself driven largely by the stock's historical
    momentum/trend — the same momentum already scored in momentum_score. Adding
    the backtest as a third additive pillar (the old 50/30/20) DOUBLE-COUNTS
    momentum and systematically inflates already-run, high-momentum stocks.
    Treating it as a bounded ± validation multiplier lets history CONFIRM or
    TEMPER the forward-looking option+momentum thesis without re-paying for the
    same signal.
    """
    if backtest_score is None:
        return 1.0
    bs = max(0.0, min(100.0, backtest_score))
    if bs >= 50:
        mult = 1.0 + 0.10 * ((bs - 50.0) / 50.0)   # 50→100 maps to 1.00→1.10
    else:
        mult = 1.0 - 0.15 * ((50.0 - bs) / 50.0)    # 50→0   maps to 1.00→0.85
    return round(mult, 4)


def final_verdict(option_score, momentum_score, weights=(0.6, 0.4),
                  backtest_score=None):
    """Blend the scores into a composite + verdict label.

    Forward-looking base = 60% option quality + 40% stock momentum. When a
    historical backtest score IS available, it acts as a VALIDATION MULTIPLIER
    on that base (range 0.85–1.10) rather than a third additive weight — see
    backtest_multiplier() for why. History confirms or tempers the thesis; it
    does not double-count momentum.
    """
    w_opt, w_mom = weights
    base = w_opt * option_score + w_mom * (momentum_score or 0.0)
    bt_mult = backtest_multiplier(backtest_score)
    composite = max(0.0, min(100.0, base * bt_mult))
    used_weights = {"option": w_opt, "momentum": w_mom,
                    "backtest_multiplier": bt_mult}
    if composite >= 72:
        label, tone = "כניסה חזקה", "strong"
    elif composite >= 58:
        label, tone = "מעניין — שקול כניסה", "good"
    elif composite >= 42:
        label, tone = "ניטרלי — המתן לאישור", "neutral"
    else:
        label, tone = "הימנע", "avoid"
    return {"composite": round(composite, 1), "label": label, "tone": tone,
            "base_score": round(base, 1),
            "option_score": option_score, "momentum_score": momentum_score,
            "backtest_score": backtest_score,
            "backtest_multiplier": bt_mult, "weights": used_weights}
