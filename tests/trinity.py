"""
test_trinity.py
────────────────────────────────────────────────────────────────────────────────
Trinity Study 4% 룰 검증

원본 Trinity Study 조건:
- 초기 자산의 4% = 연간 고정 인출액 (명목)
- 매년 인플레이션만큼 인출액 증가
- 30년간 생존 여부 확인
- 역사적 생존율: 주식 100% 기준 ~95%

테스트:
  [1] 인플레 0%   (명목 고정 인출) → 생존율이 가장 높아야
  [2] 인플레 2%   (현실적)         → 약간 낮아야
  [3] 인플레 3%   (트리니티 원본)  → ~95% 나와야
  [4] 인플레 5%   (고인플레)       → 더 낮아야

포트폴리오별 비교: SPY, QQQ, SCHD, SPY50+SCHD50
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
    from modules.retirement.withdrawal_analyzer import WithdrawalAnalyzer

    DATA_END   = datetime.date.today().strftime("%Y-%m-%d")
    DATA_START = "1964-05-04"
    engine     = PortfolioEngine()

    INITIAL       = 500_000_000          # 초기자산 5억
    ANNUAL_WD_PCT = 0.04                 # 4% 인출
    MONTHLY_WD    = round(INITIAL * ANNUAL_WD_PCT / 12)  # 월 인출 고정액
    WD_YEARS      = 30

    print("=" * 70)
    print("Trinity Study 4% 룰 검증")
    print(f"초기자산: {INITIAL:,.0f}원  연 인출율: {ANNUAL_WD_PCT:.0%}")
    print(f"월 인출액: {MONTHLY_WD:,.0f}원 (고정, 인플레 반영분은 매년 복리 증가)")
    print("=" * 70)

    def make_strategy(weights):
        def factory():
            return PeriodicRebalance(
                target_weights=weights, rebalance_frequency=None, drift_threshold=None
            )
        return factory

    def run_wd(tickers, weights, inflation):
        a = WithdrawalAnalyzer(
            portfolio_engine   = engine,
            tickers            = tickers,
            strategy_factory   = make_strategy(weights),
            data_start         = DATA_START,
            data_end           = DATA_END,
            withdrawal_years   = WD_YEARS,
            monthly_withdrawal = MONTHLY_WD,
            initial_capital    = INITIAL,
            inflation          = inflation,
            step_months        = 6,
            verbose            = False,
        )
        return a.run()

    portfolios = [
        ("SPY 100%",     ["SPY"],        {"SPY": 1.0}),
        ("QQQ 100%",     ["QQQ"],        {"QQQ": 1.0}),
        ("SCHD 100%",    ["SCHD"],       {"SCHD": 1.0}),
        ("SPY50+SCHD50", ["SPY","SCHD"], {"SPY": 0.5, "SCHD": 0.5}),
    ]

    inflation_cases = [
        (0.00, "명목 고정"),
        (0.02, "인플레 2%"),
        (0.03, "트리니티 원본 (~3%)"),
        (0.05, "고인플레 5%"),
    ]

    # ── 인플레별 SPY 생존율 ───────────────────────────────
    print(f"\n[1] SPY 100% — 인플레별 생존율 (단조감소 확인)")
    print(f"  {'인플레':<20s}  {'생존율':>7s}  {'종료배수 p10':>12s}  {'종료배수 p50':>12s}  판정")
    print(f"  {'-'*65}")

    prev_sr = 1.01
    all_monotone = True
    for inf, label in inflation_cases:
        r   = run_wd(["SPY"], {"SPY": 1.0}, inf)
        sr  = r["success_rate"]
        p10 = r["distribution"]["end_value_ratio"]["p10"]
        p50 = r["distribution"]["end_value_ratio"]["p50"]
        ok  = sr <= prev_sr
        flag = "✅" if ok else "⚠️ "
        if not ok: all_monotone = False
        print(f"  {label:<20s}  {sr:>7.1%}  {p10:>12.2f}x  {p50:>12.2f}x  {flag}")
        prev_sr = sr

    print(f"\n  단조감소: {'✅ 확인' if all_monotone else '⚠️  불규칙'}")

    # ── 트리니티 원본 조건 (인플레 3%) 포트폴리오별 비교 ─
    print(f"\n[2] 인플레 3% (트리니티 원본) — 포트폴리오별 생존율")
    print(f"    역사적 기준: 주식 100% 기준 ~95%")
    print(f"  {'포트폴리오':<18s}  {'생존율':>7s}  {'종료배수 p10':>12s}  {'종료배수 p50':>12s}  판정")
    print(f"  {'-'*65}")

    for name, tickers, weights in portfolios:
        r   = run_wd(tickers, weights, 0.03)
        sr  = r["success_rate"]
        p10 = r["distribution"]["end_value_ratio"]["p10"]
        p50 = r["distribution"]["end_value_ratio"]["p50"]
        ok  = sr >= 0.85
        flag = "✅" if ok else "⚠️ "
        print(f"  {name:<18s}  {sr:>7.1%}  {p10:>12.2f}x  {p50:>12.2f}x  {flag}")

    # ── 인출율별 생존율 (SPY, 인플레 3%) ─────────────────
    print(f"\n[3] 인출율별 생존율 (SPY, 인플레 3%)")
    print(f"    3% 룰 → ~100%, 4% → ~95%, 5% → ~80%, 6% → ~65% 예상")
    print(f"  {'인출율':<10s}  {'월인출':>14s}  {'생존율':>7s}  판정")
    print(f"  {'-'*45}")

    expected = {0.03: 0.95, 0.04: 0.85, 0.05: 0.70, 0.06: 0.55}
    for pct in [0.03, 0.04, 0.05, 0.06]:
        monthly = round(INITIAL * pct / 12)
        a = WithdrawalAnalyzer(
            portfolio_engine   = engine,
            tickers            = ["SPY"],
            strategy_factory   = make_strategy({"SPY": 1.0}),
            data_start         = DATA_START,
            data_end           = DATA_END,
            withdrawal_years   = WD_YEARS,
            monthly_withdrawal = monthly,
            initial_capital    = INITIAL,
            inflation          = 0.03,
            step_months        = 6,
            verbose            = False,
        )
        r    = a.run()
        sr   = r["success_rate"]
        ok   = sr >= expected[pct]
        flag = "✅" if ok else "⚠️ "
        print(f"  {pct:.0%}룰{'':<5s}  {monthly:>14,.0f}원  {sr:>7.1%}  {flag}")

    print(f"\n{'=' * 70}\n완료")


if __name__ == "__main__":
    main()