from modules.rebalance.base_strategy import BaseRebalanceStrategy


class ScheduledRebalance(BaseRebalanceStrategy):
    """정해진 날짜마다 목표 비중 자체를 갈아끼우는 전략.

    투자대가 13F 재현용 — 분기 공시일(filed)에 그 분기 보유로 교체한다.
    비중이 시간에 따라 변하므로 `target_weights`를 **제자리(in-place)로 갱신**한다.
    SimulationConfig.target_weights에 같은 dict 객체를 넘기면 적립금·배당 재투자
    스윕(simulation_loop의 cash_allocator)도 그 시점 비중을 따라간다.

    schedule = [("YYYY-MM-DD", {ticker: weight}), ...] — 날짜 오름차순, 비중합 1.
    """

    def __init__(self, schedule, target_weights):
        super().__init__(target_weights)
        self.schedule = list(schedule)
        self._idx = -1

    def _apply(self, i):
        self._idx = i
        self.target_weights.clear()
        self.target_weights.update(self.schedule[i][1])

    def should_rebalance(self, date, portfolio, price_dict):
        # 오늘까지 발효된 마지막 세그먼트를 찾는다. 바뀌었으면 그날이 리밸런싱일.
        # (시작일이 여러 세그먼트 뒤면 첫 매수에서 곧바로 최신 것으로 진입)
        ds = date.strftime("%Y-%m-%d")
        newest = self._idx
        j = self._idx + 1
        while j < len(self.schedule) and self.schedule[j][0] <= ds:
            newest = j
            j += 1
        if newest != self._idx:
            self._apply(newest)
            return True
        return False
