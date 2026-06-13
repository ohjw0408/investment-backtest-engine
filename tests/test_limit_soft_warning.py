"""납입 한도 soft 경고 (2026-06-13 오너 결정) — 수집기 + override 왕복.

규약: 위반 시 limit_confirm 에러(진행 확인 모달) → allow_limit_override=True 재요청이면
통과 + limit_warnings 동봉(결과 하단 경고 배너).
"""
import sys
import os
import json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import numpy as np
import pandas as pd
import pytest

from modules.multi_account_common import (
    collect_limit_violations, enforce_contribution_limits,
)


def _a(atype, init, monthly=0):
    return {'type': atype, 'initial_capital': init, 'monthly_contribution': monthly}


# ── 1. 수집기 룰 ─────────────────────────────────────────
def test_collector_rules():
    # 오너 예시: 연금저축 초기 7,000만 → 1,800만 한도 위반
    v = collect_limit_violations([_a('연금저축', 70_000_000)])
    assert len(v) == 1 and '1,800만원' in v[0]

    # ISA 초기 + 월납 동시 위반 → 둘 다? 초기 초과가 우선 1건(elif), 별도 계좌면 각각
    v = collect_limit_violations([_a('ISA', 30_000_000), _a('ISA', 0, 2_000_000)])
    assert len(v) == 2
    assert '계좌 1' in v[0] and '계좌 2' in v[1]

    # 여러 계좌 복수 위반 한번에 (오너 요구)
    v = collect_limit_violations([
        _a('ISA', 30_000_000), _a('연금저축', 10_000_000), _a('IRP', 10_000_000)])
    assert len(v) == 2          # ISA 초기 + 연금합산 초기

    # 라우팅 ON → 월납 위반 제외(cascade 처리), 초기 위반은 유지
    v = collect_limit_violations([_a('ISA', 30_000_000, 2_000_000)], routing_enabled=True)
    assert len(v) == 1 and '초기' in v[0]
    v = collect_limit_violations([_a('ISA', 0, 2_000_000)], routing_enabled=True)
    assert v == []

    # 한도 내 → 무경고
    assert collect_limit_violations([
        _a('ISA', 20_000_000), _a('연금저축', 9_000_000), _a('IRP', 9_000_000),
        _a('위탁', 999_999_999, 9_999_999)]) == []


# ── 2. enforce: override 없으면 limit_confirm raise / 있으면 경고 반환 ──
def test_enforce_confirm_then_override():
    accounts = [_a('연금저축', 70_000_000)]
    with pytest.raises(ValueError) as ei:
        enforce_contribution_limits({}, accounts)
    payload = json.loads(str(ei.value))
    assert payload['error'] == 'limit_confirm'
    assert len(payload['violations']) == 1

    warnings = enforce_contribution_limits({'allow_limit_override': True}, accounts)
    assert len(warnings) == 1
    assert enforce_contribution_limits({'allow_limit_override': True}, [_a('위탁', 1)]) == []


# ── 3. dividend_logic 왕복 (오너 예시 시나리오) ─────────────
class _FakeLoader:
    USD_KRW_START = "2000-01-01"

    def __init__(self, frames):
        self.frames = frames

    def get_price(self, code, start, end, **kw):
        df = self.frames[code].reset_index().rename(columns={"index": "date"})
        return df[["date", "close", "dividend"]].copy()


def _frames():
    dates = pd.bdate_range("2015-01-01", "2024-12-31")
    div = np.zeros(len(dates))
    seen = set()
    for i, d in enumerate(dates):
        if d.month in (3, 6, 9, 12) and (d.year, d.month) not in seen:
            seen.add((d.year, d.month))
            div[i] = 0.5
    return {"069500": pd.DataFrame({"close": 100.0, "dividend": div}, index=dates)}


def test_dividend_logic_roundtrip(monkeypatch):
    import dividend_logic

    class _Stub:
        loader = _FakeLoader(_frames())

    monkeypatch.setattr(dividend_logic, "_portfolio_engine", _Stub())
    body = {
        "tickers": [{"code": "069500", "weight": 1.0}],
        "target_monthly_div": 100_000, "probability": 0.5,
        "account_type": "pension",     # 연금저축
        "user_settings": {"earned_income": 50_000_000, "age": 40},
        "seed":    {"center": 70_000_000, "step": 0, "n": 0, "mode": "fixed"},
        "monthly": {"center": 0,          "step": 0, "n": 0, "mode": "fixed"},
        "years":   {"center": 5,          "step": 0, "n": 0, "mode": "fixed"},
    }
    # 1차: limit_confirm
    with pytest.raises(ValueError) as ei:
        dividend_logic.run_dividend_scenario_logic(body)
    assert json.loads(str(ei.value))['error'] == 'limit_confirm'

    # 2차(override): 정상 결과 + limit_warnings 동봉
    res = dividend_logic.run_dividend_scenario_logic(dict(body, allow_limit_override=True))
    assert res.get("mode") == "probability"
    assert res.get("limit_warnings") and '1,800만원' in res["limit_warnings"][0]

    # 한도 내면 limit_warnings 없음
    ok_body = dict(body, seed={"center": 10_000_000, "step": 0, "n": 0, "mode": "fixed"})
    res_ok = dividend_logic.run_dividend_scenario_logic(ok_body)
    assert not res_ok.get("limit_warnings")
