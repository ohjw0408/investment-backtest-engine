"""
test_spy_tlt_retirement.py
────────────────────────────────────────────────────────────────────────────────
SPY/TLT 포트폴리오
  - 적립: 10년 (월 step=1)
  - 인출: 15년 (월 step=1)
  - 데이터: 2003-01-01 ~ 2025-12-31

입력 변수:
  - 월 납입금       : MONTHLY_CONTRIBUTION
  - 초기 납입금     : INITIAL_CAPITAL
  - 월 인출금       : MONTHLY_WITHDRAWAL
  - 배당 재투자 여부 : DIVIDEND_MODE ("reinvest" | "cash" | "withdraw")

출력:
  - 축적기: 종료자산 분포, 총수익금, 받은 배당금, CAGR/MDD/Sharpe/Sortino/
            Calmar/MWR/배당CAGR/배당MDD 전 지표
  - 인출기: 11개 샘플(p5~p99)별 생존율/종료자산배수/MDD/배당커버리지/
            배당CAGR/배당MDD/Sequence Risk 전 지표
────────────────────────────────────────────────────────────────────────────────
"""
import warnings
warnings.filterwarnings("ignore")
import pandas as pd
pd.set_option('future.no_silent_downcasting', True)
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parents[1]))

import numpy as np
from modules.portfolio_engine import PortfolioEngine
from modules.rebalance.periodic import PeriodicRebalance
from modules.retirement.accumulation_analyzer import AccumulationAnalyzer
from modules.retirement.withdrawal_analyzer import WithdrawalAnalyzer

# ════════════════════════════════════════════════════════════════════════════════
# ★ 입력 변수 (여기만 수정)
# ════════════════════════════════════════════════════════════════════════════════

MONTHLY_CONTRIBUTION = 500_000    # 월 납입금 (원)
INITIAL_CAPITAL      = 0           # 초기 납입금 (원)
MONTHLY_WITHDRAWAL   = 2_000_000   # 월 인출금 (원)
DIVIDEND_MODE        = "reinvest"  # "reinvest" | "cash" | "withdraw"

# ════════════════════════════════════════════════════════════════════════════════
# 고정 설정
# ════════════════════════════════════════════════════════════════════════════════

TICKERS    = ["SPY", "TLT"]
WEIGHTS    = {"SPY": 0.6, "TLT": 0.4}
DATA_START = "1977-01-01"
DATA_END   = "2025-12-31"
ACC_YEARS  = 20
WD_YEARS   = 30
STEP       = 1

SAMPLE_PERCENTILES = [5, 10, 20, 30, 40, 50, 60, 70, 80, 90, 95, 99]

engine = PortfolioEngine()

def make_strategy():
    return PeriodicRebalance(target_weights=WEIGHTS, rebalance_frequency="yearly")

def sep(char="─", n=60):
    print(char * n)

# ════════════════════════════════════════════════════════════════════════════════
# 1. 축적기 실행
# ════════════════════════════════════════════════════════════════════════════════

print("\n" + "=" * 60)
print("SPY/TLT 은퇴 시뮬레이션 (장기)")
print("=" * 60)
print(f"  포트폴리오  : SPY {WEIGHTS['SPY']:.0%} / TLT {WEIGHTS['TLT']:.0%}")
print(f"  데이터 기간 : {DATA_START} ~ {DATA_END}")
print(f"  적립 기간   : {ACC_YEARS}년  (롤링 step={STEP}개월)")
print(f"  인출 기간   : {WD_YEARS}년  (롤링 step={STEP}개월)")
print(f"  월 납입금   : {MONTHLY_CONTRIBUTION:,.0f}원")
print(f"  초기 납입금 : {INITIAL_CAPITAL:,.0f}원")
print(f"  월 인출금   : {MONTHLY_WITHDRAWAL:,.0f}원")
print(f"  배당 모드   : {DIVIDEND_MODE}")

print("\n[1/2] 축적기 롤링 시뮬 실행 중...")

acc_result = AccumulationAnalyzer(
    portfolio_engine     = engine,
    tickers              = TICKERS,
    strategy_factory     = make_strategy,
    data_start           = DATA_START,
    data_end             = DATA_END,
    accumulation_years   = ACC_YEARS,
    monthly_contribution = MONTHLY_CONTRIBUTION,
    initial_capital      = INITIAL_CAPITAL,
    dividend_mode        = DIVIDEND_MODE,
    step_months          = STEP,
    verbose              = False,
).run()

acc_cases = acc_result["cases"]
acc_dist  = acc_result["distribution"]
n_acc     = len(acc_cases)
total_contribution = MONTHLY_CONTRIBUTION * ACC_YEARS * 12 + INITIAL_CAPITAL

print(f"  → {n_acc}개 케이스 완료")

# ── 축적기 출력 ──────────────────────────────────────────────────────────────

print("\n" + "=" * 60)
print("■ 축적기 결과")
print("=" * 60)
print(f"  총 납입금   : {total_contribution:>20,.0f}원")
print()

# 종료자산 분포
print("  ── 종료자산 분포 ─────────────────────────────────────")
end_vals = acc_dist["end_value"]
for pct in ["p10", "p25", "p50", "p75", "p90"]:
    profit = end_vals[pct] - total_contribution
    profit_rate = profit / total_contribution * 100 if total_contribution > 0 else 0
    print(f"  {pct:>4}: {end_vals[pct]:>18,.0f}원  (수익 {profit:>+15,.0f}원 / {profit_rate:>+6.1f}%)")
print(f"  mean: {end_vals['mean']:>18,.0f}원")
print(f"  std : {end_vals['std']:>18,.0f}원")

# 총 배당금 분포
print()
print("  ── 받은 배당금 분포 ───────────────────────────────────")
div_vals = acc_dist["total_dividend"]
for pct in ["p10", "p25", "p50", "p75", "p90"]:
    print(f"  {pct:>4}: {div_vals[pct]:>18,.0f}원")

# 전 지표 분포
print()
print("  ── 지표 분포 (p10 / p50 / p90) ───────────────────────")
metrics_labels = [
    ("cagr",         "CAGR",         ".2%"),
    ("mdd",          "MDD",          ".2%"),
    ("sharpe",       "Sharpe",       ".2f"),
    ("sortino",      "Sortino",      ".2f"),
    ("calmar",       "Calmar",       ".2f"),
    ("mwr",          "MWR",          ".2%"),
    ("dividend_cagr","배당CAGR",     ".2%"),
    ("dividend_mdd", "배당MDD",      ".2%"),
]
for key, label, fmt in metrics_labels:
    d = acc_dist[key]
    p10 = format(d["p10"], fmt)
    p50 = format(d["p50"], fmt)
    p90 = format(d["p90"], fmt)
    print(f"  {label:<10}: p10={p10:>10}  p50={p50:>10}  p90={p90:>10}")

# ════════════════════════════════════════════════════════════════════════════════
# 2. 인출기: 샘플 추출 → 각각 WithdrawalAnalyzer 실행
# ════════════════════════════════════════════════════════════════════════════════

print("\n[2/2] 인출기 롤링 시뮬 실행 중...")

end_value_arr = np.array([c["end_value"] for c in acc_cases])
sample_results = []

for pct in SAMPLE_PERCENTILES:
    initial_capital = float(np.percentile(end_value_arr, pct))

    wd_result = WithdrawalAnalyzer(
        portfolio_engine    = engine,
        tickers             = TICKERS,
        strategy_factory    = make_strategy,
        data_start          = DATA_START,
        data_end            = DATA_END,
        withdrawal_years    = WD_YEARS,
        monthly_withdrawal  = MONTHLY_WITHDRAWAL,
        initial_capital     = initial_capital,
        dividend_mode       = DIVIDEND_MODE,
        inflation           = 0.0,
        step_months         = STEP,
        verbose             = False,
    ).run()

    sample_results.append({
        "pct":            pct,
        "initial_capital": initial_capital,
        "success_rate":   wd_result["success_rate"],
        "dist":           wd_result["distribution"],
        "n_cases":        len(wd_result["cases"]),
    })

    print(f"  p{pct:02d} (초기자본 {initial_capital:,.0f}원) → 생존율 {wd_result['success_rate']:.1%}")

# ── 인출기 출력 ──────────────────────────────────────────────────────────────

print("\n" + "=" * 60)
print("■ 인출기 결과")
print("=" * 60)
print(f"  월 인출금 : {MONTHLY_WITHDRAWAL:,.0f}원")
print(f"  인출 기간 : {WD_YEARS}년 ({WD_YEARS*12}개월)")
print(f"  총 인출액 : {MONTHLY_WITHDRAWAL * WD_YEARS * 12:,.0f}원")
print()

# 샘플별 생존율 요약
print("  ── 샘플별 생존율 ─────────────────────────────────────")
print(f"  {'시나리오':>8}  {'초기자본':>18}  {'생존율':>8}  {'종료자산배수':>10}  {'MDD':>8}")
sep()
for s in sample_results:
    d        = s["dist"]
    ratio    = d["end_value_ratio"]["p50"]
    mdd      = d["mdd"]["p50"]
    print(f"  p{s['pct']:02d}      {s['initial_capital']:>18,.0f}원  {s['success_rate']:>8.1%}  {ratio:>10.2f}x  {mdd:>8.2%}")

# 전체 생존 확률 (단순 평균)
overall_survival = np.mean([s["success_rate"] for s in sample_results])
print()
print(f"  전체 평균 생존율: {overall_survival:.1%}")

# 샘플별 전 지표
print()
print("  ── 샘플별 상세 지표 (p50 기준) ───────────────────────")
wd_metrics_labels = [
    ("end_value_ratio",  "종료자산배수",   ".2f", "x"),
    ("mdd",              "MDD",            ".2%", ""),
    ("total_dividend",   "총배당금",       ",.0f", "원"),
    ("withdrawal_coverage", "배당커버리지", ".2%", ""),
    ("sequence_risk",    "Sequence Risk",  ".2%", ""),
    ("dividend_mdd",     "배당MDD",        ".2%", ""),
    ("years_to_depletion","고갈시점",      ".1f", "년"),
]

for s in sample_results:
    d = s["dist"]
    print()
    print(f"  [p{s['pct']:02d}] 초기자본 {s['initial_capital']:,.0f}원  생존율 {s['success_rate']:.1%}  (롤링 {s['n_cases']}케이스)")
    for key, label, fmt, unit in wd_metrics_labels:
        if key in d:
            val = d[key]["p50"]
            if fmt == ",.0f":
                formatted = f"{val:,.0f}{unit}"
            else:
                formatted = format(val, fmt) + unit
            print(f"    {label:<14}: {formatted}")

print("\n" + "=" * 60)
print("시뮬레이션 완료")
print("=" * 60)