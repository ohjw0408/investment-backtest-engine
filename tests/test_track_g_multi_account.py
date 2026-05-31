import os
import sys

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from modules.config.simulation_config import SimulationConfig
from modules.retirement.multi_account_analyzer import (
    MultiAccountAnalyzer,
    calc_metrics_from_history,
)
from modules.rebalance.periodic import PeriodicRebalance
from modules.simulation.multi_account_loop import MultiAccountSimulationLoop
from modules.simulation.taxable_runner import TaxableSimulationRunner
from modules.tax.account_tax import DistributionDestination, DistributionPolicy
from modules.tax.base_tax import TaxEngine


def _price_frame(start, end, start_price=100.0, end_price=None, dividend_date=None, dividend=0.0):
    dates = pd.bdate_range(start=start, end=end)
    if end_price is None:
        closes = [float(start_price)] * len(dates)
    else:
        if len(dates) == 1:
            closes = [float(end_price)]
        else:
            step = (float(end_price) - float(start_price)) / (len(dates) - 1)
            closes = [float(start_price) + step * i for i in range(len(dates))]
    df = pd.DataFrame({
        "open": closes,
        "high": closes,
        "low": closes,
        "close": closes,
        "volume": [1_000_000] * len(dates),
        "dividend": [0.0] * len(dates),
        "split": [1.0] * len(dates),
    }, index=dates)
    if dividend_date is not None:
        div_ts = pd.Timestamp(dividend_date)
        if div_ts not in df.index:
            div_ts = df.index[df.index.searchsorted(div_ts)]
        df.loc[div_ts, "dividend"] = float(dividend)
    return df


def _provider_from_frames(frame_map):
    def provider(tickers, start_date, end_date, allow_synthetic=False):
        idx = pd.bdate_range(start=start_date, end=end_date)
        out = {}
        for ticker in tickers:
            df = frame_map[ticker].loc[
                (frame_map[ticker].index >= pd.Timestamp(start_date))
                & (frame_map[ticker].index <= pd.Timestamp(end_date))
            ].copy()
            df = df.reindex(idx)
            df[["open", "high", "low", "close", "volume"]] = (
                df[["open", "high", "low", "close", "volume"]].ffill().bfill()
            )
            df["dividend"] = df["dividend"].fillna(0.0)
            df["split"] = df["split"].fillna(1.0)
            out[ticker] = df
        return out, list(idx)
    return provider


def _account(ticker, initial=100.0, monthly=0.0, account_type="위탁", stop_months=None):
    return {
        "type": account_type,
        "initial_capital": initial,
        "monthly_contribution": monthly,
        "contribution_end_months": stop_months,
        "tickers": [{"code": ticker, "weight": 1.0}],
        "rebal_mode": "none",
        "band_width": 0.05,
        "dividend_mode": "hold",
    }


def _loop_account(ticker, initial=100.0, monthly=0.0, account_type="위탁", stop_months=None):
    config = SimulationConfig(
        start_date="2020-01-01",
        end_date="2021-01-01",
        tickers=[ticker],
        target_weights={ticker: 1.0},
        initial_capital=initial,
        monthly_contribution=monthly,
        contribution_end_months=stop_months,
        withdrawal_amount=0,
        dividend_mode="hold",
        rebalance_frequency=None,
        inflation=0.0,
    )
    strategy = PeriodicRebalance({ticker: 1.0}, rebalance_frequency=None)
    return {"type": account_type, "config": config, "strategy": strategy}


def test_l0_single_account_loop_matches_taxable_runner():
    price_data = {"AAA": _price_frame("2020-01-01", "2021-01-01", 100.0, 125.0)}
    dates = list(price_data["AAA"].index)
    config = SimulationConfig(
        start_date="2020-01-01",
        end_date="2021-01-01",
        tickers=["AAA"],
        target_weights={"AAA": 1.0},
        initial_capital=10_000.0,
        monthly_contribution=0.0,
        withdrawal_amount=0,
        dividend_mode="hold",
        rebalance_frequency=None,
        inflation=0.0,
    )
    strategy = PeriodicRebalance({"AAA": 1.0}, rebalance_frequency=None)

    single = TaxableSimulationRunner().run(config, price_data, dates, strategy, tax_enabled=False)
    multi = MultiAccountSimulationLoop().run(
        [{"type": "위탁", "config": config, "strategy": PeriodicRebalance({"AAA": 1.0}, rebalance_frequency=None)}],
        price_data,
        dates,
        tax_enabled=False,
    )

    assert abs(multi.combined_end_value - single.end_value) <= 1
    m_single = calc_metrics_from_history(single.history_df, 1, 10_000.0, 0.0)
    m_multi = calc_metrics_from_history(multi.combined_history_df, 1, 10_000.0, 0.0)
    assert abs(m_multi["cagr"] - m_single["cagr"]) <= 0.0001
    assert abs(m_multi["mdd"] - m_single["mdd"]) <= 0.0001


def test_l1_scenario_level_sum_not_percentile_sum():
    def provider(tickers, start_date, end_date, allow_synthetic=False):
        first_window = pd.Timestamp(start_date).month == 1
        idx = pd.bdate_range(start=start_date, end=end_date)
        out = {}
        for ticker in tickers:
            if ticker == "AAA":
                end_price = 200.0 if first_window else 100.0
            else:
                end_price = 100.0 if first_window else 200.0
            out[ticker] = _price_frame(start_date, end_date, 100.0, end_price).reindex(idx)
        return out, list(idx)

    analyzer = MultiAccountAnalyzer(
        portfolio_engine=None,
        accounts=[_account("AAA"), _account("BBB")],
        data_start="2020-01-01",
        data_end="2021-02-01",
        accumulation_years=1,
        step_months=1,
        price_provider=provider,
    )
    result = analyzer.run()

    combined_values = result["combined"]["distribution"]["end_value"]["values"]
    account_a = result["accounts"][0]["distribution"]["end_value"]
    account_b = result["accounts"][1]["distribution"]["end_value"]

    for case in result["cases"]:
        assert case["end_value"] == sum(a["end_value"] for a in case["accounts"])
    assert combined_values == [300.0, 300.0]
    assert result["combined"]["distribution"]["end_value"]["p10"] != account_a["p10"] + account_b["p10"]


def test_l2_flat_price_contribution_and_isa_stop_months():
    price_data = {"AAA": _price_frame("2020-01-01", "2020-06-30", 100.0)}
    dates = list(price_data["AAA"].index)
    account = _loop_account(
        "AAA",
        initial=99_000_000.0,
        monthly=1_000_000.0,
        account_type="ISA",
        stop_months=1,
    )
    result = MultiAccountSimulationLoop().run([account], price_data, dates, tax_enabled=False)

    assert result.account_results[0]["end_value"] == 100_000_000.0
    assert result.account_results[0]["total_contribution"] == 100_000_000.0
    assert (result.combined_history_df["cash"] >= 0).all()


def test_l3_dividend_tax_capital_gain_tax_and_isa_liquidation():
    # 배당세: 위탁 국내형 15.4%, 10주 x 주당 10원 = 세전 100원 → 세후 84.6원
    div_data = {"458730": _price_frame("2020-01-01", "2020-12-31", 100.0, dividend_date="2020-06-01", dividend=10.0)}
    div_result = MultiAccountSimulationLoop().run(
        [_loop_account("458730", initial=1_000.0, monthly=0.0, account_type="위탁")],
        div_data,
        list(div_data["458730"].index),
        tax_enabled=True,
        user_settings={"earned_income": 0, "age": 40},
    )
    assert abs(div_result.account_results[0]["end_value"] - 1_084.6) < 1e-6
    assert abs(div_result.account_results[0]["dividend_tax_paid"] - 15.4) < 1e-6

    # 양도세: 국내상장 해외 ETF 미실현 차익 1,000원 x 15.4% = 154원
    cg_data = {"458730": _price_frame("2020-01-01", "2020-12-31", 100.0, 200.0)}
    cg_result = MultiAccountSimulationLoop().run(
        [_loop_account("458730", initial=1_000.0, monthly=0.0, account_type="위탁")],
        cg_data,
        list(cg_data["458730"].index),
        tax_enabled=True,
        user_settings={"earned_income": 0, "age": 40},
    )
    assert abs(cg_result.account_results[0]["end_value"] - 1_846.0) < 1e-6
    assert abs(cg_result.account_results[0]["liquidation_tax_paid"] - 154.0) < 1e-6

    # ISA 청산세: 순이익 1,000만원 - 일반형 비과세 200만원 = 800만원 x 9.9%
    isa_data = {"AAA": _price_frame("2020-01-01", "2023-01-02", 100.0, 200.0)}
    isa_result = MultiAccountSimulationLoop().run(
        [_loop_account("AAA", initial=10_000_000.0, monthly=0.0, account_type="ISA")],
        isa_data,
        list(isa_data["AAA"].index),
        tax_enabled=True,
        user_settings={"earned_income": 0, "age": 40, "isa_type": "general"},
    )
    assert abs(isa_result.account_results[0]["end_value"] - 19_208_000.0) < 1e-6
    assert abs(isa_result.account_results[0]["liquidation_tax_paid"] - 792_000.0) < 1e-6


def _flat_year_data():
    # 2020 한 해(12개월), 플랫가격 100, 배당 0
    return {"AAA": _price_frame("2020-01-01", "2020-12-31", 100.0)}


def test_l4_monthly_overflow_routing_cascade():
    """ISA 연 2천만 초과분이 정책대로 연금(1800만)→위탁(∞)으로 cascade.

    손계산(플랫가격 100, 세금 OFF, 월납입 ISA 500만):
      ISA  연한도 20M → m0~m3 흡수(20M). m4~m11 초과 500만 × 8 = 40M.
      정책 [연금, 위탁]:
        연금 18M 채움(m4~m6 각 5M=15M, m7 3M) → 18M
        나머지(m7 2M + m8~m11 각 5M) → 위탁 22M
      ∴ ISA 20M / 연금 18M / 위탁 22M / 합산 60M, 자금보존.
    """
    price_data = _flat_year_data()
    dates = list(price_data["AAA"].index)
    accounts = [
        _loop_account("AAA", initial=0.0, monthly=5_000_000.0, account_type="ISA"),
        _loop_account("AAA", initial=0.0, monthly=0.0, account_type="연금저축"),
        _loop_account("AAA", initial=0.0, monthly=0.0, account_type="위탁"),
    ]
    policy = DistributionPolicy(destinations=[
        DistributionDestination(account_id=1),  # 연금
        DistributionDestination(account_id=2),  # 위탁
    ])

    result = MultiAccountSimulationLoop(transfers_enabled=True).run(
        accounts, price_data, dates, tax_enabled=False, distribution_policy=policy,
    )

    isa_end = result.account_results[0]["end_value"]
    pension_end = result.account_results[1]["end_value"]
    broker_end = result.account_results[2]["end_value"]

    assert abs(isa_end - 20_000_000.0) < 1.0
    assert abs(pension_end - 18_000_000.0) < 1.0
    assert abs(broker_end - 22_000_000.0) < 1.0
    # 자금 보존: 총 납입 = 12개월 × 500만 = 6천만
    assert abs((isa_end + pension_end + broker_end) - 60_000_000.0) < 1.0
    assert abs(result.combined_end_value - 60_000_000.0) < 1.0
    # 음수 잔액 없음
    assert (result.combined_history_df["cash"] >= -1e-6).all()
    # 라우팅 발생: m4~m11 = 8회, 총 초과 4천만
    assert len(result.transfer_log) == 8
    assert abs(sum(t["overflow"] for t in result.transfer_log) - 40_000_000.0) < 1.0


def test_l4_annual_limit_resets_next_year():
    """ISA 연한도는 해가 바뀌면 리셋(총 1억은 유지)."""
    price_data = {"AAA": _price_frame("2020-01-01", "2021-12-31", 100.0)}
    dates = list(price_data["AAA"].index)
    accounts = [
        _loop_account("AAA", initial=0.0, monthly=5_000_000.0, account_type="ISA"),
        _loop_account("AAA", initial=0.0, monthly=0.0, account_type="위탁"),
    ]
    policy = DistributionPolicy(destinations=[DistributionDestination(account_id=1)])

    result = MultiAccountSimulationLoop(transfers_enabled=True).run(
        accounts, price_data, dates, tax_enabled=False, distribution_policy=policy,
    )
    # 2년 × 12개월 × 500만 = 1.2억 납입.
    # 각 해 ISA 흡수 = 연한도 20M (총 한도 1억 미도달) → ISA 40M, 위탁 80M.
    isa_end = result.account_results[0]["end_value"]
    broker_end = result.account_results[1]["end_value"]
    assert abs(isa_end - 40_000_000.0) < 1.0
    assert abs(broker_end - 80_000_000.0) < 1.0


def test_l4_total_limit_caps_isa():
    """ISA 총 1억 한도 도달 후에는 연한도 잔여와 무관하게 전액 라우팅.

    총한도는 여러 해에 걸쳐 연한도(20M)를 누적해야 도달하므로 6년으로 검증
    (초기 90M ISA 같은 단년 투입은 연 2천만 한도 자체를 위반 → 비현실).

    플랫가격, 세금 OFF, ISA 월 500만(연 6천만이나 연한도 20M가 binding):
      1~5년차: 연 20M 흡수 → 5년 후 ISA 총 1억(총한도 도달). 위탁 연 40M.
      6년차: 연한도 20M 남아도 총한도 0 → 전액(60M) 위탁.
      ∴ ISA 100M / 위탁 200M+60M=260M / 합산 360M.
    """
    price_data = {"AAA": _price_frame("2020-01-01", "2025-12-31", 100.0)}
    dates = list(price_data["AAA"].index)
    accounts = [
        _loop_account("AAA", initial=0.0, monthly=5_000_000.0, account_type="ISA"),
        _loop_account("AAA", initial=0.0, monthly=0.0, account_type="위탁"),
    ]
    policy = DistributionPolicy(destinations=[DistributionDestination(account_id=1)])

    result = MultiAccountSimulationLoop(transfers_enabled=True).run(
        accounts, price_data, dates, tax_enabled=False, distribution_policy=policy,
    )
    isa_end = result.account_results[0]["end_value"]
    broker_end = result.account_results[1]["end_value"]
    assert abs(isa_end - 100_000_000.0) < 1.0
    assert abs(broker_end - 260_000_000.0) < 1.0
    assert abs(result.combined_end_value - 360_000_000.0) < 1.0


def test_l4_auto_sync_brokerage_created():
    """정책 목적지가 없는 계좌를 가리키면 위탁 자동 싱크(첫 ISA 미러) 생성."""
    price_data = _flat_year_data()
    dates = list(price_data["AAA"].index)
    accounts = [
        _loop_account("AAA", initial=0.0, monthly=5_000_000.0, account_type="ISA"),
    ]
    # account_id=1은 존재하지 않음 → 위탁 자동 싱크
    policy = DistributionPolicy(destinations=[DistributionDestination(account_id=1)])

    result = MultiAccountSimulationLoop(transfers_enabled=True).run(
        accounts, price_data, dates, tax_enabled=False, distribution_policy=policy,
    )
    # 싱크 계좌 추가됨
    assert len(result.account_results) == 2
    assert result.account_results[1]["type"] == "위탁"
    isa_end = result.account_results[0]["end_value"]
    sync_end = result.account_results[1]["end_value"]
    assert abs(isa_end - 20_000_000.0) < 1.0
    assert abs(sync_end - 40_000_000.0) < 1.0  # 초과분 전부 싱크 위탁
    assert abs(result.combined_end_value - 60_000_000.0) < 1.0
