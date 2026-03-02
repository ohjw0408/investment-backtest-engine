from modules.core.portfolio import Portfolio


def run_test():

    print("===== CASH TEST START =====")

    # 1️⃣ 초기 100만원
    portfolio = Portfolio(initial_cash=1_000_000)

    # 2️⃣ 50만원만 투자
    portfolio.buy("QQQ", quantity=5, price=100_000)  # 50만원 사용

    # 3️⃣ 현재 가격 110,000원
    price_dict = {"QQQ": 110_000}

    print("\n--- 50% 투자 상태 ---")
    print("현금:", portfolio.cash)
    print("총 자산:", portfolio.total_value(price_dict))

    print("\n비중 (현금 포함):")
    print(portfolio.current_weights(price_dict, include_cash=True))

    print("\n비중 (현금 제외):")
    print(portfolio.current_weights(price_dict, include_cash=False))

    # 4️⃣ 일부 매도
    portfolio.sell("QQQ", quantity=2, price=110_000)

    print("\n--- 일부 매도 후 ---")
    print("현금:", portfolio.cash)
    print("총 자산:", portfolio.total_value(price_dict))

    print("\n비중 (현금 포함):")
    print(portfolio.current_weights(price_dict, include_cash=True))

    print("\n비중 (현금 제외):")
    print(portfolio.current_weights(price_dict, include_cash=False))

    print("===== CASH TEST END =====")


if __name__ == "__main__":
    run_test()
