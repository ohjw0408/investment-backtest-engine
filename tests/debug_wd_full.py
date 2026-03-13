"""
debug_dividend_cagr_cases.py
케이스별 배당 CAGR 전체 출력
"""
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parents[1]))

from modules.portfolio_engine import PortfolioEngine
from modules.rebalance.periodic import PeriodicRebalance
from modules.retirement.accumulation_analyzer import AccumulationAnalyzer

engine = PortfolioEngine()

analyzer = AccumulationAnalyzer(
    portfolio_engine     = engine,
    tickers              = ["SCHD", "QQQ"],
    strategy_factory     = lambda: PeriodicRebalance(
        target_weights      = {"SCHD": 0.7, "QQQ": 0.3},
        rebalance_frequency = "yearly"
    ),
    data_start           = "2012-01-01",
    data_end             = "2026-01-01",
    accumulation_years   = 5,
    monthly_contribution = 500_000,
    initial_capital      = 0,
    dividend_mode        = "reinvest",
    step_months          = 6,
    verbose              = False,
)

result = analyzer.run()

print(f"\n{'케이스':<6} {'기간':<25} {'배당CAGR':>10} {'CAGR':>8} {'종료자산':>15}")
print("-" * 70)

for c in result["cases"]:
    print(f"  {c['run_id']:<4} {c['start']} ~ {c['end']}  "
          f"{c['dividend_cagr']:>9.2%}  "
          f"{c['cagr']:>7.2%}  "
          f"{c['end_value']:>15,.0f}")

dist = result["distribution"]
print("-" * 70)
print(f"  {'p10':<29} {dist['dividend_cagr']['p10']:>9.2%}")
print(f"  {'p50':<29} {dist['dividend_cagr']['p50']:>9.2%}")
print(f"  {'p90':<29} {dist['dividend_cagr']['p90']:>9.2%}")

# 케이스 19 상세 분석
print("\n\n── 케이스 19 (2021-01 ~ 2026-01) 연간 DPS 상세 ──")
import pandas as pd
from modules.portfolio_engine import PortfolioEngine
from modules.rebalance.periodic import PeriodicRebalance

e2 = PortfolioEngine()
r2 = e2.run_simulation(
    tickers=["SCHD"],
    start_date="2021-01-01",
    end_date="2026-01-01",
    initial_capital=10_000_000,
    monthly_contribution=0,
    strategy=PeriodicRebalance(target_weights={"SCHD": 1.0}, rebalance_frequency="yearly"),
    dividend_mode="reinvest",
)
h2 = r2["history"]
h2["year"]  = pd.to_datetime(h2["date"]).dt.year
h2["month"] = pd.to_datetime(h2["date"]).dt.month

months_per_year = h2.groupby("year")["month"].nunique()
print("연도별 월 수:")
print(months_per_year)

annual = h2.groupby("year").agg(
    div_sum=("SCHD_dividend", "sum"),
    qty_mean=("SCHD_quantity", "mean"),
)
annual["dps"] = annual["div_sum"] / annual["qty_mean"]
print("\n연간 DPS:")
print(annual[["div_sum", "qty_mean", "dps"]])

full_years = months_per_year[months_per_year >= 12].index
print(f"\nfull_years: {list(full_years)}")