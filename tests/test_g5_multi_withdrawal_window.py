"""G5-C C3.2a: 멀티계좌 가구 디큐뮬레이션 단일윈도우 검증 (결정론·손계산).

simulate_household_window — 평탄가격에서 가구 인출 합산소진·생존판정·계좌별 종료값.
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import numpy as np
import pandas as pd

from modules.tax.base_tax import TaxEngine
from modules.retirement.multi_account_withdrawal import simulate_household_window

CODE = "069500"  # 국내 ETF — CG 비과세


def _flat_window(code=CODE, price=100.0, start="2030-01-01", end="2031-12-31"):
    """평탄가격·무배당 윈도우 (24개월: 2030-01 ~ 2031-12)."""
    dates = pd.bdate_range(start, end)
    n = len(dates)
    df = pd.DataFrame(
        {"open": price, "high": price, "low": price, "close": price,
         "volume": 1.0, "dividend": 0.0, "split": 1.0},
        index=dates,
    )
    return {code: df}, list(dates)


def _acct(account_id, atype, value, code=CODE):
    return {"account_id": account_id, "type": atype, "value": float(value),
            "target_weights": {code: 1.0}}


# ── 1. 단일 위탁 생존: 12M, 100k×24개월 = 2.4M 인출 → 종료 9.6M ──────
def test_single_brokerage_survives_flat():
    pd_data, dates = _flat_window()
    accts = [_acct(0, "위탁", 12_000_000)]
    res = simulate_household_window(accts, pd_data, dates, 100_000.0)

    assert res["success"] is True
    assert res["fail_month"] is None
    # 24개월 × 100,000 = 2,400,000 인출 → 12M - 2.4M = 9.6M
    assert abs(res["combined_end_value"] - 9_600_000.0) <= 1.0


# ── 2. 소진 순서: 위탁 먼저 고갈 → 연금 충당 (무세금 선형) ──────────
def test_drain_order_brokerage_then_pension():
    pd_data, dates = _flat_window()
    accts = [_acct(0, "위탁", 5_000_000), _acct(1, "연금저축", 5_000_000)]
    res = simulate_household_window(accts, pd_data, dates, 300_000.0)

    # 총 인출 300k×24 = 7.2M. 위탁 5M 소진 후 연금 2.2M → 연금 잔 2.8M
    assert res["success"] is True
    assert abs(res["combined_end_value"] - 2_800_000.0) <= 1.0
    by_id = {p["account_id"]: p["end_value"] for p in res["per_account"]}
    assert abs(by_id[0] - 0.0) <= 1.0        # 위탁 고갈
    assert abs(by_id[1] - 2_800_000.0) <= 1.0  # 연금 잔여


# ── 3. 고갈 실패: 인출 > 합산 자산 → success False, fail_month ──────
def test_household_depletion_fails():
    pd_data, dates = _flat_window()
    accts = [_acct(0, "위탁", 2_000_000)]
    res = simulate_household_window(accts, pd_data, dates, 200_000.0)

    # 200k×24 = 4.8M > 2M → 약 10개월 후 고갈
    assert res["success"] is False
    assert res["fail_month"] is not None
    assert abs(res["combined_end_value"]) <= 1.0


# ── 4. 연금 세금 ON → gross-up로 더 빨리 고갈 (생존 하락 방향) ───────
def test_pension_tax_reduces_survival():
    pd_data, dates = _flat_window()
    te = TaxEngine({"earned_income": 0, "age": 65})

    accts_off = [_acct(0, "연금저축", 10_000_000)]
    res_off = simulate_household_window(
        accts_off, pd_data, dates, 300_000.0, tax_engine=None,
        withdrawal_start_age=65,
    )
    accts_on = [_acct(0, "연금저축", 10_000_000)]
    res_on = simulate_household_window(
        accts_on, pd_data, dates, 300_000.0, tax_engine=te,
        withdrawal_start_age=65,
    )

    # 세금 ON은 net 300k 위해 gross > 300k 인출 → 자산 더 빨리 소진
    assert res_on["combined_end_value"] < res_off["combined_end_value"]
    assert res_on["total_pension_tax"] > 0.0
    assert res_off["total_pension_tax"] == 0.0


# ── 5. 불변식: 무세금·평탄가격 → 인출 합 = 시작 합산 − 종료 합산 ─────
def test_invariant_conservation_no_tax():
    pd_data, dates = _flat_window()
    start_total = 8_000_000.0
    accts = [_acct(0, "위탁", 5_000_000), _acct(1, "ISA", 3_000_000)]
    res = simulate_household_window(accts, pd_data, dates, 150_000.0)

    withdrawn = 150_000.0 * 24  # 3.6M
    assert abs((start_total - res["combined_end_value"]) - withdrawn) <= 1.0


if __name__ == "__main__":
    for fn in [
        test_single_brokerage_survives_flat,
        test_drain_order_brokerage_then_pension,
        test_household_depletion_fails,
        test_pension_tax_reduces_survival,
        test_invariant_conservation_no_tax,
    ]:
        fn()
        print(f"PASS {fn.__name__}")
