import pandas as pd

from modules.portfolio_engine import PortfolioEngine
from modules.rebalance.periodic import PeriodicRebalance


def main():

    # -----------------------------
    # 테스트 설정
    # -----------------------------

    tickers = ["QQQ", "SPY"]

    strategy = PeriodicRebalance(
        target_weights={
            "QQQ": 0.6,
            "SPY": 0.4
        }
    )

    engine = PortfolioEngine()

    # -----------------------------
    # Simulation 실행
    # -----------------------------

    result = engine.run_simulation(
        tickers=tickers,
        strategy=strategy,
        start_date="2018-01-01",
        end_date="2020-12-31",
        initial_cash=1_000_000
    )

    # -----------------------------
    # 결과 출력
    # -----------------------------

    print("\n===== Simulation Result =====")

    print(result.head())

    print("\nFinal Portfolio Value")

    print(result.iloc[-1])

    print("\nTotal Return")

    start_value = result.iloc[0]["portfolio_value"]
    end_value = result.iloc[-1]["portfolio_value"]

    total_return = (end_value / start_value) - 1

    print(f"{total_return * 100:.2f}%")


if __name__ == "__main__":
    main()