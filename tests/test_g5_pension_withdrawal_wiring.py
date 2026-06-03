"""
tests/test_g5_pension_withdrawal_wiring.py
G5-C C2 (L12-②): 사적연금 분리과세를 인출 gross-up·표시에 배선.

기존 _calc_gross_withdrawal/_calc_pension_tax_by_age는 pension_effective_rate
(하이브리드=1500이하 저율+초과분만 16.5%, BUG-PENSION-1)를 썼다. C2는
pension_separate_tax_annual(1500 이하 나이별 3.3~5.5%, 초과 시 전액 16.5%,
오너결정)로 교체. 여기선 그 배선을 검증(순수함수 정확값은 test_pension_withdrawal_tax).

gross-up: net 수령 위해 계좌서 빼는 gross = net/(1−실효율). 실효율은 분리과세 기준.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from modules.retirement.withdrawal_analyzer import WithdrawalAnalyzer
from modules.tax.base_tax import TaxEngine


def _wa(monthly, current_age, wd_years=5):
    return WithdrawalAnalyzer(
        portfolio_engine=None, tickers=["X"], strategy_factory=lambda: None,
        data_start="2000-01-01", data_end="2030-01-01",
        withdrawal_years=wd_years, monthly_withdrawal=monthly, initial_capital=0,
        tax_engine=TaxEngine({"age": current_age}), account_type="연금저축",
        current_age=current_age, accumulation_years=0,
    )


def test_c2_grossup_age_brackets_under_threshold():
    """연 1500만 이하: 나이별 3.3~5.5% 분리과세로 gross-up. (55→5.5·70→4.4·80→3.3)"""
    # net 100만/월(연 1200만 < 1500만)
    assert abs(_wa(1_000_000, 60)._calc_gross_withdrawal() - 1_000_000 / (1 - 0.055)) <= 1
    assert abs(_wa(1_000_000, 70)._calc_gross_withdrawal() - 1_000_000 / (1 - 0.044)) <= 1
    assert abs(_wa(1_000_000, 80)._calc_gross_withdrawal() - 1_000_000 / (1 - 0.033)) <= 1


def test_c2_grossup_over_threshold_flat_165():
    """연 1500만 초과: 전액 16.5% 분리과세(오너결정·전액) — 나이 무관."""
    # net 150만/월(연 1800만 > 1500만)
    g60 = _wa(1_500_000, 60)._calc_gross_withdrawal()
    g80 = _wa(1_500_000, 80)._calc_gross_withdrawal()
    assert abs(g60 - 1_500_000 / (1 - 0.165)) <= 1
    assert abs(g80 - 1_500_000 / (1 - 0.165)) <= 1, "1500만 초과는 나이 무관 전액 16.5%"


def test_c2_pension_tax_info_reflects_separate_tax():
    """pension_tax_info 표시: 1500만 초과면 전 구간 16.5%, 이하면 나이별 저율."""
    # 이하(연 1200만): 60세 구간 5.5%
    info_low = _wa(1_000_000, 60, wd_years=5)._calc_pension_tax_by_age()
    assert info_low["over_threshold"] is False
    assert abs(info_low["brackets"][0]["rate"] - 0.055) <= 1e-4

    # 초과(연 1800만): 전 구간 16.5% (나이 60→80 걸쳐도)
    info_hi = _wa(1_500_000, 60, wd_years=30)._calc_pension_tax_by_age()
    assert info_hi["over_threshold"] is True
    for b in info_hi["brackets"]:
        assert abs(b["rate"] - 0.165) <= 1e-4, f"초과인데 {b['age_from']}세 구간 rate={b['rate']}"


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
