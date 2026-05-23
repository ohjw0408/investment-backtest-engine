"""
Phase 1 Gate 1 검증.
SPY, 위탁, 세금 ON, rebal none:
  - harvest on vs off → end_value 달라야 함 (절세매도 효과)
  - 청산세가 기존 근사식보다 포지션 기반으로 계산되는지 확인
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from backtest_logic import run_backtest_logic


BASE_BODY = {
    "tickers": [{"code": "SPY", "weight": 1.0}],
    "start_date": "2015-01-01",
    "end_date": "2024-12-31",
    "initial_capital": 10_000_000,
    "monthly_contribution": 0,
    "dividend_mode": "reinvest",
    "rebal_mode": "none",
    "tax_enabled": True,
    "account_type": "위탁",
    "user_settings": {"earned_income": 50_000_000, "age": 40},
}


def test_harvest_off():
    body = {**BASE_BODY, "gain_harvesting": False}
    result = run_backtest_logic(body)
    ev = result["metrics"]["end_value"]
    print(f"harvest OFF: {ev:,}")
    assert ev > 0


def test_harvest_on():
    body = {**BASE_BODY, "gain_harvesting": True}
    result = run_backtest_logic(body)
    ev = result["metrics"]["end_value"]
    print(f"harvest ON:  {ev:,}")
    assert ev > 0


def test_harvest_on_gt_off():
    """절세매도 효과: harvest ON이 OFF보다 세후 자산 커야 함."""
    ev_off = run_backtest_logic({**BASE_BODY, "gain_harvesting": False})["metrics"]["end_value"]
    ev_on  = run_backtest_logic({**BASE_BODY, "gain_harvesting": True})["metrics"]["end_value"]
    print(f"harvest OFF: {ev_off:,}  |  ON: {ev_on:,}  |  diff: {ev_on - ev_off:,}")
    assert ev_on > ev_off, f"harvest ON({ev_on}) should be > OFF({ev_off})"


def test_monthly_rebal_harvest():
    """monthly rebal + harvest — 기존 경로도 정상 동작."""
    body = {**BASE_BODY, "rebal_mode": "monthly", "gain_harvesting": True}
    result = run_backtest_logic(body)
    assert result["metrics"]["end_value"] > 0


if __name__ == "__main__":
    print("=== Gate 1 검증 ===")
    test_harvest_off()
    test_harvest_on()
    test_harvest_on_gt_off()
    test_monthly_rebal_harvest()
    print("=== 전부 통과 ===")
