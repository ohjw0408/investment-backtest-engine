from typing import Dict
from modules.core.portfolio import Portfolio


class CashAllocator:

    def allocate_cash(
        self,
        portfolio: Portfolio,
        price_dict: Dict[str, float],
        target_weights: Dict[str, float],
    ):

        if portfolio.cash <= 0:
            return

        # -----------------------------
        # 현재 포트 가치 계산
        # -----------------------------
        total_value = portfolio.total_value(price_dict)

        deficits = {}

        # -----------------------------
        # deficit 계산
        # -----------------------------
        for ticker, target_weight in target_weights.items():

            if ticker == "CASH":
                continue

            price = price_dict.get(ticker)

            if price is None:
                continue

            current_value = 0

            if ticker in portfolio.positions:
                current_value = portfolio.positions[ticker].market_value(price)

            target_value = total_value * target_weight

            deficit = target_value - current_value

            deficits[ticker] = deficit

        # -----------------------------
        # deficit 기준 정렬
        # -----------------------------
        deficits = sorted(
            deficits.items(),
            key=lambda x: x[1],
            reverse=True,
        )

        # -----------------------------
        # 1차: deficit 채우기
        # -----------------------------
        for ticker, deficit in deficits:

            if portfolio.cash <= 0:
                break

            if deficit <= 0:
                continue

            price = price_dict[ticker]

            quantity = int(min(deficit, portfolio.cash) / price)

            if quantity <= 0:
                continue

            try:
                portfolio.buy(
                    ticker,
                    quantity,
                    price,
                )
            except ValueError:
                continue

        # -----------------------------
        # 2차: 남은 cash greedy 투자
        # -----------------------------
        while portfolio.cash > 0:

            # 가장 부족한 자산 찾기
            total_value = portfolio.total_value(price_dict)

            deficits = []

            for ticker, target_weight in target_weights.items():

                if ticker == "CASH":
                    continue

                price = price_dict.get(ticker)

                if price is None:
                    continue

                current_value = 0

                if ticker in portfolio.positions:
                    current_value = portfolio.positions[ticker].market_value(price)

                target_value = total_value * target_weight

                deficit = target_value - current_value

                deficits.append((ticker, deficit))

            deficits.sort(key=lambda x: x[1], reverse=True)

            if not deficits:
                break

            ticker = deficits[0][0]
            price = price_dict[ticker]

            if portfolio.cash < price:
                break

            try:
                portfolio.buy(
                    ticker,
                    1,
                    price,
                )
            except ValueError:
                break