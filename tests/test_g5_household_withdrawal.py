"""G5-C C3.1: 가구 인출 오케스트레이터 단위 검증 (손계산 ±1원).

household_withdraw — 월 가구 net 인출액을 위탁→ISA→연금/IRP 순 소진,
계좌별 인출세(위탁 CG sell_with_tax·연금 분리과세 gross-up) 정확.
"""
import sys
import os
import datetime
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from modules.core.portfolio import TaxTrackedPortfolio
from modules.execution.order_executor import TaxedOrderExecutor
from modules.tax.base_tax import TaxEngine
from modules.tax.session import TaxSessionState
from modules.retirement.household_withdrawal import household_withdraw

CODE = "069500"   # 국내 ETF — CG 비과세 (순수 인출 메커니즘 검증용)
KRF  = "458730"   # 국내상장 해외ETF — 15.4% 양도세
PX   = {CODE: 100.0}
DATE = datetime.date(2030, 1, 1)


def _acct(account_id, atype, code, qty, price, *, tax_engine=None):
    pf = TaxTrackedPortfolio(qty * price)
    pf.buy(code, qty, price)  # 자산 qty*price, cash 0
    ex = (
        TaxedOrderExecutor(tax_engine, atype, session=TaxSessionState())
        if tax_engine is not None else None
    )
    return {
        "account_id": account_id, "type": atype,
        "portfolio": pf, "executor": ex, "target_weights": {code: 1.0},
    }


# ── 1. 소진 순서 위탁→ISA→연금 + 금액 정확 (세금없음) ──────────────
def test_drain_order_and_amounts():
    A = _acct(0, "위탁", CODE, 50, 100.0)     # 5,000
    B = _acct(1, "ISA", CODE, 50, 100.0)      # 5,000
    C = _acct(2, "연금저축", CODE, 50, 100.0)  # 5,000
    res = household_withdraw([C, B, A], 8_000.0, PX, DATE)  # 입력 순서 뒤섞어 정렬 검증

    assert res["delivered_net"] == 8_000.0
    assert res["shortfall"] == 0.0
    assert res["depleted"] is False
    # 위탁 전액(5,000) → ISA 일부(3,000) → 연금 미사용
    assert abs(A["portfolio"].total_value(PX) - 0.0) <= 1.0
    assert abs(B["portfolio"].total_value(PX) - 2_000.0) <= 1.0
    assert abs(C["portfolio"].total_value(PX) - 5_000.0) <= 1.0
    # per_account 순서·금액
    assert [p["account_id"] for p in res["per_account"]] == [0, 1]
    assert res["per_account"][0]["withdrawn_net"] == 5_000.0
    assert res["per_account"][1]["withdrawn_net"] == 3_000.0


# ── 2. 연금 gross-up: 1500만 이하 나이별(70세 4.4%) ───────────────
def test_pension_grossup_under_threshold():
    te = TaxEngine({"earned_income": 0, "age": 70})
    P = _acct(0, "연금저축", CODE, 100_000, 100.0, tax_engine=te)  # 10,000,000
    start = P["portfolio"].total_value(PX)
    res = household_withdraw([P], 1_000_000.0, PX, DATE, tax_engine=te, age=70)

    assert abs(res["pension_rate"] - 0.044) <= 1e-9
    # gross = 1,000,000 / 0.956 = 1,046,025.10 ; tax = 46,025.10
    assert abs(res["per_account"][0]["pension_tax"] - 46_025.10) <= 1.0
    assert res["delivered_net"] == 1_000_000.0
    dropped = start - P["portfolio"].total_value(PX)
    assert abs(dropped - 1_046_025.10) <= 100.0  # 주당 100원 라운딩 허용


# ── 3. 연금 1500만 초과 → 전액 16.5% (70세 무관) ─────────────────
def test_pension_grossup_over_threshold_full_165():
    te = TaxEngine({"earned_income": 0, "age": 70})
    P = _acct(0, "연금저축", CODE, 100_000, 100.0, tax_engine=te)
    start = P["portfolio"].total_value(PX)
    res = household_withdraw([P], 2_000_000.0, PX, DATE, tax_engine=te, age=70)

    assert abs(res["pension_rate"] - 0.165) <= 1e-9
    # gross = 2,000,000 / 0.835 = 2,395,209.58 ; tax = 395,209.58
    assert abs(res["per_account"][0]["pension_tax"] - 395_209.58) <= 1.0
    dropped = start - P["portfolio"].total_value(PX)
    assert abs(dropped - 2_395_209.58) <= 100.0


# ── 4. 개인 합산 판정: 연금+IRP 합산 1500만 초과 → 둘 다 16.5% ────
def test_pension_aggregate_threshold_across_accounts():
    te = TaxEngine({"earned_income": 0, "age": 72})
    P1 = _acct(0, "연금저축", CODE, 5_000, 100.0, tax_engine=te)   # 500,000 (작음)
    P2 = _acct(1, "IRP", CODE, 100_000, 100.0, tax_engine=te)     # 10,000,000
    # 가구 net 1,300,000/월 → 연 합산 15,600,000 > 1,500만 → 전액 16.5%
    res = household_withdraw([P1, P2], 1_300_000.0, PX, DATE, tax_engine=te, age=72)

    assert abs(res["pension_rate"] - 0.165) <= 1e-9
    # 연금저축(P1) 우선 소진: net_cap = 500,000*(1-0.165)=417,500
    p1 = next(p for p in res["per_account"] if p["account_id"] == 0)
    p2 = next(p for p in res["per_account"] if p["account_id"] == 1)
    assert abs(p1["withdrawn_net"] - 417_500.0) <= 1.0
    assert abs(p2["withdrawn_net"] - (1_300_000.0 - 417_500.0)) <= 1.0
    # 두 계좌 모두 16.5% gross-up (tax/(net+tax) == 0.165)
    for p in (p1, p2):
        gross = p["withdrawn_net"] + p["pension_tax"]
        assert abs(p["pension_tax"] / gross - 0.165) <= 1e-6


# ── 5. 위탁 인출 CG 양도세 (BUG-TAX-2) 정확 + 인출분 유출 ──────────
def test_brokerage_withdrawal_cg_tax_exact():
    te = TaxEngine({"earned_income": 0, "age": 60})
    pf = TaxTrackedPortfolio(10_000.0)
    pf.buy(KRF, 100, 100.0)        # 취득가 100, 자산 10,000
    ex = TaxedOrderExecutor(te, "위탁", session=TaxSessionState())
    px = {KRF: 200.0}              # 200으로 상승 → 평가 20,000
    A = {"account_id": 0, "type": "위탁", "portfolio": pf,
         "executor": ex, "target_weights": {KRF: 1.0}}
    start = pf.total_value(px)
    res = household_withdraw([A], 1_000.0, px, DATE, tax_engine=te, age=60)

    # 5주 매도(@200=1,000), 차익 (200-100)*5=500, CG = 500*0.154 = 77
    assert abs(ex.total_cg_tax_paid - 77.0) <= 1.0
    assert res["delivered_net"] == 1_000.0
    # 인출분(1,000) 실제 유출 — 자산 5주 감소
    dropped = start - pf.total_value(px)
    assert abs(dropped - 1_000.0) <= 1.0


# ── 6. 고갈: 가구 인출 > 전 계좌 합산 → depleted + shortfall ────────
def test_depletion_flags_shortfall():
    A = _acct(0, "위탁", CODE, 30, 100.0)      # 3,000
    B = _acct(1, "연금저축", CODE, 20, 100.0)   # 2,000
    res = household_withdraw([A, B], 10_000.0, PX, DATE)  # 의도 10,000 > 5,000

    assert res["depleted"] is True
    assert res["shortfall"] > 0.0
    # 불변식: delivered + shortfall == net_need
    assert abs(res["delivered_net"] + res["shortfall"] - 10_000.0) <= 1.0
    # 전 계좌 소진
    assert abs(A["portfolio"].total_value(PX)) <= 1.0
    assert abs(B["portfolio"].total_value(PX)) <= 1.0


if __name__ == "__main__":
    for fn in [
        test_drain_order_and_amounts,
        test_pension_grossup_under_threshold,
        test_pension_grossup_over_threshold_full_165,
        test_pension_aggregate_threshold_across_accounts,
        test_brokerage_withdrawal_cg_tax_exact,
        test_depletion_flags_shortfall,
    ]:
        fn()
        print(f"PASS {fn.__name__}")
