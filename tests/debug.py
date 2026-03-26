import numpy as np
import copy

from modules.portfolio_engine import PortfolioEngine
from modules.rebalance.periodic import PeriodicRebalance

# 테스트 설정
TICKERS = ["SPY", "TLT"]
START   = "2010-01-01"
END     = "2020-01-01"

def make_strategy():
    return PeriodicRebalance(
        target_weights={"SPY": 0.6, "TLT": 0.4},
        rebalance_frequency="yearly"
    )

# 🔴 1. 기존 엔진 (캐시 없는 상태)
engine_old = PortfolioEngine()

# 캐시 강제 제거 (혹시 남아있을 경우 대비)
engine_old._price_cache = {}

result_old = engine_old.run_simulation(
    tickers=TICKERS,
    start_date=START,
    end_date=END,
    initial_capital=100_000_000,
    strategy=make_strategy(),
    withdrawal_amount=1_000_000,
)

# 🔵 2. 캐시 엔진
engine_new = PortfolioEngine()

result_new = engine_new.run_simulation(
    tickers=TICKERS,
    start_date=START,
    end_date=END,
    initial_capital=100_000_000,
    strategy=make_strategy(),
    withdrawal_amount=1_000_000,
)

# 🔥 비교

pv_old = result_old["history"]["portfolio_value"].values
pv_new = result_new["history"]["portfolio_value"].values

print("길이 동일:", len(pv_old) == len(pv_new))

# 완전 동일 체크
exact_equal = np.array_equal(pv_old, pv_new)
print("완전 동일:", exact_equal)

# 부동소수점 허용 비교
close_equal = np.allclose(pv_old, pv_new, rtol=1e-10, atol=1e-12)
print("수치 동일 (허용오차):", close_equal)

# 최종 값 비교
print("최종값 비교:")
print("OLD:", result_old["final_value"])
print("NEW:", result_new["final_value"])