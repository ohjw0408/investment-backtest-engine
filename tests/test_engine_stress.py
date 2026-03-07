import logging
import warnings
import subprocess
import os

logging.getLogger("yfinance").setLevel(logging.CRITICAL)
warnings.filterwarnings("ignore")
os.environ["PYTHONWARNINGS"] = "ignore"

import sys
from pathlib import Path

# 프로젝트 루트 경로 추가
sys.path.append(str(Path(__file__).resolve().parents[1]))
from modules.portfolio_engine import PortfolioEngine
from modules.analyzer.portfolio_analyzer import PortfolioAnalyzer
from modules.rebalance.periodic import PeriodicRebalance


def run_test(name, tickers, weights, initial_capital=1_000_000):

    print("\n====================================")
    print(name)
    print("====================================")

    engine = PortfolioEngine()
    analyzer = PortfolioAnalyzer()

    strategy = PeriodicRebalance(
        target_weights=weights
    )

    result = engine.run_simulation(

        tickers=tickers,
        start_date="2018-01-01",
        end_date="2020-12-31",
        initial_capital=initial_capital,
        strategy=strategy

    )

    history = result["history"]

    analysis = analyzer.analyze(history)

    print("CAGR:", round(analysis["cagr"] * 100, 2), "%")
    print("MDD:", round(analysis["mdd"] * 100, 2), "%")
    print("Volatility:", round(analysis["volatility"] * 100, 2), "%")

    print("\nPeak Date:", analysis["mdd_start"])
    print("Bottom Date:", analysis["mdd_bottom"])
    print("Recovery Date:", analysis["recovery_date"])
    print("Recovery Days:", analysis["recovery_days"])

    print("\nHistory Columns:", len(history.columns))

    print("Final Portfolio Value:", history.iloc[-1]["portfolio_value"])


def main():

    # -------------------------------------------------
    # 1️⃣ Single Asset Test
    # -------------------------------------------------

    run_test(

        "Single Asset (100% QQQ)",

        ["QQQ"],

        {
            "QQQ": 1.0
        }

    )

    # -------------------------------------------------
    # 2️⃣ Extreme Allocation Test
    # -------------------------------------------------

    run_test(

        "Extreme Allocation (99% / 1%)",

        ["QQQ", "TLT"],

        {
            "QQQ": 0.99,
            "TLT": 0.01
        }

    )

    # -------------------------------------------------
    # 3️⃣ 20 Asset Portfolio Test
    # -------------------------------------------------

    tickers = [

        "SPY","QQQ","DIA","IWM",
        "TLT","IEF","SHY",
        "LQD","HYG",
        "GLD","SLV",
        "DBC","USO",
        "VNQ","SCHH",
        "VEA","VWO",
        "MTUM","QUAL","USMV"

    ]

    weights = {t: 1/20 for t in tickers}

    run_test(

        "20 Asset Portfolio",

        tickers,

        weights

    )

    # -------------------------------------------------
    # 4️⃣ No Rebalance Test
    # -------------------------------------------------

    print("\n====================================")
    print("No Rebalance Portfolio")
    print("====================================")

    engine = PortfolioEngine()
    analyzer = PortfolioAnalyzer()

    result = engine.run_simulation(

        tickers=["QQQ", "TLT"],

    

        start_date="2018-01-01",
        end_date="2020-12-31",

        initial_capital=1_000_000,

        strategy = PeriodicRebalance(
            target_weights={
                "QQQ": 0.6,
                "TLT": 0.4
        },
        rebalance_frequency="never"
    )

    )

    history = result["history"]

    analysis = analyzer.analyze(history)

    print("CAGR:", round(analysis["cagr"] * 100, 2), "%")
    print("MDD:", round(analysis["mdd"] * 100, 2), "%")
    print("Volatility:", round(analysis["volatility"] * 100, 2), "%")

    # -------------------------------------------------
    # 5️⃣ Tiny Portfolio Test
    # -------------------------------------------------

    run_test(

        "Tiny Portfolio ($100)",

        ["QQQ","TLT"],

        {
            "QQQ":0.6,
            "TLT":0.4
        },

        initial_capital=100

    )


if __name__ == "__main__":
    main()