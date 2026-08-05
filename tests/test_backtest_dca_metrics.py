"""적립식 백테스트 지표가 납입금에 오염되지 않는지 결정론 검증 (2026-08-05 오너 제보).

버그: 연간수익률·MDD·Sharpe를 계좌 잔고(portfolio_value) 기준으로 계산 → 적립식에서
납입금 증가가 수익으로 잡혀 2006년 +1000%, 2008년(폭락 연도) +11%가 나왔다.
정답 = TWR(시간가중). TWR은 정의상 납입 스케줄과 무관해야 하므로
"적립식 결과 == 거치식 결과"가 곧 회귀 게이트다.
"""
import numpy as np
import pandas as pd
import pytest

from backtest_logic import _perf_block


def _price_path():
    """3년 영업일 가격. 2년차에 -40% 낙폭을 심어 MDD를 검증 가능하게 만든다."""
    dates = pd.bdate_range("2020-01-01", "2022-12-30")
    n = len(dates)
    t = np.arange(n)
    p = 100.0 * (1.0 + 0.0004 * t)                     # 완만한 우상향
    lo, hi = n // 3, n // 3 * 2
    dip = np.zeros(n)
    mid = (lo + hi) // 2
    dip[lo:mid] = np.linspace(0, -0.40, mid - lo)       # 하락
    dip[mid:hi] = np.linspace(-0.40, 0, hi - mid)       # 회복
    return dates, p * (1.0 + dip)


def _history(monthly):
    """매월 첫 영업일에 monthly 납입 → 그날 종가로 전량 매수. 초기금 1,000만."""
    dates, prices = _price_path()
    initial = 10_000_000.0
    rows, shares, last_month = [], 0.0, None
    for d, px in zip(dates, prices):
        cf = 0.0
        if last_month != (d.year, d.month):
            last_month = (d.year, d.month)
            cf = monthly + (initial if not rows else 0.0)
            shares += cf / px
        rows.append({"date": d, "portfolio_value": shares * px, "cash_flow": cf})
    return pd.DataFrame(rows), dates, prices


def _price_annual_returns(dates, prices):
    s = pd.Series(prices, index=dates)
    out, base = [], None
    for yr, grp in s.groupby(s.index.year):
        end = float(grp.iloc[-1])
        out.append({"year": int(yr), "return": round(end / (base if base else float(grp.iloc[0])) - 1, 4)})
        base = end
    return out


def _price_mdd(prices):
    p = np.asarray(prices, dtype=float)
    return float((p / np.maximum.accumulate(p) - 1.0).min())


@pytest.mark.parametrize("monthly", [0.0, 1_000_000.0, 5_000_000.0])
def test_annual_returns_track_price_not_contributions(monthly):
    hist, dates, prices = _history(monthly)
    perf = _perf_block(hist, float(hist["portfolio_value"].iloc[-1]), 10_000_000.0, monthly)

    got = perf["annual_returns"]
    want = _price_annual_returns(dates, prices)
    assert [g["year"] for g in got] == [w["year"] for w in want]
    for g, w in zip(got, want):
        # 첫 해는 지수 시작점(1.0) 기준 = 첫날 종가 기준이라 가격 수익률과 정확히 일치해야 한다.
        assert g["return"] == pytest.approx(w["return"], abs=1e-3), f"{g['year']}: {got}"


@pytest.mark.parametrize("monthly", [0.0, 1_000_000.0, 5_000_000.0])
def test_mdd_is_not_diluted_by_contributions(monthly):
    hist, _dates, prices = _history(monthly)
    perf = _perf_block(hist, float(hist["portfolio_value"].iloc[-1]), 10_000_000.0, monthly)
    assert perf["metrics"]["mdd"] == pytest.approx(round(_price_mdd(prices), 4), abs=1e-3)
    assert perf["metrics"]["mdd"] < -0.35   # 잔고 기준이면 납입금이 고점을 밀어 얕아진다


def test_dca_metrics_match_lumpsum():
    """TWR·MDD·Sharpe는 납입 스케줄과 무관 — 적립식과 거치식이 같아야 한다."""
    h_lump = _history(0.0)[0]
    h_dca  = _history(1_000_000.0)[0]
    lump = _perf_block(h_lump, float(h_lump["portfolio_value"].iloc[-1]), 10_000_000.0, 0.0)
    dca  = _perf_block(h_dca,  float(h_dca["portfolio_value"].iloc[-1]),  10_000_000.0, 1_000_000.0)
    for k in ("mdd", "sharpe"):
        assert lump["metrics"][k] == pytest.approx(dca["metrics"][k], abs=1e-2), k
    assert [a["return"] for a in lump["annual_returns"]] == \
           pytest.approx([a["return"] for a in dca["annual_returns"]], abs=1e-3)


def test_total_invested_is_actual_cash_flow_sum():
    hist, _d, _p = _history(1_000_000.0)
    perf = _perf_block(hist, float(hist["portfolio_value"].iloc[-1]), 10_000_000.0, 1_000_000.0)
    assert perf["metrics"]["total_invested"] == round(float(hist["cash_flow"].clip(lower=0).sum()))
    # 3년 = 36개월 납입 + 초기 1,000만
    assert perf["metrics"]["total_invested"] == 46_000_000


def test_lumpsum_cagr_equals_simple_annualized():
    """거치식(단일 유입)은 MWR이 단순 연환산과 일치해야 한다(월 IRR 연율화 왜곡 방지)."""
    hist, _d, _p = _history(0.0)
    end = float(hist["portfolio_value"].iloc[-1])
    perf = _perf_block(hist, end, 10_000_000.0, 0.0)
    years = len(hist) / 252
    assert perf["metrics"]["cagr"] == pytest.approx((end / 10_000_000.0) ** (1 / years) - 1, abs=0.01)
