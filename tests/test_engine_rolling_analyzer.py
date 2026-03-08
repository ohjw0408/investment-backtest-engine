import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from modules.portfolio_engine import PortfolioEngine
from modules.rebalance.periodic import PeriodicRebalance
from modules.analyzer.engine_rolling_analyzer import EngineRollingAnalyzer


def run_test(dividend_mode):

    engine = PortfolioEngine()

    weights = {
        "SCHD": 0.6,
        "TLT": 0.4
    }

    strategy = PeriodicRebalance(
        target_weights=weights,
        rebalance_frequency="monthly"
    )

    analyzer = EngineRollingAnalyzer(

        engine=engine,
        strategy=strategy,

        tickers=["SCHD", "TLT"],

        start_date="2010-01-01",
        end_date="2024-01-01",

        horizon_years=5,

        initial_capital=10_000_000,
        monthly_contribution=0,

        dividend_mode=dividend_mode
    )

    result = analyzer.run()

    return result


def main():

    print("\n========== Engine Rolling Analyzer Test ==========")

    # ---------------------------------------------
    # reinvest
    # ---------------------------------------------

    reinvest = run_test("reinvest")

    print("\n--- Reinvest Mode ---")

    print("Scenarios:", reinvest["scenario_count"])

    print("Wealth sample:")
    print(reinvest["wealth_distribution"][:10])

    print("Dividend sample:")
    print(reinvest["dividend_distribution"][:10])

    # ---------------------------------------------
    # cash
    # ---------------------------------------------

    cash = run_test("cash")

    print("\n--- Cash Mode ---")

    print("Scenarios:", cash["scenario_count"])

    print("Wealth sample:")
    print(cash["wealth_distribution"][:10])

    print("Dividend sample:")
    print(cash["dividend_distribution"][:10])

    # ---------------------------------------------
    # withdraw
    # ---------------------------------------------

    withdraw = run_test("withdraw")

    print("\n--- Withdraw Mode ---")

    print("Scenarios:", withdraw["scenario_count"])

    print("Wealth sample:")
    print(withdraw["wealth_distribution"][:10])

    print("Dividend sample:")
    print(withdraw["dividend_distribution"][:10])

    # ---------------------------------------------
    # 비교
    # ---------------------------------------------

    print("\n========== Comparison ==========")

    reinvest_mean = reinvest["wealth_distribution"].mean()
    cash_mean = cash["wealth_distribution"].mean()
    withdraw_mean = withdraw["wealth_distribution"].mean()

    print("\nAverage Wealth Multiple")

    print("Reinvest :", round(reinvest_mean, 3))
    print("Cash     :", round(cash_mean, 3))
    print("Withdraw :", round(withdraw_mean, 3))

    print("\nExpected relationship:")

    print("Reinvest >= Cash >= Withdraw")

    print("\nTest completed")


if __name__ == "__main__":
    main()