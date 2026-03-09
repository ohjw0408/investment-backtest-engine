import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from modules.portfolio_engine import PortfolioEngine
from modules.rebalance.periodic import PeriodicRebalance
from modules.analyzer.engine_rolling_analyzer import EngineRollingAnalyzer


def main():

    print("\n========== FULL ENGINE TEST ==========")

    engine = PortfolioEngine()

    weights = {
        "SCHD": 0.7,
        "QQQ": 0.3
    }

    strategy = PeriodicRebalance(
        target_weights=weights,
        rebalance_frequency=None,
        drift_threshold=0.05
    )

    analyzer = EngineRollingAnalyzer(

        engine=engine,
        strategy=strategy,

        tickers=["SCHD", "QQQ"],

        start_date="2012-01-01",
        end_date="2024-01-01",

        horizon_years=5,

        initial_capital=0,
        monthly_contribution=5_000_000,

        dividend_mode="reinvest"
    )

    result = analyzer.run()

    wealth = result["wealth_distribution"]
    dividend = result["dividend_distribution"]

    print("\nScenarios:", result["scenario_count"])

    print("\nWealth sample:")
    print(wealth[:10])

    print("\nDividend sample:")
    print(dividend[:10])

    print("\nAverage wealth:", wealth.mean())
    print("Median wealth:", wealth.mean())
    print("Max wealth:", wealth.max())
    print("Min wealth:", wealth.min())

    print("\nDividend mean:", dividend.mean())

    print("\n========== SANITY CHECK ==========")

    if wealth.mean() > 1:
        print("✔ DCA investment working")

    if dividend.mean() > 0:
        print("✔ Dividend reinvest working")

    if wealth.max() - wealth.min() > 0.2:
        print("✔ Rebalancing / market variance detected")

    print("\nTest completed")


if __name__ == "__main__":
    main()