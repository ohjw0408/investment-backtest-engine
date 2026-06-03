"""
tests/test_withdrawal_cg_tax.py
BUG-TAX-2: 인출 매도 시 위탁 양도세 부과 검증.

기존 버그: WithdrawalEngine이 portfolio.sell() 직행(TaxedOrderExecutor 우회)이라
인출하며 판 위탁 매도차익에 양도세가 안 붙었음. 최종 청산세는 남은 보유분만 과세.
수정: 인출 매도를 executor.sell_with_tax 경유로 라우팅.

격리 설계: rebalance_frequency=None → 리밸런싱 매도 0이므로
executor.total_cg_tax_paid는 **인출 매도에서만** 누적된다.
"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from modules.config.simulation_config       import SimulationConfig
from modules.core.portfolio                  import TaxTrackedPortfolio
from modules.execution.cash_allocator        import CashAllocator
from modules.execution.order_executor        import TaxedOrderExecutor
from modules.rebalance.periodic              import PeriodicRebalance
from modules.simulation.contribution_engine  import ContributionEngine
from modules.simulation.dividend_engine      import DividendEngine
from modules.simulation.history_recorder     import HistoryRecorder
from modules.simulation.simulation_loop      import SimulationLoop
from modules.simulation.withdrawal_engine    import WithdrawalEngine
from modules.tax.account_tax                 import TaxedDividendEngine
from modules.tax.base_tax                    import TaxEngine
from modules.tax.session                     import TaxSessionState

CODE = "458730"  # KR_FOREIGN (15.4%, 공제 없음 — 손계산 단순)


def _run(account_type: str) -> float:
    """위탁 보유 100→200 상승 후 월 인출. rebalance 없음 → CG세는 인출 매도에서만.
    executor.total_cg_tax_paid 반환."""
    dates = pd.bdate_range("2020-01-01", "2024-12-31")
    n     = len(dates)
    px    = np.where(np.arange(n) < 252, 100.0, 200.0)  # 1년 후 2배 점프 후 유지
    df    = pd.DataFrame(
        {"open": px, "high": px, "low": px, "close": px,
         "volume": 1.0, "dividend": 0.0, "split": 1.0},
        index=dates,
    )
    price_data = {CODE: df}
    dl         = list(dates)

    cfg = SimulationConfig(
        start_date="2020-01-01", end_date="2024-12-31", tickers=[CODE],
        target_weights={CODE: 1.0}, initial_capital=10_000_000.0,
        monthly_contribution=0.0, withdrawal_amount=200_000.0,
        dividend_mode="hold", rebalance_frequency=None, inflation=0.0,
    )
    strat = PeriodicRebalance({CODE: 1.0}, rebalance_frequency=None)

    te          = TaxEngine({"earned_income": 0, "age": 40})
    session     = TaxSessionState(other_financial_income=0.0)
    div_engine  = TaxedDividendEngine(DividendEngine(), te, account_type, session=session)
    executor    = TaxedOrderExecutor(te, account_type, session=session)
    portfolio   = TaxTrackedPortfolio(cfg.initial_capital)
    loop        = SimulationLoop(div_engine, ContributionEngine(), WithdrawalEngine(),
                                 executor, CashAllocator())
    recorder    = HistoryRecorder()
    loop.run(portfolio, strat, cfg, price_data, dl, recorder)
    return executor.total_cg_tax_paid


def test_withdrawal_sells_taxed_for_brokerage():
    """위탁: 인출 매도(상승분 실현)에 양도세 부과 → total_cg_tax_paid > 0 (BUG-TAX-2)."""
    cg_tax = _run("위탁")
    assert cg_tax > 0, f"인출 매도 양도세 미부과 (BUG-TAX-2 회귀): {cg_tax}"


def test_withdrawal_no_cg_for_isa():
    """ISA: 과세이연 → 인출 매도에 CG세 없음(0). 동일 시나리오 비교로 위탁 차이가 CG임을 확정."""
    assert _run("ISA") == 0.0


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
