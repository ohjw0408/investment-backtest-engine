import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from modules.portfolio_engine import PortfolioEngine
from modules.rebalance.periodic import PeriodicRebalance
from modules.analyzer.wealth_projection_analyzer import WealthProjectionAnalyzer
from modules.analyzer.rolling_scenario_analyzer import RollingScenarioAnalyzer


def main():

    print("\n========== Wealth Projection REAL DATA Test ==========")

    # -----------------------------------------
    # Engine
    # -----------------------------------------

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

        start_date="2004-01-01",
        end_date="2024-01-01",

        initial_capital=1_000_000,

        strategy=strategy
    )

    history = result["history"]

    # -----------------------------------------
    # Rolling Scenario Analyzer
    # -----------------------------------------

    rolling = RollingScenarioAnalyzer(years=10)

    rolling_result = rolling.analyze(history)


    print("\nType:", type(rolling_result))

    # wealth distribution 추출
    distribution = rolling_result["wealth_distribution"]

    print("\nDistribution sample (first 10):")
    print(distribution[:10])

    print("\nTotal scenarios:", len(distribution))

    # -----------------------------------------
    # Wealth Projection Analyzer
    # -----------------------------------------

    analyzer = WealthProjectionAnalyzer()

    stats = analyzer.analyze(distribution)

    print("\nSummary")
    print(stats["summary"])

    print("\nPercentiles")
    print(stats["percentiles"])

    print("\nExtremes")
    print(stats["extremes"])

    print("\nShape")
    print(stats["shape"])

    print("\nTest completed")


if __name__ == "__main__":
    main()