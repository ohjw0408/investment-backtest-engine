from modules.core.portfolio import Portfolio
from modules.rebalance.periodic import PeriodicRebalance


def run_test():

    print("===== REBALANCE TEST START =====")

    portfolio = Portfolio(initial_cash=1_000_000)

    portfolio.buy("QQQ", 5, 100_000)  # 50만원 투자

    price_dict = {"QQQ": 110_000}

    strategy = PeriodicRebalance(
        target_weights={
            "QQQ": 0.5,
            "CASH": 0.5
        },
        include_cash=True
    )

    orders = strategy.generate_orders(portfolio, price_dict)

    print("주문 금액 차이:", orders)

    print("===== REBALANCE TEST END =====")


if __name__ == "__main__":
    run_test()
