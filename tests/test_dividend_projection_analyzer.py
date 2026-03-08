import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from modules.portfolio_engine import PortfolioEngine
from modules.rebalance.periodic import PeriodicRebalance
from modules.analyzer.rolling_scenario_analyzer import RollingScenarioAnalyzer
from modules.analyzer.dividend_projection_analyzer import DividendProjectionAnalyzer


def main():

    print("\n========== Dividend Projection REAL DATA Test ==========")

    # -----------------------------
    # Portfolio setup
    # -----------------------------

    weights = {
        "SCHD": 0.6,
        "TLT": 0.4
    }

    strategy = PeriodicRebalance(
        target_weights=weights,
        rebalance_frequency="monthly"
    )

    engine = PortfolioEngine()

    result = engine.run_simulation(

        tickers=["SCHD", "TLT"],

        start_date="2015-01-01",
        end_date="2024-01-01",

        strategy=strategy,

        initial_capital=10_000_000,

        dividend_mode="reinvest"
    )

    history = result["history"]

    # -----------------------------
    # Rolling Scenario
    # -----------------------------

    rolling = RollingScenarioAnalyzer(years=5)

    rolling_result = rolling.analyze(history)

    dividend_distribution = rolling_result["dividend_distribution"]

    print("\nDividend distribution sample (first 10):")

    for value in dividend_distribution[:10]:
        print(round(float(value), 2))

    print("\nTotal scenarios:", len(dividend_distribution))

    # -----------------------------
    # Dividend Projection Analyzer
    # -----------------------------

    analyzer = DividendProjectionAnalyzer()

    result = analyzer.analyze(dividend_distribution)

    print("\nSummary")
    print(result["summary"])

    print("\nPercentiles")
    print(result["percentiles"])

    print("\nExtremes")
    print(result["extremes"])

    print("\nShape")
    print(result["shape"])

    print("\nTest completed")


if __name__ == "__main__":
    main()