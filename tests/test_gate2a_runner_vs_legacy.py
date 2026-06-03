"""
Gate 2a: TaxableSimulationRunner 백테스트 회귀 검증.

Phase 1 골든값(harvest off=37,365,073 / on=40,913,520)과 비교.
Runner 도입 후 동일 결과 보장.

골든 갱신 이력:
- 2026-06-04: BUG-TAX-1(단일경로 배당소득세 차감, log 업데이트 31) 반영.
  off 38,415,192→37,365,073(−1,050,119), on 41,990,905→40,913,520(−1,077,385).
  하락분 = SPY 재투자 배당에 정확히 부과된 15.4% 배당소득세.
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from backtest_logic import run_backtest_logic

GOLDEN = {
    "tickers":              [{"code": "SPY", "weight": 1.0}],
    "start_date":           "2015-01-01",
    "end_date":             "2024-12-31",
    "initial_capital":      10_000_000,
    "monthly_contribution": 0,
    "dividend_mode":        "reinvest",
    "rebal_mode":           "none",
    "tax_enabled":          True,
    "account_type":         "위탁",
    "user_settings":        {"earned_income": 50_000_000, "age": 40},
}

PHASE1_OFF = 37_365_073
PHASE1_ON  = 40_913_520
EPSILON    = 1  # 허용 오차 ±1원


def test_runner_harvest_off_matches_phase1():
    ev = run_backtest_logic({**GOLDEN, "gain_harvesting": False})["metrics"]["end_value"]
    print(f"Runner harvest OFF: {ev:,}  (기준: {PHASE1_OFF:,})")
    assert abs(ev - PHASE1_OFF) <= EPSILON, f"허용 오차 초과: {ev} vs {PHASE1_OFF}"


def test_runner_harvest_on_matches_phase1():
    ev = run_backtest_logic({**GOLDEN, "gain_harvesting": True})["metrics"]["end_value"]
    print(f"Runner harvest ON:  {ev:,}  (기준: {PHASE1_ON:,})")
    assert abs(ev - PHASE1_ON) <= EPSILON, f"허용 오차 초과: {ev} vs {PHASE1_ON}"


def test_harvest_ordering_preserved():
    """절세 효과 방향성 유지."""
    ev_off = run_backtest_logic({**GOLDEN, "gain_harvesting": False})["metrics"]["end_value"]
    ev_on  = run_backtest_logic({**GOLDEN, "gain_harvesting": True})["metrics"]["end_value"]
    print(f"OFF={ev_off:,}  ON={ev_on:,}  diff={ev_on - ev_off:,}")
    assert ev_on > ev_off, f"harvest ON({ev_on}) should be > OFF({ev_off})"


def test_runner_no_tax():
    """세금 OFF — 양수 결과만 확인."""
    ev = run_backtest_logic({**GOLDEN, "gain_harvesting": False, "tax_enabled": False})["metrics"]["end_value"]
    print(f"Runner no tax: {ev:,}")
    assert ev > 0


if __name__ == "__main__":
    print("=== Gate 2a ===")
    test_runner_harvest_off_matches_phase1()
    test_runner_harvest_on_matches_phase1()
    test_harvest_ordering_preserved()
    test_runner_no_tax()
    print("=== 통과 ===")
