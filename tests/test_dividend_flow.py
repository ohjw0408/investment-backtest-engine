import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from modules.portfolio_engine import PortfolioEngine
from modules.rebalance.periodic import PeriodicRebalance


def main():

    print("\n====================================")
    print("Dividend Flow Test")
    print("====================================")

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

        start_date="2018-01-01",
        end_date="2020-12-31",

        initial_capital=1_000_000,

        strategy=strategy
    )

    history = result["history"]

    dividend_events = history[history["dividend_income"] > 0]

    print("\nDividend Events Preview")
    print(dividend_events[["date", "dividend_income"]].head())

    total_dividend = history["dividend_income"].sum()

    print("\nTotal Dividend Received:", round(total_dividend, 2))

    if total_dividend > 0:
        print("✅ Dividend tracking PASSED")
    else:
        print("❌ Dividend tracking FAILED")


if __name__ == "__main__":
    main()