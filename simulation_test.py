from modules.portfolio_engine import PortfolioEngine
from modules.rebalance.periodic import PeriodicRebalance

from modules.analyzer.portfolio_analyzer import PortfolioAnalyzer
from modules.analyzer.retirement_analyzer import RetirementAnalyzer


def main():

    engine = PortfolioEngine()

    # ---------------------------------------
    # 리밸런싱 전략
    # ---------------------------------------

    strategy = PeriodicRebalance(
        target_weights={
            "QQQ": 0.6,
            "TLT": 0.4
        }
    )

    # ---------------------------------------
    # 포트폴리오 시뮬레이션
    # ---------------------------------------

    result = engine.run_simulation(
        tickers=["QQQ", "TLT"],
        start_date="2018-01-01",
        end_date="2020-12-31",
        strategy=strategy,
        initial_capital=1_000_000
    )

    history = result["history"]

    print("\n===== Simulation Result =====")
    print(history.head())

    print("\nFinal Portfolio State")
    print(history.iloc[-1])

    print(
        "\nTotal Return:",
        round(result["total_return"] * 100, 2),
        "%"
    )

    # ---------------------------------------
    # History 구조 확인
    # ---------------------------------------

    print("\nHistory Columns")
    print(history.columns)

    # ---------------------------------------
    # Cash Drift 검사
    # ---------------------------------------

    print("\nCash History (first 20 days)")
    print(history["cash"].head(20))

    print("\nCash History (last 20 days)")
    print(history["cash"].tail(20))

    print("\nCash Summary")
    print(history["cash"].describe())

    # ---------------------------------------
    # Portfolio Analyzer
    # ---------------------------------------

    analyzer = PortfolioAnalyzer()

    analysis = analyzer.analyze(history)

    print("\n====================================")
    print("Portfolio Analyzer Result")
    print("====================================")

    print(
        "CAGR:",
        round(analysis["cagr"] * 100, 2),
        "%"
    )

    print(
        "MDD:",
        round(analysis["mdd"] * 100, 2),
        "%"
    )

    print(
        "Volatility:",
        round(analysis["volatility"] * 100, 2),
        "%"
    )

    print(
        "Sharpe:",
        round(analysis["sharpe"], 2)
    )

    print("\nMDD Start:", analysis["mdd_start"])
    print("MDD Bottom:", analysis["mdd_bottom"])
    print("Recovery Date:", analysis["recovery_date"])
    print("Recovery Days:", analysis["recovery_days"])

    # ---------------------------------------
    # Retirement Simulation
    # ---------------------------------------

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

    print(
        "Success Probability:",
        round(ret_result["success_rate"] * 100, 2),
        "%"
    )

    print(
        "Best Terminal Wealth:",
        round(ret_result["best_terminal"], 2)
    )

    print(
        "Median Terminal Wealth:",
        round(ret_result["median_terminal"], 2)
    )

    print(
        "Worst Terminal Wealth:",
        round(ret_result["worst_terminal"], 2)
    )


if __name__ == "__main__":
    main()
