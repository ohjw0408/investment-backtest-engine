"""
tests/test_pension_withdrawal_tax.py
G5-C 토대: 사적연금 연 인출액 분리과세(전액 16.5% 규칙) 정확값 검증.

오너 결정 2026-06-03: 1500만 초과 시 전액 16.5%(초과분만 아님, 현행 선택분리과세).
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from modules.tax.base_tax import TaxEngine

_TE = TaxEngine({"earned_income": 0, "age": 40})


def test_under_threshold_age55_band():
    """연 1,200만(≤1500만), 나이 60 → 5.5% = 660,000."""
    assert abs(_TE.pension_separate_tax_annual(12_000_000, 60) - 660_000) < 1.0


def test_under_threshold_age70_band():
    """연 1,200만, 나이 72 → 4.4% = 528,000."""
    assert abs(_TE.pension_separate_tax_annual(12_000_000, 72) - 528_000) < 1.0


def test_under_threshold_age80_band():
    """연 1,200만, 나이 82 → 3.3% = 396,000."""
    assert abs(_TE.pension_separate_tax_annual(12_000_000, 82) - 396_000) < 1.0


def test_at_threshold_uses_low_rate():
    """경계 정확히 1,500만(≤) → 저율 5.5% = 825,000."""
    assert abs(_TE.pension_separate_tax_annual(15_000_000, 60) - 825_000) < 1.0


def test_over_threshold_full_16_5():
    """연 1,800만(>1500만) → 전액 16.5% = 2,970,000 (초과분만 아님)."""
    assert abs(_TE.pension_separate_tax_annual(18_000_000, 60) - 2_970_000) < 1.0


def test_just_over_threshold_full_rate():
    """1,500만 + 12원(초과) → 전액 16.5%(저율 아님). 경계 전환 확인."""
    annual = 15_000_012
    assert abs(_TE.pension_separate_tax_annual(annual, 60) - annual * 0.165) < 1.0
    # 저율(5.5%)이었다면 825,000.66 — 전액 16.5%(2,475,002)와 명확히 다름
    assert _TE.pension_separate_tax_annual(annual, 60) > 2_000_000


def test_zero():
    assert _TE.pension_separate_tax_annual(0, 60) == 0.0


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
