"""배당계산기 멀티계좌 (G5-E) — 정합 앵커 + 손계산 결정론.

검증 축: ① 멀티1계좌 == 단일(엔진 정합) ② 2계좌 = 단독 합(무이동·무세금)
③ 역산 변수 = 계좌1만 ④ 세금 개인합산(공유 세션) ⑤ G2 ISA 한도 cascade
⑥ 절세 요약(계좌별 + 합산, 위탁 불변식).
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import numpy as np
import pandas as pd

from modules.dividend_simulator import DividendSimulator
from modules.dividend_multi import MultiDividendSimulator
from modules.tax.base_tax import TaxEngine


class FakeLoader:
    USD_KRW_START = "2000-01-01"

    def __init__(self, frames):
        self.frames = frames

    def get_price(self, code, start, end, **kw):
        df = self.frames[code].reset_index().rename(columns={"index": "date"})
        return df[["date", "close", "dividend"]].copy()


def _daily_const(start="2015-01-01", end="2024-12-31", price=100.0, q_div=0.5):
    dates = pd.bdate_range(start, end)
    div = np.zeros(len(dates))
    seen = set()
    for i, d in enumerate(dates):
        if d.month in (3, 6, 9, 12) and (d.year, d.month) not in seen:
            seen.add((d.year, d.month))
            div[i] = q_div
    return pd.DataFrame({"close": price, "dividend": div}, index=dates)


def _acct(atype, seed, monthly, codes_weights, **extra):
    return {
        "type": atype, "initial_capital": float(seed), "monthly_contribution": float(monthly),
        "tickers": [{"code": c, "name": c, "badge": "", "weight": w}
                    for c, w in codes_weights.items()],
        "rebal_mode": "none", **extra,
    }


def _multi(accounts, frames, tax=False, settings=None):
    return MultiDividendSimulator(
        loader=FakeLoader(frames), accounts=accounts, div_mode="reinvest",
        tax_enabled=tax, user_settings=settings or {"earned_income": 50_000_000, "age": 40},
    )


def _single(frames, weights, atype="위탁", tax=False):
    te = TaxEngine({"earned_income": 50_000_000, "age": 40}) if tax else None
    return DividendSimulator(
        loader=FakeLoader(frames), tickers=list(weights), weights=weights,
        div_mode="reinvest", rebal_mode="none",
        tax_engine=te, account_type=atype,
    )


F1 = {"069500": _daily_const()}
F2 = {"069500": _daily_const(), "458730": _daily_const(q_div=1.0)}


# ── 1. 정합 앵커: 멀티 1계좌 == 단일 (무세금) ──────────────────
def test_multi_one_account_equals_single():
    single = _single(F1, {"069500": 1.0})._simulate_one(10_000_000, 300_000, 5, "2016-01-04")
    multi = _multi([_acct("위탁", 10_000_000, 300_000, {"069500": 1.0})], F1)._simulate_one(
        10_000_000, 300_000, 5, "2016-01-04")
    assert single > 0
    assert abs(single - multi) <= 1.0, f"단일 {single} vs 멀티1 {multi}"


# ── 2. 2계좌 합산 == 단독 합 (무세금·무이동) ───────────────────
def test_two_accounts_sum_of_singles():
    a = _single(F2, {"069500": 1.0})._simulate_one(10_000_000, 0, 5, "2016-01-04")
    b = _single(F2, {"458730": 1.0})._simulate_one(5_000_000, 200_000, 5, "2016-01-04")
    multi = _multi([
        _acct("위탁", 10_000_000, 0, {"069500": 1.0}),
        _acct("위탁", 5_000_000, 200_000, {"458730": 1.0}),
    ], F2)._simulate_one(10_000_000, 0, 5, "2016-01-04")
    assert abs((a + b) - multi) <= 2.0, f"합 {a+b} vs 멀티 {multi}"


# ── 3. 역산 변수 = 계좌1만 (계좌2 고정) ───────────────────────
def test_inversion_variable_is_account1_only():
    accounts = [
        _acct("위탁", 999, 0, {"069500": 1.0}),       # 계좌1 — seed는 호출 인자로 대체됨
        _acct("위탁", 5_000_000, 0, {"458730": 1.0}),  # 계좌2 — 고정
    ]
    sim = _multi(accounts, F2)
    zero = sim._simulate_one(0, 0, 5, "2016-01-04")
    big  = sim._simulate_one(50_000_000, 0, 5, "2016-01-04")
    only_b = _single(F2, {"458730": 1.0})._simulate_one(5_000_000, 0, 5, "2016-01-04")
    assert abs(zero - only_b) <= 1.0      # 계좌1 시드 0 → 계좌2 배당만
    assert big > zero * 2                  # 계좌1 시드가 실제 역산 변수로 동작


# ── 4. 세금 개인합산: 각 임계 미만·합산 초과 → 합동 < 단독합 ────
def test_person_level_comprehensive_pooling():
    frames = {"069500": _daily_const(q_div=12.0)}   # 시드 1억(100만주)→연 4,800만? 조정: 시드 3천만
    settings = {"earned_income": 100_000_000, "age": 40}
    # 계좌당 연 gross ≈ 30만주? → 시드 3천만 = 30만주 ×12×4 = 1,440만 (임계 미만), 2계좌 합 2,880만(초과)
    acct = lambda: _acct("위탁", 30_000_000, 0, {"069500": 1.0})
    joint = MultiDividendSimulator(
        loader=FakeLoader(frames), accounts=[acct(), acct()], div_mode="reinvest",
        tax_enabled=True, user_settings=settings,
    )._simulate_one(30_000_000, 0, 3, "2016-01-04")
    alone = _single(frames, {"069500": 1.0}, tax=True)
    # 단일 엔진은 earned 5천만 기본 — 동일 조건 위해 직접 100M 엔진
    alone.tax_engine = TaxEngine(settings)
    alone_v = alone._simulate_one(30_000_000, 0, 3, "2016-01-04")
    assert joint < 2 * alone_v - 1_000.0, f"개인합산 미작동 — 합동 {joint} vs 단독×2 {2*alone_v}"


# ── 5. G2 라우팅: ISA 월납 한도 초과분 → 위탁 cascade ──────────
def test_isa_limit_cascade_to_brokerage():
    settings = {"earned_income": 50_000_000, "age": 40}
    accounts = [
        _acct("ISA", 0, 2_000_000, {"069500": 1.0}),    # 연 2,400만 > ISA 연 2,000만
        _acct("위탁", 0, 0, {"069500": 1.0}),
    ]
    body_policy = {"destinations": [{"account_id": 0}, {"account_id": 1}]}
    from modules.tax.account_tax import DistributionPolicy
    multi = MultiDividendSimulator(
        loader=FakeLoader(F1), accounts=accounts, div_mode="reinvest",
        tax_enabled=True, user_settings=settings,
        distribution_policy=DistributionPolicy.from_dict(body_policy),
    )
    routed = multi._simulate_one(0, 2_000_000, 5, "2016-01-04")
    # 라우팅 없는 ISA 단독(한도 컷, isa_total_limit이 아닌 연한도는 단일에선 미모델 →
    # 비교 기준 = 월 166.7만(연 2,000만)만 ISA에 들어간 단일과 "전액 투자" 사이)
    isa_capped = _single(F1, {"069500": 1.0}, atype="ISA", tax=True)._simulate_one(
        0, 2_000_000 * (20 / 24), 5, "2016-01-04")
    # cascade가 작동하면 초과분(연 400만)도 위탁에서 굴러 배당 발생 → 한도 컷 단독보다 큼
    assert routed > isa_capped + 1_000.0, f"cascade 미작동 — 멀티 {routed} vs ISA컷 {isa_capped}"


# ── 5b. dividend_logic 멀티 분기: 응답 형식 + 역산 + 절세 ──────
def test_logic_multi_branch(monkeypatch):
    import dividend_logic

    class _StubEngine:
        loader = FakeLoader(F2)

    monkeypatch.setattr(dividend_logic, "_portfolio_engine", _StubEngine())
    body = {
        "tickers": [{"code": "069500", "weight": 1.0}],   # 상단(계좌1) — accounts[0]과 동일
        "accounts": [
            {"type": "ISA", "initial_capital": 10_000_000, "monthly_contribution": 0,
             "tickers": [{"code": "069500", "weight": 1.0}], "rebal_mode": "none"},
            {"type": "위탁", "initial_capital": 5_000_000, "monthly_contribution": 100_000,
             "tickers": [{"code": "458730", "weight": 1.0}], "rebal_mode": "none"},
        ],
        "tax_enabled": True,
        "target_monthly_div": 50_000,
        "probability": 0.5,
        "user_settings": {"earned_income": 50_000_000, "age": 40, "isa_type": "general"},
        "seed":    {"center": 10_000_000, "step": 0, "n": 0, "mode": "fixed"},
        "monthly": {"center": 0,          "step": 0, "n": 0, "mode": "fixed"},
        "years":   {"center": 5,          "step": 0, "n": 0, "mode": "fixed"},
    }
    res = dividend_logic.run_dividend_scenario_logic(body)
    assert res.get("mode") == "probability"
    assert res.get("multi_account", {}).get("enabled") is True
    assert res["multi_account"]["n_accounts"] == 2
    assert res["result"]["cases_count"] >= 1
    assert res.get("savings") is not None and len(res["savings"]["accounts"]) == 2

    # 역산(시드 자동) — solved_seed 산출되고 0 이상
    body_opt = dict(body, seed={"center": 0, "step": 0, "n": 0, "mode": "optimize"},
                    target_monthly_div=200_000)
    res2 = dividend_logic.run_dividend_scenario_logic(body_opt)
    assert "solved_seed" in (res2.get("result") or {}), res2
    assert res2["result"]["solved_seed"] >= 0


# ── 6. 절세 요약: 계좌별 + 합산, 위탁 불변식 ───────────────────
def test_multi_savings_summary():
    settings = {"earned_income": 50_000_000, "age": 40}
    accounts = [
        _acct("ISA", 10_000_000, 0, {"069500": 1.0}),
        _acct("위탁", 10_000_000, 0, {"458730": 1.0}),
    ]
    sim = MultiDividendSimulator(
        loader=FakeLoader(F2), accounts=accounts, div_mode="reinvest",
        tax_enabled=True, user_settings=settings,
    )
    out = sim.get_savings_summary(10_000_000, 0, 5)
    assert out is not None and len(out["accounts"]) == 2
    isa = next(a for a in out["accounts"] if a["type"] == "ISA")
    brk = next(a for a in out["accounts"] if a["type"] == "위탁")
    assert isa["tax_saving"] > 0                       # ISA 과세이연 절세
    assert brk["tax_saving"] <= max(1.0, brk["brokerage_assumed_tax"] * 0.01)  # 위탁 ≈ 0
    assert abs(out["combined"]["tax_saving"]
               - (isa["tax_saving"] + brk["tax_saving"])) < 0.01
    assert out["n_windows"] >= 1
