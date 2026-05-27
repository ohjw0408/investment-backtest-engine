"""
Gate 2c 검증 스크립트
조건:
  G5: tax ON 세후 < tax OFF (동일 조건에서 세금 있으면 더 많은 초기금 필요)
  G6: 역산 수렴 (solved_seed가 유한한 양수, 에러 없음)

사용법: python tests/gate_2c_verify.py
서버에서 실행 (실제 price_daily.db 필요)
"""

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parents[1]))

from dividend_logic import run_dividend_scenario_logic

PASS = "✅ PASS"
FAIL = "❌ FAIL"


def _solved_seed(body: dict) -> float:
    result = run_dividend_scenario_logic(body)
    if "error" in result:
        raise RuntimeError(f"Error: {result['error']}")
    r = result.get("result", {})
    v = r.get("solved_seed")
    if v is None:
        raise RuntimeError(f"solved_seed missing. result={result}")
    return float(v)


def _make_body(ticker: str, account_type: str, monthly: int = 500_000,
               years: int = 20, target: int = 3_000_000,
               earned_income: int = 50_000_000) -> dict:
    return {
        "tickers": [{"code": ticker, "weight": 1.0}],
        "account_type": account_type,
        "target_monthly_div": target,
        "dividend_mode": "reinvest",
        "rebal_mode": "none",
        "band_width": 0.05,
        "probability": 0.90,
        "seed":    {"center": 0,       "step": 0, "n": 0, "mode": "optimize"},
        "monthly": {"center": monthly, "step": 0, "n": 0, "mode": "fixed"},
        "years":   {"center": years,   "step": 0, "n": 0, "mode": "fixed"},
        "user_settings": {
            "earned_income": earned_income,
            "isa_type": "general",
            "age": 40,
        },
    }


def check_case(label: str, ticker: str, monthly: int = 500_000, years: int = 20,
               target: int = 3_000_000, earned_income: int = 50_000_000):
    print(f"\n--- {label} ---")
    print(f"  ticker={ticker}  monthly={monthly:,}  years={years}  target={target:,}")

    body_off = _make_body(ticker, "none",    monthly, years, target, earned_income)
    body_on  = _make_body(ticker, "general", monthly, years, target, earned_income)

    try:
        seed_off = _solved_seed(body_off)
        seed_on  = _solved_seed(body_on)
    except Exception as e:
        print(f"  {FAIL}  예외 발생: {e}")
        return False

    print(f"  tax OFF seed: {seed_off:,.0f}원")
    print(f"  tax ON  seed: {seed_on:,.0f}원")

    # G6: 수렴 확인 (finite positive)
    import math
    g6_off = math.isfinite(seed_off) and seed_off > 0
    g6_on  = math.isfinite(seed_on)  and seed_on  > 0
    g6_ok  = g6_off and g6_on
    print(f"  G6 역산수렴: {PASS if g6_ok else FAIL}  (off={seed_off:.0f}, on={seed_on:.0f})")

    # G5: tax ON > tax OFF (세금 있으면 더 많이 필요)
    g5_ok = seed_on > seed_off
    diff_pct = (seed_on - seed_off) / seed_off * 100 if seed_off > 0 else float("inf")
    print(f"  G5 세금영향: {PASS if g5_ok else FAIL}  (차이 {diff_pct:+.1f}%)")

    return g5_ok and g6_ok


def main():
    print("=" * 55)
    print("Gate 2c 검증")
    print("=" * 55)

    cases = [
        # (label, ticker, monthly, years, target)
        ("G5/G6-1  SCHD 위탁",       "SCHD",   500_000, 20, 3_000_000),
        ("G5/G6-2  458730(TIGER) 위탁", "458730", 500_000, 20, 3_000_000),
        ("G5/G6-3  SCHD 종합과세 경계", "SCHD",   500_000, 20, 5_000_000),  # 더 높은 목표 → 더 높은 배당소득
    ]

    results = []
    for (label, ticker, monthly, years, target) in cases:
        ok = check_case(label, ticker, monthly, years, target)
        results.append((label, ok))

    print("\n" + "=" * 55)
    print("요약")
    print("=" * 55)
    all_pass = True
    for label, ok in results:
        status = PASS if ok else FAIL
        print(f"  {status}  {label}")
        if not ok:
            all_pass = False

    print()
    if all_pass:
        print("Gate 2c: ✅ PASSED")
    else:
        print("Gate 2c: ❌ FAILED — 위 실패 항목 확인 필요")
    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
