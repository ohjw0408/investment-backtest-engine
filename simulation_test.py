
from modules.portfolio_engine import PortfolioEngine
from modules.rebalance.periodic import PeriodicRebalance
from modules.analyzer.portfolio_analyzer import PortfolioAnalyzer
from modules.analyzer.retirement_analyzer import RetirementAnalyzer


def main():

    engine = PortfolioEngine()

    # -------------------------------------------------
    # 기본 전략 (3자산 테스트)
    # -------------------------------------------------

    strategy = PeriodicRebalance(
        target_weights={
            "QQQ": 0.5,
            "TLT": 0.3,
            "GLD": 0.2
        },
        rebalance_frequency="monthly"
    )

    result = engine.run_simulation(
        tickers=["QQQ", "TLT", "GLD"],
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

    print("\nTotal Return:", round(result["total_return"] * 100, 2), "%")

    # -------------------------------------------------
    # history 구조 확인
    # -------------------------------------------------

    print("\n====================================")
    print("History Columns")
    print("====================================")

    print(history.columns)

    # -------------------------------------------------
    # 자산 value 확인
    # -------------------------------------------------

    print("\n====================================")
    print("Asset Value Preview")
    print("====================================")

    value_cols = [c for c in history.columns if "_value" in c]
    print(history[value_cols].head())

    # -------------------------------------------------
    # 자산 weight 확인
    # -------------------------------------------------

    print("\n====================================")
    print("Asset Weight Preview")
    print("====================================")

    weight_cols = [c for c in history.columns if "_weight" in c]
    print(history[weight_cols].head())

    # -------------------------------------------------
    # weight 합 확인
    # -------------------------------------------------

    print("\n====================================")
    print("Weight Sum Check")
    print("====================================")

    print(history[weight_cols].sum(axis=1).head())

    # -------------------------------------------------
    # 배당 테스트
    # -------------------------------------------------

    print("\n====================================")
    print("Dividend Income Preview")
    print("====================================")

    print(history["dividend_income"].head(20))

    print("\nTotal Dividend Received")
    print(round(history["dividend_income"].sum(), 2))

    # -------------------------------------------------
    # 배당 이벤트 확인
    # -------------------------------------------------

    print("\n====================================")
    print("Dividend Events")
    print("====================================")

    dividend_events = history[history["dividend_income"] > 0]
    print(dividend_events[["date", "dividend_income"]].head())

    print("\nTotal Dividend Events:", len(dividend_events))

    # -------------------------------------------------
    # Cash drift 확인
    # -------------------------------------------------

    print("\n====================================")
    print("Cash Drift Check")
    print("====================================")

    print(history["cash"].describe())

    # -------------------------------------------------
    # Portfolio Analyzer
    # -------------------------------------------------

    analyzer = PortfolioAnalyzer()

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

    # -------------------------------------------------
    # Retirement Simulation
    # -------------------------------------------------

    print("\n====================================")
    print("Retirement Simulation")
    print("====================================")

    retirement = RetirementAnalyzer(
        monthly_withdrawal=3000,
        years=2,
        inflation=0.02
    )

    ret_result = retirement.analyze(
        history,
        initial_capital=1_000_000
    )

    print("Success Probability:", round(
        ret_result["success_rate"] * 100, 2), "%")
    print("Best Terminal Wealth:", round(ret_result["best_terminal"], 2))
    print("Median Terminal Wealth:", round(ret_result["median_terminal"], 2))
    print("Worst Terminal Wealth:", round(ret_result["worst_terminal"], 2))

    # =================================================
    # Rebalance vs No Rebalance Test
    # =================================================

    print("\n====================================")
    print("Rebalance vs No Rebalance Test")
    print("====================================")

    # -----------------------------
    # Case 1 : Monthly Rebalance
    # -----------------------------

    rebalance_strategy = PeriodicRebalance(
        target_weights={
            "QQQ": 0.6,
            "TLT": 0.4
        },
        rebalance_frequency="monthly"
    )

    result_rebalance = engine.run_simulation(
        tickers=["QQQ", "TLT"],
        start_date="2018-01-01",
        end_date="2020-12-31",
        strategy=rebalance_strategy,
        initial_capital=1_000_000,
        reinvest_dividend=True
    )

    analysis_rebalance = analyzer.analyze(result_rebalance["history"])

    print("\n--- Monthly Rebalance ---")

    print("CAGR:", round(analysis_rebalance["cagr"] * 100, 2), "%")
    print("MDD:", round(analysis_rebalance["mdd"] * 100, 2), "%")
    print("Volatility:", round(analysis_rebalance["volatility"] * 100, 2), "%")

    print("Peak Date:", analysis_rebalance["mdd_start"])
    print("Bottom Date:", analysis_rebalance["mdd_bottom"])
    print("Recovery Date:", analysis_rebalance["recovery_date"])
    print("Recovery Days:", analysis_rebalance["recovery_days"])

    # -----------------------------
    # Case 2 : No Rebalance
    # -----------------------------

    no_rebalance_strategy = PeriodicRebalance(
        target_weights={
            "QQQ": 0.6,
            "TLT": 0.4
        },
        rebalance_frequency=None
    )

    result_no_rebalance = engine.run_simulation(
        tickers=["QQQ", "TLT"],
        start_date="2018-01-01",
        end_date="2020-12-31",
        strategy=no_rebalance_strategy,
        initial_capital=1_000_000,
        reinvest_dividend=True
    )

    analysis_no_rebalance = analyzer.analyze(result_no_rebalance["history"])

    print("\n--- No Rebalance ---")

    print("CAGR:", round(analysis_no_rebalance["cagr"] * 100, 2), "%")
    print("MDD:", round(analysis_no_rebalance["mdd"] * 100, 2), "%")
    print("Volatility:", round(
        analysis_no_rebalance["volatility"] * 100, 2), "%")

    print("Peak Date:", analysis_no_rebalance["mdd_start"])
    print("Bottom Date:", analysis_no_rebalance["mdd_bottom"])
    print("Recovery Date:", analysis_no_rebalance["recovery_date"])
    print("Recovery Days:", analysis_no_rebalance["recovery_days"])


if __name__ == "__main__":
    main()
