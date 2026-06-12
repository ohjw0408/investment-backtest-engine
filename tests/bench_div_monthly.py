# -*- coding: utf-8 -*-
"""게이트 벤치마크 (divrefactoring) — 구 DividendSimulator vs 신 월별모드 SimulationLoop.

실데이터(로컬 DB)로 동일 롤링 윈도우 집합을 양쪽으로 실행해
① 속도비(신/구) ② 수치 드리프트 분포를 출력한다.

게이트 기준(오너 합의): 역산 1회 비용 비율 ≤ 5배. 초과 시 통합 중단·보고.
실행: venv\\Scripts\\python.exe tests\\bench_div_monthly.py
"""
import sys
import os
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.stdout.reconfigure(encoding="utf-8")

import numpy as np
import pandas as pd

from modules.dividend_simulator import DividendSimulator
from modules.simulation.monthly_mode import to_monthly_price_data, last_year_dividend

TICKERS = {"458730": 1.0}     # TIGER 미국배당다우존스 — 대표 배당 시나리오
SEED, MONTHLY, YEARS = 50_000_000.0, 1_000_000.0, 15
STEP_MONTHS = 3


def _new_one(daily_data, weights, start, years, seed, monthly_amt, tax_engine=None):
    from modules.config.simulation_config import SimulationConfig
    from modules.core.portfolio import Portfolio, TaxTrackedPortfolio
    from modules.execution.order_executor import OrderExecutor, TaxedOrderExecutor
    from modules.execution.cash_allocator import CashAllocator
    from modules.simulation.dividend_engine import DividendEngine
    from modules.tax.account_tax import TaxedDividendEngine
    from modules.tax.session import TaxSessionState
    from modules.simulation.contribution_engine import ContributionEngine
    from modules.simulation.withdrawal_engine import WithdrawalEngine
    from modules.simulation.history_recorder import HistoryRecorder
    from modules.simulation.simulation_loop import SimulationLoop
    from modules.rebalance.periodic import PeriodicRebalance

    start = pd.Timestamp(start)
    end = start + pd.DateOffset(years=years)
    sliced = {t: df.loc[start:end] for t, df in daily_data.items()}
    if any(s.empty for s in sliced.values()):
        return None
    m_data, m_dates = to_monthly_price_data(sliced)

    cfg = SimulationConfig(
        start_date=str(start.date()), end_date=str(end.date()),
        tickers=list(weights.keys()), target_weights=weights,
        initial_capital=seed, monthly_contribution=monthly_amt,
        withdrawal_amount=0, dividend_mode="reinvest",
        rebalance_frequency=None, inflation=0.0,
    )
    if tax_engine is not None:
        session = TaxSessionState(other_financial_income=0.0)
        pf = TaxTrackedPortfolio(seed)
        div_engine = TaxedDividendEngine(DividendEngine(), tax_engine, "위탁", session=session)
        executor = TaxedOrderExecutor(tax_engine, "위탁", session=session)
    else:
        pf = Portfolio(seed)
        div_engine = DividendEngine()
        executor = OrderExecutor()
    loop = SimulationLoop(div_engine, ContributionEngine(),
                          WithdrawalEngine(), executor, CashAllocator())
    rec = HistoryRecorder()
    loop.run(pf, PeriodicRebalance(weights, rebalance_frequency=None),
             cfg, m_data, m_dates, rec)
    return last_year_dividend(rec.to_dataframe(), end)


def main():
    from modules.portfolio_engine import PortfolioEngine
    loader = PortfolioEngine().loader

    sim = DividendSimulator(loader=loader, tickers=list(TICKERS),
                            weights=TICKERS, div_mode="reinvest", rebal_mode="none")
    daily_data = {t: sim._load(t) for t in TICKERS}
    # 속도 벤치 목적 — 백필 포함 전체 범위 사용(시뮬 비용은 기간 길이에 비례, 정확 서비스 재현 아님)
    data_start = max(df.index.min() for df in daily_data.values())
    data_end = min(df.index.max() for df in daily_data.values())
    print(f"data: {data_start.date()} ~ {data_end.date()}")

    # 동일 윈도우 집합 (구엔진 _roll_window와 같은 스텝). 최대 40개로 캡(벤치 시간 관리).
    windows, cur = [], pd.Timestamp(data_start)
    while cur + pd.DateOffset(years=YEARS) <= data_end and len(windows) < 40:
        windows.append(cur)
        cur += pd.DateOffset(months=STEP_MONTHS)
    print(f"windows: {len(windows)} (years={YEARS}, step={STEP_MONTHS}m)")
    if not windows:
        print("윈도우 0개 - 기간 줄여서 재시도 필요")
        return

    # ── 구엔진 (무세금) ──
    t0 = time.perf_counter()
    old_vals = [sim._simulate_one(SEED, MONTHLY, YEARS, s) for s in windows]
    t_old = time.perf_counter() - t0

    # ── 구엔진 (세금 ON — 실사용 기준선) ──
    from modules.tax.base_tax import TaxEngine as _TE
    sim_tax = DividendSimulator(loader=loader, tickers=list(TICKERS), weights=TICKERS,
                                div_mode="reinvest", rebal_mode="none",
                                tax_engine=_TE({"earned_income": 50_000_000, "age": 40}),
                                account_type="위탁")
    sim_tax._price_cache = sim._price_cache
    t0 = time.perf_counter()
    oldtax_vals = [sim_tax._simulate_one(SEED, MONTHLY, YEARS, s) for s in windows]
    t_oldtax = time.perf_counter() - t0

    # ── 신엔진 (무세금) ──
    t0 = time.perf_counter()
    new_vals = [_new_one(daily_data, TICKERS, s, YEARS, SEED, MONTHLY) for s in windows]
    t_new = time.perf_counter() - t0

    # ── 신엔진 (세금 ON — 실사용 형태) ──
    from modules.tax.base_tax import TaxEngine
    te = TaxEngine({"earned_income": 50_000_000, "age": 40})
    t0 = time.perf_counter()
    newtax_vals = [_new_one(daily_data, TICKERS, s, YEARS, SEED, MONTHLY, tax_engine=te)
                   for s in windows]
    t_newtax = time.perf_counter() - t0

    pairs = [(o, n) for o, n in zip(old_vals, new_vals) if o and n and o > 0]
    rels = [abs(o - n) / o for o, n in pairs]
    tax_pairs = [(o, n) for o, n in zip(oldtax_vals, newtax_vals) if o and n and o > 0]
    tax_rels = [abs(o - n) / o for o, n in tax_pairs]
    print(f"\n속도  구(무세금): {t_old:.2f}s / 신(무세금): {t_new:.2f}s (x{t_new/t_old:.2f})")
    print(f"속도  구(세금ON): {t_oldtax:.2f}s / 신(세금ON): {t_newtax:.2f}s (x{t_newtax/t_oldtax:.2f})")
    print(f"수치(무세금 {len(pairs)}윈도우)  중앙 상대차 {np.median(rels):.4f} / 최대 {max(rels):.4f}")
    print(f"수치(세금ON {len(tax_pairs)}윈도우)  중앙 상대차 {np.median(tax_rels):.4f} / 최대 {max(tax_rels):.4f}")
    print(f"표본  구 p50 {np.median([o for o,_ in pairs]):,.0f} / "
          f"신 p50 {np.median([n for _,n in pairs]):,.0f}")
    ratio = t_newtax / t_oldtax
    print(f"\n게이트(세금ON 동조건 ≤5배): {'PASS' if ratio <= 5 else 'FAIL'} (x{ratio:.2f})")

    if "--profile" in sys.argv:
        import cProfile, pstats
        pr = cProfile.Profile()
        pr.enable()
        for s in windows[:10]:
            _new_one(daily_data, TICKERS, s, YEARS, SEED, MONTHLY, tax_engine=te)
        pr.disable()
        pstats.Stats(pr).sort_stats("cumulative").print_stats(25)


if __name__ == "__main__":
    main()
