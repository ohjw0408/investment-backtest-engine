"""
timing_test.py
495330 가상 데이터 시뮬레이션 병목 구간 측정.
실행: python3 scripts/timing_test.py
"""
import time
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

print("=== 타이밍 테스트 시작 ===")

t0 = time.time()
from modules.portfolio_engine import PortfolioEngine
pe = PortfolioEngine()
print(f"PortfolioEngine 초기화: {time.time()-t0:.2f}s")

# 1. 데이터 로드 타이밍
t1 = time.time()
data, dates = pe.price_loader.load(
    ['495330'], '1991-01-01', '2011-01-01', allow_synthetic=True
)
print(f"load(): {time.time()-t1:.2f}s  rows={len(dates)}")

# 2. 시뮬레이션 타이밍
from modules.simulation.taxable_runner import TaxableSimulationRunner
from modules.config.simulation_config import SimulationConfig
from modules.rebalance.periodic import PeriodicRebalance

cfg = SimulationConfig(
    start_date='1991-01-01', end_date='2011-01-01',
    tickers=['495330'],
    target_weights={'495330': 1.0},
    initial_capital=10_000_000,
    monthly_contribution=300_000,
    withdrawal_amount=0,
    dividend_mode='reinvest',
    rebalance_frequency=None,
    inflation=0.0,
)
strat = PeriodicRebalance(
    target_weights={'495330': 1.0},
    rebalance_frequency=None,
    drift_threshold=None,
)

t2 = time.time()
r = TaxableSimulationRunner().run(
    config=cfg, price_data=data, dates=dates, strategy=strat
)
print(f"simulate(): {time.time()-t2:.2f}s")
print(f"총 1 윈도우: {time.time()-t1:.2f}s")
print(f"60 윈도우 예상: {(time.time()-t1)*60:.0f}s")
