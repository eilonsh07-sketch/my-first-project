"""
בדיקות לתמחור אמריקאי — CRR + LSM.
מאמת מול Black-Scholes, מול ערכי benchmark מהספרות (Hull), ותכונות מימוש מוקדם.

הרצה:  cd backend && python -m pytest tests/test_american_pricing.py -v
או:    cd backend && python tests/test_american_pricing.py   (runner ידני, ללא pytest)
"""
import math
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.pricing import bs_price
from engine.american_pricing import (
    binomial_crr, lsm_price, american_price, should_use_american,
)

PASS = 0
FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ✓ {name}")
    else:
        FAIL += 1
        print(f"  ✗ {name}  {detail}")


def test_crr_european_converges_to_bs():
    """CRR אירופאי (american=False) חייב להתכנס ל-Black-Scholes ללא דיבידנד."""
    print("\n[CRR אירופאי -> Black-Scholes]")
    cases = [
        # (S, K, T, r, sigma, kind)
        (100, 100, 1.0, 0.05, 0.20, "call"),
        (100, 110, 0.5, 0.03, 0.30, "call"),
        (100, 90, 1.0, 0.05, 0.25, "put"),
        (50, 50, 2.0, 0.04, 0.40, "put"),
    ]
    for S, K, T, r, sigma, kind in cases:
        bs = bs_price(S, K, T, r, sigma, kind)
        crr = binomial_crr(S, K, T, r, sigma, kind, steps=500, american=False)
        check(f"CRR≈BS {kind} S={S} K={K}", abs(bs - crr) < 0.05,
              f"BS={bs:.4f} CRR={crr:.4f} diff={abs(bs-crr):.4f}")


def test_american_call_no_div_equals_european():
    """CALL אמריקאי ללא דיבידנד = אירופאי (מימוש מוקדם אף פעם לא אופטימלי)."""
    print("\n[CALL אמריקאי ללא דיבידנד = אירופאי]")
    S, K, T, r, sigma = 100, 100, 1.0, 0.05, 0.25
    euro = bs_price(S, K, T, r, sigma, "call")
    amer = binomial_crr(S, K, T, r, sigma, "call", steps=500, american=True)
    check("CALL amer≈euro (no div)", abs(amer - euro) < 0.05,
          f"euro={euro:.4f} amer={amer:.4f}")
    # LSM צריך להגיע לאותה מסקנה (בקירוב מונטה-קרלו)
    lsm = lsm_price(S, K, T, r, sigma, "call", n=20000, steps=50, seed=7)
    check("CALL LSM≈euro (no div)", abs(lsm - euro) < 0.6,
          f"euro={euro:.4f} lsm={lsm:.4f}")


def test_american_put_premium_positive():
    """PUT אמריקאי > PUT אירופאי (פרמיית מימוש מוקדם חיובית)."""
    print("\n[PUT אמריקאי > אירופאי — פרמיית מימוש מוקדם]")
    S, K, T, r, sigma = 100, 110, 1.0, 0.08, 0.30  # ITM put, ריבית גבוהה
    euro = bs_price(S, K, T, r, sigma, "put")
    amer = binomial_crr(S, K, T, r, sigma, "put", steps=500, american=True)
    check("PUT amer > euro", amer > euro + 0.05,
          f"euro={euro:.4f} amer={amer:.4f}")
    lsm = lsm_price(S, K, T, r, sigma, "put", n=30000, steps=50, seed=11)
    check("PUT LSM > euro", lsm > euro,
          f"euro={euro:.4f} lsm={lsm:.4f}")
    # CRR ו-LSM צריכים להתכנס זה לזה (~2% סובלנות)
    check("PUT CRR≈LSM", abs(crr_lsm_rel(amer, lsm)) < 0.04,
          f"crr={amer:.4f} lsm={lsm:.4f} rel={crr_lsm_rel(amer,lsm):.4f}")


def crr_lsm_rel(a, b):
    return (a - b) / b if b else 0.0


def test_benchmark_two_methods_agree():
    """בדיקת benchmark: American PUT, S=K=50, r=0.10, sigma=0.40, T=0.4167.
    הערך הנכון (מאומת על ידי שתי שיטות בלתי-תלויות) ≈ 4.28.
    המבחן האמיתי: CRR ו-LSM מתכנסים לאותו ערך — זהו אימות צולב."""
    print("\n[benchmark — American PUT, שתי שיטות מתכנסות ≈ 4.28]")
    amer = binomial_crr(50, 50, 0.4167, 0.10, 0.40, "put", steps=1000, american=True)
    check("CRR put ≈4.28", abs(amer - 4.284) < 0.05, f"got {amer:.4f}")
    lsm = lsm_price(50, 50, 0.4167, 0.10, 0.40, "put", n=50000, steps=60, seed=3)
    check("LSM put ≈4.28", abs(lsm - 4.284) < 0.20, f"got {lsm:.4f}")


def test_dividend_call_early_exercise():
    """CALL על מניה עם דיבידנד רציף גבוה: אמריקאי > אירופאי."""
    print("\n[CALL עם דיבידנד — פרמיית מימוש מוקדם]")
    S, K, T, r, sigma, q = 100, 95, 1.0, 0.05, 0.25, 0.08  # דיבידנד 8%
    euro = bs_price(S, K, T, r, sigma, "call", q=q)
    amer = binomial_crr(S, K, T, r, sigma, "call", q=q, steps=500, american=True)
    check("CALL+div amer > euro", amer > euro + 0.02,
          f"euro={euro:.4f} amer={amer:.4f}")


def test_discrete_dividends():
    """דיבידנדים בדידים: מחיר חיובי וסביר, אמריקאי >= אירופאי."""
    print("\n[דיבידנדים בדידים]")
    S, K, T, r, sigma = 100, 100, 1.0, 0.05, 0.25
    divs = [(0.25, 1.5), (0.75, 1.5)]  # שני דיבידנדים של 1.5 לאורך השנה
    res = american_price(S, K, T, r, sigma, "call", dividends=divs, method="crr", steps=400)
    check("discrete div CALL amer>=euro", res["american"] >= res["european"] - 1e-6,
          f"amer={res['american']:.4f} euro={res['european']:.4f}")
    check("discrete div premium>=0", res["early_exercise_premium"] >= -1e-6,
          f"prem={res['early_exercise_premium']:.4f}")


def test_american_price_interface():
    """ממשק american_price מחזיר את כל השדות הנדרשים."""
    print("\n[ממשק american_price]")
    res = american_price(100, 105, 1.0, 0.06, 0.30, "put", method="crr", steps=300)
    for key in ("american", "european", "early_exercise_premium",
                "early_exercise_premium_pct", "method", "steps"):
        check(f"has '{key}'", key in res)
    check("premium = amer - euro",
          abs(res["early_exercise_premium"] - (res["american"] - res["european"])) < 1e-6)


def test_should_use_american():
    """שכבת ההחלטה 'רק כשמשתלם'."""
    print("\n[should_use_american — מתי להפעיל]")
    # PUT עמוק בתוך הכסף -> כן
    use, _ = should_use_american(80, 100, "put")
    check("deep ITM put -> True", use)
    # CALL OTM ללא דיבידנד -> לא
    use, _ = should_use_american(100, 130, "call", q=0.0)
    check("OTM call no div -> False", not use)
    # ATM -> כן
    use, _ = should_use_american(100, 101, "call", q=0.0)
    check("ATM -> True", use)
    # CALL על מניית דיבידנד -> כן
    use, _ = should_use_american(100, 130, "call", q=0.03)
    check("call + dividend -> True", use)


def test_convergence_stability():
    """יציבות: הגדלת steps לא משנה את המחיר דרמטית (כבר התכנס)."""
    print("\n[יציבות התכנסות]")
    S, K, T, r, sigma = 100, 100, 1.0, 0.05, 0.30
    p200 = binomial_crr(S, K, T, r, sigma, "put", steps=200, american=True)
    p800 = binomial_crr(S, K, T, r, sigma, "put", steps=800, american=True)
    check("steps 200 vs 800 stable", abs(p200 - p800) < 0.05,
          f"p200={p200:.4f} p800={p800:.4f}")


def run_all():
    test_crr_european_converges_to_bs()
    test_american_call_no_div_equals_european()
    test_american_put_premium_positive()
    test_benchmark_two_methods_agree()
    test_dividend_call_early_exercise()
    test_discrete_dividends()
    test_american_price_interface()
    test_should_use_american()
    test_convergence_stability()
    print(f"\n{'='*50}\nPASS={PASS}  FAIL={FAIL}\n{'='*50}")
    return FAIL == 0


if __name__ == "__main__":
    ok = run_all()
    sys.exit(0 if ok else 1)
