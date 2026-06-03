"""G5-C C3.2b: 가구 인출 롤링 분석 검증 (생존율 + 분포).

analyze_household_withdrawal — 실가격 롤링 윈도우 → survival_rate, 합산/계좌별 분포.
평탄가격이면 전 윈도우 동일 → 생존율 1.0/0.0 결정론.
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pandas as pd

from modules.retirement.multi_account_withdrawal import analyze_household_withdrawal

CODE = "069500"


def _flat_data(price=100.0, start="2030-01-01", end="2040-12-31"):
    dates = pd.bdate_range(start, end)
    df = pd.DataFrame(
        {"open": price, "high": price, "low": price, "close": price,
         "volume": 1.0, "dividend": 0.0, "split": 1.0},
        index=dates,
    )
    return {CODE: df}, list(dates)


def _acct(account_id, atype, value):
    return {"account_id": account_id, "type": atype, "value": float(value),
            "target_weights": {CODE: 1.0}}


def test_survival_rate_one_when_all_windows_survive():
    data, dates = _flat_data()
    accts = [_acct(0, "위탁", 12_000_000)]
    res = analyze_household_withdrawal(
        accts, data, dates, "2030-01-01", "2040-12-31",
        withdrawal_years=2, monthly_net=100_000.0, step_months=12,
    )
    assert res["survival_rate"] == 1.0
    assert res["n_windows"] >= 5
    # 2년 윈도우 = 24~25개월 인출(경계 영업일 의존) × 100k → 9.5M~9.6M
    assert 9_500_000.0 - 1.0 <= res["combined_end_value"]["p50"] <= 9_600_000.0 + 1.0


def test_survival_rate_zero_when_all_deplete():
    data, dates = _flat_data()
    accts = [_acct(0, "위탁", 2_000_000)]
    res = analyze_household_withdrawal(
        accts, data, dates, "2030-01-01", "2040-12-31",
        withdrawal_years=2, monthly_net=200_000.0, step_months=12,
    )
    assert res["survival_rate"] == 0.0
    assert abs(res["combined_end_value"]["p50"]) <= 1.0


def test_per_account_distribution_surfaced():
    data, dates = _flat_data()
    accts = [_acct(0, "위탁", 5_000_000), _acct(1, "ISA", 5_000_000)]
    res = analyze_household_withdrawal(
        accts, data, dates, "2030-01-01", "2040-12-31",
        withdrawal_years=2, monthly_net=150_000.0, step_months=12,
    )
    assert res["survival_rate"] == 1.0
    assert len(res["per_account"]) == 2
    assert res["per_account"][0]["type"] == "위탁"
    assert res["per_account"][1]["type"] == "ISA"
    # 위탁 먼저 소진(150k×24~25 = 3.6M~3.75M < 5M) → ISA 전액 5M 잔존(견고)
    assert abs(res["per_account"][1]["end_value"]["p50"] - 5_000_000.0) <= 1.0
    assert 1_250_000.0 - 1.0 <= res["per_account"][0]["end_value"]["p50"] <= 1_400_000.0 + 1.0
    # 합산 = 위탁 + ISA
    assert abs(
        res["combined_end_value"]["p50"]
        - (res["per_account"][0]["end_value"]["p50"] + 5_000_000.0)
    ) <= 1.0


if __name__ == "__main__":
    for fn in [
        test_survival_rate_one_when_all_windows_survive,
        test_survival_rate_zero_when_all_deplete,
        test_per_account_distribution_surfaced,
    ]:
        fn()
        print(f"PASS {fn.__name__}")
