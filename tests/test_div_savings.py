"""배당계산기 절세액 3종 (P4) — 손계산 결정론 + 배선 검증.

규약: 무청산(결과=배당 흐름) → 잔여 미실현 양쪽 미가산 → 위탁이면 절세 0(불변식).
합성 보충 윈도우는 절세 미산출 — 실측 윈도우만 p50.
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import numpy as np
import pandas as pd

from modules.dividend_simulator import DividendSimulator
from modules.tax.base_tax import TaxEngine


class FakeLoader:
    USD_KRW_START = "2000-01-01"

    def __init__(self, frames):
        self.frames = frames

    def get_price(self, code, start, end, **kw):
        df = self.frames[code].reset_index().rename(columns={"index": "date"})
        return df[["date", "close", "dividend"]].copy()


def _daily_const(start, end, price=100.0, q_div=0.5):
    dates = pd.bdate_range(start, end)
    div = np.zeros(len(dates))
    seen = set()
    for i, d in enumerate(dates):
        if d.month in (3, 6, 9, 12) and (d.year, d.month) not in seen:
            # 분기 첫 영업일에 배당 (월합산이라 일자 무관)
            seen.add((d.year, d.month))
            div[i] = q_div
    return pd.DataFrame({"close": price, "dividend": div}, index=dates)


def _sim(account_type, tax=True, frames=None):
    frames = frames or {"069500": _daily_const("2015-01-01", "2024-12-31")}
    te = TaxEngine({"earned_income": 50_000_000, "age": 40}) if tax else None
    return DividendSimulator(
        loader=FakeLoader(frames), tickers=list(frames), weights={t: 1.0 for t in frames},
        div_mode="reinvest", rebal_mode="none",
        tax_engine=te, account_type=account_type,
    ), frames


# ── 1. 위탁 불변식: 가정 == 실제(배당세 동일·무리밸·무청산) → 절세 0 ──
def test_brokerage_invariant_zero_saving():
    sim, _ = _sim("위탁")
    val = sim._simulate_one(10_000_000.0, 0.0, 5, "2016-01-04")
    s = sim._last_savings
    assert val > 0 and s is not None
    assert abs(s["brokerage_assumed_tax"] - s["actual_tax"]) < 1.0
    assert s["tax_saving"] < 1.0


# ── 2. ISA 배당 절세 = Σgross × 15.4% 손계산 (과세이연 → 실제 배당세 0) ──
def test_isa_saving_equals_gross_div_tax():
    sim, _ = _sim("ISA")
    seed, years = 10_000_000.0, 5
    val = sim._simulate_one(seed, 0.0, years, "2016-01-04")
    s = sim._last_savings
    assert val > 0 and s is not None
    # 독립 재현: 시드 100,000주(@100), 분기마다 gross=qty×0.5 → 전액 재투자(ISA 무세금)
    qty, total_gross = seed / 100.0, 0.0
    n_quarters = years * 4
    for _ in range(n_quarters):
        g = qty * 0.5
        total_gross += g
        qty += g / 100.0
    expected_saving = total_gross * 0.154
    assert s["actual_tax"] < 1.0                              # 과세이연
    assert abs(s["tax_saving"] - expected_saving) / expected_saving < 0.02, (
        f"saving {s['tax_saving']} vs 손계산 {expected_saving}"
    )


# ── 3. 요약 p50: 실측 윈도우만, 합성 보충 미포함 / 무세금 None ──
def test_savings_summary_p50_and_untaxed_none():
    sim, _ = _sim("ISA")
    out = sim.get_savings_summary(10_000_000.0, 0.0, 5)
    assert out is not None
    assert out["n_windows"] >= 1
    assert out["tax_saving"] > 0
    assert out["brokerage_assumed_tax"] >= out["tax_saving"]
    # 캐시 정합: 같은 콤보 재호출 = 동일 결과(재계산 없음)
    assert sim.get_savings_summary(10_000_000.0, 0.0, 5) == out

    sim2, _ = _sim("위탁", tax=False)
    assert sim2.get_savings_summary(10_000_000.0, 0.0, 5) is None


# ── 3b. BUG-DIV-YEARS 회귀: float years × 합성 보충 경로 ──
def test_float_years_with_synthetic_fallback():
    """기간 자동(_find_anchor_years)이 float 반환 → 합성 경로 range(years*12) 크래시였음.
    짧은 데이터(3y)로 합성 폴백 강제 + years=5.0 float → 정상 + int 경로와 캐시 일치."""
    frames = {"069500": _daily_const("2022-01-01", "2024-12-31")}
    sim, _ = _sim("위탁", frames=frames)
    out_f = sim._run_rolling(10_000_000.0, 0.0, 5.0)   # float — 크래시 회귀 지점
    assert len(out_f) >= sim.MIN_CASES                  # 합성 보충 발동 확인
    out_i = sim._run_rolling(10_000_000.0, 0.0, 5)      # int — 같은 캐시 키로 정규화
    assert out_f == out_i                               # 22.0/22 캐시 분열 방지


# ── 4. dividend_logic 응답 배선: savings 키 + 계좌유형 ──
def test_logic_response_has_savings(monkeypatch):
    import dividend_logic

    class _StubEngine:
        loader = FakeLoader({"069500": _daily_const("2015-01-01", "2024-12-31")})

    monkeypatch.setattr(dividend_logic, "_portfolio_engine", _StubEngine())
    body = {
        "tickers": [{"code": "069500", "weight": 1.0}],
        "target_monthly_div": 100_000,
        "probability": 0.5,
        "account_type": "isa",
        "user_settings": {"earned_income": 50_000_000, "age": 40, "isa_type": "general"},
        "seed":    {"center": 10_000_000, "step": 0, "n": 0, "mode": "fixed"},
        "monthly": {"center": 0,          "step": 0, "n": 0, "mode": "fixed"},
        "years":   {"center": 5,          "step": 0, "n": 0, "mode": "fixed"},
    }
    res = dividend_logic.run_dividend_scenario_logic(body)
    assert res.get("mode") == "probability"
    assert res.get("savings") is not None
    assert res["savings"]["tax_saving"] > 0
    assert res.get("savings_account_type") == "ISA"

    # 세금 OFF → savings 키 자체 없음
    body_off = dict(body, account_type="none")
    res_off = dividend_logic.run_dividend_scenario_logic(body_off)
    assert "savings" not in res_off
