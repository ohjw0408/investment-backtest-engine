import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

import pandas as pd

from modules.portfolio_engine import PortfolioEngine
from modules.rebalance.periodic import PeriodicRebalance


def run_simulation(dividend_mode, target_weights, withdrawal=0):

    engine = PortfolioEngine()

    strategy = PeriodicRebalance(
        target_weights=target_weights,
        rebalance_frequency="monthly"
    )

    result = engine.run_simulation(

        tickers=["QQQ", "TLT"],

        start_date="2018-01-01",

        end_date="2020-12-31",

        initial_capital=1_000_000,

        strategy=strategy,

        dividend_mode=dividend_mode,

        withdrawal_amount=withdrawal
    )

    return result["history"]


def test_dividend_reinvest():

    print("\n==============================")
    print("TEST 1: DIVIDEND REINVEST")
    print("==============================")

    history = run_simulation(

        dividend_mode="reinvest",

        target_weights={
            "QQQ": 0.6,
            "TLT": 0.4
        }
    )

    cash_mean = history["cash"].mean()

    print("Mean Cash:", cash_mean)

    if cash_mean < 500:
        print("PASS: reinvest keeps cash low")
    else:
        print("FAIL: reinvest not investing dividends")


def test_dividend_cash():

    print("\n==============================")
    print("TEST 2: DIVIDEND CASH MODE")
    print("==============================")

    history = run_simulation(

        dividend_mode="cash",

        target_weights={
            "QQQ": 0.6,
            "TLT": 0.4
        }
    )

    cash_mean = history["cash"].mean()

    print("Mean Cash:", cash_mean)

    if cash_mean > 5000:
        print("PASS: cash mode accumulating dividends")
    else:
        print("FAIL: cash mode not working")


def test_dividend_withdraw():

    print("\n==============================")
    print("TEST 3: DIVIDEND WITHDRAW")
    print("==============================")

    history = run_simulation(

        dividend_mode="withdraw",

        target_weights={
            "QQQ": 0.6,
            "TLT": 0.4
        }
    )

    dividend_total = history["dividend_income"].sum()

    cash_mean = history["cash"].mean()

    print("Dividend Total:", dividend_total)
    print("Mean Cash:", cash_mean)

    if cash_mean < 500:
        print("PASS: withdraw mode removing dividends")
    else:
        print("FAIL: withdraw mode keeping dividend cash")


def test_cash_target():

    print("\n==============================")
    print("TEST 4: CASH TARGET")
    print("==============================")

    history = run_simulation(

        dividend_mode="reinvest",

        target_weights={
            "QQQ": 0.55,
            "TLT": 0.35,
            "CASH": 0.10
        }
    )

    weights = history["cash"] / history["portfolio_value"]

    mean_cash_weight = weights.mean()

    print("Mean Cash Weight:", mean_cash_weight)

    if 0.08 < mean_cash_weight < 0.12:
        print("PASS: cash target maintained")
    else:
        print("FAIL: cash target not respected")


def test_rebalance_with_cash():

    print("\n==============================")
    print("TEST 5: REBALANCE + CASH")
    print("==============================")

    history = run_simulation(

        dividend_mode="reinvest",

        target_weights={
            "QQQ": 0.5,
            "TLT": 0.4,
            "CASH": 0.1
        }
    )

    qqq_weight = history["QQQ_weight"].iloc[-1]

    print("Final QQQ Weight:", qqq_weight)

    if 0.45 < qqq_weight < 0.55:
        print("PASS: rebalance working")
    else:
        print("FAIL: rebalance broken")


def test_withdrawal():

    print("\n==============================")
    print("TEST 6: WITHDRAWAL")
    print("==============================")

    history = run_simulation(

        dividend_mode="reinvest",

        target_weights={
            "QQQ": 0.6,
            "TLT": 0.4
        },

        withdrawal=2000
    )

    start_value = history["portfolio_value"].iloc[0]

    end_value = history["portfolio_value"].iloc[-1]

    print("Start:", start_value)
    print("End:", end_value)

    if end_value < start_value * 2:
        print("PASS: withdrawal affecting portfolio")
    else:
        print("FAIL: withdrawal not applied")


def main():

    print("\n=======================================")
    print("CASH / DIVIDEND ENGINE INTEGRATION TEST")
    print("=======================================\n")

    test_dividend_reinvest()
    test_dividend_cash()
    test_dividend_withdraw()
    test_cash_target()
    test_rebalance_with_cash()
    test_withdrawal()

    print("\n=======================================")
    print("ENGINE CASH TEST COMPLETE")
    print("=======================================\n")


if __name__ == "__main__":
    main()