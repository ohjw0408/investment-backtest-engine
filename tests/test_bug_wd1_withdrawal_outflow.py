"""
BUG-WD-1: WithdrawalEngine 인출 유출 누락 (~2배 과소인출).

매도로 인출 충당 시 proceeds를 cash에 주차하고 인출액을 빼지 않아,
매도월엔 자산→cash 이동만 일어나고 실제 유출은 다음달 주차 cash 소비 때만 발생.
→ 격월로만 유출 → 유효 인출률 ≈ 50%.

수정 후: 매달 withdrawal_amount(인플레이션 반영)가 실제로 포트폴리오를 떠나야 함.
위탁 CG세는 그와 별개로 추가 유출(retiree net + 정부 세금).
"""
import sys
import os
import datetime
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from modules.core.portfolio import Portfolio
from modules.simulation.withdrawal_engine import WithdrawalEngine


def _run_months(p, amount, n, price=100.0, inflation=0.0):
    we = WithdrawalEngine()
    lm = None
    for m in range(n):
        d = datetime.date(2020 + m // 12, m % 12 + 1, 1)
        lm = we.process(
            p, amount, {"A": price}, {"A": 1.0},
            date=d, last_month=lm, elapsed_months=m, inflation=inflation,
        )


def test_flat_price_full_outflow():
    """평탄가격·세금없음: 12개월 × 1000 인출 → 정확히 12,000 유출."""
    p = Portfolio(12_000.0)
    p.buy("A", 120, 100.0)  # 자산 12,000, cash 0
    start = p.total_value({"A": 100.0})
    _run_months(p, 1_000.0, 12)
    removed = start - p.total_value({"A": 100.0})
    assert abs(removed - 12_000.0) <= 1.0, f"유출 {removed} != 12,000 (의도)"


def test_existing_cash_consumed_first():
    """기존 cash 우선 소비 후 매도 — 합계 유출 정확."""
    p = Portfolio(15_000.0)
    p.buy("A", 100, 100.0)  # 자산 10,000, cash 5,000
    start = p.total_value({"A": 100.0})  # 15,000
    _run_months(p, 1_000.0, 12)
    removed = start - p.total_value({"A": 100.0})
    assert abs(removed - 12_000.0) <= 1.0, f"유출 {removed} != 12,000"


def test_inflation_outflow():
    """인플레이션 반영 인출 — 누적 유출 = Σ 월별 inflated."""
    p = Portfolio(100_000.0)
    p.buy("A", 1000, 100.0)
    start = p.total_value({"A": 100.0})
    infl = 0.03
    _run_months(p, 1_000.0, 24, inflation=infl)
    expected = sum(1_000.0 * (1 + infl / 12) ** m for m in range(24))
    removed = start - p.total_value({"A": 100.0})
    assert abs(removed - expected) <= 2.0, f"유출 {removed} != {expected}"


def test_depletion_floors_at_zero():
    """자산 부족 시 음수 없이 0 바닥 — 생존 실패 케이스."""
    p = Portfolio(3_000.0)
    p.buy("A", 30, 100.0)  # 자산 3,000
    _run_months(p, 1_000.0, 12)  # 의도 12,000 > 자산
    assert p.total_value({"A": 100.0}) >= -1.0
    assert p.total_value({"A": 100.0}) <= 1.0  # 전액 소진


if __name__ == "__main__":
    test_flat_price_full_outflow()
    test_existing_cash_consumed_first()
    test_inflation_outflow()
    test_depletion_floors_at_zero()
    print("PASS")
