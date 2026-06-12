"""divrefactoring 3-1/3-2 — 월별 모드 헬퍼 손계산 검증 + 구엔진 등치 앵커.

게이트 전제: 월별 모드 결과가 구 DividendSimulator와 허용 오차 내 일치해야 후속 단계 진행.
상수가격 케이스는 수학적으로 정확히 같아야 함(±1원) — 등치 앵커.
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import numpy as np
import pandas as pd

from modules.simulation.monthly_mode import to_monthly_price_data, last_year_dividend


def _daily_frame(start, end, price_fn, div_dates=None):
    """date 인덱스 일별 프레임. price_fn(i)→close, div_dates={date_str: 주당배당}."""
    dates = pd.bdate_range(start, end)
    closes = np.array([price_fn(i) for i in range(len(dates))], dtype=float)
    div = np.zeros(len(dates))
    if div_dates:
        for ds, amt in div_dates.items():
            pos = dates.searchsorted(pd.Timestamp(ds))
            if pos < len(dates):
                div[pos] = amt
    return pd.DataFrame(
        {"open": closes, "high": closes, "low": closes, "close": closes,
         "volume": 1.0, "dividend": div, "split": 1.0},
        index=dates,
    )


# ── 1. to_monthly: 합집합 달력·월말 종가·배당 월합·leading NaN ──
def test_to_monthly_basic():
    a = _daily_frame("2020-01-01", "2020-06-30", lambda i: 100.0 + i,
                     div_dates={"2020-02-10": 1.0, "2020-02-20": 2.0})
    b = _daily_frame("2020-03-01", "2020-06-30", lambda i: 50.0)
    monthly, dates = to_monthly_price_data({"A": a, "B": b})

    assert len(dates) == 6                                  # 1~6월 ME 합집합
    assert all(d == d + pd.offsets.MonthEnd(0) for d in dates)  # 전부 월말 라벨
    # 위치 정렬: 각 df 인덱스 == dates
    assert list(monthly["A"].index) == dates
    assert list(monthly["B"].index) == dates
    # A 1월 close = 그 달 마지막 일별 종가
    jan_last = a.loc["2020-01"]["close"].iloc[-1]
    assert monthly["A"]["close"].iloc[0] == jan_last
    # 배당 = 월 합계 (2월 1+2=3), 다른 달 0
    assert monthly["A"]["dividend"].iloc[1] == 3.0
    assert monthly["A"]["dividend"].iloc[0] == 0.0
    # B 상장 전 leading NaN 유지 + 배당 0
    assert np.isnan(monthly["B"]["close"].iloc[0])
    assert monthly["B"]["dividend"].iloc[0] == 0.0
    # B 상장 후 ffill 유효
    assert monthly["B"]["close"].iloc[2] == 50.0


# ── 2. last_year_dividend: 경계 = window_end − 1년, 이상(>=) ──
def test_last_year_dividend_boundary():
    rows = [
        {"date": pd.Timestamp("2023-06-30"), "dividend_income": 10.0},   # 경계 정확히 1년 전 → 포함
        {"date": pd.Timestamp("2023-06-29"), "dividend_income": 999.0},  # 1년+1일 전 → 제외
        {"date": pd.Timestamp("2024-01-31"), "dividend_income": 5.0},
        {"date": pd.Timestamp("2024-06-30"), "dividend_income": 7.0},
    ]
    df = pd.DataFrame(rows)
    assert last_year_dividend(df, pd.Timestamp("2024-06-30")) == 22.0
    assert last_year_dividend(pd.DataFrame(), "2024-06-30") == 0.0


# ── 등치 앵커용 공통 러너 ──────────────────────────────────
def _run_new_monthly(daily_data, start, years, seed, monthly_amt, weights):
    """신 경로: 월별 데이터 + SimulationLoop (무세금)."""
    from modules.config.simulation_config import SimulationConfig
    from modules.core.portfolio import Portfolio
    from modules.execution.order_executor import OrderExecutor
    from modules.execution.cash_allocator import CashAllocator
    from modules.simulation.dividend_engine import DividendEngine
    from modules.simulation.contribution_engine import ContributionEngine
    from modules.simulation.withdrawal_engine import WithdrawalEngine
    from modules.simulation.history_recorder import HistoryRecorder
    from modules.simulation.simulation_loop import SimulationLoop
    from modules.rebalance.periodic import PeriodicRebalance

    start = pd.Timestamp(start)
    end = start + pd.DateOffset(years=years)
    sliced = {t: df.loc[start:end] for t, df in daily_data.items()}
    m_data, m_dates = to_monthly_price_data(sliced)

    cfg = SimulationConfig(
        start_date=str(start.date()), end_date=str(end.date()),
        tickers=list(weights.keys()), target_weights=weights,
        initial_capital=seed, monthly_contribution=monthly_amt,
        withdrawal_amount=0, dividend_mode="reinvest",
        rebalance_frequency=None, inflation=0.0,
    )
    pf = Portfolio(seed)
    loop = SimulationLoop(DividendEngine(), ContributionEngine(),
                          WithdrawalEngine(), OrderExecutor(), CashAllocator())
    rec = HistoryRecorder()
    loop.run(pf, PeriodicRebalance(weights, rebalance_frequency=None),
             cfg, m_data, m_dates, rec)
    return last_year_dividend(rec.to_dataframe(), end)


class _FakeLoader:
    USD_KRW_START = "2000-01-01"

    def __init__(self, frames):
        self.frames = frames

    def get_price(self, code, start, end, **kw):
        df = self.frames[code].reset_index().rename(columns={"index": "date"})
        return df[["date", "close", "dividend"]].copy()


def _run_old(daily_data, start, years, seed, monthly_amt, weights):
    """구 경로: DividendSimulator._simulate_one (무세금)."""
    from modules.dividend_simulator import DividendSimulator
    sim = DividendSimulator(
        loader=_FakeLoader(daily_data), tickers=list(weights.keys()),
        weights=weights, div_mode="reinvest", rebal_mode="none",
    )
    return sim._simulate_one(seed, monthly_amt, years, start)


# ── 3. 진리값 앵커: 상수가격·무적립 → 닫힌형 손계산과 ±1원 ────
def test_truth_anchor_constant_price_closed_form():
    """가격 100 고정, 적립 0, 분기배당 0.5/주, 재투자.
    qty_n = 100,000 × 1.005^n (분기마다 0.5% 재투자).
    마지막 1년 배당 = 0.5 × 100,000 × (1.005^8 + 1.005^9 + 1.005^10 + 1.005^11)."""
    daily = {"DIV": _daily_frame(
        "2018-01-01", "2023-12-31", lambda i: 100.0,
        div_dates={f"{y}-{m:02d}-28": 0.5
                   for y in range(2018, 2024) for m in (3, 6, 9, 12)},
    )}
    new = _run_new_monthly(daily, "2019-01-02", 3, 10_000_000.0, 0.0, {"DIV": 1.0})
    expected = 0.5 * 100_000.0 * sum(1.005 ** k for k in (8, 9, 10, 11))
    # ±5원: CashAllocator 정수주 매수 잔돈(현금 보유분)만큼 재투자 수량이 미세하게 작음
    assert abs(new - expected) <= 5.0, f"신 {new} vs 손계산 {expected}"


# ── 3b. 위임 등치: DividendSimulator._simulate_one == 직접 조립 월별 루프 ──
# (3-5 교체 후 _simulate_one이 메인 엔진 월별 모드로 위임 — 배선 등치 검증.
#  구 자체루프 대비 드리프트는 게이트 벤치로 기록: 중앙 ~1%·최대 ~3.3%, 2026-06-13.)
def test_simulator_delegates_to_monthly_engine():
    daily = {"DIV": _daily_frame(
        "2018-01-01", "2023-12-31", lambda i: 100.0,
        div_dates={f"{y}-{m:02d}-28": 0.5
                   for y in range(2018, 2024) for m in (3, 6, 9, 12)},
    )}
    args = ("2019-01-02", 3, 10_000_000.0, 500_000.0, {"DIV": 1.0})
    via_sim = _run_old(daily, *args)          # DividendSimulator 경유(교체된 경로)
    direct = _run_new_monthly(daily, *args)   # 직접 조립
    assert via_sim > 0
    assert abs(via_sim - direct) <= 1.0, f"위임 {via_sim} vs 직접 {direct}"


# ── 4. 변동가격: 상대오차 5% 이내 (plan 전제조건 1) ───────────
def test_equivalence_varying_price_within_5pct():
    daily = {"DIV": _daily_frame(
        "2015-01-01", "2023-12-31", lambda i: 100.0 * (1.0003 ** i),
        div_dates={f"{y}-{m:02d}-15": 1.2
                   for y in range(2015, 2024) for m in (3, 6, 9, 12)},
    )}
    args = ("2016-01-04", 5, 20_000_000.0, 300_000.0, {"DIV": 1.0})
    old = _run_old(daily, *args)
    new = _run_new_monthly(daily, *args)
    assert old > 0 and new > 0
    rel = abs(old - new) / old
    assert rel < 0.05, f"상대오차 {rel:.4f} — 구 {old} vs 신 {new}"
