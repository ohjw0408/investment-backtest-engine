import sys
from pathlib import Path

# 프로젝트 루트 path 추가
sys.path.append(str(Path(__file__).resolve().parents[1]))

from modules.portfolio_engine import PortfolioEngine
from modules.rebalance.periodic import PeriodicRebalance
from modules.analyzer.portfolio_analyzer import PortfolioAnalyzer


def main():

    print("\n====================================")
    print("Multi Asset Portfolio Test")
    print("====================================")

    engine = PortfolioEngine()
    analyzer = PortfolioAnalyzer()

    tickers = [
        "SPY","QQQ","DIA","IWM",

    "TLT","IEF","SHY","LQD","HYG",

    "GLD","SLV","DBC","USO",

    "VNQ","SCHH",

    "VEA","VWO",

    "MTUM","QUAL","USMV"
    ]

    weight = 1 / len(tickers)

    weights = {t: weight for t in tickers}

    strategy = PeriodicRebalance(
        target_weights=weights,
        rebalance_frequency="monthly"
    )

    result = engine.run_simulation(

        tickers=tickers,

        start_date="2018-01-01",
        end_date="2020-12-31",

        strategy=strategy,

        initial_capital=1_000_000,

        reinvest_dividend=True
    )

    history = result["history"]

    print("\n===== Simulation Result =====")
    print(history.head())

    print("\nHistory Columns")
    print(history.columns)

    # -----------------------------
    # Weight 확인
    # -----------------------------

    weight_cols = [c for c in history.columns if "_weight" in c]

    print("\nWeight Columns")
    print(weight_cols)

    print("\nWeight Sum Check")
    print(history[weight_cols].sum(axis=1).head())

    # -----------------------------
    # Asset value 확인
    # -----------------------------

    value_cols = [c for c in history.columns if "_value" in c]

    print("\nAsset Value Preview")
    print(history[value_cols].head())

    # -----------------------------
    # Dividend 확인
    # -----------------------------

    print("\nDividend Preview")
    print(history["dividend_income"].head(20))

    print("\nTotal Dividend Received")
    print(history["dividend_income"].sum())

    # -----------------------------
    # Analyzer
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


if __name__ == "__main__":
    main()