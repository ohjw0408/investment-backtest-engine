import sys
from pathlib import Path

# 프로젝트 루트 추가
sys.path.append(str(Path(__file__).resolve().parents[1]))

from modules.portfolio_engine import PortfolioEngine
from modules.rebalance.periodic import PeriodicRebalance


def main():

    print("\n====================================")
    print("Portfolio Accounting Test")
    print("====================================")

    engine = PortfolioEngine()

    strategy = PeriodicRebalance(
        target_weights={
            "QQQ": 0.6,
            "TLT": 0.4
        }
    )

    result = engine.run_simulation(

        tickers=["QQQ", "TLT"],

        start_date="2018-01-01",
        end_date="2020-12-31",

        initial_capital=1_000_000,

        strategy=strategy

    )

    history = result["history"]

    errors = []

    for i, row in history.iterrows():

        portfolio_value = row["portfolio_value"]
        cash = row["cash"]

        asset_value = 0

        for col in history.columns:

            if col.endswith("_value") and col != "portfolio_value":
                asset_value += row[col]

        check_value = asset_value + cash

        diff = abs(portfolio_value - check_value)

        if diff > 1e-6:
            errors.append((i, portfolio_value, check_value))

    if len(errors) == 0:
        print("✅ Portfolio accounting PASSED")
    else:
        print("❌ Portfolio accounting FAILED")
        print(errors[:5])


if __name__ == "__main__":
    main()