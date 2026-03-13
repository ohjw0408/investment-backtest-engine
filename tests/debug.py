# tests/debug_dividend_cagr.py 만들어서 돌려주세요
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parents[1]))

from modules.portfolio_engine import PortfolioEngine
from modules.rebalance.periodic import PeriodicRebalance

engine = PortfolioEngine()
strategy = PeriodicRebalance(
    target_weights={"SCHD": 0.7, "QQQ": 0.3},
    rebalance_frequency="yearly"
)

result = engine.run_simulation(
    tickers=["SCHD", "QQQ"],
    start_date="2012-01-01",
    end_date="2026-01-01",
    initial_capital=10_000_000,
    monthly_contribution=0,
    strategy=strategy,
    dividend_mode="reinvest",
)

h = result["history"]
import pandas as pd
h["year"] = pd.to_datetime(h["date"]).dt.year

for ticker in ["SCHD", "QQQ"]:
    print(f"\n── {ticker} 연간 DPS ──")
    annual = h.groupby("year").agg(
        div_sum=(f"{ticker}_dividend", "sum"),
        qty_mean=(f"{ticker}_quantity", "mean"),
    )
    annual = annual[annual["qty_mean"] > 0]
    annual["dps"] = annual["div_sum"] / annual["qty_mean"]
    print(annual[["dps"]])