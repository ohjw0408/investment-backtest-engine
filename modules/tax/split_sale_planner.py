"""
modules/tax/split_sale_planner.py
────────────────────────────────────────────────────────────────────────────────
KR_FOREIGN 미실현 이익 분할 매도 절세 계획 계산기 (Phase 2e)

배경:
  국내상장 해외 ETF(KR_FOREIGN) 청산 이익은 배당소득세(15.4% 분리과세)이나,
  연간 금융소득 합계가 2천만원 초과 시 종합과세 적용 → 최대 49.5%.
  n년에 걸쳐 분할 매도하면 각 연도의 금융소득을 2천만원 미만으로 유지 가능.

주의:
  - 시뮬레이션 end_value 계산 변경 없음. 이 모듈은 "절세 계획" 참고용 패널용.
  - 실제 세법 해석은 세무사와 확인 필요.
"""

from __future__ import annotations


def _comprehensive_tax(taxable_income: float) -> float:
    """종합소득세 계산 (지방소득세 포함). base_tax.py와 동일 로직."""
    LOCAL_TAX_MULT = 1.1
    BRACKETS = [
        (14_000_000,   0.06,        0),
        (50_000_000,   0.15,  1_260_000),
        (88_000_000,   0.24,  5_760_000),
        (150_000_000,  0.35, 15_440_000),
        (300_000_000,  0.38, 19_940_000),
        (500_000_000,  0.40, 25_940_000),
        (1_000_000_000, 0.42, 35_940_000),
        (float("inf"), 0.45, 65_940_000),
    ]
    if taxable_income <= 0:
        return 0.0
    for bracket, rate, deduction in BRACKETS:
        if taxable_income <= bracket:
            return (taxable_income * rate - deduction) * LOCAL_TAX_MULT
    return (taxable_income * 0.45 - 65_940_000) * LOCAL_TAX_MULT


_DIVIDEND_THRESHOLD = 20_000_000


def _year_tax(
    gain_this_year: float,
    other_financial_income: float,
    earned_income: float,
) -> float:
    """
    단일 연도 기준 KR_FOREIGN 이익의 세금 계산.

    Parameters
    ----------
    gain_this_year          : 이 연도에 실현할 KR_FOREIGN 이익
    other_financial_income  : 이 연도의 기타 금융소득 (이자·배당 등)
    earned_income           : 근로/사업소득
    """
    total_fin = gain_this_year + other_financial_income

    if total_fin <= _DIVIDEND_THRESHOLD:
        # 2천만 이하: 15.4% 분리과세
        return gain_this_year * 0.154

    # 2천만 초과: 임계값 아래 부분 15.4%, 초과 부분 종합과세
    below = max(0.0, _DIVIDEND_THRESHOLD - other_financial_income)
    above = gain_this_year - below

    tax = below * 0.154

    if above > 0:
        # 종합과세 초과분: 종합소득세 증분 - 이미 원천징수된 15.4% 크레딧
        prev_fin = max(0.0, other_financial_income - _DIVIDEND_THRESHOLD)
        curr_fin = prev_fin + above
        gross_extra = (
            _comprehensive_tax(earned_income + curr_fin)
            - _comprehensive_tax(earned_income + prev_fin)
        )
        # 초과 부분에 이미 원천징수된 15.4% 공제
        withheld_on_above = above * 0.154
        net_extra = max(0.0, gross_extra - withheld_on_above)
        tax += withheld_on_above + net_extra   # 원천징수 + 추가납부

    return tax


def compute_split_sale_plan(
    kr_foreign_gain: float,
    earned_income: float,
    other_financial_income: float = 0.0,
    split_years: int = 5,
) -> dict:
    """
    KR_FOREIGN 미실현 이익 n년 균등 분할 매도 시 절세 시나리오.

    Parameters
    ----------
    kr_foreign_gain         : 청산 시 KR_FOREIGN 미실현 이익 합계
    earned_income           : 유저 근로/사업소득
    other_financial_income  : 기존 금융소득 (이자·배당 등)
    split_years             : 분할 매도 연수 (참고용, optimal_years와 다를 수 있음)

    Returns
    -------
    dict:
        lump_sum_tax    : int — 일괄 청산 시 세금
        split_tax       : int — split_years년 분할 시 총 세금
        saving          : int — lump_sum_tax - split_tax
        optimal_years   : int — 세금 최소화 연수 (1~20년 탐색)
        optimal_tax     : int — optimal_years 적용 시 총 세금
        plan_by_year    : dict[str, int] — {n: total_tax} n=1..20
        over_threshold  : bool — 일괄 시 2천만 초과 여부
    """
    if kr_foreign_gain <= 0:
        return {
            "lump_sum_tax": 0, "split_tax": 0, "saving": 0,
            "optimal_years": 1, "optimal_tax": 0,
            "plan_by_year": {}, "over_threshold": False,
        }

    # 일괄 청산 세금
    lump_sum_tax   = _year_tax(kr_foreign_gain, other_financial_income, earned_income)
    over_threshold = (kr_foreign_gain + other_financial_income) > _DIVIDEND_THRESHOLD

    # 1~20년 분할 시나리오
    plan_by_year: dict[str, int] = {}
    for n in range(1, 21):
        gain_per_year   = kr_foreign_gain / n
        tax_per_year    = _year_tax(gain_per_year, other_financial_income, earned_income)
        plan_by_year[str(n)] = round(tax_per_year * n)

    optimal_years = min(plan_by_year, key=lambda k: plan_by_year[k])
    optimal_tax   = plan_by_year[optimal_years]
    split_tax     = plan_by_year.get(str(split_years), round(lump_sum_tax))

    return {
        "lump_sum_tax":  round(lump_sum_tax),
        "split_tax":     split_tax,
        "saving":        round(lump_sum_tax) - split_tax,
        "optimal_years": int(optimal_years),
        "optimal_tax":   optimal_tax,
        "plan_by_year":  plan_by_year,
        "over_threshold": over_threshold,
    }
