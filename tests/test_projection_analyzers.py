import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

import numpy as np

from modules.portfolio_engine import PortfolioEngine
from modules.rebalance.periodic import PeriodicRebalance
from modules.analyzer.engine_rolling_analyzer import EngineRollingAnalyzer
from modules.analyzer.wealth_projection_analyzer import WealthProjectionAnalyzer
from modules.analyzer.dividend_projection_analyzer import DividendProjectionAnalyzer


def analyze_and_print(name, distribution, analyzer):

    print(f"\n========== {name} ==========")

    print("Sample:")
    print(distribution[:10])

    stats = analyzer.analyze(distribution)

    print("\nScenario count:", stats["scenario_count"])

    print("\nSummary")
    print(stats["summary"])

    print("\nPercentiles")
    print(stats["percentiles"])

    print("\nExtremes")
    print(stats["extremes"])

    print("\nShape")
    print(stats["shape"])


def main():

    print("\n========== FULL DISTRIBUTION TEST ==========")

    engine = PortfolioEngine()

    weights = {
        "SCHD": 0.7,
        "QQQ": 0.3
    }

    strategy = PeriodicRebalance(
        target_weights=weights,
        rebalance_frequency="monthly"
    )

    # -------------------------------------------------
    # 🔎 history 구조 확인용 단일 시뮬레이션
    # -------------------------------------------------

    test = engine.run_simulation(
        tickers=["SCHD", "QQQ"],
        start_date="2012-01-01",
        end_date="2017-01-01",
        initial_capital=0,
        monthly_contribution=5_000_000,
        strategy=strategy
    )

    print("\n===== HISTORY COLUMNS =====")
    print(test["history"].columns)

    print("\n===== HISTORY SAMPLE HEAD =====")
    print(test["history"].head(10))

    print("\n===== HISTORY SAMPLE TAIL =====")
    print(test["history"].tail(10))

    # -------------------------------------------------
    # Rolling analyzer 실행
    # -------------------------------------------------

    analyzer = EngineRollingAnalyzer(

        engine=engine,
        strategy=strategy,

        tickers=["SCHD", "QQQ"],

        start_date="2012-01-01",
        end_date="2024-01-01",

        horizon_years=5,

        initial_capital=0,
        monthly_contribution=5_000_000,

        dividend_mode="reinvest"
    )

    result = analyzer.run()

    print("\nTotal scenarios:", result["scenario_count"])

    wealth_analyzer = WealthProjectionAnalyzer()
    dividend_analyzer = DividendProjectionAnalyzer()

    # -----------------------------
    # Wealth related distributions
    # -----------------------------

    analyze_and_print(
        "WEALTH MULTIPLE",
        result["wealth_distribution"],
        wealth_analyzer
    )

    analyze_and_print(
        "CAGR",
        result["cagr_distribution"],
        wealth_analyzer
    )

    analyze_and_print(
        "VOLATILITY",
        result["volatility_distribution"],
        wealth_analyzer
    )

    analyze_and_print(
        "MAX DRAWDOWN",
        result["max_drawdown_distribution"],
        wealth_analyzer
    )

    # -----------------------------
    # Dividend related distributions
    # -----------------------------

    analyze_and_print(
        "TERMINAL DIVIDEND",
        result["terminal_dividend_distribution"],
        dividend_analyzer
    )

    analyze_and_print(
        "TOTAL DIVIDEND",
        result["total_dividend_distribution"],
        dividend_analyzer
    )

    analyze_and_print(
        "YIELD ON COST",
        result["yield_on_cost_distribution"],
        dividend_analyzer
    )

    analyze_and_print(
        "DIVIDEND CAGR",
        result["dividend_cagr_distribution"],
        dividend_analyzer
    )

    print("\n========== TEST COMPLETE ==========")


if __name__ == "__main__":
    main()