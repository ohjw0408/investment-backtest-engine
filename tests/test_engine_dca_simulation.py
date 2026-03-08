import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

import numpy as np

from modules.portfolio_engine import PortfolioEngine
from modules.analyzer.engine_rolling_analyzer import EngineRollingAnalyzer
from modules.rebalance.periodic import PeriodicRebalance


def run_test():

    engine = PortfolioEngine()

    strategy = PeriodicRebalance(
        target_weights={
            "SCHD": 0.6,
            "TLT": 0.4
        },
        rebalance_frequency="monthly"
    )

    analyzer = EngineRollingAnalyzer(

        engine=engine,

        tickers=["SCHD", "TLT"],

        start_date="2010-01-01",
        end_date="2024-01-01",

        horizon_years=5,

        initial_capital=0,
        monthly_contribution=1000,

        strategy=strategy,

        dividend_mode="reinvest"
    )

    result = analyzer.run()

    wealth = result["wealth_distribution"]
    dividend = result["dividend_distribution"]

    print("\n========== DCA Rolling Simulation Test ==========")

    print("\nScenario count:", len(wealth))

    print("\nWealth distribution sample:")
    print(wealth[:10])

    print("\nDividend distribution sample:")
    print(dividend[:10])

    print("\nAverage wealth multiple:", round(np.mean(wealth), 3))
    print("Median wealth multiple:", round(np.median(wealth), 3))

    print("\nMax wealth:", np.max(wealth))
    print("Min wealth:", np.min(wealth))

    print("\nTest completed")


def main():
    run_test()


if __name__ == "__main__":
    main()