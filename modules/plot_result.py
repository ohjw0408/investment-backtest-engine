import matplotlib.pyplot as plt
from modules.backtest_engine import BacktestEngine


if __name__ == "__main__":
    engine = BacktestEngine()

    result = engine.run(
        code="QQQ",
        start_date="2015-01-01",
        end_date="2020-12-31",
        initial_capital=1_000_000,
    )

    df = result["history"]

    # -----------------------------
    # 그래프 1: 누적 수익률
    # -----------------------------
    plt.figure()
    plt.plot(df["date"], df["cum_return"], label="Cumulative Return")
    plt.title("Cumulative Return")
    plt.xlabel("Date")
    plt.ylabel("Multiple")
    plt.legend()
    plt.grid(True)
    plt.show()

    # -----------------------------
    # 그래프 2: Drawdown (MDD)
    # -----------------------------
    plt.figure()
    plt.plot(df["date"], df["drawdown"], label="Drawdown")
    plt.title("Drawdown (MDD)")
    plt.xlabel("Date")
    plt.ylabel("Drawdown")
    plt.legend()
    plt.grid(True)
    plt.show()

    # 콘솔 요약
    print("총 수익률:", round(result["total_return"] * 100, 2), "%")
    print("CAGR:", round(result["cagr"] * 100, 2), "%")
    print("MDD:", round(result["mdd"] * 100, 2), "%")
