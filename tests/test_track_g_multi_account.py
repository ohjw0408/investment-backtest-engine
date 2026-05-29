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
