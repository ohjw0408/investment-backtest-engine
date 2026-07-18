"""리스크-리턴 도표 로직 — 손계산 결정론 검증 (FakeLoader, DB 무접근)."""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import numpy as np
import pandas as pd
import pytest

from risk_return_logic import compute_risk_return, MIN_YEARS_WARN


class FakeLoader:
    def __init__(self, frames):
        self.frames = frames

    def get_price(self, code, start, end, **kw):
        if code not in self.frames:
            raise ValueError(f"no data: {code}")
        return self.frames[code].copy()


def _frame(start, n_days, daily_ret=0.0, monthly_div=0.0, start_price=100.0):
    dates = pd.bdate_range(start, periods=n_days)
    closes = start_price * np.cumprod(np.full(n_days, 1.0 + daily_ret))
    div = np.zeros(n_days)
    if monthly_div:
        seen = set()
        for i, d in enumerate(dates):
            key = (d.year, d.month)
            if key not in seen:
                seen.add(key)
                div[i] = monthly_div
    return pd.DataFrame({"date": dates, "close": closes, "dividend": div})


def _pf(name, *pairs):
    return {"name": name, "tickers": [{"code": c, "weight": w} for c, w in pairs]}


def _point(res, name):
    return next(p for p in res["points"] if p["name"] == name)


# ── 1. 상수성장 단일자산: CAGR = (1+r)^252 − 1, vol=0 ──────────
def test_constant_growth_cagr_exact():
    loader = FakeLoader({"AAA": _frame("2020-01-01", 505, daily_ret=0.001)})
    res = compute_risk_return([_pf("올인", ("AAA", 100))], [], loader, data_end="2022-12-31")
    p = _point(res, "올인")
    assert abs(p["cagr"] - (1.001 ** 252 - 1)) < 1e-6
    assert p["vol"] == 0.0 and p["sharpe"] == 0.0   # 상수 수익률 → 변동성 0 가드


# ── 2. 50/50 혼합 + 현금 드래그 등가 ───────────────────────────
def test_mix_and_cash_drag():
    frames = {
        "UP":   _frame("2020-01-01", 505, daily_ret=0.001),
        "FLAT": _frame("2020-01-01", 505, daily_ret=0.0),
    }
    loader = FakeLoader(frames)
    res = compute_risk_return(
        [_pf("혼합", ("UP", 50), ("FLAT", 50)), _pf("절반현금", ("UP", 50))],
        [], loader, data_end="2022-12-31",
    )
    half = 1.0005 ** 252 - 1
    assert abs(_point(res, "혼합")["cagr"] - half) < 1e-6
    # 비중 50% + 현금 50% == UP 50% + 무수익 자산 50% (현금 = 수익 0 규약)
    assert abs(_point(res, "절반현금")["cagr"] - half) < 1e-6


# ── 3. 비중합 > 100% → 합으로 정규화(레버리지 방지) ─────────────
def test_overweight_normalized():
    loader = FakeLoader({
        "UP":   _frame("2020-01-01", 505, daily_ret=0.001),
        "FLAT": _frame("2020-01-01", 505, daily_ret=0.0),
    })
    res = compute_risk_return(
        [_pf("과비중", ("UP", 80), ("FLAT", 40))], [], loader, data_end="2022-12-31")
    # 80/120, 40/120 → UP 2/3 → 일 0.001×2/3
    expected = (1 + 0.001 * 2 / 3) ** 252 - 1
    assert abs(_point(res, "과비중")["cagr"] - expected) < 1e-6


# ── 4. 배당 재투자(총수익): 가격 보합 + 배당 → CAGR > 0, 재현 일치 ──
def test_dividend_total_return():
    f = _frame("2020-01-01", 505, daily_ret=0.0, monthly_div=1.0)  # 가격 100 보합, 월 1원
    loader = FakeLoader({"DIV": f})
    res = compute_risk_return([], [{"code": "DIV", "name": "DIV"}], loader, data_end="2022-12-31")
    p = _point(res, "DIV")
    # 독립 재현: r_t = (close+div)/prev−1
    closes, divs = f["close"].values, f["dividend"].values
    r = (closes[1:] + divs[1:]) / closes[:-1] - 1.0
    growth = float(np.prod(1 + r))
    expected = growth ** (252.0 / len(r)) - 1.0
    assert p["cagr"] > 0
    assert abs(p["cagr"] - expected) < 1e-6


# ── 5. 공통 겹침 기간 + 3년 미만 경고 ─────────────────────────
def test_common_period_and_warning():
    loader = FakeLoader({
        "LONG":  _frame("2015-01-01", 2000, daily_ret=0.0005),
        "SHORT": _frame("2021-06-01", 300, daily_ret=0.0005),   # ~1.2년
    })
    res = compute_risk_return(
        [_pf("긴것", ("LONG", 100))],
        [{"code": "SHORT", "name": "SHORT"}], loader, data_end="2022-12-31")
    assert res["period"]["start"] == "2021-06-01"               # 공통 시작 = 늦은 쪽
    assert res["period"]["years"] < MIN_YEARS_WARN
    assert res["period"]["warning"]                              # 경고 존재
    # 공통 구간으로 잘렸으므로 두 점의 일수 동일 → 같은 일수익률이면 CAGR 동일
    assert abs(_point(res, "긴것")["cagr"] - _point(res, "SHORT")["cagr"]) < 1e-6


# ── 6. 데이터 없는 종목: skipped + 결측 종목만 빼고 잔여 재정규화 유지 ─────────
def test_missing_code_skipped():
    loader = FakeLoader({"AAA": _frame("2020-01-01", 505, daily_ret=0.001)})
    res = compute_risk_return(
        [_pf("정상", ("AAA", 100)), _pf("부분", ("AAA", 50), ("NOPE", 50))],
        [{"code": "GONE", "name": "GONE"}], loader, data_end="2022-12-31")
    assert sorted(res["skipped"]) == ["GONE", "NOPE"]
    names = [p["name"] for p in res["points"]]
    # 2026-07-18: 통째 무경고 제외 → 결측 종목 제외 + 잔여 재정규화 유지로 변경
    assert "정상" in names and "부분" in names and "GONE" not in names
    # 부분 = AAA 50%가 100%로 재정규화 → 정상(AAA 100%)과 동일 지표
    assert abs(_point(res, "정상")["cagr"] - _point(res, "부분")["cagr"]) < 1e-9
    assert res["partial_portfolios"] == [{"name": "부분", "missing": ["NOPE"], "dropped": False}]


# ── 7. 변동성·샤프: 교대 수익률 손계산 ─────────────────────────
def test_vol_sharpe_alternating():
    n = 504
    dates = pd.bdate_range("2020-01-01", periods=n)
    rets = np.tile([0.01, -0.005], n // 2)
    closes = 100.0 * np.cumprod(1 + np.concatenate([[0.0], rets[1:]]))
    # close 시계열을 수익률에서 역산 (첫 r은 NaN 처리되므로 rets[1:] 사용)
    f = pd.DataFrame({"date": dates, "close": closes, "dividend": 0.0})
    loader = FakeLoader({"ALT": f})
    res = compute_risk_return([], [{"code": "ALT", "name": "ALT"}], loader, data_end="2022-12-31")
    p = _point(res, "ALT")
    r = pd.Series(closes).pct_change().dropna()
    assert abs(p["vol"] - float(r.std() * np.sqrt(252))) < 1e-6
    assert abs(p["sharpe"] - float(r.mean() / r.std() * np.sqrt(252))) < 1e-3
