import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from modules.portfolio_engine import PortfolioEngine
from modules.rebalance.periodic import PeriodicRebalance
from modules.analyzer.portfolio_analyzer import PortfolioAnalyzer


def main():

    print("\n====================================")
    print("Basic Portfolio Simulation Test")
    print("====================================")

    engine = PortfolioEngine()
    analyzer = PortfolioAnalyzer()

    strategy = PeriodicRebalance(
        target_weights={
            "QQQ": 0.6,
            "TLT": 0.4,
        },
        rebalance_frequency="monthly"
    )

    result = engine.run_simulation(

        tickers=["QQQ", "TLT"],

        start_date="2018-01-01",
        end_date="2020-12-31",

        strategy=strategy,

        initial_capital=1_000_000,

        reinvest_dividend=True
    )

    history = result["history"]

    print("\n===== Simulation Result =====")
    print(history.head())

    print("\nFinal Portfolio State")
    print(history.iloc[-1])

    total_return = (
        history["portfolio_value"].iloc[-1] /
        history["portfolio_value"].iloc[0] - 1
    )

    print("\nTotal Return:", round(total_return * 100, 2), "%")

    # -----------------------------
    # History 구조 확인
    # -----------------------------

    print("\n====================================")
    print("History Columns")
    print("====================================")

    print(history.columns)

    # -----------------------------
    # 자산 가치 확인
    # -----------------------------

    print("\n====================================")
    print("Asset Value Preview")
    print("====================================")

    print(
        history[
            [
                "portfolio_value",
                "QQQ_value",
                "TLT_value",
            ]
        ].head()
    )

    # -----------------------------
    # 자산 비중 확인
    # -----------------------------

    print("\n====================================")
    print("Asset Weight Preview")
    print("====================================")

    print(
        history[
            [
                "QQQ_weight",
                "TLT_weight",
            ]
        ].head()
    )

    # -----------------------------
    # weight 합 확인
    # -----------------------------

    print("\n====================================")
    print("Weight Sum Check")
    print("====================================")

    print(
        (
            history["QQQ_weight"]
            + history["TLT_weight"]
        ).head()
    )

    # -----------------------------
    # 배당 확인
    # -----------------------------

    print("\n====================================")
    print("Dividend Income Preview")
    print("====================================")

    print(history["dividend_income"].head(20))

    print("\nTotal Dividend Received")

    print(history["dividend_income"].sum())

    # -----------------------------
    # cash drift 확인
    # -----------------------------

    print("\n====================================")
    print("Cash Drift Check")
    print("====================================")

    print(history["cash"].describe())

    # -----------------------------
    # Portfolio Analyzer
    # -----------------------------

    analysis = analyzer.analyze(history)

    print("\n====================================")
    print("Portfolio Analyzer Result")
    print("====================================")

    print("CAGR:", round(analysis["cagr"] * 100, 2), "%")
    print("MDD:", round(analysis["mdd"] * 100, 2), "%")
    print("Volatility:", round(analysis["volatility"] * 100, 2), "%")
    print("Sharpe:", round(analysis["sharpe"], 2))

    print("\nPeak Date:", analysis["mdd_start"])
    print("Bottom Date:", analysis["mdd_bottom"])
    print("Recovery Date:", analysis["recovery_date"])
    print("Recovery Days:", analysis["recovery_days"])
    
    print(history["cash"].head(50))


if __name__ == "__main__":
    main()
