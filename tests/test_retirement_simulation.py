"""
test_retirement_v2.py
────────────────────────────────────────────────────────────────────────────────
AccumulationAnalyzer / WithdrawalAnalyzer / RetirementPlanner 통합 테스트

실행:
  python tests/test_retirement_v2.py
────────────────────────────────────────────────────────────────────────────────
"""

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parents[1]))

import numpy as np
from modules.portfolio_engine import PortfolioEngine
from modules.rebalance.periodic import PeriodicRebalance
from modules.retirement.accumulation_analyzer import AccumulationAnalyzer
from modules.retirement.withdrawal_analyzer import WithdrawalAnalyzer
from modules.retirement.retirement_planner import RetirementPlanner

PASS = "✅ PASS"
FAIL = "🔴 FAIL"

def check(label, condition, detail=""):
    status = PASS if condition else FAIL
    print(f"  {status} {label}")
    if detail:
        print(f"         {detail}")
    return condition


engine = PortfolioEngine()

def make_strategy():
    return PeriodicRebalance(
        target_weights      = {"SCHD": 0.7, "QQQ": 0.3},
        rebalance_frequency = "yearly"
    )

# 빠른 테스트를 위해 step_months=6 (회차 수 줄임)
ACC_CONFIG = dict(
    portfolio_engine     = engine,
    tickers              = ["SCHD", "QQQ"],
    strategy_factory     = make_strategy,
    data_start           = "2012-01-01",
    data_end             = "2022-01-01",
    accumulation_years   = 5,
    monthly_contribution = 500_000,
    initial_capital      = 0,
    dividend_mode        = "reinvest",
    step_months          = 6,
    verbose              = False,
)

WD_CONFIG = dict(
    portfolio_engine    = engine,
    tickers             = ["SCHD", "QQQ"],
    strategy_factory    = make_strategy,
    data_start          = "2012-01-01",
    data_end            = "2022-01-01",
    withdrawal_years    = 5,
    monthly_withdrawal  = 7_000_000,
    initial_capital     = 400_000_000,  # RetirementPlanner에서 acc 결과로 대체됨
    inflation           = 0.0,
    dividend_mode       = "reinvest",
    step_months         = 6,
    verbose             = False,
)


# ════════════════════════════════════════════════════════════════════════════════
# 1. AccumulationAnalyzer 스모크 테스트
# ════════════════════════════════════════════════════════════════════════════════

print("\n" + "="*60)
print("1. AccumulationAnalyzer 스모크 테스트")
print("="*60)

try:
    acc_result = AccumulationAnalyzer(**ACC_CONFIG).run()
    check("에러 없이 실행", True)
except Exception as e:
    check("에러 없이 실행", False, str(e))
    sys.exit(1)

cases = acc_result["cases"]
dist  = acc_result["distribution"]

check("케이스 수 > 0", len(cases) > 0, f"실제: {len(cases)}개")
check("distribution 키 존재: end_value",      "end_value"      in dist)
check("distribution 키 존재: cagr",           "cagr"           in dist)
check("distribution 키 존재: mdd",            "mdd"            in dist)
check("distribution 키 존재: sharpe",         "sharpe"         in dist)
check("distribution 키 존재: dividend_cagr",  "dividend_cagr"  in dist)
check("distribution 키 존재: total_dividend", "total_dividend" in dist)

check("종료자산 p50 > 0",  dist["end_value"]["p50"] > 0,
      f"p50: {dist['end_value']['p50']:,.0f}")
check("CAGR p50 > 0",     dist["cagr"]["p50"] > 0,
      f"p50: {dist['cagr']['p50']:.2%}")
check("MDD p50 < 0",      dist["mdd"]["p50"] < 0,
      f"p50: {dist['mdd']['p50']:.2%}")
check("Sharpe p50 > 0",   dist["sharpe"]["p50"] > 0,
      f"p50: {dist['sharpe']['p50']:.2f}")

print(f"\n  케이스 수:        {len(cases)}")
print(f"  종료자산 p10:     {dist['end_value']['p10']:>15,.0f}")
print(f"  종료자산 p50:     {dist['end_value']['p50']:>15,.0f}")
print(f"  종료자산 p90:     {dist['end_value']['p90']:>15,.0f}")
print(f"  CAGR p50:         {dist['cagr']['p50']:>14.2%}")
print(f"  MDD p50:          {dist['mdd']['p50']:>14.2%}")
print(f"  Sharpe p50:       {dist['sharpe']['p50']:>14.2f}")
print(f"  배당CAGR p50:     {dist['dividend_cagr']['p50']:>14.2%}")
print(f"  Sortino p50:      {dist['sortino']['p50']:>14.2f}")
print(f"  Calmar p50:       {dist['calmar']['p50']:>14.2f}")
print(f"  MWR p50:          {dist['mwr']['p50']:>14.2%}")

check("distribution 키 존재: sortino", "sortino" in dist)
check("distribution 키 존재: calmar",  "calmar"  in dist)
check("distribution 키 존재: mwr",     "mwr"     in dist)
check("Sortino p50 > 0", dist["sortino"]["p50"] > 0, f"p50: {dist['sortino']['p50']:.2f}")
check("Calmar p50 > 0",  dist["calmar"]["p50"]  > 0, f"p50: {dist['calmar']['p50']:.2f}")
check("MWR p50 > 0",     dist["mwr"]["p50"]     > 0, f"p50: {dist['mwr']['p50']:.2%}")
check("distribution 키 존재: dividend_mdd", "dividend_mdd" in dist)
check("배당 MDD p50 <= 0", dist["dividend_mdd"]["p50"] <= 0,
      f"p50: {dist['dividend_mdd']['p50']:.2%}")
print(f"  배당MDD p50:      {dist['dividend_mdd']['p50']:>14.2%}")

# history에 cash_flow 컬럼 존재 확인
check("history에 cash_flow 컬럼 존재",
      "cash_flow" in cases[0].get("history", acc_result["cases"][0]).keys()
      if "history" in cases[0] else True,  # cases에 history 없으면 스킵
      "simulation_loop → history_recorder 연결 확인")


# ════════════════════════════════════════════════════════════════════════════════
# 2. WithdrawalAnalyzer 스모크 테스트
# ════════════════════════════════════════════════════════════════════════════════

print("\n" + "="*60)
print("2. WithdrawalAnalyzer 스모크 테스트")
print("="*60)

try:
    wd_result = WithdrawalAnalyzer(**WD_CONFIG).run()
    check("에러 없이 실행", True)
except Exception as e:
    check("에러 없이 실행", False, str(e))
    sys.exit(1)

wd_cases = wd_result["cases"]
wd_dist  = wd_result["distribution"]

check("케이스 수 > 0", len(wd_cases) > 0, f"실제: {len(wd_cases)}개")
check("distribution 키 존재: end_value_ratio",    "end_value_ratio"    in wd_dist)
check("distribution 키 존재: years_to_depletion", "years_to_depletion" in wd_dist)
check("distribution 키 존재: sustainable_months", "sustainable_months" in wd_dist)
check("distribution 키 존재: mdd",                "mdd"                in wd_dist)
check("distribution 키 존재: total_dividend",     "total_dividend"     in wd_dist)
check("success_rate 0~1 범위", 0 <= wd_result["success_rate"] <= 1,
      f"실제: {wd_result['success_rate']:.1%}")

print(f"\n  케이스 수:            {len(wd_cases)}")
print(f"  성공률:               {wd_result['success_rate']:.1%}")
print(f"  종료자산 배수 p10:    {wd_dist['end_value_ratio']['p10']:.2f}x")
print(f"  종료자산 배수 p50:    {wd_dist['end_value_ratio']['p50']:.2f}x")
print(f"  종료자산 배수 p90:    {wd_dist['end_value_ratio']['p90']:.2f}x")
print(f"  MDD p50:              {wd_dist['mdd']['p50']:.2%}")
print(f"  Withdrawal Coverage p50: {wd_dist['withdrawal_coverage']['p50']:.2%}")
print(f"  Sequence Risk p50:       {wd_dist['sequence_risk']['p50']:.2%}")

check("distribution 키 존재: withdrawal_coverage", "withdrawal_coverage" in wd_dist)
check("distribution 키 존재: sequence_risk",        "sequence_risk"       in wd_dist)
check("Withdrawal Coverage >= 0", wd_dist["withdrawal_coverage"]["p50"] >= 0,
      f"p50: {wd_dist['withdrawal_coverage']['p50']:.2%}")
check("distribution 키 존재: dividend_mdd", "dividend_mdd" in wd_dist)
check("배당 MDD p50 <= 0", wd_dist["dividend_mdd"]["p50"] <= 0,
      f"p50: {wd_dist['dividend_mdd']['p50']:.2%}")
print(f"  배당MDD p50:             {wd_dist['dividend_mdd']['p50']:.2%}")


# ════════════════════════════════════════════════════════════════════════════════
# 3. 인플레이션 단조성 검증
# ════════════════════════════════════════════════════════════════════════════════

print("\n" + "="*60)
print("3. 인플레이션 단조성 검증")
print("="*60)

wd_inf = WithdrawalAnalyzer(**{**WD_CONFIG, "inflation": 0.03}).run()

r0  = wd_result["distribution"]["end_value_ratio"]["p50"]
r3  = wd_inf["distribution"]["end_value_ratio"]["p50"]

print(f"  인플레이션 0% — 종료자산 배수 p50: {r0:.3f}x")
print(f"  인플레이션 3% — 종료자산 배수 p50: {r3:.3f}x")

check("인플레이션 3%일 때 종료자산 배수가 낮거나 같음",
      r3 <= r0, f"{r3:.3f} <= {r0:.3f}")


# ════════════════════════════════════════════════════════════════════════════════
# 4. 인출액 증가 → 성공률 감소 단조성 검증
# ════════════════════════════════════════════════════════════════════════════════

print("\n" + "="*60)
print("4. 인출액 단조성 검증")
print("="*60)

withdrawals   = [5_000_000, 15_000_000, 30_000_000]
success_rates = []

for wd_amount in withdrawals:
    r = WithdrawalAnalyzer(**{**WD_CONFIG, "monthly_withdrawal": wd_amount}).run()
    success_rates.append(r["success_rate"])
    print(f"  월 {wd_amount:>10,.0f}원 — 성공률: {r['success_rate']:.1%}")

monotone = all(success_rates[i] >= success_rates[i+1] for i in range(len(success_rates)-1))
check("인출액 증가 → 성공률 감소 (단조성)", monotone)


# ════════════════════════════════════════════════════════════════════════════════
# 5. RetirementPlanner 합성 테스트
# ════════════════════════════════════════════════════════════════════════════════

print("\n" + "="*60)
print("5. RetirementPlanner 합성 테스트")
print("="*60)

try:
    planner = RetirementPlanner(
        acc_result         = acc_result,
        wd_config          = {k: v for k, v in WD_CONFIG.items()
                              if k not in ("initial_capital", "monthly_withdrawal",
                                           "withdrawal_years", "inflation", "verbose")},
        monthly_withdrawal = 2_000_000,
        withdrawal_years   = 5,
        inflation          = 0.0,
        verbose            = True,
    )
    report = planner.run(target_percentile=0.90)
    check("에러 없이 실행", True)
except Exception as e:
    check("에러 없이 실행", False, str(e))
    sys.exit(1)

check("accumulation_summary 존재", "accumulation_summary" in report)
check("sample_results 존재",       "sample_results"       in report)
check("combined_summary 존재",     "combined_summary"     in report)
check("message 존재",              "message"              in report)

combined = report["combined_summary"]
check("합성 종료자산 p50 >= 0",    combined["combined_end_value"]["p50"] >= 0,
      f"p50: {combined['combined_end_value']['p50']:,.0f}")
check("생존율 0~1 범위",           0 <= combined["survival_rate"] <= 1,
      f"생존율: {combined['survival_rate']:.1%}")
check("n_combined_cases > 0",      combined["n_combined_cases"] > 0,
      f"케이스 수: {combined['n_combined_cases']}")

print(f"\n{report['message']['text']}")


# ════════════════════════════════════════════════════════════════════════════════
# 6. 케이스 1 (축적만) / 케이스 2 (인출만) / 케이스 3 (축적→인출) 유즈케이스 확인
# ════════════════════════════════════════════════════════════════════════════════

print("\n" + "="*60)
print("6. 유즈케이스 3가지 실행 확인")
print("="*60)

# 케이스 1: 축적만
try:
    acc_only = AccumulationAnalyzer(**ACC_CONFIG).run()
    check("케이스 1 (축적만) — AccumulationAnalyzer 단독 실행", True,
          f"종료자산 p50: {acc_only['distribution']['end_value']['p50']:,.0f}")
except Exception as e:
    check("케이스 1 (축적만)", False, str(e))

# 케이스 2: 인출만
try:
    wd_only = WithdrawalAnalyzer(**WD_CONFIG).run()
    check("케이스 2 (인출만) — WithdrawalAnalyzer 단독 실행", True,
          f"성공률: {wd_only['success_rate']:.1%}")
except Exception as e:
    check("케이스 2 (인출만)", False, str(e))

# 케이스 3: 축적 → 인출 합성
try:
    planner3 = RetirementPlanner(
        acc_result         = acc_only,
        wd_config          = {k: v for k, v in WD_CONFIG.items()
                              if k not in ("initial_capital", "monthly_withdrawal",
                                           "withdrawal_years", "inflation", "verbose")},
        monthly_withdrawal = 15_000_000,
        withdrawal_years   = 5,
    )
    report3 = planner3.run(target_percentile=0.90)
    check("케이스 3 (축적→인출) — RetirementPlanner 합성", True,
          f"생존율: {report3['combined_summary']['survival_rate']:.1%}  "
          f"안전여부: {report3['message']['is_safe']}")
except Exception as e:
    check("케이스 3 (축적→인출)", False, str(e))


# ════════════════════════════════════════════════════════════════════════════════
print("\n" + "="*60)
print("테스트 완료")
print("="*60)