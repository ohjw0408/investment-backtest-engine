"""
check_tlt_dividend.py
TLT, SCHD 배당 데이터 확인
"""

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parents[1]))

from modules.portfolio_engine import PortfolioEngine

engine = PortfolioEngine()
loader = engine.loader

for ticker in ["SCHD", "TLT", "QQQ"]:
    raw = loader.get_price(ticker, "2012-01-01", "2026-01-01")
    div = raw[raw["dividend"] > 0].copy()
    import pandas as pd
    div["year"] = pd.to_datetime(div["date"]).dt.year
    annual = div.groupby("year")["dividend"].sum()

    print(f"\n{'='*40}")
    print(f"{ticker} 배당 데이터")
    print(f"  총 배당 발생일수: {len(div)}개")
    print(f"  연간 DPS 합계:")
    for yr, dps in annual.items():
        print(f"    {yr}: {dps:.4f}")
    print(f"  전체 DPS 합계: {div['dividend'].sum():.4f}")