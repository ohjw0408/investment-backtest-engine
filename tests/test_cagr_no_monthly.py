import math

import pandas as pd

from modules.retirement.accumulation_analyzer import AccumulationAnalyzer
from modules.retirement.multi_account_analyzer import calc_metrics_from_history


def _history(start_value=1_000_000_000, end_value=1_200_000_000):
    return pd.DataFrame(
        [
            {
                "date": pd.Timestamp("2020-01-01"),
                "portfolio_value": start_value,
                "cash_flow": start_value,
            },
            {
                "date": pd.Timestamp("2027-01-01"),
                "portfolio_value": end_value,
                "cash_flow": 0,
            },
        ]
    )


def test_single_account_cagr_uses_simple_annual_rate_without_monthly_flows():
    analyzer = AccumulationAnalyzer.__new__(AccumulationAnalyzer)
    analyzer.initial_capital = 1_000_000_000
    analyzer.monthly_contribution = 0
    analyzer.div_start = None

    metrics = analyzer._calc_metrics(_history(), years=7)

    expected = (1.2 ** (1 / 7)) - 1
    assert math.isclose(metrics["cagr"], expected, rel_tol=1e-9)
    assert metrics["cagr"] < 0.03


def test_multi_account_cagr_uses_simple_annual_rate_without_monthly_flows():
    metrics = calc_metrics_from_history(
        _history(),
        years=7,
        initial_capital=1_000_000_000,
        monthly_contribution=0,
        div_start=None,
    )

    expected = (1.2 ** (1 / 7)) - 1
    assert math.isclose(metrics["cagr"], expected, rel_tol=1e-9)
    assert metrics["cagr"] < 0.03
