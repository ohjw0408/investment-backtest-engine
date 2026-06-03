"""G5-C C3.3: 은퇴 인출단계 멀티계좌 배선 검증 (L12 end-to-end).

_run_multi_account_retirement_logic이 적립 분포 → 11분위 샘플 → 가구 디큐뮬레이션
롤링 → 합성 생존율을 올바르게 배선하는지 검증(withdrawal_pending 스텁 해소).

L11 하니스(_patched/provider/_flat_frame/_account) 재사용 — 결정론 평탄가격.
"""
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import retirement_logic
from test_g5_retirement_accum import (
    _patched, _flat_frame, _account, EFF_START, DATA_END, KRF, KRD,
)


def _body(accounts, *, monthly_withdrawal, withdrawal_years=4,
          tax_enabled=False, user_settings=None, target_percentile=0.90):
    return {
        "accounts": accounts, "accumulation_years": 4,
        "tax_enabled": tax_enabled, "user_settings": user_settings or {},
        "dividend_mode": "hold",
        "monthly_withdrawal": monthly_withdrawal,
        "withdrawal_years": withdrawal_years,
        "inflation": 0.0,
        "target_percentile": target_percentile,
    }


# ── 1. 생존 end-to-end: 평탄·큰자산·작은인출 → 생존율 1.0, pending 해소 ──
def test_l12_survival_wired():
    dates = pd.bdate_range(EFF_START, DATA_END)
    fmap  = {KRF: _flat_frame(dates), KRD: _flat_frame(dates)}
    accounts = [_account(KRF, 100_000_000), _account(KRD, 100_000_000)]
    with _patched(fmap):
        res = retirement_logic._run_multi_account_retirement_logic(
            _body(accounts, monthly_withdrawal=100_000.0))

    assert res["withdrawal_pending"] is False
    assert res["combined_summary"] is not None
    assert res["combined_summary"]["survival_rate"] == 1.0
    assert len(res["sample_results"]) == 11
    assert res["message"]["is_safe"] is True


# ── 2. 고갈 end-to-end: 작은자산·큰인출 → 생존율 0.0 ──────────────────
def test_l12_depletion_wired():
    dates = pd.bdate_range(EFF_START, DATA_END)
    fmap  = {KRF: _flat_frame(dates)}
    accounts = [_account(KRF, 2_000_000), _account(KRD, 1_000_000)]
    fmap[KRD] = _flat_frame(dates)
    with _patched(fmap):
        res = retirement_logic._run_multi_account_retirement_logic(
            _body(accounts, monthly_withdrawal=200_000.0))

    assert res["withdrawal_pending"] is False
    assert res["combined_summary"]["survival_rate"] == 0.0
    assert res["message"]["is_safe"] is False


# ── 3. 구조·불변식: sample_results·combined_summary 형식 ─────────────
def test_l12_structure_and_invariants():
    dates = pd.bdate_range(EFF_START, DATA_END)
    fmap  = {KRF: _flat_frame(dates), KRD: _flat_frame(dates)}
    accounts = [_account(KRF, 50_000_000), _account(KRD, 50_000_000)]
    with _patched(fmap):
        res = retirement_logic._run_multi_account_retirement_logic(
            _body(accounts, monthly_withdrawal=300_000.0))

    cs = res["combined_summary"]
    assert 0.0 <= cs["survival_rate"] <= 1.0
    assert set(["p10", "p25", "p50", "p75", "p90"]).issubset(cs["combined_end_value"].keys())
    assert cs["total_withdrawal"] == round(300_000.0 * 4 * 12)
    for s in res["sample_results"]:
        assert s["percentile"] in (5, 10, 20, 30, 40, 50, 60, 70, 80, 90, 95)
        assert 0.0 <= s["success_rate"] <= 1.0
        assert s["initial_capital"] > 0
    # is_safe = survival >= target
    assert res["message"]["is_safe"] == (cs["survival_rate"] >= cs["target_percentile"])


# ── 4. 인출 입력 없으면 여전히 pending (스텁 활성화 안 됨) ──────────────
def test_l12_no_withdrawal_input_stays_pending():
    dates = pd.bdate_range(EFF_START, DATA_END)
    fmap  = {KRF: _flat_frame(dates), KRD: _flat_frame(dates)}
    accounts = [_account(KRF, 5_000_000), _account(KRD, 3_000_000)]
    body = {
        "accounts": accounts, "accumulation_years": 4, "tax_enabled": False,
        "user_settings": {}, "dividend_mode": "hold",
    }  # monthly_withdrawal/withdrawal_years 없음
    with _patched(fmap):
        res = retirement_logic._run_multi_account_retirement_logic(body)
    assert res["withdrawal_pending"] is True
    assert res["sample_results"] == []
    assert res["combined_summary"] is None


# ── 5. 세금 ON(연금 gross-up) → 생존율 ≤ OFF (동일 입력) ───────────────
def test_l12_pension_tax_not_higher_survival():
    dates = pd.bdate_range(EFF_START, DATA_END)
    fmap  = {KRF: _flat_frame(dates)}
    # 연금 계좌 단일(초기자본 한도 1800만 이내), 인출 경계 → 세금 ON이 더 빨리 고갈
    accounts = [{"type": "연금저축", "initial_capital": 14_800_000,
                 "monthly_contribution": 0,
                 "tickers": [{"code": KRF, "weight": 1.0}],
                 "rebal_mode": "none", "dividend_mode": "hold"}]
    us = {"earned_income": 0, "age": 60}
    with _patched(fmap):
        off = retirement_logic._run_multi_account_retirement_logic(
            _body(accounts, monthly_withdrawal=400_000.0, tax_enabled=False))
        on = retirement_logic._run_multi_account_retirement_logic(
            _body(accounts, monthly_withdrawal=400_000.0, tax_enabled=True,
                  user_settings=us))
    assert (on["combined_summary"]["survival_rate"]
            <= off["combined_summary"]["survival_rate"])


if __name__ == "__main__":
    for fn in [
        test_l12_survival_wired,
        test_l12_depletion_wired,
        test_l12_structure_and_invariants,
        test_l12_no_withdrawal_input_stays_pending,
        test_l12_pension_tax_not_higher_survival,
    ]:
        fn()
        print(f"PASS {fn.__name__}")
