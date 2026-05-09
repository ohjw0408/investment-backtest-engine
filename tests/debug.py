"""
test_quantitative.py
────────────────────────────────────────────────────────────────────────────────
정량 검증 테스트

[A] 역사적 수익률 벤치마크 비교
    - SPY  20년 CAGR 중앙값 → 역사적 ~10%
    - QQQ  20년 CAGR 중앙값 → 역사적 ~15%
    - SCHD 20년 CAGR 중앙값 → 역사적 ~12%

[B] 4% 룰 검증 (Trinity Study)
    - 초기자산의 4% 연간 인출 = 월 인출액
    - 30년 생존율 → 역사적으로 ~95% (SPY 기준)

[C] 포트폴리오 비교표
    - SPY 100% / QQQ 100% / SCHD 100%
    - SPY 50%+SCHD 50% / QQQ 70%+SCHD 30%
    - 축적 20년: CAGR p50, MDD p50, Sharpe p50
    - 인출 30년: 생존율, 종료자산배수 p50
────────────────────────────────────────────────────────────────────────────────
"""

import sys, datetime, multiprocessing
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if not (ROOT / "modules").exists():
    ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

multiprocessing.freeze_support()


def main():
    from modules.portfolio_engine import PortfolioEngine
    from modules.rebalance.periodic import PeriodicRebalance
    from modules.retirement.accumulation_analyzer import AccumulationAnalyzer
    from modules.retirement.withdrawal_analyzer   import WithdrawalAnalyzer
    from modules.retirement.data_preparer         import DataPreparer

    DATA_END   = datetime.date.today().strftime("%Y-%m-%d")
    PRICE_DB   = ROOT / "data" / "price_cache" / "price_daily.db"
    engine     = PortfolioEngine()

    def make_strategy(weights, rebal=None):
        def factory():
            return PeriodicRebalance(
                target_weights=weights, rebalance_frequency=rebal, drift_threshold=None
            )
        return factory

    def prep_data(tickers, sim_years):
        p = DataPreparer(price_db_path=PRICE_DB, verbose=False)
        r = p.prepare(tickers=tickers, sim_years=sim_years, data_end=DATA_END)
        p.close()
        return r["data_start"]

    def acc(tickers, weights, years=20, monthly=500_000, initial=10_000_000, step=6):
        data_start = prep_data(tickers, years)
        a = AccumulationAnalyzer(
            portfolio_engine     = engine,
            tickers              = tickers,
            strategy_factory     = make_strategy(weights),
            data_start           = data_start,
            data_end             = DATA_END,
            accumulation_years   = years,
            monthly_contribution = monthly,
            initial_capital      = initial,
            step_months          = step,
            verbose              = False,
        )
        return a.run()

    def wd(tickers, weights, initial, monthly_wd, years=30, inflation=0.02, step=6):
        data_start = prep_data(tickers, years)
        a = WithdrawalAnalyzer(
            portfolio_engine   = engine,
            tickers            = tickers,
            strategy_factory   = make_strategy(weights),
            data_start         = data_start,
            data_end           = DATA_END,
            withdrawal_years   = years,
            monthly_withdrawal = monthly_wd,
            initial_capital    = initial,
            inflation          = inflation,
            step_months        = step,
            verbose            = False,
        )
        return a.run()

    # ════════════════════════════════════════════════════════
    # [A] 역사적 수익률 벤치마크
    # ════════════════════════════════════════════════════════
    print("=" * 65)
    print("[A] 역사적 수익률 벤치마크 (축적 20년, 월적립 없음, 초기 1억)")
    print("=" * 65)
    print(f"  {'종목':<12s}  {'CAGR p10':>9s}  {'CAGR p50':>9s}  {'CAGR p90':>9s}  {'기준값':>8s}  판정")
    print(f"  {'-'*62}")

    benchmarks = [
        (["SPY"],  {"SPY":  1.0}, "~10%", 0.07, 0.13),
        (["QQQ"],  {"QQQ":  1.0}, "~15%", 0.10, 0.22),
        (["SCHD"], {"SCHD": 1.0}, "~12%", 0.08, 0.17),
    ]

    for tickers, weights, label, low, high in benchmarks:
        r    = acc(tickers, weights, years=20, monthly=0, initial=100_000_000)
        dist = r["distribution"]["cagr"]
        p10, p50, p90 = dist["p10"], dist["p50"], dist["p90"]
        ok   = low <= p50 <= high
        flag = "✅" if ok else "⚠️ "
        print(f"  {tickers[0]:<12s}  {p10:>8.2%}  {p50:>8.2%}  {p90:>8.2%}  {label:>8s}  {flag}")

    # ════════════════════════════════════════════════════════
    # [B] 4% 룰 검증 (Trinity Study)
    # ════════════════════════════════════════════════════════
    print(f"\n{'=' * 65}")
    print("[B] 4% 룰 검증 (SPY, 30년, 초기자산의 4% 연간 인출, 인플레 0%)")
    print("    Trinity Study 기준: 생존율 ~95%")
    print("=" * 65)

    initial_4pct  = 500_000_000
    monthly_4pct  = round(initial_4pct * 0.04 / 12)
    print(f"  초기자산: {initial_4pct:,.0f}원  월인출: {monthly_4pct:,.0f}원")

    r_4pct = wd(
        tickers    = ["SPY"],
        weights    = {"SPY": 1.0},
        initial    = initial_4pct,
        monthly_wd = monthly_4pct,
        years      = 30,
        inflation  = 0.0,
    )
    sr   = r_4pct["success_rate"]
    ok   = 0.85 <= sr <= 1.0
    flag = "✅" if ok else "⚠️ "
    print(f"  생존율: {sr:.1%}  (기준: 85~100%)  {flag}")
    print(f"  종료자산배수 p50: {r_4pct['distribution']['end_value_ratio']['p50']:.2f}x")

    # ════════════════════════════════════════════════════════
    # [C] 포트폴리오 비교표
    # ════════════════════════════════════════════════════════
    print(f"\n{'=' * 65}")
    print("[C] 포트폴리오 비교 (축적 20년 / 인출 30년)")
    print("=" * 65)

    portfolios = [
        ("SPY 100%",         ["SPY"],         {"SPY": 1.0}),
        ("QQQ 100%",         ["QQQ"],         {"QQQ": 1.0}),
        ("SCHD 100%",        ["SCHD"],        {"SCHD": 1.0}),
        ("SPY50+SCHD50",     ["SPY","SCHD"],  {"SPY": 0.5, "SCHD": 0.5}),
        ("QQQ70+SCHD30",     ["QQQ","SCHD"],  {"QQQ": 0.7, "SCHD": 0.3}),
    ]

    # 축적 비교
    print(f"\n  [축적 20년]  월적립 50만, 초기 1천만")
    print(f"  {'포트폴리오':<18s}  {'CAGR p50':>9s}  {'MDD p50':>8s}  {'Sharpe p50':>10s}  {'케이스':>6s}")
    print(f"  {'-'*60}")

    acc_results = {}
    for name, tickers, weights in portfolios:
        r = acc(tickers, weights, years=20, monthly=500_000, initial=10_000_000)
        d = r["distribution"]
        cagr   = d["cagr"]["p50"]
        mdd    = d["mdd"]["p50"]
        sharpe = d["sharpe"]["p50"]
        n      = r["n_real"]
        acc_results[name] = r
        print(f"  {name:<18s}  {cagr:>8.2%}  {mdd:>8.2%}  {sharpe:>10.2f}  {n:>6d}")

    # 인출 비교 (축적 p50 종료자산을 초기자산으로)
    print(f"\n  [인출 30년]  월인출 300만, 인플레 2%")
    print(f"  {'포트폴리오':<18s}  {'초기자산':>14s}  {'생존율':>7s}  {'종료배수 p50':>12s}")
    print(f"  {'-'*60}")

    for name, tickers, weights in portfolios:
        initial_wd = acc_results[name]["distribution"]["end_value"]["p50"]
        r = wd(
            tickers    = tickers,
            weights    = weights,
            initial    = initial_wd,
            monthly_wd = 3_000_000,
            years      = 30,
            inflation  = 0.02,
        )
        sr    = r["success_rate"]
        ratio = r["distribution"]["end_value_ratio"]["p50"]
        print(f"  {name:<18s}  {initial_wd:>14,.0f}  {sr:>7.1%}  {ratio:>12.2f}x")

    print(f"\n{'=' * 65}")
    print("완료")


if __name__ == "__main__":
    main()