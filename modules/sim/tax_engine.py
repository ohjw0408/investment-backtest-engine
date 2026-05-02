"""
tax_engine.py
세금 계산 엔진

계좌 유형: general(일반), isa(ISA), pension(연금)
자산 지역: KR(국내), US(미국), CRYPTO(암호화폐), GOLD(금현물)
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional


# ── 누진세율표 ──────────────────────────────────────────────────────────────
PROGRESSIVE_TAX_BRACKETS = [
    (12_000_000,   0.06),
    (46_000_000,   0.15),
    (88_000_000,   0.24),
    (150_000_000,  0.35),
    (300_000_000,  0.38),
    (500_000_000,  0.40),
    (float('inf'), 0.42),
]

def calc_progressive_tax(income: float) -> float:
    """누진세율 적용 세금 계산"""
    tax = 0.0
    prev = 0.0
    for bracket, rate in PROGRESSIVE_TAX_BRACKETS:
        if income <= prev:
            break
        taxable = min(income, bracket) - prev
        tax += taxable * rate
        prev = bracket
    return tax


# ── 연금소득세율 (나이별) ──────────────────────────────────────────────────
def pension_tax_rate(age: int) -> float:
    if age >= 80: return 0.033
    if age >= 70: return 0.044
    return 0.055


@dataclass
class UserProfile:
    """사용자 소득/공제 정보"""
    earned_income:        float = 0.0   # 근로/사업소득
    other_financial_income: float = 0.0 # 기타 금융소득 (이자 등)
    age:                  int   = 40    # 나이 (연금 수령 세율용)
    dependents:           int   = 0     # 부양가족 수

    def marginal_rate(self) -> float:
        """근로소득 기준 한계세율"""
        tax_base = max(0, self.earned_income)
        prev_bracket = 0.0
        for bracket, rate in PROGRESSIVE_TAX_BRACKETS:
            if tax_base <= bracket:
                return rate
            prev_bracket = bracket
        return 0.42


@dataclass
class TaxState:
    """연간 세금 누적 상태"""
    year:               int   = 0
    total_financial_income: float = 0.0   # 연간 금융소득 누적
    total_capital_gain: float = 0.0       # 연간 양도차익 누적
    withheld_tax:       float = 0.0       # 원천징수 납부 세금
    comprehensive_tax:  float = 0.0       # 종합과세 추가 세금


class TaxEngine:
    """
    세금 계산 엔진

    사용법:
        engine = TaxEngine(account_type='general', profile=UserProfile(earned_income=50_000_000))
        net_div = engine.apply_dividend_tax(gross_div, region='US', year=2024)
    """

    COMPREHENSIVE_THRESHOLD = 20_000_000  # 금융소득 종합과세 기준 2000만원
    OVERSEAS_CAPITAL_DEDUCTION = 2_500_000  # 해외주식 양도세 기본공제 250만원

    def __init__(
        self,
        account_type: str = 'general',   # 'general', 'isa', 'pension'
        isa_type:     str = 'general',   # 'general'(200만), 'preferential'(400만)
        profile:      Optional[UserProfile] = None,
        tax_loss_harvesting: bool = False,  # 절세매매 여부
    ):
        self.account_type        = account_type
        self.isa_type            = isa_type
        self.profile             = profile or UserProfile()
        self.tax_loss_harvesting = tax_loss_harvesting

        # 연간 상태 추적
        self._states: dict[int, TaxState] = {}

    def _get_state(self, year: int) -> TaxState:
        if year not in self._states:
            self._states[year] = TaxState(year=year)
        return self._states[year]

    # ── 배당소득세 ──────────────────────────────────────────────────────────
    def apply_dividend_tax(self, gross_div: float, region: str, year: int) -> float:
        """
        배당금에서 세금 차감 후 실수령액 반환
        region: 'KR', 'US', 'CRYPTO', 'GOLD'
        """
        if gross_div <= 0:
            return 0.0

        # 금현물, 암호화폐는 배당 없음
        if region in ('GOLD', 'CRYPTO'):
            return gross_div

        # ISA: 운용 중 비과세
        if self.account_type == 'isa':
            return gross_div

        # 연금: 과세 이연
        if self.account_type == 'pension':
            return gross_div

        # 일반 계좌: 원천징수
        if region == 'US':
            rate = 0.15    # 미국 원천징수 15%
        else:
            rate = 0.154   # 국내 15.4% (소득세 14% + 지방세 1.4%)

        tax = gross_div * rate
        state = self._get_state(year)
        state.withheld_tax += tax
        state.total_financial_income += gross_div

        return gross_div - tax

    # ── 금융소득 종합과세 (연말 정산) ──────────────────────────────────────
    def calc_comprehensive_tax(self, year: int) -> float:
        """
        연간 금융소득이 2000만원 초과 시 종합과세 추가 세금 계산
        반환값: 추가 납부 세금 (이미 낸 원천징수 차감 후)
        """
        if self.account_type != 'general':
            return 0.0

        state = self._get_state(year)
        total = state.total_financial_income

        if total <= self.COMPREHENSIVE_THRESHOLD:
            return 0.0

        # 초과분을 근로소득에 합산
        excess = total - self.COMPREHENSIVE_THRESHOLD
        combined_income = self.profile.earned_income + excess

        # 합산 후 세금 - 근로소득만의 세금 = 초과분 세금
        tax_combined = calc_progressive_tax(combined_income)
        tax_base     = calc_progressive_tax(self.profile.earned_income)
        additional   = tax_combined - tax_base

        # 이미 낸 원천징수 중 초과분 비율만큼 차감
        excess_ratio = excess / total if total > 0 else 0
        already_paid = state.withheld_tax * excess_ratio

        result = max(0.0, additional - already_paid)
        state.comprehensive_tax = result
        return result

    # ── 양도소득세 ──────────────────────────────────────────────────────────
    def calc_capital_gain_tax(self, gain: float, region: str, year: int) -> float:
        """
        양도차익에 대한 세금 계산
        gain: 양도차익 (매도가 - 매수가)
        """
        if gain <= 0:
            return 0.0

        # ISA, 연금: 비과세 or 과세이연
        if self.account_type in ('isa', 'pension'):
            return 0.0

        # 금현물: 비과세
        if region == 'GOLD':
            return 0.0

        # 국내 주식/ETF: 일반 투자자 비과세
        if region == 'KR':
            return 0.0

        # 해외 주식/ETF, 암호화폐: 연 250만 공제 후 22%
        state = self._get_state(year)
        state.total_capital_gain += gain

        total_gain = state.total_capital_gain
        taxable = max(0.0, total_gain - self.OVERSEAS_CAPITAL_DEDUCTION)

        # 이미 납부한 양도세 차감
        already_taxed_gain = max(0.0, total_gain - gain)
        already_paid = max(0.0, already_taxed_gain - self.OVERSEAS_CAPITAL_DEDUCTION) * 0.22

        return max(0.0, taxable * 0.22 - already_paid)

    # ── 절세매매 ────────────────────────────────────────────────────────────
    def calc_tax_loss_harvest(self, gains: dict, losses: dict, year: int) -> float:
        """
        연말 손익통산 절세
        gains:  {ticker: 차익}
        losses: {ticker: 손실(양수)}
        반환값: 절세 금액
        """
        if not self.tax_loss_harvesting:
            return 0.0
        if self.account_type != 'general':
            return 0.0

        total_gain = sum(gains.values())
        total_loss = sum(losses.values())
        net_gain   = max(0.0, total_gain - total_loss)
        taxable    = max(0.0, net_gain - self.OVERSEAS_CAPITAL_DEDUCTION)
        return taxable * 0.22

    # ── ISA 만기 정산 ───────────────────────────────────────────────────────
    def calc_isa_maturity_tax(self, total_profit: float) -> float:
        """
        ISA 만기 시 세금 계산
        서민형: 400만 비과세, 초과분 9.9%
        일반형: 200만 비과세, 초과분 9.9%
        """
        deduction = 4_000_000 if self.isa_type == 'preferential' else 2_000_000
        taxable = max(0.0, total_profit - deduction)
        return taxable * 0.099

    def calc_isa_early_termination_tax(self, total_profit: float) -> float:
        """ISA 중도해지 시 일반과세 적용"""
        return total_profit * 0.154 if total_profit > 0 else 0.0

    # ── 연금 수령 세금 ──────────────────────────────────────────────────────
    def calc_pension_withdrawal_tax(self, amount: float, is_annuity: bool = True) -> float:
        """
        연금 수령 세금
        is_annuity=True:  연금 형태 수령 → 연금소득세 3.3~5.5%
        is_annuity=False: 중도해지/일시금 → 기타소득세 16.5%
        """
        if not is_annuity:
            return amount * 0.165  # 중도해지: 기타소득세 16.5%
        rate = pension_tax_rate(self.profile.age)
        return amount * rate

    # ── 연간 요약 ────────────────────────────────────────────────────────────
    def get_year_summary(self, year: int) -> dict:
        state = self._get_state(year)
        comprehensive = self.calc_comprehensive_tax(year)
        return {
            "year":               year,
            "total_financial_income": state.total_financial_income,
            "withheld_tax":       state.withheld_tax,
            "comprehensive_tax":  comprehensive,
            "total_tax":          state.withheld_tax + comprehensive,
        }