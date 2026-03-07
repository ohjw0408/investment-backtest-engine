import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from modules.portfolio_engine import PortfolioEngine
from modules.rebalance.periodic import PeriodicRebalance


def run_simulation(
    title,
    tickers,
    weights,
    monthly_contribution,
):

    print("\n====================================")
    print(title)
    print("====================================")

    engine = PortfolioEngine()

    strategy = PeriodicRebalance(
        target_weights=weights,
        rebalance_frequency="monthly"
    )

    result = engine.run_simulation(

        tickers=tickers,

        start_date="2018-01-01",

        end_date="2020-12-31",

        initial_capital=1_000_000,

        monthly_contribution=monthly_contribution,

        strategy=strategy
    )

    history = result["history"]

    final_value = history["portfolio_value"].iloc[-1]

    print("Final Portfolio Value:", round(final_value, 2))

    return history


def test1_dca_only():

    history = run_simulation(

        "TEST 1: DCA ONLY",

        ["QQQ"],

        {"QQQ": 1.0},

        monthly_contribution=1_000_000
    )

    if history["portfolio_value"].iloc[-1] > history["portfolio_value"].iloc[0]:
        print("✔ PASS: DCA growth detected")
    else:
        print("❌ FAIL: DCA not applied")


def test2_dca_weight_balance():

    history = run_simulation(

        "TEST 2: DCA WEIGHT BALANCE",

        ["QQQ", "TLT"],

        {
            "QQQ": 0.5,
            "TLT": 0.5
        },

        monthly_contribution=1_000_000
    )

    weights = history[["QQQ_weight", "TLT_weight"]].iloc[-1]

    if abs(weights["QQQ_weight"] - 0.5) < 0.1:
        print("✔ PASS: weight balanced")
    else:
        print("❌ FAIL: weight imbalance")


def test3_dividend_plus_dca():

    history = run_simulation(

        "TEST 3: DIVIDEND + DCA",

        ["QQQ", "TLT"],

        {
            "QQQ": 0.6,
            "TLT": 0.4
        },

        monthly_contribution=500_000
    )

    dividend_total = history["dividend_income"].sum()

    print("Total Dividend:", round(dividend_total, 2))

    if dividend_total > 0:
        print("✔ PASS: dividend detected")
    else:
        print("❌ FAIL: dividend missing")


def test4_cash_drift():

    history = run_simulation(

        "TEST 4: CASH DRIFT",

        ["QQQ", "TLT"],

        {
            "QQQ": 0.6,
            "TLT": 0.4
        },

        monthly_contribution=1_000_000
    )

    cash_stats = history["cash"].describe()

    print(cash_stats)

    if cash_stats["max"] < 500000:
        print("✔ PASS: cash sweep working")
    else:
        print("❌ FAIL: cash accumulating")


def test5_rebalance_with_dca():

    history = run_simulation(

        "TEST 5: REBALANCE + DCA",

        ["QQQ", "TLT"],

        {
            "QQQ": 0.7,
            "TLT": 0.3
        },

        monthly_contribution=1_000_000
    )

    weights = history[["QQQ_weight", "TLT_weight"]].iloc[-1]

    print("Final Weights")
    print(weights)

    if abs(weights["QQQ_weight"] - 0.7) < 0.15:
        print("✔ PASS: rebalance working")
    else:
        print("❌ FAIL: rebalance broken")


def main():

    test1_dca_only()

    test2_dca_weight_balance()

    test3_dividend_plus_dca()

    test4_cash_drift()

    test5_rebalance_with_dca()

    print("\n====================================")
    print("DCA ENGINE TEST COMPLETE")
    print("====================================")


if __name__ == "__main__":
    main()