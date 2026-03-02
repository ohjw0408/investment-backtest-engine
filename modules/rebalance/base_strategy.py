from typing import Dict
from modules.core.portfolio import Portfolio


class BaseRebalanceStrategy:
    """
    리밸런싱 전략의 기본 인터페이스
    """

    def __init__(self, target_weights: Dict[str, float], include_cash: bool = True):
        self.target_weights = target_weights
        self.include_cash = include_cash

    def generate_orders(
        self,
        portfolio: Portfolio,
        price_dict: Dict[str, float],
    ) -> Dict[str, float]:
        """
        각 자산별 목표 금액 차이 계산
        반환값:
            { ticker: 목표 대비 추가 매수(+)/매도(-) 금액 }
        """
        raise NotImplementedError
