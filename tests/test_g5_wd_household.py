"""G5-D: 은퇴 인출기(standalone) 멀티계좌+세금 배선 검증 (L13).

엔진(analyze_household_withdrawal)은 test_g5_multi_withdrawal_rolling에서 검증됨.
여기선 `run_withdrawal_logic`/`_run_multi_account_withdrawal_logic`의 **신규 배선**만:
  ① dispatch(accounts>1 → 멀티, 1 → 단일)
  ② account_specs cost_basis = 목돈 − 미실현차익 (위탁·세금ON / 그 외 None)
  ③ 반환 매핑(multi_account.accounts[].distribution.end_value · combined_summary · median_pension_tax)
  ④ 세금 ON/OFF
DB 의존 차단 — 평탄 합성가격 주입으로 결정론.
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pandas as pd
import pytest

import retirement_logic
import modules.retirement.multi_account_withdrawal as mw
import modules.data_preparation as dp

CODE = "069500"   # 국내 ETF — CG 비과세


def _flat_data(price=100.0, start="2008-01-01", end="2026-12-31"):
    dates = pd.bdate_range(start, end)
    df = pd.DataFrame(
        {"open": price, "high": price, "low": price, "close": price,
         "volume": 1.0, "dividend": 0.0, "split": 1.0},
        index=dates,
    )
    return {CODE: df}, list(dates)


class _FakeLoader:
    USD_KRW_START = "1990-01-01"
    def get_price(self, *a, **k):
        return None


class _FakePriceLoader:
    def __init__(self, data, dates):
        self._d = (data, dates)
    def load(self, tickers, start, end):
        return self._d


class _FakeEngine:
    def __init__(self, data, dates):
        self.loader = _FakeLoader()
        self.price_loader = _FakePriceLoader(data, dates)


def _patch_db(monkeypatch, start="2008-01-01"):
    data, dates = _flat_data(start=start)
    monkeypatch.setattr(retirement_logic, "_get_portfolio_engine",
                        lambda: _FakeEngine(data, dates))
    monkeypatch.setattr(dp, "prepare_scenario_data",
                        lambda **k: {"effective_start": start})


def _acct(atype, code, initial, weight=1.0, **extra):
    return dict(type=atype, initial_capital=initial,
                tickers=[{"code": code, "weight": weight}], **extra)


# ── ① dispatch ───────────────────────────────────────────────────
def test_dispatch_routes_multi_for_two_accounts(monkeypatch):
    sentinel = object()
    monkeypatch.setattr(retirement_logic, "_run_multi_account_withdrawal_logic",
                        lambda body, cb=None: sentinel)
    body = {"accounts": [_acct("위탁", CODE, 5_000_000),
                         _acct("ISA", CODE, 5_000_000)],
            "monthly_withdrawal": 100_000, "withdrawal_years": 2}
    assert retirement_logic.run_withdrawal_logic(body) is sentinel


def test_dispatch_single_account_not_routed_to_multi(monkeypatch):
    # 단일계좌(1개)는 멀티로 가면 안 됨 → 단일경로 진입(tickers 키 없어 KeyError).
    monkeypatch.setattr(retirement_logic, "_run_multi_account_withdrawal_logic",
                        lambda body, cb=None: pytest.fail("단일계좌가 멀티로 라우팅됨"))
    body = {"accounts": [_acct("위탁", CODE, 5_000_000)],
            "monthly_withdrawal": 100_000, "withdrawal_years": 2}
    with pytest.raises(KeyError):   # 단일경로 진입 증거(body['tickers'] 없음)
        retirement_logic.run_withdrawal_logic(body)


# ── ② cost_basis = 목돈 − 미실현차익 ─────────────────────────────
def test_cost_basis_from_unrealized_gain(monkeypatch):
    captured = {}
    def _stub(accounts, *a, **k):
        captured["accounts"] = accounts
        return {"survival_rate": 1.0, "n_real": 1, "n_synthetic": 0,
                "combined_end_value": {f"p{p}": 0.0 for p in (10, 25, 50, 75, 90)},
                "per_account": [], "median_pension_tax": 0.0}
    monkeypatch.setattr(mw, "analyze_household_withdrawal", _stub)
    _patch_db(monkeypatch)

    body = {
        "accounts": [
            _acct("위탁", CODE, 10_000_000, unrealized_gain=4_000_000),
            _acct("ISA", CODE, 5_000_000, unrealized_gain=9_999),
            _acct("연금저축", CODE, 3_000_000),
        ],
        "monthly_withdrawal": 100_000, "withdrawal_years": 2,
        "tax_enabled": True, "user_settings": {"age": 65, "earned_income": 0},
        "pension_start_age": 65,
    }
    retirement_logic.run_withdrawal_logic(body)
    specs = captured["accounts"]
    # 위탁·세금ON → cost_basis = 10,000,000 − 4,000,000
    assert specs[0]["type"] == "위탁"
    assert specs[0]["cost_basis"] == 6_000_000.0
    assert specs[0]["value"] == 10_000_000.0
    # ISA·연금 → cost_basis None (미실현차익 무의미)
    assert specs[1]["cost_basis"] is None
    assert specs[2]["cost_basis"] is None


def test_cost_basis_none_when_tax_off(monkeypatch):
    captured = {}
    monkeypatch.setattr(mw, "analyze_household_withdrawal",
        lambda accounts, *a, **k: captured.update(accounts=accounts) or {
            "survival_rate": 1.0, "n_real": 1, "n_synthetic": 0,
            "combined_end_value": {f"p{p}": 0.0 for p in (10, 25, 50, 75, 90)},
            "per_account": [], "median_pension_tax": 0.0})
    _patch_db(monkeypatch)
    body = {"accounts": [_acct("위탁", CODE, 10_000_000, unrealized_gain=4_000_000),
                         _acct("ISA", CODE, 5_000_000)],
            "monthly_withdrawal": 100_000, "withdrawal_years": 2,
            "tax_enabled": False}
    retirement_logic.run_withdrawal_logic(body)
    assert all(s["cost_basis"] is None for s in captured["accounts"])


# ── ③ 반환 매핑 (실엔진, 평탄가격 결정론) ────────────────────────
def test_return_shape_real_engine(monkeypatch):
    _patch_db(monkeypatch)
    body = {
        "accounts": [_acct("위탁", CODE, 5_000_000),
                     _acct("ISA", CODE, 5_000_000)],
        "monthly_withdrawal": 150_000, "withdrawal_years": 2,
        "tax_enabled": False,
    }
    res = retirement_logic.run_withdrawal_logic(body)
    # multi_account 구조 (renderMultiAccountSummary 소비형)
    assert res["multi_account"]["enabled"] is True
    accs = res["multi_account"]["accounts"]
    assert len(accs) == 2
    assert accs[0]["type"] == "위탁" and "end_value" in accs[0]["distribution"]
    assert set(accs[0]["distribution"]["end_value"]) == {"p10", "p25", "p50", "p75", "p90"}
    # combined_summary
    assert res["combined_summary"]["survival_rate"] == 1.0
    assert res["survival_rate"] == 1.0
    # 위탁(5M) 먼저 소진 → ISA 5M 잔존 / 합산 = 위탁 + ISA p50
    assert abs(accs[1]["distribution"]["end_value"]["p50"] - 5_000_000.0) <= 1.0
    assert abs(
        res["combined_summary"]["combined_end_value"]["p50"]
        - (accs[0]["distribution"]["end_value"]["p50"] + 5_000_000.0)
    ) <= 1.0
    # 연금세 필드 존재 (위탁/ISA만이라 0)
    assert res["median_pension_tax"] == 0.0
    assert "n_real" in res and "n_synthetic" in res


# ── ④ 세금 ON/OFF: 연금 인출 → median_pension_tax 부과 ────────────
def test_pension_tax_surfaced_when_tax_on(monkeypatch):
    _patch_db(monkeypatch)
    body = {
        "accounts": [_acct("연금저축", CODE, 12_000_000),
                     _acct("위탁", CODE, 100_000)],
        "monthly_withdrawal": 200_000, "withdrawal_years": 2,
        "tax_enabled": True, "user_settings": {"age": 65, "earned_income": 0},
        "pension_start_age": 65,
    }
    res = retirement_logic.run_withdrawal_logic(body)
    # 위탁 소진 후 연금 인출 → 연금소득세 > 0
    assert res["median_pension_tax"] > 0.0


if __name__ == "__main__":
    import subprocess
    sys.exit(subprocess.call([sys.executable, "-m", "pytest", __file__, "-q"]))
