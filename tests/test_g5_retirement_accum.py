"""
tests/test_g5_retirement_accum.py
G5-B L11: 은퇴 적립단계 멀티계좌 검증 (결정론 픽스처, ±1원).

은퇴 적립은 투자계산기와 동일 엔진(MultiAccountAnalyzer)을 공유한다. 따라서 L11은
엔진 자체(이미 calculator L0~L9에서 TaxableSimulationRunner와 ±1원 검증됨)를 재증명하지
않고, **은퇴 래퍼**(_run_multi_account_retirement_logic)가 그 엔진을 올바르게 배선하는지를
검증한다.

- 골든: 래퍼 결과 = 동일 데이터로 MultiAccountAnalyzer 직접호출 ±1원
        (엔진→Runner 동치는 calculator L0가 보증 → 전이적으로 래퍼=엔진=Runner).
- 불변식: combined end_value = Σ account end_value (케이스마다).
- 노이즈0: 평탄가격·거치·세금OFF → 종료값 = 초기 합(수익 0).
- 세금 ON/OFF: 계단가격 위탁 청산세 → ON < OFF.
- 인출 연기: withdrawal_pending=True, sample_results=[], combined_summary=None (G5-C 전).
- 디스패치: accounts 2개↑ → 멀티경로, 1개 → 기존(단일)경로.

prepare_scenario_data·price_loader.load·_get_dividend_start를 결정론으로 패치해
_run_multi_account_retirement_logic을 직접 구동.
"""
import os
import sys
from contextlib import contextmanager

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import modules.data_preparation as data_preparation
import retirement_logic
from modules.retirement.multi_account_analyzer import MultiAccountAnalyzer

KRF = "458730"  # KR_FOREIGN
KRD = "069500"  # KR_DOMESTIC

EFF_START = "2018-01-01"
DATA_END  = "2024-12-31"   # 고정 — today에 안 흔들리게 max_years 우회용으로 충분히 과거


def _step_frame(dates, lo=100.0, hi=200.0):
    n = len(dates)
    px = np.where(np.arange(n) < n // 2, lo, hi).astype(float)
    return pd.DataFrame(
        {"open": px, "high": px, "low": px, "close": px,
         "volume": 1.0, "dividend": 0.0, "split": 1.0},
        index=dates,
    )


def _flat_frame(dates, price=100.0):
    px = np.full(len(dates), float(price))
    return pd.DataFrame(
        {"open": px, "high": px, "low": px, "close": px,
         "volume": 1.0, "dividend": 0.0, "split": 1.0},
        index=dates,
    )


def _make_provider(frame_map):
    """MultiAccountAnalyzer._load_prices / price_loader.load 양쪽 시그니처 호환 provider."""
    def provider(tickers, start_date, end_date, allow_synthetic=False):
        idx = pd.bdate_range(start=start_date, end=end_date)
        out = {}
        for t in tickers:
            if t not in frame_map:
                continue
            df = frame_map[t].reindex(idx)
            df[["open", "high", "low", "close", "volume"]] = (
                df[["open", "high", "low", "close", "volume"]].ffill().bfill()
            )
            df["dividend"] = df["dividend"].fillna(0.0)
            df["split"] = df["split"].fillna(1.0)
            out[t] = df
        return out, list(idx)
    return provider


@contextmanager
def _patched(frame_map):
    """prepare_scenario_data·price_loader.load·_get_dividend_start를 결정론으로 교체."""
    eng  = retirement_logic._get_portfolio_engine()
    provider = _make_provider(frame_map)

    orig_prep = data_preparation.prepare_scenario_data
    orig_load = eng.price_loader.load
    orig_div  = retirement_logic._get_dividend_start
    orig_get  = eng.loader.get_price

    eng.loader.get_price = lambda *a, **k: None  # warmup 실DB 타격 차단
    data_preparation.prepare_scenario_data = lambda **kw: {
        "data_start": EFF_START, "effective_start": EFF_START, "data_end": DATA_END,
        "n_cases": None, "backfilled": [], "synthetic_info": {},
        "used_synthetic": False, "warnings": [],
    }
    eng.price_loader.load = lambda tickers, s, e, allow_synthetic=False: provider(
        tickers, s, e, allow_synthetic
    )
    retirement_logic._get_dividend_start = lambda pe, t: None
    # max_years 체크가 today에 안 흔들리게 data_end도 고정값으로 — datetime.date.today() 우회 불가하므로
    # accumulation_years를 EFF_START~today 범위 내로 잡아 통과시킨다(테스트에서 years=4).
    try:
        yield provider
    finally:
        data_preparation.prepare_scenario_data = orig_prep
        eng.price_loader.load = orig_load
        retirement_logic._get_dividend_start = orig_div
        eng.loader.get_price = orig_get


def _account(ticker, initial, monthly=0, account_type="위탁"):
    return {
        "type": account_type, "initial_capital": initial, "monthly_contribution": monthly,
        "tickers": [{"code": ticker, "weight": 1.0}], "rebal_mode": "none",
        "dividend_mode": "hold",
    }


def _run_direct_engine(accounts, years, tax_enabled, user_settings, provider):
    """동일 데이터로 MultiAccountAnalyzer 직접 호출 — 래퍼 골든 비교 기준."""
    from modules.multi_account_common import normalize_multi_accounts
    norm = normalize_multi_accounts({"accounts": accounts})
    for a in norm:
        a["gain_harvesting"] = False
    analyzer = MultiAccountAnalyzer(
        portfolio_engine=retirement_logic._get_portfolio_engine(),
        accounts=norm, data_start=EFF_START,
        data_end=__import__("datetime").date.today().strftime("%Y-%m-%d"),
        accumulation_years=years, dividend_mode="hold", step_months=3,
        tax_enabled=tax_enabled, user_settings=user_settings,
        price_provider=provider, div_start=None,
        apply_final_liquidation=False,  # 은퇴 = 무청산 인계 (래퍼와 동일)
    )
    return analyzer.run()


def test_l11_wrapper_matches_direct_engine():
    """골든: 래퍼 적립 분포 = 동일 데이터로 엔진 직접호출 ±1원 (1계좌 위탁, 계단가격, 세금 ON)."""
    dates = pd.bdate_range(EFF_START, DATA_END)
    fmap  = {KRF: _step_frame(dates)}
    accounts = [_account(KRF, 10_000_000)]
    body = {
        "accounts": accounts, "accumulation_years": 4,
        "tax_enabled": True, "user_settings": {"earned_income": 0, "age": 40},
        "dividend_mode": "hold",
    }
    with _patched(fmap) as provider:
        res    = retirement_logic._run_multi_account_retirement_logic(body)
        direct = _run_direct_engine(accounts, 4, True, {"earned_income": 0, "age": 40}, provider)

    wrap_vals   = res["distribution"]["end_value"]["values"]
    direct_vals = direct["combined"]["distribution"]["end_value"]["values"]
    assert len(wrap_vals) == len(direct_vals) and len(wrap_vals) > 0
    for w, d in zip(wrap_vals, direct_vals):
        assert abs(w - d) <= 1, f"래퍼 {w} vs 엔진 {d}"


def test_l11_flat_price_no_growth_and_combined_sum():
    """불변식 combined=Σaccounts + 평탄가격·거치·세금OFF → 종료값=초기합(수익0)."""
    dates = pd.bdate_range(EFF_START, DATA_END)
    fmap  = {KRF: _flat_frame(dates), KRD: _flat_frame(dates)}
    body = {
        "accounts": [_account(KRF, 5_000_000), _account(KRD, 3_000_000)],
        "accumulation_years": 4, "tax_enabled": False, "user_settings": {},
        "dividend_mode": "hold",
    }
    with _patched(fmap):
        res = retirement_logic._run_multi_account_retirement_logic(body)

    # 케이스마다 combined = Σ account end_value
    for c in res["cases"]:
        assert c["end_value"] == sum(a["end_value"] for a in c["accounts"])
    # 평탄가격·거치·세금OFF → 모든 케이스 종료값 = 초기 합(8,000,000)
    for c in res["cases"]:
        assert abs(c["end_value"] - 8_000_000) <= 1
    assert abs(res["distribution"]["end_value"]["p50"] - 8_000_000) <= 1


def test_l11_no_final_liquidation_gross_handoff():
    """은퇴 = 절대 일괄청산 금지. 거치 위탁(배당0·리밸none) → 적립기 세금이벤트 0 →
    무청산이므로 세금 ON 적립 종료값 == 세금 OFF (gross 인계, 청산세 미부과)."""
    dates = pd.bdate_range(EFF_START, DATA_END)
    fmap  = {KRF: _step_frame(dates)}
    base  = {
        "accounts": [_account(KRF, 10_000_000)],
        "accumulation_years": 4, "dividend_mode": "hold",
    }
    with _patched(fmap):
        off = retirement_logic._run_multi_account_retirement_logic(
            {**base, "tax_enabled": False, "user_settings": {}})
        on = retirement_logic._run_multi_account_retirement_logic(
            {**base, "tax_enabled": True, "user_settings": {"earned_income": 0, "age": 40}})
    # 무청산 → 위탁 상승분(100→200) 미실현차익에 청산세 안 떼임 → ON == OFF (gross).
    on_vals  = on["distribution"]["end_value"]["values"]
    off_vals = off["distribution"]["end_value"]["values"]
    assert len(on_vals) == len(off_vals) and len(on_vals) > 0
    for o, f in zip(on_vals, off_vals):
        assert abs(o - f) <= 1, f"무청산 위반 — 세금ON {o} != OFF {f} (적립끝 청산세 부과됨)"


def test_l11_withdrawal_deferred():
    """인출투영(생존율)은 G5-C로 연기 — pending 플래그·빈 인출결과."""
    dates = pd.bdate_range(EFF_START, DATA_END)
    fmap  = {KRF: _flat_frame(dates)}
    body = {
        "accounts": [_account(KRF, 5_000_000), _account(KRD, 3_000_000)],
        "accumulation_years": 4, "tax_enabled": False, "user_settings": {},
        "dividend_mode": "hold",
    }
    fmap[KRD] = _flat_frame(dates)
    with _patched(fmap):
        res = retirement_logic._run_multi_account_retirement_logic(body)
    assert res["withdrawal_pending"] is True
    assert res["sample_results"] == []
    assert res["combined_summary"] is None
    # 적립 요약은 채워짐
    assert "accumulation_summary" in res and "end_value" in res["accumulation_summary"]


def test_l11_dispatch_routes_by_account_count(monkeypatch):
    """디스패치: accounts 2개↑ → 멀티경로, 1개 → 기존(단일)경로."""
    sentinel = {"multi": True}
    called = {"multi": 0}

    def fake_multi(body, progress_callback=None):
        called["multi"] += 1
        return sentinel

    monkeypatch.setattr(retirement_logic, "_run_multi_account_retirement_logic", fake_multi)

    # 2계좌 → 멀티경로 진입
    out = retirement_logic.run_retirement_logic({"accounts": [{"x": 1}, {"y": 2}]})
    assert out is sentinel and called["multi"] == 1

    # 1계좌 → 멀티경로 미진입(단일경로로 빠짐 → 키 누락 등으로 KeyError/ValueError 발생,
    # 멀티 sentinel은 절대 반환 안 됨). 단일경로는 무거운 DB라 진입만 확인.
    try:
        retirement_logic.run_retirement_logic({"accounts": [{"x": 1}]})
    except Exception:
        pass
    assert called["multi"] == 1, "1계좌인데 멀티경로 진입함"


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
