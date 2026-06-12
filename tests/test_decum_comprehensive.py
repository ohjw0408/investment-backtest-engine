"""GAP-DECUM-COMP 검증: 은퇴 인출(decum) 중 금융소득 종합과세 배선.

감사(2026-06-09) 등록 당시 "위탁 배당 연 2천만 초과해도 종합과세 가산 안 함"으로
기록됐으나, C3.2(89c927a)부터 simulate_household_window가 TaxSessionState를
계좌 전체에 공유 — 위탁 배당 gross·KR_FOREIGN 인출매도 차익이 한 풀로 합산되어
after_tax_dividend/_calc_cg_tax가 2천만 초과분 종합과세를 가산한다.

여기서는 그 배선을 결정론으로 증명한다(순수함수 정확값은 test_phase2f_comprehensive):
1. 배당 풀 누적 → after_tax_dividend 순차 재현값과 종료값 등치 (초과·연도리셋 포함)
2. 임계 미만이면 플랫 15.4% 등치 (스퓨리어스 가산 없음)
3. 계좌 2개 합산이 임계를 넘으면 가구 합동 < 단독 합 (개인 합산 풀 증명)
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import numpy as np
import pandas as pd

from modules.core.portfolio import TaxTrackedPortfolio
from modules.execution.cash_allocator import CashAllocator
from modules.tax.base_tax import TaxEngine
from modules.retirement.multi_account_withdrawal import simulate_household_window

KRD = "069500"   # KR_DOMESTIC — 배당 15.4% 원천 + 종합과세 대상
KRF = "458730"   # KR_FOREIGN — 매매차익도 배당소득(풀 합산) 대상


def _div_frame(dates, price, monthly_div):
    """평탄가격 + 매월 1영업일 배당."""
    px = np.full(len(dates), price)
    df = pd.DataFrame(
        {"open": px, "high": px, "low": px, "close": px,
         "volume": 1.0, "dividend": 0.0, "split": 1.0},
        index=dates,
    )
    seen = set()
    div = np.zeros(len(dates))
    for i, d in enumerate(dates):
        key = (d.year, d.month)
        if key not in seen:
            seen.add(key)
            div[i] = monthly_div
    df["dividend"] = div
    return df


def _initial_qty(value, price):
    """엔진과 동일 경로(CashAllocator)로 초기 매수 수량 산출."""
    pf = TaxTrackedPortfolio(value)
    CashAllocator().allocate_cash(pf, {KRD: price}, {KRD: 1.0})
    return float(pf.positions[KRD].quantity)


def _acct(value, account_id=0):
    return {"account_id": account_id, "type": "위탁", "value": value,
            "target_weights": {KRD: 1.0}}


def _run(accounts, dates, data, tax_engine):
    return simulate_household_window(
        accounts, data, list(dates), 0.0,
        tax_engine=tax_engine, dividend_mode="hold",
    )


def _replay_net_dividends(te, events_gross):
    """TaxedDividendEngine 의도 동작 재현 — (year, gross) 순차, 연도별 풀 리셋."""
    total_net = 0.0
    ytd, cur_year = 0.0, None
    for year, gross in events_gross:
        if year != cur_year:
            cur_year, ytd = year, 0.0
        total_net += te.after_tax_dividend(gross, KRD, "위탁", ytd)
        ytd += gross
    return total_net


def test_decum_dividend_comprehensive_over_threshold():
    """연 배당 3천만(>2천만) + 근로 1억 → 종료값 = 시작 + 재현 net 합. 가산 실제 발생."""
    te = TaxEngine({"earned_income": 100_000_000, "age": 60})
    dates = pd.bdate_range("2030-01-01", "2031-12-31")   # 2개년 — 연도 풀 리셋 포함
    value, price = 10_000_000.0, 100.0
    qty = _initial_qty(value, price)
    div_ps = 25.0                                         # 월 gross = 25×qty ≈ 250만
    data = {KRD: _div_frame(dates, price, div_ps)}

    res = _run([_acct(value)], dates, data, te)

    events, seen = [], set()
    for d in dates:
        key = (d.year, d.month)
        if key not in seen:
            seen.add(key)
            events.append((d.year, div_ps * qty))
    expected_net = _replay_net_dividends(te, events)
    gross_sum = sum(g for _, g in events)

    end = res["combined_end_value"]
    assert abs(end - (value + expected_net)) <= 1.0, (
        f"종료값 {end} != 시작 {value} + 재현net {expected_net}"
    )
    # 종합과세 가산이 실제로 발생(연 3천만 > 2천만, 한계세율 > 15.4%)
    assert expected_net < gross_sum * (1 - 0.154) - 1_000.0


def test_decum_dividend_flat_under_threshold():
    """연 배당 120만(<2천만) → 플랫 15.4%만. 스퓨리어스 종합과세 없음."""
    te = TaxEngine({"earned_income": 100_000_000, "age": 60})
    dates = pd.bdate_range("2030-01-01", "2030-12-31")
    value, price = 10_000_000.0, 100.0
    qty = _initial_qty(value, price)
    div_ps = 1.0                                          # 연 gross = 1×qty×12 ≈ 120만
    data = {KRD: _div_frame(dates, price, div_ps)}

    res = _run([_acct(value)], dates, data, te)

    gross_sum = div_ps * qty * 12
    expected_net = gross_sum * (1 - 0.154)
    end = res["combined_end_value"]
    assert abs(end - (value + expected_net)) <= 1.0, (
        f"종료값 {end} != 시작 {value} + 플랫net {expected_net}"
    )


def test_decum_two_accounts_person_level_pooling():
    """계좌별 1,440만(각 <2천만) 합산 2,880만(>2천만) → 가구 합동 < 단독 합."""
    te = TaxEngine({"earned_income": 100_000_000, "age": 60})
    dates = pd.bdate_range("2030-01-01", "2030-12-31")
    value, price = 10_000_000.0, 100.0
    div_ps = 12.0                                         # 계좌당 연 ≈ 1,440만
    data = {KRD: _div_frame(dates, price, div_ps)}

    joint = _run([_acct(value, 0), _acct(value, 1)], dates, data, te)
    alone = _run([_acct(value, 0)], dates, data, te)

    joint_end = joint["combined_end_value"]
    sum_alone = 2 * alone["combined_end_value"]
    assert joint_end < sum_alone - 1_000.0, (
        f"개인 합산 풀 미작동 의심 — 합동 {joint_end} >= 단독합 {sum_alone}"
    )


def test_decum_krf_sale_gain_joins_dividend_pool():
    """KR_FOREIGN 인출매도 차익이 배당 풀과 합산 — 타계좌 배당이 임계를 채우면
    같은 매도차익의 세금이 커진다(_calc_cg_tax 세션 배선의 decum 레벨 증명)."""
    te = TaxEngine({"earned_income": 100_000_000, "age": 60})
    dates = pd.bdate_range("2030-01-01", "2030-12-31")

    # B(id 0, KRF, 가격 100→200 램프): 인출 전담 → 매도 실현차익 발생. 두 시뮬 동일.
    px = np.linspace(100.0, 200.0, len(dates))
    krf_df = pd.DataFrame(
        {"open": px, "high": px, "low": px, "close": px,
         "volume": 1.0, "dividend": 0.0, "split": 1.0},
        index=dates,
    )
    acct_b = {"account_id": 0, "type": "위탁", "value": 10_000_000.0,
              "target_weights": {KRF: 1.0}}

    # A(id 1, KRD 평탄가격): 배당만 — X는 연 2,400만(임계 초과), Y는 무배당.
    def _acct_a(div_ps):
        return {"account_id": 1, "type": "위탁", "value": 10_000_000.0,
                "target_weights": {KRD: 1.0}}, _div_frame(dates, 100.0, div_ps)

    def _run_case(div_ps):
        a, krd_df = _acct_a(div_ps)
        res = simulate_household_window(
            [acct_b, a], {KRF: krf_df, KRD: krd_df}, list(dates), 500_000.0,
            tax_engine=te, dividend_mode="hold",
        )
        return next(p for p in res["per_account"] if p["account_id"] == 0)

    b_with_div = _run_case(20.0)   # A 연 배당 ≈ 2,400만 → 풀 임계 초과
    b_no_div   = _run_case(0.0)

    # B의 actual_tax = B 양도세만(배당·연금 0) — 매도는 동일하므로 차이 = 종합과세 가산분.
    assert b_with_div["actual_tax"] > b_no_div["actual_tax"] + 1_000.0, (
        f"KRF 차익 풀 합산 미작동 의심 — with {b_with_div['actual_tax']} "
        f"<= without {b_no_div['actual_tax']}"
    )
