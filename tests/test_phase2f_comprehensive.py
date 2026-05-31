# -*- coding: utf-8 -*-
"""
Phase 2f 검증 — 금융소득 종합과세 정확도.

1) 청산 KR_FOREIGN 차익 + 그 해 배당 ytd 합산 종합과세 (오너 1.3억 케이스).
2) TaxedDividendEngine._ytd_income = other_financial_income 주입 + 연도 베이스라인.
3) 연도별 종합과세 대상 트래킹.
4) 회귀: KR_FOREIGN 소액(2천만 이하)은 기존 15.4% 그대로.

실행: python tests/test_phase2f_comprehensive.py
"""
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

from modules.tax.base_tax import TaxEngine
from modules.tax.account_tax import TaxedDividendEngine
from modules.tax.liquidation import apply_liquidation_tax
from modules.tax.split_sale_planner import _year_tax

THRESHOLD = 20_000_000
fails = []


def approx(a, b, tol=1.0):
    return abs(a - b) <= tol


# ── Fake portfolio (positions + unrealized_gain) ──
class _Pos:
    def __init__(self, qty): self.quantity = qty


class _FakePortfolio:
    def __init__(self, gains: dict):
        self.positions = {t: _Pos(1) for t in gains}
        self._gains = gains

    def unrealized_gain(self, ticker, price):
        return self._gains[ticker]


def _engine(earned=0):
    eng = TaxEngine({"earned_income": earned, "age": 40})
    eng.classify_asset = lambda t: "KR_FOREIGN"  # 강제 분류
    return eng


# ── 1) 청산 차익 + 배당 ytd 합산 종합과세 ──
def test_liquidation_combines_with_dividends():
    eng = _engine(earned=0)
    pf = _FakePortfolio({"KRF": 100_000_000})   # 청산 차익 1억
    last = {"KRF": 100.0}

    # ytd 배당 3천만 → 합산 1.3억 종합과세
    after = apply_liquidation_tax(
        end_value=1_000_000_000, portfolio=pf, last_prices=last,
        tax_engine=eng, account_type="위탁", total_contribution=0,
        ytd_financial_income=30_000_000,
    )
    tax_combined = 1_000_000_000 - after

    # 같은 입력의 _year_tax(분할=1=일괄)와 일치해야 함
    expected = _year_tax(100_000_000, 30_000_000, 0)
    if not approx(tax_combined, expected, tol=2.0):
        fails.append(f"1) 청산 합산세금 {tax_combined:.0f} != _year_tax {expected:.0f}")

    # 합산 종합과세는 flat 15.4%(1540만)보다 커야 함 (1.3억이 누진구간)
    if not (tax_combined > 100_000_000 * 0.154 + 1.0):
        fails.append(f"1) 합산세금 {tax_combined:.0f} 이 flat 15.4%({100_000_000*0.154:.0f}) 이하 — 합산 안 됨")


# ── 2) ytd=0 (배당 없음) 일 때는 1억 단독 종합과세 ──
def test_liquidation_no_dividends():
    eng = _engine(earned=0)
    pf = _FakePortfolio({"KRF": 100_000_000})
    after = apply_liquidation_tax(
        end_value=1_000_000_000, portfolio=pf, last_prices={"KRF": 100.0},
        tax_engine=eng, account_type="위탁", total_contribution=0,
        ytd_financial_income=0,
    )
    tax = 1_000_000_000 - after
    expected = _year_tax(100_000_000, 0, 0)
    if not approx(tax, expected, tol=2.0):
        fails.append(f"2) ytd0 세금 {tax:.0f} != {expected:.0f}")


# ── 3) 소액 회귀: 차익 1천만 + ytd 0 → flat 15.4% 유지 ──
def test_small_gain_flat():
    eng = _engine(earned=0)
    pf = _FakePortfolio({"KRF": 10_000_000})
    after = apply_liquidation_tax(
        end_value=100_000_000, portfolio=pf, last_prices={"KRF": 100.0},
        tax_engine=eng, account_type="위탁", total_contribution=0,
        ytd_financial_income=0,
    )
    tax = 100_000_000 - after
    if not approx(tax, 10_000_000 * 0.154, tol=2.0):
        fails.append(f"3) 소액 세금 {tax:.0f} != flat {10_000_000*0.154:.0f}")


# ── 4) _ytd_income 주입 + 연도 베이스라인 ──
def test_ytd_injection():
    eng = TaxEngine({"earned_income": 0})
    de = TaxedDividendEngine(base_engine=None, tax_engine=eng, account_type="위탁",
                             other_financial_income=19_000_000)
    if not approx(de._ytd_income, 19_000_000):
        fails.append(f"4) 초기 _ytd_income {de._ytd_income} != 1900만")


# ── 5) 연도별 트래킹 + 종합과세 대상 flag ──
def test_year_tracking():
    eng = TaxEngine({"earned_income": 0})
    de = TaxedDividendEngine(base_engine=None, tax_engine=eng, account_type="위탁",
                             other_financial_income=5_000_000)
    # 2023: 배당 1천만 → 총 1500만 (2천만 이하)
    de._current_year = 2023
    de._sim_div_this_year = 10_000_000
    # 2024로 전환(트래킹 기록 트리거) — process의 연도전환 로직 직접 호출 흉내
    de.financial_income_by_year[2023] = de.other_financial_income + de._sim_div_this_year
    de._current_year = 2024
    de._sim_div_this_year = 20_000_000   # 2024: 배당 2천만 → 총 2500만 (초과)
    fiby = de.finalize_year_tracking(extra_final_year_income=0)
    if fiby.get(2023) != 15_000_000 or fiby.get(2024) != 25_000_000:
        fails.append(f"5) 연도별 금융소득 {fiby} 기대 2023=1500만/2024=2500만")
    targets = sorted(y for y, v in fiby.items() if v > THRESHOLD)
    if targets != [2024]:
        fails.append(f"5) 종합과세 대상연도 {targets} != [2024]")


if __name__ == "__main__":
    for fn in [test_liquidation_combines_with_dividends, test_liquidation_no_dividends,
               test_small_gain_flat, test_ytd_injection, test_year_tracking]:
        fn()
    total = 5
    print(f"[Phase 2f] {total - len(fails)}/{total} PASS")
    for f in fails:
        print("  ✗", f)
    sys.exit(0 if not fails else 1)
