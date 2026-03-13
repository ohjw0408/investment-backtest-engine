"""
test_comprehensive.py
────────────────────────────────────────────────────────────────────────────────
종합 통합 테스트

변수: 종목/비중, 월납입금, 초기납입금, 인출금액
적립 1년 → 인출 3년

테스트 항목:
  1. 단조성 검증 (납입↑→자산↑, 인출↑→성공률↓, 초기자본↑→자산↑)
  2. 경계값 검증 (초기자본 0, 월납입 0, 인출 0, 극단값)
  3. 모드별 검증 (reinvest / cash / withdraw)
  4. 종목 조합별 검증 (SCHD/QQQ, SCHD/TLT, QQQ/TLT, SCHD단독)
────────────────────────────────────────────────────────────────────────────────
"""

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parents[1]))

from modules.portfolio_engine import PortfolioEngine
from modules.rebalance.periodic import PeriodicRebalance
from modules.retirement.accumulation_analyzer import AccumulationAnalyzer
from modules.retirement.withdrawal_analyzer import WithdrawalAnalyzer
from modules.retirement.retirement_planner import RetirementPlanner

PASS = "✅ PASS"
FAIL = "🔴 FAIL"
engine = PortfolioEngine()

def check(label, condition, detail=""):
    status = PASS if condition else FAIL
    print(f"  {status} {label}")
    if detail:
        print(f"         {detail}")
    return condition

def make_strategy(weights, freq="yearly"):
    def _factory():
        return PeriodicRebalance(target_weights=weights, rebalance_frequency=freq)
    return _factory

def run_acc(tickers, weights, monthly, initial, step=6):
    return AccumulationAnalyzer(
        portfolio_engine     = engine,
        tickers              = tickers,
        strategy_factory     = make_strategy(weights),
        data_start           = "2012-01-01",
        data_end             = "2026-01-01",
        accumulation_years   = 1,
        monthly_contribution = monthly,
        initial_capital      = initial,
        dividend_mode        = "reinvest",
        step_months          = step,
        verbose              = False,
    ).run()

def run_wd(tickers, weights, monthly_wd, initial, mode="reinvest", inflation=0.0, step=6):
    return WithdrawalAnalyzer(
        portfolio_engine    = engine,
        tickers             = tickers,
        strategy_factory    = make_strategy(weights),
        data_start          = "2012-01-01",
        data_end            = "2026-01-01",
        withdrawal_years    = 5,
        monthly_withdrawal  = monthly_wd,
        initial_capital     = initial,
        dividend_mode       = mode,
        inflation           = inflation,
        step_months         = step,
        verbose             = False,
    ).run()

# ════════════════════════════════════════════════════════════════════════════════
# 종목 조합 정의
# ════════════════════════════════════════════════════════════════════════════════

COMBOS = {
    "SCHD/QQQ": (["SCHD", "QQQ"], {"SCHD": 0.7, "QQQ": 0.3}),
    "SCHD/TLT": (["SCHD", "TLT"], {"SCHD": 0.7, "TLT": 0.3}),
    "QQQ/TLT":  (["QQQ",  "TLT"], {"QQQ":  0.6, "TLT": 0.4}),
    "SCHD단독":  (["SCHD"],        {"SCHD": 1.0}),
}

passed = 0
failed = 0

def tcheck(label, condition, detail=""):
    global passed, failed
    ok = check(label, condition, detail)
    if ok: passed += 1
    else:  failed += 1
    return ok

# ════════════════════════════════════════════════════════════════════════════════
# 1. 단조성 검증
# ════════════════════════════════════════════════════════════════════════════════

print("\n" + "="*60)
print("1. 단조성 검증")
print("="*60)

tickers, weights = COMBOS["SCHD/QQQ"]

# 1-1. 월납입↑ → 종료자산↑
print("\n  [1-1] 월납입 증가 → 종료자산 증가")
r1 = run_acc(tickers, weights, monthly=100_000,   initial=0)
r2 = run_acc(tickers, weights, monthly=500_000,   initial=0)
r3 = run_acc(tickers, weights, monthly=1_000_000, initial=0)
v1 = r1["distribution"]["end_value"]["p50"]
v2 = r2["distribution"]["end_value"]["p50"]
v3 = r3["distribution"]["end_value"]["p50"]
print(f"    월 10만: {v1:,.0f}  월 50만: {v2:,.0f}  월 100만: {v3:,.0f}")
tcheck("월납입 단조성", v1 < v2 < v3)

# 1-2. 초기자본↑ → 종료자산↑
print("\n  [1-2] 초기자본 증가 → 종료자산 증가")
r1 = run_acc(tickers, weights, monthly=300_000, initial=0)
r2 = run_acc(tickers, weights, monthly=300_000, initial=10_000_000)
r3 = run_acc(tickers, weights, monthly=300_000, initial=50_000_000)
v1 = r1["distribution"]["end_value"]["p50"]
v2 = r2["distribution"]["end_value"]["p50"]
v3 = r3["distribution"]["end_value"]["p50"]
print(f"    초기 0: {v1:,.0f}  초기 1천만: {v2:,.0f}  초기 5천만: {v3:,.0f}")
tcheck("초기자본 단조성", v1 < v2 < v3)

# 1-3. 인출액↑ → 성공률↓
print("\n  [1-3] 인출액 증가 → 성공률 감소")
initial = 15_000_000
r1 = run_wd(tickers, weights, monthly_wd=300_000,   initial=initial)
r2 = run_wd(tickers, weights, monthly_wd=500_000,   initial=initial)
r3 = run_wd(tickers, weights, monthly_wd=1_000_000, initial=initial)
s1, s2, s3 = r1["success_rate"], r2["success_rate"], r3["success_rate"]
print(f"    월 30만: {s1:.1%}  월 50만: {s2:.1%}  월 100만: {s3:.1%}")
tcheck("인출액 단조성", s1 >= s2 >= s3)

# 1-4. 인플레이션↑ → 종료자산 배수↓
print("\n  [1-4] 인플레이션 증가 → 종료자산 배수 감소")
r1 = run_wd(tickers, weights, monthly_wd=500_000, initial=initial, inflation=0.0)
r2 = run_wd(tickers, weights, monthly_wd=500_000, initial=initial, inflation=0.03)
v1 = r1["distribution"]["end_value_ratio"]["p50"]
v2 = r2["distribution"]["end_value_ratio"]["p50"]
print(f"    인플레이션 0%: {v1:.3f}x  3%: {v2:.3f}x")
tcheck("인플레이션 단조성", v2 <= v1)

# ════════════════════════════════════════════════════════════════════════════════
# 2. 경계값 검증
# ════════════════════════════════════════════════════════════════════════════════

print("\n" + "="*60)
print("2. 경계값 검증")
print("="*60)

# 2-1. 초기자본 0 + 월납입만
print("\n  [2-1] 초기자본 0, 월납입만")
r = run_acc(tickers, weights, monthly=500_000, initial=0)
v = r["distribution"]["end_value"]["p50"]
print(f"    종료자산 p50: {v:,.0f}")
tcheck("초기자본 0 정상 실행", v > 0)

# 2-2. 월납입 0 + 초기자본만
print("\n  [2-2] 월납입 0, 초기자본만")
r = run_acc(tickers, weights, monthly=0, initial=10_000_000)
v = r["distribution"]["end_value"]["p50"]
print(f"    종료자산 p50: {v:,.0f}")
tcheck("월납입 0 정상 실행", v > 0)

# 2-3. 인출 0 (생존율 100% 이어야 함)
print("\n  [2-3] 인출액 0")
r = run_wd(tickers, weights, monthly_wd=0, initial=50_000_000)
print(f"    성공률: {r['success_rate']:.1%}")
tcheck("인출 0 → 성공률 100%", r["success_rate"] == 1.0)

# 2-4. 극단적 인출 (초기자본보다 첫달 인출이 큰 경우)
print("\n  [2-4] 극단적 인출 (월 5천만, 초기자본 1천만)")
r = run_wd(tickers, weights, monthly_wd=50_000_000, initial=10_000_000)
print(f"    성공률: {r['success_rate']:.1%}")
tcheck("극단적 인출 → 성공률 0%", r["success_rate"] == 0.0)

# ════════════════════════════════════════════════════════════════════════════════
# 3. 모드별 검증
# ════════════════════════════════════════════════════════════════════════════════

print("\n" + "="*60)
print("3. 모드별 검증")
print("="*60)

initial = 50_000_000

# 3-1. reinvest > cash > withdraw (종료자산 기준)
print("\n  [3-1] reinvest 종료자산 > withdraw 종료자산")
r_reinvest = run_wd(tickers, weights, monthly_wd=300_000, initial=initial, mode="reinvest")
r_cash     = run_wd(tickers, weights, monthly_wd=300_000, initial=initial, mode="cash")
r_withdraw = run_wd(tickers, weights, monthly_wd=300_000, initial=initial, mode="withdraw")
v_r = r_reinvest["distribution"]["end_value_ratio"]["p50"]
v_c = r_cash["distribution"]["end_value_ratio"]["p50"]
v_w = r_withdraw["distribution"]["end_value_ratio"]["p50"]
print(f"    reinvest: {v_r:.3f}x  cash: {v_c:.3f}x  withdraw: {v_w:.3f}x")
tcheck("reinvest >= withdraw (배당 재투자 효과)", v_r >= v_w)
tcheck("cash >= withdraw (배당 보유 효과)", v_c >= v_w)

# 3-2. withdraw 모드: 배당이 포트폴리오에서 빠져나감
print("\n  [3-2] withdraw 모드 배당 출금 확인")
# reinvest 대비 종료자산이 작아야 함
tcheck("withdraw 종료자산 < reinvest 종료자산", v_w < v_r,
       f"{v_w:.3f}x < {v_r:.3f}x")

# ════════════════════════════════════════════════════════════════════════════════
# 4. 종목 조합별 검증
# ════════════════════════════════════════════════════════════════════════════════

print("\n" + "="*60)
print("4. 종목 조합별 검증")
print("="*60)

for name, (tickers, weights) in COMBOS.items():
    print(f"\n  [{name}]")
    try:
        # 적립
        acc = run_acc(tickers, weights, monthly=500_000, initial=5_000_000)
        d = acc["distribution"]
        acc_p50      = d["end_value"]["p50"]
        acc_cagr     = d["cagr"]["p50"]
        acc_mdd      = d["mdd"]["p50"]
        acc_sharpe   = d["sharpe"]["p50"]
        acc_div_cagr = d["dividend_cagr"]["p50"]
        acc_div_mdd  = d["dividend_mdd"]["p50"]
        acc_sortino  = d["sortino"]["p50"]
        acc_calmar   = d["calmar"]["p50"]
        acc_mwr      = d["mwr"]["p50"]

        print(f"    ── 적립 지표 (p50) ──────────────────────────")
        print(f"    종료자산:     {acc_p50:>20,.0f}원")
        print(f"    CAGR:         {acc_cagr:>19.2%}")
        print(f"    MDD:          {acc_mdd:>19.2%}")
        print(f"    Sharpe:       {acc_sharpe:>20.2f}")
        print(f"    Sortino:      {acc_sortino:>20.2f}")
        print(f"    Calmar:       {acc_calmar:>20.2f}")
        print(f"    MWR:          {acc_mwr:>19.2%}")
        print(f"    배당CAGR:     {acc_div_cagr:>19.2%}")
        print(f"    배당MDD:      {acc_div_mdd:>19.2%}")

        # 인출: 적립 종료자산을 3년 안에 소진 직전 수준 (간당간당)
        # 수익률 감안해도 고갈 가능한 수준: 종료자산 / 24개월
        monthly_wd = int(acc_p50 / 24)
        wd = run_wd(tickers, weights, monthly_wd=monthly_wd, initial=acc_p50)
        wd_d     = wd["distribution"]
        wd_sr    = wd["success_rate"]
        wd_ratio = wd_d["end_value_ratio"]["p50"]
        wd_mdd   = wd_d["mdd"]["p50"]
        wd_cov   = wd_d["withdrawal_coverage"]["p50"]
        wd_seqr  = wd_d["sequence_risk"]["p50"]
        wd_divmdd= wd_d["dividend_mdd"]["p50"]
        wd_total_div = wd_d["total_dividend"]["p50"]

        print(f"    ── 인출 지표 (월 {monthly_wd:,.0f}원, p50) ─────────────")
        print(f"    성공률:       {wd_sr:>19.1%}")
        print(f"    종료자산 배수:{wd_ratio:>20.2f}x")
        print(f"    MDD:          {wd_mdd:>19.2%}")
        print(f"    총배당금:     {wd_total_div:>20,.0f}원")
        print(f"    배당커버리지: {wd_cov:>19.2%}")
        print(f"    Sequence Risk:{wd_seqr:>19.2%}")
        print(f"    배당MDD:      {wd_divmdd:>19.2%}")

        tcheck(f"{name} 적립 정상 실행", acc_p50 > 0)
        tcheck(f"{name} 인출 성공률 범위", 0 <= wd_sr <= 1)
        tcheck(f"{name} 종료자산 배수 범위", wd_ratio >= 0)

    except Exception as e:
        tcheck(f"{name} 실행 오류 없음", False, str(e))

# ════════════════════════════════════════════════════════════════════════════════
# 결과 요약
# ════════════════════════════════════════════════════════════════════════════════

print("\n" + "="*60)
print(f"종합 결과: {passed}개 통과 / {failed}개 실패 / 총 {passed+failed}개")
print("="*60)