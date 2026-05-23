"""
Gate 2b: AccumulationAnalyzer Runner 마이그레이션 검증.

1. 단일 윈도 AccumulationAnalyzer end_value ≈ 동일 기간 백테스트 end_value (±1원)
2. harvest on/off 방향성 유지
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from backtest_logic import run_backtest_logic

START  = "2018-01-01"
END    = "2023-01-01"  # START + 5년 (단일 윈도)
YEARS  = 5
PARAMS = dict(
    tickers              = ["SPY"],
    target_weights       = {"SPY": 1.0},
    initial_capital      = 10_000_000,
    monthly_contribution = 0,
    dividend_mode        = "reinvest",
    account_type         = "위탁",
    user_settings        = {"earned_income": 50_000_000, "age": 40},
)
EPSILON = 1  # ±1원


def _run_single_window(gain_harvesting: bool) -> float:
    """AccumulationAnalyzer를 단일 윈도(START~END)로 강제 실행."""
    from modules.portfolio_engine import PortfolioEngine
    from modules.retirement.accumulation_analyzer import AccumulationAnalyzer
    from modules.tax.base_tax import TaxEngine
    from calculator_logic import _make_strategy_factory

    pe             = PortfolioEngine()
    tax_engine     = TaxEngine(PARAMS["user_settings"])
    strategy_factory = _make_strategy_factory(PARAMS["target_weights"], "none")

    analyzer = AccumulationAnalyzer(
        portfolio_engine     = pe,
        tickers              = PARAMS["tickers"],
        strategy_factory     = strategy_factory,
        data_start           = START,
        data_end             = END,        # 딱 1개 윈도만 생성
        accumulation_years   = YEARS,
        monthly_contribution = PARAMS["monthly_contribution"],
        initial_capital      = PARAMS["initial_capital"],
        dividend_mode        = PARAMS["dividend_mode"],
        step_months          = 120,        # 크게 잡아 추가 윈도 방지
        tax_engine           = tax_engine,
        account_type         = PARAMS["account_type"],
        gain_harvesting      = gain_harvesting,
    )
    result = analyzer.run()
    cases  = result["cases"]
    assert len(cases) == 1, f"단일 윈도 기대, {len(cases)}개 생성됨"
    return cases[0]["end_value"]


def test_accumulation_harvest_off_runs():
    ev = _run_single_window(False)
    print(f"Accumulation harvest OFF: {ev:,.0f}")
    assert ev > 0


def test_accumulation_harvest_on_runs():
    ev = _run_single_window(True)
    print(f"Accumulation harvest ON:  {ev:,.0f}")
    assert ev > 0


def test_harvest_ordering_preserved():
    """절세 효과 방향성: ON > OFF."""
    ev_off = _run_single_window(False)
    ev_on  = _run_single_window(True)
    print(f"Accumulation OFF={ev_off:,.0f}  ON={ev_on:,.0f}  diff={ev_on - ev_off:,.0f}")
    assert ev_on > ev_off, f"harvest ON({ev_on}) should be > OFF({ev_off})"


def test_single_window_matches_backtest():
    """동일 기간: AccumulationAnalyzer end_value ≈ 백테스트 end_value (±1원)."""
    acc_ev = _run_single_window(False)
    bt_ev  = run_backtest_logic({
        "tickers":              [{"code": "SPY", "weight": 1.0}],
        "start_date":           START,
        "end_date":             "2022-12-31",
        "initial_capital":      PARAMS["initial_capital"],
        "monthly_contribution": PARAMS["monthly_contribution"],
        "rebal_mode":           "none",
        "dividend_mode":        PARAMS["dividend_mode"],
        "tax_enabled":          True,
        "account_type":         PARAMS["account_type"],
        "user_settings":        PARAMS["user_settings"],
        "gain_harvesting":      False,
    })["metrics"]["end_value"]
    print(f"Accumulation={acc_ev:,.0f}  Backtest={bt_ev:,.0f}  diff={abs(acc_ev - bt_ev):,.0f}")
    assert abs(acc_ev - bt_ev) <= EPSILON, (
        f"AccumulationAnalyzer({acc_ev}) vs Backtest({bt_ev}) 허용 오차 초과 (±{EPSILON}원)"
    )


if __name__ == "__main__":
    print("=== Gate 2b ===")
    test_accumulation_harvest_off_runs()
    test_accumulation_harvest_on_runs()
    test_harvest_ordering_preserved()
    test_single_window_matches_backtest()
    print("=== 통과 ===")
