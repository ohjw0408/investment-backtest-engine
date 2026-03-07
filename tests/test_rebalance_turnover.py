import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from modules.portfolio_engine import PortfolioEngine
from modules.rebalance.periodic import PeriodicRebalance


def calculate_turnover(history):

    turnover = 0

    value_cols = [c for c in history.columns if c.endswith("_value") and c != "portfolio_value"]

    prev_values = None

    for i, row in history.iterrows():

        current_values = {c: row[c] for c in value_cols}

        if prev_values is not None:

            for c in value_cols:

                turnover += abs(current_values[c] - prev_values[c])

        prev_values = current_values

    return turnover


def run_simulation(strategy):

    engine = PortfolioEngine()

    result = engine.run_simulation(

        tickers=["QQQ", "TLT"],

        start_date="2018-01-01",
        end_date="2020-12-31",

        initial_capital=1_000_000,

        strategy=strategy

    )

    return result["history"]


def main():

    print("\n====================================")
    print("Rebalance Turnover Test")
    print("====================================")

    # -----------------------------
    # Rebalance 전략
    # -----------------------------

    rebalance_strategy = PeriodicRebalance(

        target_weights={
            "QQQ": 0.6,
            "TLT": 0.4
        },

        rebalance_frequency="monthly"

    )

    history_rebalance = run_simulation(rebalance_strategy)

    turnover_rebalance = calculate_turnover(history_rebalance)

    # -----------------------------
    # Buy & Hold 전략
    # -----------------------------

    history_hold = run_simulation(None)

    turnover_hold = calculate_turnover(history_hold)

    print("\nTurnover Comparison")

    print("Rebalance Turnover:", round(turnover_rebalance, 2))
    print("Buy & Hold Turnover:", round(turnover_hold, 2))

    if turnover_rebalance > turnover_hold:
        print("\n✅ Rebalance generates more trades (PASSED)")
    else:
        print("\n❌ Rebalance turnover test FAILED")


if __name__ == "__main__":
    main()