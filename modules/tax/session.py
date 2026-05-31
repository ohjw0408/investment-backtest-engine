"""TaxSessionState — 시뮬레이션 1회당 세금 누적 상태 (계좌/세션 공유).

배당 엔진과 주문 실행기가 **같은 연도 금융소득 풀**을 공유하게 하는 단일 소스.
- ytd_financial_income: 위탁 배당 gross + KR_FOREIGN 실현차익(배당소득) + 외부 금융소득.
  → 배당·중간실현·청산을 한 풀로 합산해 금융소득 종합과세(2천만 초과) 정확 판정.
- ytd_us_realized_gains: US_DIRECT 양도차익(별도 22%, 250만 공제용). 금융소득 풀에 미합산.
- financial_income_by_year: 연도별 금융소득 합계 → 종합과세 대상 연도 트래킹(Track G ISA 자격 입력).

세션/가구 레벨 추상 — 단일계좌(Phase 2f)에서 쓰고, G2가 계좌간 집계로 확장.
"""
from dataclasses import dataclass, field


@dataclass
class TaxSessionState:
    other_financial_income: float = 0.0   # 시뮬 밖 외부 금융소득(매년 베이스라인)
    ytd_financial_income: float = 0.0     # 당해연도 금융소득 누계(배당 + KR_FOREIGN 실현차익 + 외부)
    ytd_us_realized_gains: float = 0.0    # 당해연도 US_DIRECT 실현 차익(양도소득, 별도)
    year: int | None = None               # 현재 추적 연도
    financial_income_by_year: dict = field(default_factory=dict)

    def __post_init__(self):
        self.other_financial_income = float(self.other_financial_income or 0.0)
        self.ytd_financial_income = self.other_financial_income

    def touch(self, date) -> None:
        """거래일마다 호출(배당엔진·주문실행기 둘 다). 연도 바뀌면 직전 연도 기록 후 리셋."""
        y = date.year
        if self.year is None:
            self.year = y
            self.ytd_financial_income = self.other_financial_income
            self.ytd_us_realized_gains = 0.0
        elif y != self.year:
            self.financial_income_by_year[self.year] = self.ytd_financial_income
            self.year = y
            self.ytd_financial_income = self.other_financial_income
            self.ytd_us_realized_gains = 0.0

    def add_financial_income(self, amount: float) -> None:
        """배당 gross 또는 KR_FOREIGN 실현차익을 금융소득 풀에 가산."""
        self.ytd_financial_income += float(amount or 0.0)

    def add_us_gain(self, amount: float) -> None:
        """US_DIRECT 실현 차익(양도소득) 누적. 음수=손익통산 공제 여유."""
        self.ytd_us_realized_gains += float(amount or 0.0)

    def finalize(self, extra_final_year_income: float = 0.0) -> dict:
        """마지막 연도 flush + (선택) 청산 KR_FOREIGN 미실현차익을 마지막 연도에 가산."""
        if self.year is not None:
            self.financial_income_by_year[self.year] = (
                self.ytd_financial_income + float(extra_final_year_income or 0.0)
            )
        return dict(self.financial_income_by_year)
