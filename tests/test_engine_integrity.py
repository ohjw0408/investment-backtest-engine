import sys
from pathlib import Path

# 프로젝트 루트 경로 추가
sys.path.append(str(Path(__file__).resolve().parents[1]))

import pandas as pd

from modules.portfolio_engine import PortfolioEngine
from modules.analyzer.portfolio_analyzer import PortfolioAnalyzer
from modules.rebalance.periodic import PeriodicRebalance
from modules.price_loader import PriceLoader


def main():

    print("\n====================================")
    print("ENGINE INTEGRITY TEST")
    print("====================================")

    engine = PortfolioEngine()
    analyzer = PortfolioAnalyzer()
    loader = PriceLoader()

    tickers = ["QQQ", "TLT"]

    strategy = PeriodicRebalance(
        target_weights={
            "QQQ": 0.6,
            "TLT": 0.4,
        }
    )

    result = engine.run_simulation(
        tickers=tickers,
        start_date="2018-01-01",
        end_date="2020-12-31",
        initial_capital=1_000_000,
        strategy=strategy,
    )

    history = result["history"]

    print("\n===== Simulation Result =====")
    print(history.head())

    # -------------------------------------------------
    # 가격 데이터 다시 로드 (정확한 가격 검증용)
    # -------------------------------------------------

    price_data = {}

    for ticker in tickers:

        df = loader.get_price(
            ticker,
            "2018-01-01",
            "2020-12-31",
        )

        df["date"] = pd.to_datetime(df["date"])
        df = df.set_index("date")

        price_data[ticker] = df

    # -------------------------------------------------
    # TEST 1: CASH ALLOCATION
    # -------------------------------------------------

    print("\n-----------------------------------")
    print("TEST 1: CASH ALLOCATION")
    print("-----------------------------------")

    last_row = history.iloc[-1]
    last_date = last_row["date"]
    cash = last_row["cash"]

    prices = []

    for ticker in tickers:

        price = price_data[ticker].loc[last_date, "close"]
        prices.append(price)

    cheapest_price = min(prices)

    print("Final Cash:", cash)
    print("Cheapest Asset Price:", cheapest_price)

    if cash < cheapest_price:
        print("✔ PASS: Cash allocation correct")
    else:
        print("❌ FAIL: Cash allocation incomplete")

    # -------------------------------------------------
    # TEST 2: WEIGHT SUM
    # -------------------------------------------------

    print("\n-----------------------------------")
    print("TEST 2: WEIGHT SUM")
    print("-----------------------------------")

    weight_cols = [c for c in history.columns if "_weight" in c]

    weight_sum = history[weight_cols].sum(axis=1)

    print(weight_sum.head())

    if (abs(weight_sum - 1) < 0.01).all():
        print("✔ PASS: Weight sum valid")
    else:
        print("❌ FAIL: Weight sum error")

    # -------------------------------------------------
    # TEST 3: DIVIDEND FLOW
    # -------------------------------------------------

    print("\n-----------------------------------")
    print("TEST 3: DIVIDEND FLOW")
    print("-----------------------------------")

    dividends = history["dividend_income"]

    print("Total Dividend:", dividends.sum())

    if dividends.sum() > 0:
        print("✔ PASS: Dividend recorded")
    else:
        print("❌ FAIL: Dividend missing")

    # -------------------------------------------------
    # TEST 4: CASH DRIFT
    # -------------------------------------------------

    print("\n-----------------------------------")
    print("TEST 4: CASH DRIFT")
    print("-----------------------------------")

    cash_series = history["cash"]

    print(cash_series.describe())

    # 평균 cash가 너무 크면 allocator 문제
    if cash_series.mean() < 1000:
        print("✔ PASS: Cash drift controlled")
    else:
        print("❌ FAIL: Cash drift too large")

    # -------------------------------------------------
    # TEST 5: ANALYZER CONSISTENCY
    # -------------------------------------------------

    print("\n-----------------------------------")
    print("TEST 5: ANALYZER CONSISTENCY")
    print("-----------------------------------")

    analysis = analyzer.analyze(history)

    print("CAGR:", round(analysis["cagr"] * 100, 2), "%")
    print("MDD:", round(analysis["mdd"] * 100, 2), "%")
    print("Volatility:", round(analysis["volatility"] * 100, 2), "%")

    if analysis["mdd"] < 0 and analysis["volatility"] > 0:
        print("✔ PASS: Analyzer valid")
    else:
        print("❌ FAIL: Analyzer error")

    print("\n====================================")
    print("ENGINE TEST COMPLETE")
    print("====================================")


if __name__ == "__main__":
    main()