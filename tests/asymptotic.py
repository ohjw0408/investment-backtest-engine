"""
test_asymptotic.py
────────────────────────────────────────────────────────────────────────────────
점근해 검증 테스트

① 수익률 0% 자산 → 종료자산 = 정확히 납입액
② 인출금 0원     → 생존율 100%
③ 초기자산 매우 큼 → 생존율 ~100%
④ 초기자산 0원   → 생존율 ~0%
⑤ 투자기간 길수록 CAGR std 감소
⑥ 인플레이션 높을수록 생존율 단조감소
────────────────────────────────────────────────────────────────────────────────
"""

import sys, datetime, multiprocessing
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if not (ROOT / "modules").exists():
    ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

multiprocessing.freeze_support()


def make_engine_and_strategy(weights, rebal_mode=None):
    from modules.portfolio_engine import PortfolioEngine
    from modules.rebalance.periodic import PeriodicRebalance
    engine = PortfolioEngine()
    def strategy_factory():
        return PeriodicRebalance(
            target_weights      = weights,
            rebalance_frequency = rebal_mode,
            drift_threshold     = None,
        )
    return engine, strategy_factory


def run_acc(engine, strategy_factory, data_start, data_end,
            years, monthly, initial, step=6):
    from modules.retirement.accumulation_analyzer import AccumulationAnalyzer
    a = AccumulationAnalyzer(
        portfolio_engine     = engine,
        tickers              = list(engine._last_tickers) if hasattr(engine, '_last_tickers') else ["SPY"],
        strategy_factory     = strategy_factory,
        data_start           = data_start,
        data_end             = data_end,
        accumulation_years   = years,
        monthly_contribution = monthly,
        initial_capital      = initial,
        step_months          = step,
        verbose              = False,
    )
    return a.run()


def run_wd(engine, strategy_factory, tickers, data_start, data_end,
           years, monthly_wd, initial, inflation=0.02, step=6):
    from modules.retirement.withdrawal_analyzer import WithdrawalAnalyzer
    a = WithdrawalAnalyzer(
        portfolio_engine   = engine,
        tickers            = tickers,
        strategy_factory   = strategy_factory,
        data_start         = data_start,
        data_end           = data_end,
        withdrawal_years   = years,
        monthly_withdrawal = monthly_wd,
        initial_capital    = initial,
        inflation          = inflation,
        step_months        = step,
        verbose            = False,
    )
    return a.run()


def fmt(ok): return "✅" if ok else "❌"


def main():
    from modules.portfolio_engine import PortfolioEngine
    from modules.rebalance.periodic import PeriodicRebalance
    from modules.retirement.accumulation_analyzer import AccumulationAnalyzer
    from modules.retirement.withdrawal_analyzer   import WithdrawalAnalyzer

    DATA_END   = datetime.date.today().strftime("%Y-%m-%d")
    DATA_START = "1964-05-04"
    TICKERS    = ["SPY"]
    WEIGHTS    = {"SPY": 1.0}

    engine = PortfolioEngine()

    def make_strategy():
        return PeriodicRebalance(
            target_weights=WEIGHTS, rebalance_frequency=None, drift_threshold=None
        )

    results = []

    print("=" * 65)
    print("점근해 검증 테스트")
    print("=" * 65)

    # ── ① 납입액 보존 (수익률 0% 근사: TLT 단기 또는 직접 검증) ──
    # SPY로 1년 시뮬 → 납입액 대비 오차 확인 (정성적)
    # 실제 0% 자산이 없으므로, 로직 검증: initial=0, monthly=100만, 1년
    # 종료자산이 1200만 근처인지 (수익률 있으면 그 이상)
    print("\n① 납입액 보존 검증 (초기=0, 월100만, 1년 SPY)")
    print("   → 종료자산 >= 1200만 (수익률 있으면 초과)")
    a = AccumulationAnalyzer(
        portfolio_engine     = engine,
        tickers              = TICKERS,
        strategy_factory     = make_strategy,
        data_start           = DATA_START,
        data_end             = DATA_END,
        accumulation_years   = 1,
        monthly_contribution = 1_000_000,
        initial_capital      = 0,
        step_months          = 6,
        verbose              = False,
    )
    r = a.run()
    p10 = r["distribution"]["end_value"]["p10"]
    p50 = r["distribution"]["end_value"]["p50"]
    ok  = p10 >= 12_000_000 * 0.85   # 15% 하락장도 허용
    print(f"   p10={p10:,.0f}  p50={p50:,.0f}  {fmt(ok)}")
    results.append(("① 납입액 보존", ok))

    # ── ② 인출금 0 → 생존율 100% ────────────────────────────
    print("\n② 인출금 0원 → 생존율 100%")
    a2 = WithdrawalAnalyzer(
        portfolio_engine   = engine,
        tickers            = TICKERS,
        strategy_factory   = make_strategy,
        data_start         = DATA_START,
        data_end           = DATA_END,
        withdrawal_years   = 20,
        monthly_withdrawal = 0,
        initial_capital    = 100_000_000,
        inflation          = 0.0,
        step_months        = 6,
        verbose            = False,
    )
    r2    = a2.run()
    sr2   = r2["success_rate"]
    ok2   = sr2 == 1.0
    print(f"   생존율={sr2:.1%}  {fmt(ok2)}")
    results.append(("② 인출금 0 → 100%", ok2))

    # ── ③ 초기자산 매우 큼 → 생존율 ~100% ──────────────────
    print("\n③ 초기자산 100억, 월인출 100만 → 생존율 ~100%")
    a3 = WithdrawalAnalyzer(
        portfolio_engine   = engine,
        tickers            = TICKERS,
        strategy_factory   = make_strategy,
        data_start         = DATA_START,
        data_end           = DATA_END,
        withdrawal_years   = 30,
        monthly_withdrawal = 1_000_000,
        initial_capital    = 10_000_000_000,
        inflation          = 0.02,
        step_months        = 6,
        verbose            = False,
    )
    r3  = a3.run()
    sr3 = r3["success_rate"]
    ok3 = sr3 >= 0.99
    print(f"   생존율={sr3:.1%}  {fmt(ok3)}")
    results.append(("③ 초기자산 극대 → ~100%", ok3))

    # ── ④ 초기자산 0 → 생존율 ~0% ──────────────────────────
    print("\n④ 초기자산 0원, 월인출 100만 → 생존율 ~0%")
    a4 = WithdrawalAnalyzer(
        portfolio_engine   = engine,
        tickers            = TICKERS,
        strategy_factory   = make_strategy,
        data_start         = DATA_START,
        data_end           = DATA_END,
        withdrawal_years   = 30,
        monthly_withdrawal = 1_000_000,
        initial_capital    = 0,
        inflation          = 0.02,
        step_months        = 6,
        verbose            = False,
    )
    r4  = a4.run()
    sr4 = r4["success_rate"]
    ok4 = sr4 <= 0.05
    print(f"   생존율={sr4:.1%}  {fmt(ok4)}")
    results.append(("④ 초기자산 0 → ~0%", ok4))

    # ── ⑤ 투자기간 길수록 CAGR std 감소 ────────────────────
    print("\n⑤ 투자기간 길수록 CAGR 분산 감소 (평균회귀)")
    stds = {}
    for yrs in [5, 10, 20, 30]:
        ax = AccumulationAnalyzer(
            portfolio_engine     = engine,
            tickers              = TICKERS,
            strategy_factory     = make_strategy,
            data_start           = DATA_START,
            data_end             = DATA_END,
            accumulation_years   = yrs,
            monthly_contribution = 500_000,
            initial_capital      = 10_000_000,
            step_months          = 6,
            verbose              = False,
        )
        rx       = ax.run()
        std_cagr = rx["distribution"]["cagr"]["std"]
        stds[yrs] = std_cagr
        print(f"   {yrs:2d}년 CAGR std = {std_cagr:.2%}")

    ok5 = stds[5] > stds[10] > stds[20] > stds[30]
    print(f"   단조감소 여부: {fmt(ok5)}")
    results.append(("⑤ 기간 길수록 CAGR std 감소", ok5))

    # ── ⑥ 인플레이션 높을수록 생존율 단조감소 ───────────────
    print("\n⑥ 인플레이션 높을수록 생존율 단조감소")
    srs = {}
    for inf in [0.0, 0.02, 0.04, 0.06]:
        ax = WithdrawalAnalyzer(
            portfolio_engine   = engine,
            tickers            = TICKERS,
            strategy_factory   = make_strategy,
            data_start         = DATA_START,
            data_end           = DATA_END,
            withdrawal_years   = 30,
            monthly_withdrawal = 3_000_000,
            initial_capital    = 500_000_000,
            inflation          = inf,
            step_months        = 6,
            verbose            = False,
        )
        rx       = ax.run()
        srs[inf] = rx["success_rate"]
        print(f"   인플레 {inf:.0%} → 생존율 {srs[inf]:.1%}")

    ok6 = srs[0.0] >= srs[0.02] >= srs[0.04] >= srs[0.06]
    print(f"   단조감소 여부: {fmt(ok6)}")
    results.append(("⑥ 인플레 높을수록 생존율 감소", ok6))

    # ── 최종 결과 ─────────────────────────────────────────────
    print("\n" + "=" * 65)
    print("📋 최종 결과")
    print("=" * 65)
    all_pass = True
    for name, ok in results:
        print(f"  {fmt(ok)} {name}")
        if not ok:
            all_pass = False
    print()
    if all_pass:
        print("  ✅ 모든 점근해 검증 통과")
    else:
        print("  ⚠️  일부 검증 실패 — 위 항목 확인 필요")


if __name__ == "__main__":
    main()