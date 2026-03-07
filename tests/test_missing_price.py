import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from modules.portfolio_engine import PortfolioEngine
from modules.rebalance.periodic import PeriodicRebalance


def main():

    print("\n====================================")
    print("Missing Price Robustness Test")
    print("====================================")

    engine = PortfolioEngine()

    # 일부 ETF는 과거 데이터가 짧음
    tickers = [
        "QQQ",
        "TLT",
        "MTUM",   # launch later
        "USMV",   # launch later
    ]

    strategy = PeriodicRebalance(
        target_weights={
            "QQQ": 0.4,
            "TLT": 0.4,
            "MTUM": 0.1,
            "USMV": 0.1
        },
        rebalance_frequency="monthly"
    )

    try:

        result = engine.run_simulation(

            tickers=tickers,

            start_date="2005-01-01",   # 일부 ETF는 존재하지 않는 기간

            end_date="2020-12-31",

            initial_capital=1_000_000,

            strategy=strategy
        )

        history = result["history"]

        print("\nSimulation completed successfully")

        print("History rows:", len(history))

        if "portfolio_value" in history.columns:
            print("✅ Portfolio value computed")
        else:
            print("❌ Portfolio value missing")

    except Exception as e:

        print("❌ Engine crashed")
        print(e)


if __name__ == "__main__":
    main()