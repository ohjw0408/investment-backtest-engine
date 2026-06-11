"""절세액 P3 — 인출기(가구 디큐뮬레이션) 절세 3종 결정론 검증 (L-SAVE-WD).

핵심 규약(절세액표시_plan.md P3):
- 위탁가정 = 세전 배당 + 실현차익(인출·리밸 매도)을 위탁 세율로. 미실현 미가산
  (wd end_value는 무청산 gross — 양쪽 다 청산 제외해야 위탁 불변식 유지).
- 실제 = 배당세 + 양도세 + 연금소득세. 절세 = max(0, 가정 − 실제).
- 신규 메커니즘 = sell_with_tax 직접호출(인출 매도) 위탁가정 누적
  (execute_orders 경로는 기존 _accrue와 이중집계 금지 — L-SAVE 26종이 회귀 가드).
"""
import pandas as pd
import pytest

from modules.tax.base_tax import TaxEngine
from modules.retirement.multi_account_withdrawal import simulate_household_window

TKR = "WDTEST"  # isalpha → US_DIRECT 기본 분류
USER = {"age": 65, "earned_income": 0, "isa_type": "general"}


def _monthly_prices(n_months: int, price: float = 10_000.0, div_at: dict | None = None):
    """월초(MS) 달력, flat 가격. div_at = {date_index: 주당 배당}."""
    dates = pd.date_range("2020-01-01", periods=n_months, freq="MS")
    div = [0.0] * n_months
    for i, amt in (div_at or {}).items():
        div[i] = amt
    px = pd.DataFrame({"close": price, "dividend": div}, index=dates)
    return {TKR: px}, list(dates)


def _acct(aid, atype, value, cost_basis=None):
    return {
        "account_id": aid, "type": atype, "value": value,
        "cost_basis": cost_basis, "target_weights": {TKR: 1.0},
        "rebal_mode": "none",
    }


# ── 1) 위탁 불변식: 인출 매도 실현차익 — 가정 == 실제 → 절세 0 ──────────
def test_wd_brokerage_invariant_with_gains():
    """위탁 1억(취득 6천만, 차익 4천만), 월 100만 인출 2년.
    인출 매도 실현차익의 위탁가정(연 250만 공제 22%) == 실제 sell_with_tax 과세
    → 절세 정확히 0. (신규 sell_with_tax 누적이 실제 과세와 일치함을 증명)"""
    price_data, dates = _monthly_prices(25)
    r = simulate_household_window(
        [_acct(0, "위탁", 100_000_000, cost_basis=60_000_000)],
        price_data, dates, 1_000_000,
        tax_engine=TaxEngine(USER), withdrawal_start_age=65,
    )
    a = r["per_account"][0]
    assert a["brokerage_assumed_tax"] > 0          # 차익 실현 있었음
    assert a["tax_saving"] == pytest.approx(0, abs=1)
    assert a["actual_tax"] == pytest.approx(a["brokerage_assumed_tax"], abs=1)


# ── 2) 위탁 차익 0: 가정 0 · 실제 0 · 절세 0 ───────────────────────────
def test_wd_brokerage_zero_gain_all_zero():
    price_data, dates = _monthly_prices(13)
    r = simulate_household_window(
        [_acct(0, "위탁", 50_000_000, cost_basis=50_000_000)],
        price_data, dates, 500_000,
        tax_engine=TaxEngine(USER), withdrawal_start_age=65,
    )
    a = r["per_account"][0]
    assert a["brokerage_assumed_tax"] == pytest.approx(0, abs=1)
    assert a["actual_tax"] == pytest.approx(0, abs=1)
    assert a["tax_saving"] == pytest.approx(0, abs=1)


# ── 3) 연금 단독: 실제 = 연금소득세 손계산, 절세 0 하한 ─────────────────
def test_wd_pension_actual_tax_hand_calc():
    """연금저축 2억, 월 net 100만 × 12회(13개월 달력, 첫 달 무인출).
    연 추정 1,200만 ≤ 1,500만 → 65세 5.5% 분리과세.
    월 연금세 = 100만×r/(1−r) = 58,201.06원 → 12회 = 698,412.70원.
    위탁가정 = 0(배당·실현차익 없음) → 절세 = max(0, 0−실제) = 0."""
    price_data, dates = _monthly_prices(13)
    r = simulate_household_window(
        [_acct(0, "연금저축", 200_000_000)],
        price_data, dates, 1_000_000,
        tax_engine=TaxEngine(USER), withdrawal_start_age=65,
    )
    a = r["per_account"][0]
    rate = 0.055
    expected_monthly = 1_000_000 * rate / (1 - rate)
    assert r["total_pension_tax"] == pytest.approx(expected_monthly * 12, abs=1)
    assert a["actual_tax"] == pytest.approx(expected_monthly * 12, abs=1)
    assert a["brokerage_assumed_tax"] == pytest.approx(0, abs=1)
    assert a["tax_saving"] == pytest.approx(0, abs=1)


# ── 4) ISA + 배당: 절세 = 세전배당 × 15.4% (KR_FOREIGN) ────────────────
def test_wd_isa_dividend_saving_hand_calc(monkeypatch):
    """ISA 5천만(5,000주@1만), 둘째 달에 주당 100원 배당(그 날 보유 5,000주).
    ISA 배당 비과세·인출 비과세 → 실제 0. 위탁가정 = 500,000×15.4% = 77,000원 = 절세."""
    monkeypatch.setattr(TaxEngine, "classify_asset", lambda self, t: "KR_FOREIGN")
    price_data, dates = _monthly_prices(13, div_at={1: 100.0})
    r = simulate_household_window(
        [_acct(0, "ISA", 50_000_000)],
        price_data, dates, 100_000,
        tax_engine=TaxEngine(USER), withdrawal_start_age=65,
    )
    a = r["per_account"][0]
    assert a["actual_tax"] == pytest.approx(0, abs=1)
    assert a["brokerage_assumed_tax"] == pytest.approx(77_000, abs=1)
    assert a["tax_saving"] == pytest.approx(77_000, abs=1)


# ── 5) 혼합(위탁+ISA): 위탁 절세 0 · ISA 절세 >0 · 드레인 순서 보존 ──────
def test_wd_mixed_brokerage_zero_isa_positive(monkeypatch):
    monkeypatch.setattr(TaxEngine, "classify_asset", lambda self, t: "KR_FOREIGN")
    price_data, dates = _monthly_prices(13, div_at={1: 100.0})
    r = simulate_household_window(
        [_acct(0, "위탁", 30_000_000, cost_basis=20_000_000),
         _acct(1, "ISA", 50_000_000)],
        price_data, dates, 500_000,
        tax_engine=TaxEngine(USER), withdrawal_start_age=65,
    )
    by_type = {a["type"]: a for a in r["per_account"]}
    assert by_type["위탁"]["tax_saving"] == pytest.approx(0, abs=1)
    assert by_type["ISA"]["tax_saving"] > 0
    # 위탁 먼저 소진(드레인 순서) — 위탁만 실현차익 발생
    assert by_type["위탁"]["brokerage_assumed_tax"] > 0


# ── 6) 세금 OFF: savings 필드 부재 (기존 동작 무변경) ───────────────────
def test_wd_tax_off_no_savings_fields():
    price_data, dates = _monthly_prices(13)
    r = simulate_household_window(
        [_acct(0, "위탁", 50_000_000)],
        price_data, dates, 500_000,
        tax_engine=None, withdrawal_start_age=65,
    )
    assert "tax_saving" not in r["per_account"][0]
