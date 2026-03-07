import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from modules.portfolio_engine import PortfolioEngine
from modules.rebalance.periodic import PeriodicRebalance


def main():

    print("\n====================================")
    print("Weight Drift Test")
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

    tolerance = 0.05

    errors = []

    prev_month = None

    for i, row in history.iterrows():

        date = row["date"]
        month = date.month

        if prev_month is None:
            prev_month = month
            continue

        # 월이 바뀌면 rebalance 직후
        if month != prev_month:

            qqq_weight = row["QQQ_weight"]
            tlt_weight = row["TLT_weight"]

            if abs(qqq_weight - 0.6) > tolerance:
                errors.append(("QQQ", date, qqq_weight))

            if abs(tlt_weight - 0.4) > tolerance:
                errors.append(("TLT", date, tlt_weight))

        prev_month = month

    if len(errors) == 0:
        print("✅ Weight rebalance PASSED")
    else:
        print("❌ Weight rebalance FAILED")
        print(errors[:5])

    last = history.iloc[-1]

    print("\nFinal Weights")
    print("QQQ:", round(last["QQQ_weight"], 4))
    print("TLT:", round(last["TLT_weight"], 4))


if __name__ == "__main__":
    main()