import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

import pandas as pd
import numpy as np

from modules.portfolio_engine import PortfolioEngine
from modules.rebalance.periodic import PeriodicRebalance
from modules.analyzer.rolling_scenario_analyzer import RollingScenarioAnalyzer


# -------------------------------------------------
# synthetic history 생성
# -------------------------------------------------

def generate_fake_history(years=40):

    months = years * 12

    dates = pd.date_range("1980-01-31", periods=months, freq="ME")

    returns = np.random.normal(0.01, 0.04, size=months)

    value = 100
    values = []

    for r in returns:
        value *= (1 + r)
        values.append(value)

    df = pd.DataFrame({

        "date": dates,
        "portfolio_value": values,
        "dividend_income": np.random.uniform(0, 1, size=months)

    })

    return df


# -------------------------------------------------
# synthetic data 테스트
# -------------------------------------------------

def test_synthetic_distribution():

    history = generate_fake_history(40)

    analyzer = RollingScenarioAnalyzer(years=20)

    result = analyzer.analyze(history)

    wealth_dist = result["wealth_distribution"]

    monthly_rows = len(history)
    horizon = 20 * 12
    expected = monthly_rows - horizon

    print("\n================ Synthetic Test ================")

    print("Total Months:", monthly_rows)
    print("Horizon (months):", horizon)
    print("Expected Scenarios:", expected)
    print("Actual Scenarios:", len(wealth_dist))

    print("Median Wealth:", np.median(wealth_dist))
    print("Min Wealth:", np.min(wealth_dist))
    print("Max Wealth:", np.max(wealth_dist))

    assert len(wealth_dist) == expected


# -------------------------------------------------
# 실제 엔진 테스트
# -------------------------------------------------

def test_real_engine():

    engine = PortfolioEngine()

    strategy = PeriodicRebalance(

        target_weights={
            "QQQ": 0.6,
            "TLT": 0.4
        },

        rebalance_frequency="monthly"

    )

    result = engine.run_simulation(

        tickers=["QQQ", "TLT"],

        start_date="2003-01-01",
        end_date="2023-12-31",

        initial_capital=1_000_000,

        strategy=strategy

    )

    history = result["history"]

    analyzer = RollingScenarioAnalyzer(years=10)

    result = analyzer.analyze(history)

    wealth_dist = result["wealth_distribution"]

    df = history.copy()
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date")

    monthly_rows = len(df["portfolio_value"].resample("ME").last())
    horizon = 10 * 12
    expected = monthly_rows - horizon

    print("\n================ Real Market Test ================")

    print("Total Months:", monthly_rows)
    print("Horizon (months):", horizon)
    print("Expected Scenarios:", expected)
    print("Actual Scenarios:", len(wealth_dist))

    print("Median Wealth:", np.median(wealth_dist))
    print("Min Wealth:", np.min(wealth_dist))
    print("Max Wealth:", np.max(wealth_dist))

    assert len(wealth_dist) == expected


# -------------------------------------------------

if __name__ == "__main__":

    test_synthetic_distribution()
    test_real_engine()

    print("\nRolling Scenario Analyzer tests completed.")