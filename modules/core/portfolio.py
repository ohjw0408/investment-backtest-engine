from typing import Dict
from modules.core.position import Position


class Portfolio:
    """
    수량 기반 포트폴리오 상태 객체
    """

    def __init__(self, initial_cash: float):
        self.cash = initial_cash
        self.positions: Dict[str, Position] = {}

    # -------------------------
    # 포지션 가져오기
    # -------------------------
    def get_position(self, ticker: str) -> Position:
        if ticker not in self.positions:
            self.positions[ticker] = Position(ticker)
        return self.positions[ticker]

    # -------------------------
    # 매수
    # -------------------------
    def buy(self, ticker: str, quantity: float, price: float):
        cost = quantity * price

        if cost > self.cash:
            raise ValueError("현금이 부족합니다.")

        position = self.get_position(ticker)
        position.buy(quantity, price)

        self.cash -= cost

    # -------------------------
    # 매도
    # -------------------------
    def sell(self, ticker: str, quantity: float, price: float):
        position = self.get_position(ticker)
        position.sell(quantity, price)

        proceeds = quantity * price
        self.cash += proceeds

    # -------------------------
    # 총 자산 가치 (현금 포함)
    # -------------------------
    def total_value(self, price_dict: Dict[str, float]) -> float:
        total = self.cash

        for ticker, position in self.positions.items():
            if ticker in price_dict:
                total += position.market_value(price_dict[ticker])

        return total

    # -------------------------
    # 현재 비중 계산
    # -------------------------
    def current_weights(
        self,
        price_dict: Dict[str, float],
        include_cash: bool = True,
    ) -> Dict[str, float]:

        weights = {}

        total = self.total_value(price_dict)

        if total == 0:
            return weights

        # 1️⃣ 자산 비중 계산
        asset_total = 0.0

        for ticker, position in self.positions.items():
            if ticker in price_dict:
                value = position.market_value(price_dict[ticker])
                asset_total += value

        for ticker, position in self.positions.items():
            if ticker in price_dict:
                value = position.market_value(price_dict[ticker])

                if include_cash:
                    weights[ticker] = value / total
                else:
                    if asset_total > 0:
                        weights[ticker] = value / asset_total

        # 2️⃣ 현금 비중 추가 (옵션)
        if include_cash:
            weights["CASH"] = self.cash / total

        return weights

    # -------------------------
    # 상태 요약
    # -------------------------
    def summary(self, price_dict: Dict[str, float]) -> dict:
        return {
            "cash": self.cash,
            "total_value": self.total_value(price_dict),
            "weights_including_cash": self.current_weights(
                price_dict, include_cash=True
            ),
            "weights_excluding_cash": self.current_weights(
                price_dict, include_cash=False
            ),
        }
