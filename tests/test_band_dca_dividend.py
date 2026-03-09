import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

import numpy as np

from modules.portfolio_engine import PortfolioEngine
from modules.rebalance.periodic import PeriodicRebalance
from modules.analyzer.engine_rolling_analyzer import EngineRollingAnalyzer


def main():

    print("\n========== FULL ENGINE TEST ==========")

    engine = PortfolioEngine()

    # ---------------------------------
    # 포트폴리오 설정
    # ---------------------------------

    weights = {
        "SCHD": 0.7,
        "QQQ": 0.3
    }

    strategy = PeriodicRebalance(

        target_weights=weights,

        rebalance_frequency="monthly",

        drift_threshold=0.05
    )

    # ---------------------------------
    # Rolling Analyzer
    # ---------------------------------

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
    terminal_dividend = result["terminal_dividend_distribution"]

    # ---------------------------------
    # 기본 출력
    # ---------------------------------

    print("\nScenarios:", result["scenario_count"])

    print("\nWealth sample:")
    print(wealth[:10])

    print("\nTerminal dividend sample:")
    print(terminal_dividend[:10])

    # ---------------------------------
    # Wealth statistics
    # ---------------------------------

    print("\n========== Wealth Statistics ==========")

    print("Average wealth:", np.mean(wealth))
    print("Median wealth:", np.median(wealth))
    print("Max wealth:", np.max(wealth))
    print("Min wealth:", np.min(wealth))

    # ---------------------------------
    # Dividend statistics
    # ---------------------------------

    print("\n========== Dividend Statistics ==========")

    print("Average terminal dividend:", np.mean(terminal_dividend))
    print("Median terminal dividend:", np.median(terminal_dividend))
    print("Max terminal dividend:", np.max(terminal_dividend))
    print("Min terminal dividend:", np.min(terminal_dividend))

    # ---------------------------------
    # Sanity check
    # ---------------------------------

    print("\n========== SANITY CHECK ==========")

    if np.mean(wealth) > 1:
        print("✔ DCA investment working")

    if np.mean(terminal_dividend) > 0:
        print("✔ Dividend generation working")

    if np.max(wealth) - np.min(wealth) > 0.2:
        print("✔ Rebalancing / market variance detected")

    print("\nTest completed")


if __name__ == "__main__":
    main()