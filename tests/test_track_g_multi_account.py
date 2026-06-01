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


def _account(ticker, initial=100.0, monthly=0.0, account_type="위탁", stop_months=None,
             isa_renewal=False):
    return {
        "type": account_type,
        "initial_capital": initial,
        "monthly_contribution": monthly,
        "contribution_end_months": stop_months,
        "tickers": [{"code": ticker, "weight": 1.0}],
        "rebal_mode": "none",
        "band_width": 0.05,
        "dividend_mode": "hold",
        "isa_renewal": isa_renewal,
    }


def _loop_account(ticker, initial=100.0, monthly=0.0, account_type="위탁", stop_months=None,
                  start_date="2020-01-01", end_date="2021-01-01",
                  isa_renewal=False, reinvest_tax_credit=False):
    config = SimulationConfig(
        start_date=start_date,
        end_date=end_date,
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
    return {
        "type": account_type, "config": config, "strategy": strategy,
        "isa_renewal": isa_renewal, "reinvest_tax_credit": reinvest_tax_credit,
    }


_ISA_TOTAL = 100_000_000
_PENSION_ANNUAL = 18_000_000


def assert_invariants(result, expected_total_in=None, flat_price=False):
    """전 L케이스 공통 불변식.

    - 음수 잔액 없음
    - ISA 납입(total_contribution) ≤ 총 1억
    - (expected_total_in 주어지면) Σ계좌 납입 = 실제 투입 총액
      → 라우팅은 재분배일 뿐 보존(ISA가 못 받은 건 다른 계좌가 받음)
    - (flat_price면) Σ raw_end_value = Σ투입 (수익 0이므로 자금 보존 직접 확인)
    """
    df = result.combined_history_df
    if not df.empty:
        assert (df["cash"] >= -1e-6).all(), "음수 잔액 발생"

    total_contrib = 0.0
    for ar in result.account_results:
        tc = float(ar.get("total_contribution", 0.0))
        total_contrib += tc
        if ar["type"] == "ISA":
            # 풍차 ISA는 만기마다 한도 리셋 → 평생 납입은 1억 초과 가능.
            # 1억 불변식은 "현재 사이클" 납입 기준으로 검사.
            basis = float(ar.get("cycle_contribution", tc))
            assert basis <= _ISA_TOTAL + 1.0, f"ISA 사이클 납입 {basis} > 1억"

    if expected_total_in is not None:
        assert abs(total_contrib - expected_total_in) < 1.0, (
            f"자금보존 위반: Σ납입 {total_contrib} != 투입 {expected_total_in}"
        )
    if flat_price:
        raw = sum(float(ar.get("raw_end_value", 0.0)) for ar in result.account_results)
        assert abs(raw - total_contrib) < 1.0, (
            f"플랫가격 자금보존 위반: Σraw_end {raw} != Σ납입 {total_contrib}"
        )


def _two_year_step_data(rise_code, flat_code):
    """1년차 100 고정 → 2년차 100→200 상승(rise_code), flat_code는 2년 내내 100.

    라우팅 매수가 1년차 100으로 결정되고 2년차 청산가 200 → 수익 손계산 가능.
    """
    y1 = _price_frame("2020-01-01", "2020-12-31", 100.0, 100.0)
    y2 = _price_frame("2021-01-01", "2021-12-31", 100.0, 200.0)
    rise = pd.concat([y1, y2])
    flat = _price_frame("2020-01-01", "2021-12-31", 100.0, 100.0)
    return {rise_code: rise, flat_code: flat}


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


def test_l0_single_account_loop_matches_taxable_runner_tax_on():
    """세금 ON 골든: 1계좌 위탁(458730 상승) 청산세까지 Runner와 ±1원 일치."""
    price_data = {"458730": _price_frame("2020-01-01", "2021-01-01", 100.0, 200.0)}
    dates = list(price_data["458730"].index)
    config = SimulationConfig(
        start_date="2020-01-01", end_date="2021-01-01",
        tickers=["458730"], target_weights={"458730": 1.0},
        initial_capital=10_000_000.0, monthly_contribution=0.0,
        withdrawal_amount=0, dividend_mode="hold",
        rebalance_frequency=None, inflation=0.0,
    )
    us = {"earned_income": 0, "age": 40}
    single = TaxableSimulationRunner().run(
        config, price_data, dates, PeriodicRebalance({"458730": 1.0}, rebalance_frequency=None),
        tax_enabled=True, account_type="위탁", user_settings=us,
    )
    multi = MultiAccountSimulationLoop().run(
        [{"type": "위탁", "config": config,
          "strategy": PeriodicRebalance({"458730": 1.0}, rebalance_frequency=None)}],
        price_data, dates, tax_enabled=True, user_settings=us,
    )
    assert abs(multi.combined_end_value - single.end_value) <= 1
    assert_invariants(multi)


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
    # 합산은 시나리오 단위 — 두 계좌 모두 같은 시나리오에서 200+100=300
    for case in result["cases"]:
        assert case["end_value"] == 300.0


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
    # 초기 9900만 + 월 100만 × 1개월(stop) = 1억 정확
    assert_invariants(result, expected_total_in=100_000_000.0, flat_price=True)


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

    # ISA 비과세한도 경계: 순이익이 일반형 비과세 200만 이하면 청산세 0.
    # 초기 1000만 → 1.2배(1200만), 순이익 200만 = 비과세한도 정확 → 세금 0.
    isa_edge_data = {"AAA": _price_frame("2020-01-01", "2023-01-02", 100.0, 120.0)}
    isa_edge_result = MultiAccountSimulationLoop().run(
        [_loop_account("AAA", initial=10_000_000.0, monthly=0.0, account_type="ISA")],
        isa_edge_data,
        list(isa_edge_data["AAA"].index),
        tax_enabled=True,
        user_settings={"earned_income": 0, "age": 40, "isa_type": "general"},
    )
    assert abs(isa_edge_result.account_results[0]["liquidation_tax_paid"] - 0.0) < 1e-6
    assert abs(isa_edge_result.account_results[0]["end_value"] - 12_000_000.0) < 1e-6

    # ISA 서민형(preferential): 순이익 1,000만 - 서민형 400만 = 600만 x 9.9% = 59.4만
    isa_pref_result = MultiAccountSimulationLoop().run(
        [_loop_account("AAA", initial=10_000_000.0, monthly=0.0, account_type="ISA")],
        isa_data,
        list(isa_data["AAA"].index),
        tax_enabled=True,
        user_settings={"earned_income": 0, "age": 40, "isa_type": "preferential"},
    )
    assert abs(isa_pref_result.account_results[0]["liquidation_tax_paid"] - 594_000.0) < 1e-6
    assert abs(isa_pref_result.account_results[0]["end_value"] - 19_406_000.0) < 1e-6


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
    assert_invariants(result, expected_total_in=60_000_000.0, flat_price=True)


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
    assert_invariants(result, expected_total_in=120_000_000.0, flat_price=True)


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
    assert_invariants(result, expected_total_in=360_000_000.0, flat_price=True)


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
    assert_invariants(result, expected_total_in=60_000_000.0, flat_price=True)


# ── L4 구멍 메꿈 (2026-06-01): cap·leftover·연금IRP합산·세금ON ──

def test_l4_policy_cap_caps_destination():
    """정책 destination.cap(전기간 누적 상한)이 capacity보다 작으면 cap까지만 받고 cascade.

    ISA 월500만/1년 → 초과 40M. 정책 [연금(cap=1000만 누적), 위탁]:
      연금은 한도 1800만 있어도 정책 누적 cap 1000만까지만 → 1000만.
      나머지 30M → 위탁.
    ∴ ISA 20M / 연금 10M / 위탁 30M / 합산 60M.
    """
    price_data = _flat_year_data()
    dates = list(price_data["AAA"].index)
    accounts = [
        _loop_account("AAA", initial=0.0, monthly=5_000_000.0, account_type="ISA"),
        _loop_account("AAA", initial=0.0, monthly=0.0, account_type="연금저축"),
        _loop_account("AAA", initial=0.0, monthly=0.0, account_type="위탁"),
    ]
    policy = DistributionPolicy(destinations=[
        DistributionDestination(account_id=1, cap=10_000_000.0),
        DistributionDestination(account_id=2),
    ])
    result = MultiAccountSimulationLoop(transfers_enabled=True).run(
        accounts, price_data, dates, tax_enabled=False, distribution_policy=policy,
    )
    assert abs(result.account_results[0]["end_value"] - 20_000_000.0) < 1.0
    assert abs(result.account_results[1]["end_value"] - 10_000_000.0) < 1.0
    assert abs(result.account_results[2]["end_value"] - 30_000_000.0) < 1.0
    assert_invariants(result, expected_total_in=60_000_000.0, flat_price=True)


def test_l4_leftover_when_policy_cannot_absorb():
    """정책에 무제한(위탁) 목적지가 없으면 흡수 못한 잔액 = leftover.

    ISA 월500만/1년 → 초과 40M. 정책 [연금만(한도 1800만)]:
      연금 18M 흡수, 나머지 22M 흡수 불가 → leftover 누적 22M.
      leftover는 어느 계좌에도 안 들어감(현금 미주입) → 합산 = ISA20 + 연금18 = 38M.
    """
    price_data = _flat_year_data()
    dates = list(price_data["AAA"].index)
    accounts = [
        _loop_account("AAA", initial=0.0, monthly=5_000_000.0, account_type="ISA"),
        _loop_account("AAA", initial=0.0, monthly=0.0, account_type="연금저축"),
    ]
    policy = DistributionPolicy(destinations=[DistributionDestination(account_id=1)])
    result = MultiAccountSimulationLoop(transfers_enabled=True).run(
        accounts, price_data, dates, tax_enabled=False, distribution_policy=policy,
    )
    assert abs(result.account_results[0]["end_value"] - 20_000_000.0) < 1.0
    assert abs(result.account_results[1]["end_value"] - 18_000_000.0) < 1.0
    total_leftover = sum(t["leftover"] for t in result.transfer_log)
    assert abs(total_leftover - 22_000_000.0) < 1.0
    # leftover는 투입에서 빠진 게 아니라 "어디에도 안 간" 돈 → 계좌합 < 실투입
    assert abs(result.combined_end_value - 38_000_000.0) < 1.0
    # 들어간 돈 기준 불변식(누락분 제외)
    assert_invariants(result, flat_price=True)


def test_l4_pension_irp_share_annual_limit():
    """연금저축 + IRP는 합산 연 1800만 풀을 공유.

    ISA 월500만/1년 → 초과 40M. 정책 [연금, IRP, 위탁]:
      연금+IRP 합산 1800만까지만(풀 공유). 연금 먼저 1800만 → IRP 0.
      나머지 22M → 위탁.
    ∴ ISA 20M / 연금 18M / IRP 0 / 위탁 22M.
    """
    price_data = _flat_year_data()
    dates = list(price_data["AAA"].index)
    accounts = [
        _loop_account("AAA", initial=0.0, monthly=5_000_000.0, account_type="ISA"),
        _loop_account("AAA", initial=0.0, monthly=0.0, account_type="연금저축"),
        _loop_account("AAA", initial=0.0, monthly=0.0, account_type="IRP"),
        _loop_account("AAA", initial=0.0, monthly=0.0, account_type="위탁"),
    ]
    policy = DistributionPolicy(destinations=[
        DistributionDestination(account_id=1),
        DistributionDestination(account_id=2),
        DistributionDestination(account_id=3),
    ])
    result = MultiAccountSimulationLoop(transfers_enabled=True).run(
        accounts, price_data, dates, tax_enabled=False, distribution_policy=policy,
    )
    assert abs(result.account_results[1]["end_value"] - 18_000_000.0) < 1.0
    assert abs(result.account_results[2]["end_value"] - 0.0) < 1.0
    assert abs(result.account_results[3]["end_value"] - 22_000_000.0) < 1.0
    assert_invariants(result, expected_total_in=60_000_000.0, flat_price=True)


def test_l4_tax_on_routing_liquidation():
    """L4-tax: 세금 ON 라우팅. ISA 고정종목(청산세0) + 위탁 수신분 상승 → 15.4% 청산세.

    종목: AAA=ISA 보유(2년 100 고정), 458730=위탁 보유(1년차100→2년차200).
    ISA 월200만/1년(stop 12) → 연한도 2000만은 m0~m9(10개월) 흡수, m10·m11 각200만 초과.
      초과 400만 → 위탁(458730) 1년차 가격100에 매수 = 4만주.
    2년차: 납입 stop → 라우팅 0. 가격 458730 100→200.
      위탁 청산수익 = 4만주×(200-100) = 400만. KR_FOREIGN 15.4% → 청산세 61.6만.
    ∴ ISA 2000만(세금0) / 위탁 800만-61.6만=738.4만.
    """
    price_data = _two_year_step_data(rise_code="458730", flat_code="AAA")
    dates = sorted(set(price_data["458730"].index) | set(price_data["AAA"].index))
    isa = _loop_account("AAA", initial=0.0, monthly=2_000_000.0, account_type="ISA", stop_months=12)
    broker = _loop_account("458730", initial=0.0, monthly=0.0, account_type="위탁")
    policy = DistributionPolicy(destinations=[DistributionDestination(account_id=1)])

    result = MultiAccountSimulationLoop(transfers_enabled=True).run(
        [isa, broker], price_data, dates,
        tax_enabled=True, user_settings={"earned_income": 0, "age": 40},
        distribution_policy=policy,
    )
    isa_res = result.account_results[0]
    broker_res = result.account_results[1]
    assert abs(isa_res["end_value"] - 20_000_000.0) < 1.0       # ISA 수익0 → 청산세0
    assert abs(isa_res["liquidation_tax_paid"] - 0.0) < 1.0
    assert abs(broker_res["liquidation_tax_paid"] - 616_000.0) < 1.0
    assert abs(broker_res["end_value"] - 7_384_000.0) < 1.0
    assert_invariants(result)


# ── L5 만기분배 (2-2): 3년 풍차 만기 목돈을 정책대로 재배분 ──

def _grow_then_flat(code, mult, start="2020-01-01", grow_end="2022-12-31",
                    flat_end="2023-12-31", start_price=100.0):
    """3년간 start_price→start_price*mult 선형상승 후 만기가격으로 평탄.

    3년 보유 ISA가 만기에 정확히 start_price*mult배 가치가 되도록.
    """
    end_price = start_price * mult
    grow = _price_frame(start, grow_end, start_price, end_price)
    flat = _price_frame(pd.Timestamp(grow_end) + pd.Timedelta(days=1), flat_end,
                        end_price, end_price)
    return {code: pd.concat([grow, flat])}


def test_l5_maturity_distribution_normal():
    """풍차 만기(3년): ISA 청산→목돈을 정책 [ISA(재가입 2천만), 위탁(나머지)]로 배분.

    손계산(세금 OFF, 초기 1천만 @100 = 100,000주, 3년 후 ×4 = 4천만):
      만기 목돈 4천만 → ISA 재가입 2천만(연한도) + 위탁 2천만.
      4년차 평탄(400) → ISA 2천만, 위탁 2천만 유지. 합산 4천만.
    remainder(4년차 1년 부분 사이클)도 함께 검증 — 만기 1회 후 최종청산.
    """
    price_data = _grow_then_flat("AAA", mult=4.0, flat_end="2023-12-31")
    dates = list(price_data["AAA"].index)
    isa = _loop_account("AAA", initial=10_000_000.0, account_type="ISA",
                        start_date="2020-01-01", end_date="2024-01-01", isa_renewal=True)
    broker = _loop_account("AAA", initial=0.0, account_type="위탁",
                           start_date="2020-01-01", end_date="2024-01-01")
    policy = DistributionPolicy(destinations=[
        DistributionDestination(account_id=0),  # 새 ISA(재가입)
        DistributionDestination(account_id=1),  # 위탁(나머지)
    ])
    result = MultiAccountSimulationLoop(transfers_enabled=True).run(
        [isa, broker], price_data, dates, tax_enabled=False, distribution_policy=policy,
    )
    isa_res = result.account_results[0]
    broker_res = result.account_results[1]
    assert abs(isa_res["end_value"] - 20_000_000.0) < 1.0
    assert abs(broker_res["end_value"] - 20_000_000.0) < 1.0
    assert abs(result.combined_end_value - 40_000_000.0) < 1.0

    maturities = [t for t in result.transfer_log if t.get("type") == "maturity"]
    assert len(maturities) == 1
    assert abs(maturities[0]["lump"] - 40_000_000.0) < 1.0
    allocs = dict(maturities[0]["allocations"])
    assert abs(allocs[0] - 20_000_000.0) < 1.0
    assert abs(allocs[1] - 20_000_000.0) < 1.0
    assert abs(maturities[0]["leftover"]) < 1.0
    assert_invariants(result)


def test_l5_maturity_below_isa_limit_all_to_isa():
    """경계: 만기액 < 2천만 → 전액 새 ISA 재가입(위탁 0)."""
    price_data = _grow_then_flat("AAA", mult=1.5, flat_end="2023-12-31")  # 1천만→1.5천만
    dates = list(price_data["AAA"].index)
    isa = _loop_account("AAA", initial=10_000_000.0, account_type="ISA",
                        start_date="2020-01-01", end_date="2024-01-01", isa_renewal=True)
    broker = _loop_account("AAA", initial=0.0, account_type="위탁",
                           start_date="2020-01-01", end_date="2024-01-01")
    policy = DistributionPolicy(destinations=[
        DistributionDestination(account_id=0), DistributionDestination(account_id=1),
    ])
    result = MultiAccountSimulationLoop(transfers_enabled=True).run(
        [isa, broker], price_data, dates, tax_enabled=False, distribution_policy=policy,
    )
    assert abs(result.account_results[0]["end_value"] - 15_000_000.0) < 1.0
    assert abs(result.account_results[1]["end_value"] - 0.0) < 1.0
    maturities = [t for t in result.transfer_log if t.get("type") == "maturity"]
    assert abs(dict(maturities[0]["allocations"])[0] - 15_000_000.0) < 1.0
    assert 1 not in dict(maturities[0]["allocations"])
    assert_invariants(result)


def test_l5_maturity_above_total_limit_caps_isa():
    """경계: 만기액 > 1억 → 새 ISA는 연한도 2천만까지만, 나머지 위탁."""
    price_data = _grow_then_flat("AAA", mult=6.0, flat_end="2023-12-31")  # 2천만→1.2억
    dates = list(price_data["AAA"].index)
    isa = _loop_account("AAA", initial=20_000_000.0, account_type="ISA",
                        start_date="2020-01-01", end_date="2024-01-01", isa_renewal=True)
    broker = _loop_account("AAA", initial=0.0, account_type="위탁",
                           start_date="2020-01-01", end_date="2024-01-01")
    policy = DistributionPolicy(destinations=[
        DistributionDestination(account_id=0), DistributionDestination(account_id=1),
    ])
    result = MultiAccountSimulationLoop(transfers_enabled=True).run(
        [isa, broker], price_data, dates, tax_enabled=False, distribution_policy=policy,
    )
    assert abs(result.account_results[0]["end_value"] - 20_000_000.0) < 1.0    # 재가입 연한도
    assert abs(result.account_results[1]["end_value"] - 100_000_000.0) < 1.0   # 나머지 1억
    assert abs(result.combined_end_value - 120_000_000.0) < 1.0
    assert_invariants(result)


def test_l5_maturity_tax_on():
    """L5-tax: 세금 ON 만기 청산세 후 목돈 분배.

    초기 1천만 @100 → 만기 4천만(순이익 3천만). ISA 일반형 비과세 200만.
      과세표준 2800만 × 9.9% = 277.2만 만기세 → 목돈 3722.8만.
      재배분 [ISA 2천만, 위탁 1722.8만]. 4년차 평탄 → 추가 수익 0.
    """
    price_data = _grow_then_flat("AAA", mult=4.0, flat_end="2023-12-31")
    dates = list(price_data["AAA"].index)
    isa = _loop_account("AAA", initial=10_000_000.0, account_type="ISA",
                        start_date="2020-01-01", end_date="2024-01-01", isa_renewal=True)
    broker = _loop_account("AAA", initial=0.0, account_type="위탁",
                           start_date="2020-01-01", end_date="2024-01-01")
    policy = DistributionPolicy(destinations=[
        DistributionDestination(account_id=0), DistributionDestination(account_id=1),
    ])
    result = MultiAccountSimulationLoop(transfers_enabled=True).run(
        [isa, broker], price_data, dates, tax_enabled=True,
        user_settings={"earned_income": 0, "age": 40, "isa_type": "general"},
        distribution_policy=policy,
    )
    isa_res = result.account_results[0]
    broker_res = result.account_results[1]
    assert abs(isa_res["maturity_tax_paid"] - 2_772_000.0) < 1.0
    assert abs(isa_res["end_value"] - 20_000_000.0) < 1.0       # 재가입분 추가수익0
    assert abs(broker_res["end_value"] - 17_228_000.0) < 1.0
    assert abs(result.combined_end_value - 37_228_000.0) < 1.0
    assert_invariants(result)


# ── L5b 다중사이클 풍차 (2-2): 9년 3사이클 ──

def _multi_cycle_x2(code):
    """3년마다 ×2: 100→200(2020-22) →400(2023-25) →800(2026-28)."""
    c1 = _price_frame("2020-01-01", "2022-12-31", 100.0, 200.0)
    c2 = _price_frame("2023-01-01", "2025-12-31", 200.0, 400.0)
    c3 = _price_frame("2026-01-01", "2028-12-31", 400.0, 800.0)
    return {code: pd.concat([c1, c2, c3])}


def test_l5b_multi_cycle_windmill():
    """9년 3사이클: 매 만기 ISA 2천만 재가입 + 위탁 누적. 비과세 리셋.

    손계산(세금 OFF, 초기 2천만, 사이클당 ×2):
      사이클1 만기(2023-01,@200): ISA 4천만→재가입2천만+위탁2천만(100,000주@200)
      사이클2 만기(2026-01,@400): ISA 4천만→재가입2천만+위탁2천만
        위탁: 100,000주→4천만(@400)+50,000주=150,000주
      사이클3 최종(2028-12,@800): ISA 재가입2천만→4천만, 위탁 150,000주×800=1.2억
      ∴ ISA 4천만 / 위탁 1.2억 / 합산 1.6억. 만기 2회.
    """
    price_data = _multi_cycle_x2("AAA")
    dates = list(price_data["AAA"].index)
    isa = _loop_account("AAA", initial=20_000_000.0, account_type="ISA",
                        start_date="2020-01-01", end_date="2029-01-01", isa_renewal=True)
    broker = _loop_account("AAA", initial=0.0, account_type="위탁",
                           start_date="2020-01-01", end_date="2029-01-01")
    policy = DistributionPolicy(destinations=[
        DistributionDestination(account_id=0), DistributionDestination(account_id=1),
    ])
    result = MultiAccountSimulationLoop(transfers_enabled=True).run(
        [isa, broker], price_data, dates, tax_enabled=False, distribution_policy=policy,
    )
    isa_res = result.account_results[0]
    broker_res = result.account_results[1]
    assert abs(isa_res["end_value"] - 40_000_000.0) < 1.0
    assert abs(broker_res["end_value"] - 120_000_000.0) < 1.0
    assert abs(result.combined_end_value - 160_000_000.0) < 1.0

    maturities = [t for t in result.transfer_log if t.get("type") == "maturity"]
    assert len(maturities) == 2
    for m in maturities:
        assert abs(m["lump"] - 40_000_000.0) < 1.0
        assert abs(dict(m["allocations"])[0] - 20_000_000.0) < 1.0
        assert abs(dict(m["allocations"])[1] - 20_000_000.0) < 1.0
    assert_invariants(result)


def test_l5b_multi_cycle_tax_accumulates():
    """L5b-tax: 사이클별 청산세 누적. 매 사이클 순이익 2천만 동일(재가입 2천만 캡).

    각 만기/최종: (2천만 − 비과세 200만) × 9.9% = 178.2만.
      만기 2회 누적 = 356.4만, 최종청산 178.2만.
    """
    price_data = _multi_cycle_x2("AAA")
    dates = list(price_data["AAA"].index)
    isa = _loop_account("AAA", initial=20_000_000.0, account_type="ISA",
                        start_date="2020-01-01", end_date="2029-01-01", isa_renewal=True)
    broker = _loop_account("AAA", initial=0.0, account_type="위탁",
                           start_date="2020-01-01", end_date="2029-01-01")
    policy = DistributionPolicy(destinations=[
        DistributionDestination(account_id=0), DistributionDestination(account_id=1),
    ])
    result = MultiAccountSimulationLoop(transfers_enabled=True).run(
        [isa, broker], price_data, dates, tax_enabled=True,
        user_settings={"earned_income": 0, "age": 40, "isa_type": "general"},
        distribution_policy=policy,
    )
    isa_res = result.account_results[0]
    maturities = [t for t in result.transfer_log if t.get("type") == "maturity"]
    assert len(maturities) == 2
    for m in maturities:
        assert abs(m["maturity_tax"] - 1_782_000.0) < 1.0
    assert abs(isa_res["maturity_tax_paid"] - 3_564_000.0) < 1.0
    assert abs(isa_res["liquidation_tax_paid"] - 1_782_000.0) < 1.0
    assert_invariants(result)


# ── L6 연금이전 세액공제 (G3): ISA 만기 → 연금 전환 시 10%(연 300만) 공제 ──

def test_l6_pension_transfer_credit_normal():
    """만기 목돈 일부를 연금 이전 → 이전액 10% 세액공제(< 300만 상한).

    손계산(세금 OFF, 초기 1천만 ×4 = 만기 4천만):
      정책 [연금(cap 1800만), 위탁]: 연금 1800만 전환 → 공제 min(180만,300만)=180만.
      나머지 2200만 → 위탁. (전환은 1800만 납입한도와 별도 — pension_unlimited)
    """
    price_data = _grow_then_flat("AAA", mult=4.0, flat_end="2023-12-31")
    dates = list(price_data["AAA"].index)
    isa = _loop_account("AAA", initial=10_000_000.0, account_type="ISA",
                        start_date="2020-01-01", end_date="2024-01-01", isa_renewal=True)
    pension = _loop_account("AAA", initial=0.0, account_type="연금저축",
                            start_date="2020-01-01", end_date="2024-01-01")
    broker = _loop_account("AAA", initial=0.0, account_type="위탁",
                           start_date="2020-01-01", end_date="2024-01-01")
    policy = DistributionPolicy(destinations=[
        DistributionDestination(account_id=1, cap=18_000_000.0),  # 연금 1800만까지
        DistributionDestination(account_id=2),                    # 위탁 나머지
    ])
    result = MultiAccountSimulationLoop(transfers_enabled=True).run(
        [isa, pension, broker], price_data, dates, tax_enabled=False,
        distribution_policy=policy,
    )
    assert abs(result.account_results[0]["end_value"] - 0.0) < 1.0          # ISA 미재가입
    assert abs(result.account_results[1]["end_value"] - 18_000_000.0) < 1.0  # 연금 전환분
    assert abs(result.account_results[2]["end_value"] - 22_000_000.0) < 1.0  # 위탁 나머지
    assert abs(result.account_results[1]["pension_transfer_credit"] - 1_800_000.0) < 1.0
    assert_invariants(result)


def test_l6_pension_transfer_credit_capped_full_transfer():
    """경계+세금ON: 전액 연금이전 → 공제 300만 상한 적중.

    세금 ON, 초기 1천만 ×4 = 만기 4천만, 만기세 277.2만 → 목돈 3722.8만.
      정책 [연금만]: 전액(3722.8만) 연금 전환(무제한). 공제 base 3000만 cap →
      공제 min(3722.8만×0.1, 300만) = 300만 (상한 적중).
    """
    price_data = _grow_then_flat("AAA", mult=4.0, flat_end="2023-12-31")
    dates = list(price_data["AAA"].index)
    isa = _loop_account("AAA", initial=10_000_000.0, account_type="ISA",
                        start_date="2020-01-01", end_date="2024-01-01", isa_renewal=True)
    pension = _loop_account("AAA", initial=0.0, account_type="연금저축",
                            start_date="2020-01-01", end_date="2024-01-01")
    policy = DistributionPolicy(destinations=[DistributionDestination(account_id=1)])
    result = MultiAccountSimulationLoop(transfers_enabled=True).run(
        [isa, pension], price_data, dates, tax_enabled=True,
        user_settings={"earned_income": 0, "age": 40, "isa_type": "general"},
        distribution_policy=policy,
    )
    assert abs(result.account_results[0]["end_value"] - 0.0) < 1.0
    assert abs(result.account_results[1]["pension_transfer_credit"] - 3_000_000.0) < 1.0
    assert_invariants(result)


def test_l6_pension_transfer_credit_reinvested():
    """세액공제 환급금 재투자 옵션: 공제 300만이 연금 계좌에 추가 투입 → 종료값 증가.

    세금 OFF, 만기 4천만 전액 연금이전(공제 300만 상한). reinvest ON →
      연금 종료값 = 전환 4천만 + 재투자 300만 = 4300만.
    """
    price_data = _grow_then_flat("AAA", mult=4.0, flat_end="2023-12-31")
    dates = list(price_data["AAA"].index)
    isa = _loop_account("AAA", initial=10_000_000.0, account_type="ISA",
                        start_date="2020-01-01", end_date="2024-01-01", isa_renewal=True)
    pension = _loop_account("AAA", initial=0.0, account_type="연금저축",
                            start_date="2020-01-01", end_date="2024-01-01")
    policy = DistributionPolicy(destinations=[DistributionDestination(account_id=1)])
    result = MultiAccountSimulationLoop(transfers_enabled=True).run(
        [isa, pension], price_data, dates, tax_enabled=False,
        distribution_policy=policy, reinvest_tax_credit=True,
    )
    assert abs(result.account_results[1]["pension_transfer_credit"] - 3_000_000.0) < 1.0
    assert abs(result.account_results[1]["end_value"] - 43_000_000.0) < 1.0
    assert abs(result.combined_end_value - 43_000_000.0) < 1.0
    assert_invariants(result)


# ── L5c 금종세 ISA 풍차중단 (2-4): 종합과세 대상이면 풍차 정지·기존 ISA 무한유지 ──

def _l5c_accounts(end_date="2029-01-01"):
    isa = _loop_account("AAA", initial=20_000_000.0, account_type="ISA",
                        start_date="2020-01-01", end_date=end_date, isa_renewal=True)
    broker = _loop_account("AAA", initial=0.0, account_type="위탁",
                           start_date="2020-01-01", end_date=end_date)
    policy = DistributionPolicy(destinations=[
        DistributionDestination(account_id=0), DistributionDestination(account_id=1),
    ])
    return isa, broker, policy


def test_l5c_comprehensive_blocks_then_resumes():
    """수동 오버라이드 2022 대상 → 2023 만기 풍차 정지(기존 ISA 유지),
    직전 3년이 비대상으로 바뀌는 2026 만기엔 풍차 재개(롤링 재평가).

    ∴ 만기 1회(2026)만 발생(L5b는 2회). 세금 OFF, ×2/사이클, 초기 2천만:
      2020~2025 ISA 보유(200,000주@100) → 2026-01(@400) 가치 8천만 →
      재가입 2천만 + 위탁 6천만(150,000주@400) → 2028 종료 ISA 4천만/위탁 1.2억.
    """
    price_data = _multi_cycle_x2("AAA")
    dates = list(price_data["AAA"].index)
    isa, broker, policy = _l5c_accounts()
    result = MultiAccountSimulationLoop(transfers_enabled=True).run(
        [isa, broker], price_data, dates, tax_enabled=False, distribution_policy=policy,
        manual_comprehensive_years={2022},
    )
    maturities = [t for t in result.transfer_log if t.get("type") == "maturity"]
    assert len(maturities) == 1
    assert maturities[0]["date"].startswith("2026")
    assert abs(result.account_results[0]["end_value"] - 40_000_000.0) < 1.0
    assert abs(result.account_results[1]["end_value"] - 120_000_000.0) < 1.0
    assert abs(result.combined_end_value - 160_000_000.0) < 1.0
    assert_invariants(result)


def test_l5c_always_comprehensive_holds_forever():
    """경계(무한유지): 매 만기창에 대상연도 존재 → 풍차 0회, ISA 9년 통째 보유.

    수동 {2022, 2025}: 2023 만기(2022 대상)·2026 만기(2025 대상) 모두 정지.
      ISA 200,000주@100 → 종료 @800 = 1.6억. 위탁 0.
    """
    price_data = _multi_cycle_x2("AAA")
    dates = list(price_data["AAA"].index)
    isa, broker, policy = _l5c_accounts()
    result = MultiAccountSimulationLoop(transfers_enabled=True).run(
        [isa, broker], price_data, dates, tax_enabled=False, distribution_policy=policy,
        manual_comprehensive_years={2022, 2025},
    )
    maturities = [t for t in result.transfer_log if t.get("type") == "maturity"]
    assert len(maturities) == 0
    assert abs(result.account_results[0]["end_value"] - 160_000_000.0) < 1.0
    assert abs(result.account_results[1]["end_value"] - 0.0) < 1.0
    # 무한유지 ISA 사이클 납입 = 초기 2천만(리셋 없음) ≤ 1억
    assert abs(result.account_results[0]["cycle_contribution"] - 20_000_000.0) < 1.0
    assert_invariants(result)


def test_l5c_held_isa_total_limit_reroutes():
    """무한유지 중 1억 한도 도달 → 추가납입 0 → 2-1 리라우팅(위탁).

    풍차 정지(수동 2022) + 월납입 5백만(연 6천만, 연한도 2천만 binding), 플랫:
      5년간 ISA 2천만/년 누적 → 1억(총한도). 매년 초과분 위탁.
      6년차 총한도 도달 → 전액(6천만) 위탁.
      ∴ ISA 1억 / 위탁 = 5×4천만 + 6천만 = 2.6억. 만기 0회(정지).
    """
    price_data = {"AAA": _price_frame("2020-01-01", "2025-12-31", 100.0)}
    dates = list(price_data["AAA"].index)
    isa = _loop_account("AAA", initial=0.0, monthly=5_000_000.0, account_type="ISA",
                        start_date="2020-01-01", end_date="2026-01-01", isa_renewal=True)
    broker = _loop_account("AAA", initial=0.0, account_type="위탁",
                           start_date="2020-01-01", end_date="2026-01-01")
    policy = DistributionPolicy(destinations=[
        DistributionDestination(account_id=0), DistributionDestination(account_id=1),
    ])
    result = MultiAccountSimulationLoop(transfers_enabled=True).run(
        [isa, broker], price_data, dates, tax_enabled=False, distribution_policy=policy,
        manual_comprehensive_years={2022},
    )
    maturities = [t for t in result.transfer_log if t.get("type") == "maturity"]
    assert len(maturities) == 0
    assert abs(result.account_results[0]["end_value"] - 100_000_000.0) < 1.0
    assert abs(result.account_results[1]["end_value"] - 260_000_000.0) < 1.0
    assert_invariants(result, expected_total_in=360_000_000.0, flat_price=True)


def test_l5c_live_dividend_triggers_comprehensive():
    """세금 ON 라이브 판정: 위탁 배당 gross 3천만(2022) → 공유세션이 2022 종합과세 판정
    → 2023 만기 풍차 정지. comprehensive_years에 2022 포함(멀티배선 검증).

    위탁 3억@100=3,000,000주, 2022-06-01 배당 10/주 = gross 3천만(>2천만).
    ISA(AAA 플랫, 배당0)는 세션에 미가산. 4년 sim(2020~2023), 만기 후보 2023 1회 정지.
    """
    div_ticker = _price_frame("2020-01-01", "2023-12-31", 100.0,
                              dividend_date="2022-06-01", dividend=10.0)
    isa_ticker = _price_frame("2020-01-01", "2023-12-31", 100.0)
    price_data = {"458730": div_ticker, "AAA": isa_ticker}
    dates = sorted(set(div_ticker.index) | set(isa_ticker.index))
    isa = _loop_account("AAA", initial=10_000_000.0, account_type="ISA",
                        start_date="2020-01-01", end_date="2024-01-01", isa_renewal=True)
    broker = _loop_account("458730", initial=300_000_000.0, account_type="위탁",
                           start_date="2020-01-01", end_date="2024-01-01")
    policy = DistributionPolicy(destinations=[
        DistributionDestination(account_id=0), DistributionDestination(account_id=1),
    ])
    result = MultiAccountSimulationLoop(transfers_enabled=True).run(
        [isa, broker], price_data, dates, tax_enabled=True,
        user_settings={"earned_income": 0, "age": 40},
        distribution_policy=policy,
    )
    # 공유세션이 위탁 배당 3천만을 2022 금융소득으로 집계 → 종합과세 대상
    assert 2022 in result.comprehensive_years
    assert result.financial_income_by_year.get(2022, 0) >= 30_000_000.0 - 1.0
    # 2023 만기 풍차 정지(기존 ISA 유지) → 만기 0회
    maturities = [t for t in result.transfer_log if t.get("type") == "maturity"]
    assert len(maturities) == 0
    # ISA 플랫·수익0 보유 → 청산세 0, 종료 1천만
    assert abs(result.account_results[0]["end_value"] - 10_000_000.0) < 1.0
    assert_invariants(result)


# ── L8 연 납입 세액공제 (G4): 매년 연금/IRP 납입 환급 ──

def _two_year_flat(code="AAA"):
    return {code: _price_frame("2020-01-01", "2021-12-31", 100.0)}


def test_l8_annual_deduction_normal():
    """정상경로: 연금 600만 + IRP 300만/년·저소득(16.5%) → 환급 900만×16.5%=148.5만/년.

    2년(2020·2021 각 완납) → 총 297만. 세금 ON, 재투자 OFF.
    """
    price_data = _two_year_flat()
    dates = list(price_data["AAA"].index)
    pension = _loop_account("AAA", initial=0.0, monthly=500_000.0, account_type="연금저축",
                            start_date="2020-01-01", end_date="2022-01-01")
    irp = _loop_account("AAA", initial=0.0, monthly=250_000.0, account_type="IRP",
                        start_date="2020-01-01", end_date="2022-01-01")
    result = MultiAccountSimulationLoop(transfers_enabled=True).run(
        [pension, irp], price_data, dates, tax_enabled=True,
        user_settings={"earned_income": 50_000_000, "age": 40},
    )
    assert abs(result.annual_deduction_credit - 2_970_000.0) < 1.0
    assert_invariants(result)


def test_l8_pension_only_cap_and_high_income():
    """경계: 연금 단독 1200만(600만 한도 cap) + 고소득 13.2% → 600만×13.2%=79.2만/년.

    2년 → 158.4만. IRP 없음.
    """
    price_data = _two_year_flat()
    dates = list(price_data["AAA"].index)
    pension = _loop_account("AAA", initial=0.0, monthly=1_000_000.0, account_type="연금저축",
                            start_date="2020-01-01", end_date="2022-01-01")
    result = MultiAccountSimulationLoop(transfers_enabled=True).run(
        [pension], price_data, dates, tax_enabled=True,
        user_settings={"earned_income": 70_000_000, "age": 40},
    )
    assert abs(result.annual_deduction_credit - 1_584_000.0) < 1.0
    assert_invariants(result)


def test_l8_combined_900_cap():
    """경계: 연금600+IRP600 = 합산 1200만 → 900만 합산 한도 cap. 저소득 16.5%.

    환급 900만×16.5%=148.5만/년 × 2 = 297만.
    """
    price_data = _two_year_flat()
    dates = list(price_data["AAA"].index)
    pension = _loop_account("AAA", initial=0.0, monthly=500_000.0, account_type="연금저축",
                            start_date="2020-01-01", end_date="2022-01-01")
    irp = _loop_account("AAA", initial=0.0, monthly=500_000.0, account_type="IRP",
                        start_date="2020-01-01", end_date="2022-01-01")
    result = MultiAccountSimulationLoop(transfers_enabled=True).run(
        [pension, irp], price_data, dates, tax_enabled=True,
        user_settings={"earned_income": 50_000_000, "age": 40},
    )
    assert abs(result.annual_deduction_credit - 2_970_000.0) < 1.0
    assert_invariants(result)


def test_l8_no_pension_zero_credit():
    """경계: 연금/IRP 납입 없으면(위탁만) 연납입 공제 0."""
    price_data = _two_year_flat()
    dates = list(price_data["AAA"].index)
    broker = _loop_account("AAA", initial=10_000_000.0, monthly=0.0, account_type="위탁",
                           start_date="2020-01-01", end_date="2022-01-01")
    result = MultiAccountSimulationLoop(transfers_enabled=True).run(
        [broker], price_data, dates, tax_enabled=True,
        user_settings={"earned_income": 50_000_000, "age": 40},
    )
    assert abs(result.annual_deduction_credit - 0.0) < 1.0
    assert_invariants(result)


def test_l8_reinvest_routes_through_policy():
    """L8-tax: 환급금 재투자 = 분배 정책 cascade. 직전 해분만 재투입(마지막 해 보고만).

    연금600+IRP300·저소득→148.5만/년. 정책 [위탁]. 재투자 ON:
      2020 환급 148.5만 → 2021 연경계서 위탁 재투입(플랫 → 위탁 종료 148.5만).
      2021 환급 148.5만 → 최종정산(보고만, 재투입 X).
      ∴ annual_deduction_credit 297만, credit_reinvest 1회, 위탁 종료 148.5만.
    """
    price_data = _two_year_flat()
    dates = list(price_data["AAA"].index)
    pension = _loop_account("AAA", initial=0.0, monthly=500_000.0, account_type="연금저축",
                            start_date="2020-01-01", end_date="2022-01-01")
    irp = _loop_account("AAA", initial=0.0, monthly=250_000.0, account_type="IRP",
                        start_date="2020-01-01", end_date="2022-01-01")
    broker = _loop_account("AAA", initial=0.0, monthly=0.0, account_type="위탁",
                           start_date="2020-01-01", end_date="2022-01-01")
    policy = DistributionPolicy(destinations=[DistributionDestination(account_id=2)])  # 위탁
    result = MultiAccountSimulationLoop(transfers_enabled=True).run(
        [pension, irp, broker], price_data, dates, tax_enabled=True,
        user_settings={"earned_income": 50_000_000, "age": 40},
        distribution_policy=policy, reinvest_tax_credit=True,
    )
    assert abs(result.annual_deduction_credit - 2_970_000.0) < 1.0
    reinvests = [t for t in result.transfer_log if t.get("type") == "credit_reinvest"]
    assert len(reinvests) == 1
    assert reinvests[0]["kind"] == "annual_deduction"
    assert abs(reinvests[0]["amount"] - 1_485_000.0) < 1.0
    assert abs(result.account_results[2]["end_value"] - 1_485_000.0) < 1.0
    assert_invariants(result)


# ── L9 logic/analyzer 관통 (B1): 엔진 G2 결과가 analyzer 결과로 정확히 도달 ──

from calculator_logic import _normalize_multi_accounts


def test_l9_analyzer_maturity_surfaced():
    """analyzer 관통: ISA 풍차 만기 결과가 cases에 정확히 surfacing.

    L5 정상경로(초기1천만 ×4 만기→재가입2천만+위탁2천만)를 analyzer 단일 윈도우로 재현.
    """
    provider = _provider_from_frames(_grow_then_flat("AAA", mult=4.0, flat_end="2024-01-01"))
    accounts = [
        _account("AAA", initial=10_000_000.0, account_type="ISA", isa_renewal=True),
        _account("AAA", initial=0.0, account_type="위탁"),
    ]
    policy = DistributionPolicy(destinations=[
        DistributionDestination(account_id=0), DistributionDestination(account_id=1),
    ])
    analyzer = MultiAccountAnalyzer(
        portfolio_engine=None, accounts=accounts,
        data_start="2020-01-01", data_end="2024-01-01",
        accumulation_years=4, step_months=12, tax_enabled=False,
        price_provider=provider, transfers_enabled=True, distribution_policy=policy,
    )
    result = analyzer.run()
    assert result["cases_count"] == 1
    case = result["cases"][0]
    maturities = [t for t in case["transfer_log"] if t.get("type") == "maturity"]
    assert len(maturities) == 1
    assert abs(case["accounts"][0]["end_value"] - 20_000_000.0) < 1.0
    assert abs(case["accounts"][1]["end_value"] - 20_000_000.0) < 1.0
    assert abs(case["end_value"] - 40_000_000.0) < 1.0


def test_l9_analyzer_credit_and_comprehensive_surfaced():
    """analyzer 관통(세금ON): G4 연납입공제·금종세 수동연도가 cases에 정확히 surfacing.

    연금600+IRP300·저소득→환급 148.5만/년 × 2년 = 297만. manual {2020} → 종합과세연도 포함.
    """
    provider = _provider_from_frames(
        {"AAA": _price_frame("2020-01-01", "2022-01-01", 100.0)}
    )
    accounts = [
        _account("AAA", initial=0.0, monthly=500_000.0, account_type="연금저축"),
        _account("AAA", initial=0.0, monthly=250_000.0, account_type="IRP"),
    ]
    analyzer = MultiAccountAnalyzer(
        portfolio_engine=None, accounts=accounts,
        data_start="2020-01-01", data_end="2022-01-01",
        accumulation_years=2, step_months=12, tax_enabled=True,
        user_settings={"earned_income": 50_000_000, "age": 40},
        price_provider=provider, transfers_enabled=True,
        manual_comprehensive_years={2020},
    )
    result = analyzer.run()
    case = result["cases"][0]
    assert abs(case["annual_deduction_credit"] - 2_970_000.0) < 1.0
    assert 2020 in case["comprehensive_years"]


def test_l9_g1_regression_no_transfers():
    """경계: 정책無·풍차無 → transfers OFF(G1 동일). G2 결과 필드 비어있음."""
    provider = _provider_from_frames(
        {"AAA": _price_frame("2020-01-01", "2022-01-01", 100.0)}
    )
    accounts = [_account("AAA", initial=1_000.0), _account("AAA", initial=2_000.0)]
    analyzer = MultiAccountAnalyzer(
        portfolio_engine=None, accounts=accounts,
        data_start="2020-01-01", data_end="2022-01-01",
        accumulation_years=2, step_months=12, tax_enabled=False,
        price_provider=provider,  # transfers_enabled 기본 False
    )
    result = analyzer.run()
    case = result["cases"][0]
    assert case["transfer_log"] == []
    assert case["comprehensive_years"] == []
    assert case["annual_deduction_credit"] == 0.0
    # 합산 = 초기자본 합(플랫, 무납입) → G1 동작
    assert abs(case["end_value"] - 3_000.0) < 1.0


def test_l9_normalize_reads_isa_renewal():
    """calculator_logic 정규화: 계좌별 isa_renewal 독해."""
    body = {
        "accounts": [
            {"type": "ISA", "initial_capital": 0, "monthly_contribution": 0,
             "tickers": [{"code": "AAA", "weight": 1.0}], "isa_renewal": True},
            {"type": "위탁", "initial_capital": 0, "monthly_contribution": 0,
             "tickers": [{"code": "BBB", "weight": 1.0}]},
        ]
    }
    accounts = _normalize_multi_accounts(body)
    assert accounts[0]["isa_renewal"] is True
    assert accounts[1]["isa_renewal"] is False


def test_l9_pension_transfers_equivalence():
    """회귀 가드: 한도 내 연금/IRP는 transfers ON/OFF 종료값 동일.

    (공제는 별도 보고이며 reinvest OFF면 포트폴리오 미주입 → 계좌 종료값 불변)
    → calculator_logic이 순수 연금/IRP에 transfers를 켜도 안전함을 보장.
    """
    price_data = _two_year_flat()
    dates = list(price_data["AAA"].index)

    def mk():
        return [
            _loop_account("AAA", initial=0.0, monthly=500_000.0, account_type="연금저축",
                          start_date="2020-01-01", end_date="2022-01-01"),
            _loop_account("AAA", initial=0.0, monthly=250_000.0, account_type="IRP",
                          start_date="2020-01-01", end_date="2022-01-01"),
        ]

    off = MultiAccountSimulationLoop(transfers_enabled=False).run(
        mk(), price_data, dates, tax_enabled=True,
        user_settings={"earned_income": 50_000_000, "age": 40},
    )
    on = MultiAccountSimulationLoop(transfers_enabled=True).run(
        mk(), price_data, dates, tax_enabled=True,
        user_settings={"earned_income": 50_000_000, "age": 40},
    )
    for a_off, a_on in zip(off.account_results, on.account_results):
        assert abs(a_off["end_value"] - a_on["end_value"]) < 1.0
    # transfers ON에서만 연납입공제 산출(297만), OFF는 0
    assert abs(on.annual_deduction_credit - 2_970_000.0) < 1.0
    assert abs(off.annual_deduction_credit - 0.0) < 1.0


def test_b2_g2_result_json_serializable():
    """B2: analyzer가 내는 G2 결과 필드가 JSON 직렬화 가능(API jsonify 안전).

    과거 numpy.bool_/타입 누수로 'not JSON serializable' 버그 전례 → 가드.
    """
    import json
    provider = _provider_from_frames(_grow_then_flat("AAA", mult=4.0, flat_end="2024-01-01"))
    accounts = [
        _account("AAA", initial=10_000_000.0, account_type="ISA", isa_renewal=True),
        _account("AAA", initial=0.0, account_type="위탁"),
    ]
    policy = DistributionPolicy(destinations=[
        DistributionDestination(account_id=0), DistributionDestination(account_id=1),
    ])
    analyzer = MultiAccountAnalyzer(
        portfolio_engine=None, accounts=accounts,
        data_start="2020-01-01", data_end="2024-01-01",
        accumulation_years=4, step_months=12, tax_enabled=True,
        user_settings={"earned_income": 50_000_000, "age": 40},
        price_provider=provider, transfers_enabled=True, distribution_policy=policy,
        manual_comprehensive_years={2021},
    )
    result = analyzer.run()
    case = result["cases"][0]
    # 응답에 실리는 G2 필드를 그대로 직렬화 (예외 없어야 함)
    payload = {
        "transfer_log": case["transfer_log"],
        "comprehensive_years": case["comprehensive_years"],
        "annual_deduction_credit": case["annual_deduction_credit"],
        "pension_transfer_credit": case["pension_transfer_credit"],
    }
    s = json.dumps(payload)  # raises if non-serializable
    assert "transfer_log" in s
    assert 2021 in case["comprehensive_years"]
