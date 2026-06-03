from typing import Dict
from modules.core.portfolio import Portfolio


class OrderExecutor:
    """
    주문 실행 엔진

    RebalanceStrategy가 생성한
    value 기반 주문을 실제 거래로 변환한다.
    """

    def execute_orders(
        self,
        portfolio: Portfolio,
        orders: Dict[str, float],
        price_dict: Dict[str, float],
        date=None,
    ) -> None:

        if not orders:
            return

        # -----------------------------
        # 1️⃣ 먼저 매도
        # -----------------------------
        for ticker, value in orders.items():

            if ticker == "CASH":
                continue

            if value >= 0:
                continue

            if ticker not in price_dict:
                continue

            price = price_dict[ticker]

            if not price or price != price or price <= 0:  # None/NaN/0 체크
                continue

            quantity = int(abs(value) / price)

            if quantity <= 0:
                continue

            position = portfolio.positions.get(ticker)

            if position is None:
                continue

            quantity = min(quantity, int(position.quantity))

            if quantity <= 0:
                continue

            portfolio.sell(ticker, quantity, price)

        # -----------------------------
        # 2️⃣ 매수
        # -----------------------------
        for ticker, value in orders.items():

            if ticker == "CASH":
                continue

            if value <= 0:
                continue

            if ticker not in price_dict:
                continue

            price = price_dict[ticker]

            if not price or price != price or price <= 0:  # None/NaN/0 체크
                continue

            quantity = int(value / price)

            if quantity <= 0:
                continue

            try:
                portfolio.buy(ticker, quantity, price)

            except ValueError:
                continue

class TaxedOrderExecutor(OrderExecutor):
    """
    OrderExecutor 확장 - 리밸런싱 매도 시 양도차익세 차감.

    위탁 계좌:
      KR_FOREIGN (국내상장 해외ETF) → 차익 × 15.4%
      US_DIRECT  (해외 직접투자)   → 연 250만 공제 후 × 22%
      KR_DOMESTIC / KR_STOCK       → 비과세

    ISA / 연금저축 / IRP → 과세이연, CG세 없음
    """

    OVERSEAS_EXEMPT = 2_500_000
    OVERSEAS_RATE   = 0.22
    KR_FOREIGN_RATE = 0.154

    def __init__(
        self,
        tax_engine,
        account_type: str = "위탁",
        gain_harvesting: bool = False,
        session=None,
    ):
        self.tax_engine        = tax_engine
        self.account_type      = account_type
        self.gain_harvesting   = gain_harvesting  # 연간 250만 공제 소진 절세 매도
        # 공유 세션(TaxSessionState) — 있으면 배당엔진과 금융소득 풀 공유(KR_FOREIGN 중간실현 합산).
        self._session          = session
        self._ytd_us_gains     = 0.0   # 세션 없을 때만 사용
        self._current_year     = None
        self.total_cg_tax_paid = 0.0
        self._harvested_year   = None  # 올해 이미 harvest 했으면 스킵
        # 절세액(위탁 가정): 계좌유형 무관하게 매도 실현차익 누적 — 실제 과세와 독립.
        self._brk_krf_gain     = 0.0   # KR_FOREIGN 실현차익(이익분만, 손익통산 없음)
        self._brk_us_by_year   = {}    # US_DIRECT 실현차익 연도별(손익통산)
        self._brk_us_harvested_total = 0.0  # GH 절세매도로 실현·기준리셋한 누적차익(GH 절세 산출용)

    # ── US 양도차익 YTD (세션 있으면 세션, 없으면 자체) ──
    def _ytd_us(self) -> float:
        return self._session.ytd_us_realized_gains if self._session is not None else self._ytd_us_gains

    def _add_us(self, amount: float) -> None:
        if self._session is not None:
            self._session.add_us_gain(amount)
        else:
            self._ytd_us_gains += amount

    def _update_year(self, date) -> None:
        if self._session is not None:
            if date:
                self._session.touch(date)
            return
        if date and (self._current_year is None or date.year != self._current_year):
            self._current_year = date.year
            self._ytd_us_gains = 0.0

    def execute_orders(
        self,
        portfolio,
        orders: Dict[str, float],
        price_dict: Dict[str, float],
        date=None,
    ) -> None:
        self._update_year(date)

        # 절세액(위탁 가정): 계좌유형 무관하게 매도 실현차익을 분류별 누적(과세 전 단계).
        self._accrue_brokerage_gain(portfolio, orders, price_dict, date)

        # ISA / 연금저축 / IRP: CG세 없음
        if self.account_type in ("ISA", "연금저축", "IRP"):
            super().execute_orders(portfolio, orders, price_dict)
            return

        # 위탁: 매도 먼저 (CG세 계산)
        for ticker, value in orders.items():
            if ticker == "CASH" or value >= 0:
                continue
            if ticker not in price_dict:
                continue
            price = price_dict[ticker]
            if not price or price != price or price <= 0:
                continue
            quantity = int(abs(value) / price)
            if quantity <= 0:
                continue
            position = portfolio.positions.get(ticker)
            if position is None:
                continue
            quantity = min(quantity, int(position.quantity))
            if quantity <= 0:
                continue

            self.sell_with_tax(portfolio, ticker, quantity, price)

        # 매수
        for ticker, value in orders.items():
            if ticker == "CASH" or value <= 0:
                continue
            if ticker not in price_dict:
                continue
            price = price_dict[ticker]
            if not price or price != price or price <= 0:
                continue
            quantity = int(value / price)
            if quantity <= 0:
                continue
            try:
                portfolio.buy(ticker, quantity, price)
            except ValueError:
                continue

        # 연간 250만 공제 소진 절세 매도 (12월 마지막 거래일 근처)
        if (
            self.gain_harvesting
            and self.account_type == "위탁"
            and date is not None
            and date.month == 12
            and self._harvested_year != date.year
        ):
            self._do_gain_harvest(portfolio, price_dict, date)

    def sell_with_tax(self, portfolio, ticker: str, quantity: int, price: float) -> None:
        """위탁 매도 실현차익에 양도세 부과 후 매도. ISA/연금/IRP는 과세이연(비과세 매도).

        리밸런싱 매도와 인출 매도가 공유한다(BUG-TAX-2: 인출하며 판 위탁 매도차익도
        양도세 대상 — 기존엔 WithdrawalEngine이 portfolio.sell 직행으로 누락).
        """
        if quantity <= 0:
            return
        avg_cost = (
            portfolio.get_avg_cost(ticker)
            if hasattr(portfolio, "get_avg_cost")
            else None
        )
        if avg_cost is None:
            avg_cost = price  # 취득단가 불명 → 차익 0 (보수적 처리)
        realized_gain = (price - avg_cost) * quantity

        portfolio.sell(ticker, quantity, price)

        # ISA / 연금저축 / IRP: 과세이연, CG세 없음
        if self.account_type in ("ISA", "연금저축", "IRP"):
            return

        # US_DIRECT 손실도 YTD에 반영 (손익통산 — 양도소득세)
        if realized_gain < 0 and avg_cost != price:
            if self.tax_engine.classify_asset(ticker) == "US_DIRECT":
                self._add_us(realized_gain)  # 음수 → 공제 여유 증가

        if realized_gain > 0:
            cg_tax = self._calc_cg_tax(ticker, realized_gain)
            if cg_tax > 0:
                portfolio.cash = max(0.0, portfolio.cash - cg_tax)
                self.total_cg_tax_paid += cg_tax

    def _accrue_brokerage_gain(self, portfolio, orders, price_dict, date) -> None:
        """절세액(위탁 가정): 매도 실현차익을 자산분류별 누적. 계좌유형·실제과세와 독립.

        KR_FOREIGN = 이익분만(손익통산 없음). US_DIRECT = 손익통산(연도별 누적).
        국내·KRX금 = 0%이므로 무시. avg_cost는 매도 실행 전(현재) 값을 읽는다.
        """
        year = date.year if date is not None else 0
        for ticker, value in orders.items():
            if ticker == "CASH" or value >= 0 or ticker not in price_dict:
                continue
            price = price_dict[ticker]
            if not price or price != price or price <= 0:
                continue
            position = portfolio.positions.get(ticker)
            if position is None:
                continue
            quantity = min(int(abs(value) / price), int(position.quantity))
            if quantity <= 0:
                continue
            avg_cost = (
                portfolio.get_avg_cost(ticker)
                if hasattr(portfolio, "get_avg_cost")
                else None
            )
            if avg_cost is None:
                continue
            realized = (price - avg_cost) * quantity
            asset_type = self.tax_engine.classify_asset(ticker)
            if asset_type == "KR_FOREIGN":
                if realized > 0:
                    self._brk_krf_gain += realized
            elif asset_type == "US_DIRECT":
                self._brk_us_by_year[year] = self._brk_us_by_year.get(year, 0.0) + realized

    def maybe_gain_harvest(self, portfolio, price_dict: Dict[str, float], date) -> None:
        """
        12월에 리밸런싱 없이도 절세매도 실행.
        simulation_loop에서 매 거래일 호출 — 12월 여부와 중복 실행 여부를 내부에서 판단.
        """
        if not self.gain_harvesting or self.account_type != "위탁":
            return
        if date is None or date.month != 12:
            return
        self._update_year(date)
        self._do_gain_harvest(portfolio, price_dict, date)

    def _do_gain_harvest(self, portfolio, price_dict: Dict[str, float], date) -> None:
        """
        연간 250만원 공제 소진 절세 매도.

        US_DIRECT 종목의 미실현 차익 중 (250만 - 올해 이미 실현한 차익)만큼
        추가로 매도 후 즉시 재매수 → 취득단가 리셋, 세금 0원.

        남은 공제 여유가 없거나 미실현 차익이 없으면 아무 것도 안 함.
        """
        self._harvested_year = date.year
        remaining_exempt = max(0.0, self.OVERSEAS_EXEMPT - self._ytd_us())
        if remaining_exempt <= 0:
            return

        for ticker, position in list(portfolio.positions.items()):
            if position.quantity <= 0:
                continue
            if ticker not in price_dict:
                continue
            asset_type = self.tax_engine.classify_asset(ticker)
            if asset_type != "US_DIRECT":
                continue

            price    = price_dict[ticker]
            avg_cost = portfolio.get_avg_cost(ticker) if hasattr(portfolio, "get_avg_cost") else None
            if avg_cost is None or avg_cost >= price:
                continue  # 취득단가 불명 또는 손실 포지션은 스킵

            gain_per_share    = price - avg_cost
            harvest_shares    = int(remaining_exempt / gain_per_share)
            harvest_shares    = min(harvest_shares, int(position.quantity))
            if harvest_shares <= 0:
                continue

            harvest_gain = gain_per_share * harvest_shares
            self._add_us(harvest_gain)
            # 위탁 가정: 절세매도는 기준단가 리셋(비과세 실현)이므로 _brk_us_by_year엔 누적 안 함
            # (남은 미실현분만 최종청산에서 과세 → 위탁 절세 0 불변식). 단 GH 절세 산출용으로
            # harvest 누계는 별도 추적(GH 없었으면 최종 단일실현됐을 분).
            self._brk_us_harvested_total += harvest_gain
            remaining_exempt   -= harvest_gain

            # 매도 후 즉시 재매수 (취득단가 현재가로 리셋)
            portfolio.sell(ticker, harvest_shares, price)
            try:
                portfolio.buy(ticker, harvest_shares, price)
            except ValueError:
                pass  # 현금 부족 시 재매수 포기 (매도는 이미 완료)

            if remaining_exempt <= 0:
                break

    def _calc_cg_tax(self, ticker: str, realized_gain: float) -> float:
        # ISA / 연금저축 / IRP: 비과세
        if self.account_type in ("ISA", "연금저축", "IRP"):
            return 0.0

        asset_type = self.tax_engine.classify_asset(ticker)

        if asset_type == "KR_FOREIGN":
            # 배당소득세: 15.4% 분리. 단 세션 있으면 그 해 금융소득 풀과 합산 → 2천만 초과분 종합과세.
            if self._session is not None:
                ytd = self._session.ytd_financial_income
                withheld = realized_gain * self.KR_FOREIGN_RATE
                tax = withheld
                if ytd + realized_gain > self.tax_engine.DIVIDEND_THRESHOLD:
                    tax += self.tax_engine._comprehensive_extra_tax(realized_gain, ytd, withheld)
                self._session.add_financial_income(realized_gain)  # 실현차익을 금융소득 풀에 가산
                return tax
            return realized_gain * self.KR_FOREIGN_RATE

        elif asset_type == "US_DIRECT":
            self._add_us(realized_gain)
            ytd_us = self._ytd_us()
            if ytd_us <= self.OVERSEAS_EXEMPT:
                return 0.0
            prev = ytd_us - realized_gain
            if prev >= self.OVERSEAS_EXEMPT:
                taxable = realized_gain
            else:
                taxable = ytd_us - self.OVERSEAS_EXEMPT
            return max(0.0, taxable) * self.OVERSEAS_RATE

        return 0.0  # KR_DOMESTIC: 비과세