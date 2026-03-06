import sys
from pathlib import Path

# 프로젝트 루트 path 추가
sys.path.append(str(Path(__file__).resolve().parents[1]))

from modules.portfolio_engine import PortfolioEngine
from modules.rebalance.periodic import PeriodicRebalance
from modules.analyzer.portfolio_analyzer import PortfolioAnalyzer


def run_test(strategy_name, strategy):

    engine = PortfolioEngine()
    analyzer = PortfolioAnalyzer()

    result = engine.run_simulation(

        tickers=["QQQ", "TLT"],

        start_date="2018-01-01",
        end_date="2020-12-31",

        strategy=strategy,

        initial_capital=1_000_000,

        reinvest_dividend=True
    )

    history = result["history"]

    analysis = analyzer.analyze(history)

    print("\n---", strategy_name, "---")

    print("CAGR:", round(analysis["cagr"] * 100, 2), "%")
    print("MDD:", round(analysis["mdd"] * 100, 2), "%")
    print("Volatility:", round(analysis["volatility"] * 100, 2), "%")

    print("Peak Date:", analysis["mdd_start"])
    print("Bottom Date:", analysis["mdd_bottom"])
    print("Recovery Date:", analysis["recovery_date"])
    print("Recovery Days:", analysis["recovery_days"])


def main():

    weights = {
        "QQQ": 0.6,
        "TLT": 0.4
    }

    # -----------------------------
    # Monthly
    # -----------------------------

    monthly = PeriodicRebalance(
        target_weights=weights,
        rebalance_frequency="monthly"
    )

    run_test("Monthly Rebalance", monthly)

    # -----------------------------
    # Quarterly
    # -----------------------------

    quarterly = PeriodicRebalance(
        target_weights=weights,
        rebalance_frequency="quarterly"
    )

    run_test("Quarterly Rebalance", quarterly)

    # -----------------------------
    # Yearly
    # -----------------------------

    yearly = PeriodicRebalance(
        target_weights=weights,
        rebalance_frequency="yearly"
    )

    run_test("Yearly Rebalance", yearly)

    # -----------------------------
    # No rebalance
    # -----------------------------

    none = PeriodicRebalance(
        target_weights=weights,
        rebalance_frequency=None
    )

    run_test("No Rebalance", none)

    # -----------------------------
    # Drift rebalance
    # -----------------------------

    drift = PeriodicRebalance(
        target_weights=weights,
        rebalance_frequency=None,
        drift_threshold=0.05
    )

    run_test("Drift Rebalance (5%)", drift)


if __name__ == "__main__":
    main()