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

KR_FOREIGN_CODE  = "458730"  # 국내상장 해외ETF — 15.4% 배당소득세
US_DIRECT_CODE   = "SPY"     # 해외 직접 — 연 250만 공제 후 22%
KR_DOMESTIC_CODE = "069500"  # 국내주식형 ETF — 비과세


def _run(account_type: str, code: str = KR_FOREIGN_CODE, jump: float = 200.0,
         monthly_wd: float = 200_000.0, jump_day: int = 252) -> float:
    """보유 100→jump 상승 후 월 인출. rebalance 없음 → CG세는 인출 매도에서만 누적.
    executor.total_cg_tax_paid 반환."""
    dates = pd.bdate_range("2020-01-01", "2024-12-31")
    n     = len(dates)
    px    = np.where(np.arange(n) < jump_day, 100.0, jump)
    df    = pd.DataFrame(
        {"open": px, "high": px, "low": px, "close": px,
         "volume": 1.0, "dividend": 0.0, "split": 1.0},
        index=dates,
    )
    price_data = {code: df}
    dl         = list(dates)

    cfg = SimulationConfig(
        start_date="2020-01-01", end_date="2024-12-31", tickers=[code],
        target_weights={code: 1.0}, initial_capital=10_000_000.0,
        monthly_contribution=0.0, withdrawal_amount=monthly_wd,
        dividend_mode="hold", rebalance_frequency=None, inflation=0.0,
    )
    strat = PeriodicRebalance({code: 1.0}, rebalance_frequency=None)

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
    """위탁 KR_FOREIGN: 인출 매도(상승분 실현)에 15.4% 부과 → CG세 > 0 (BUG-TAX-2)."""
    assert _run("위탁") > 0, "인출 매도 양도세 미부과 (BUG-TAX-2 회귀)"


def test_withdrawal_no_cg_for_isa():
    """ISA: 과세이연 → 인출 매도에 CG세 없음(0). 위탁과의 차이가 CG임을 확정."""
    assert _run("ISA") == 0.0


def test_withdrawal_us_direct_taxed():
    """위탁 US_DIRECT: 연 250만 공제 초과 차익에 22% → CG세 > 0.

    조기 점프(고갈 전 차익 실현) + 큰 월인출로 연 실현차익 > 250만 만듦.
    """
    assert _run("위탁", US_DIRECT_CODE, jump=200.0, monthly_wd=1_000_000.0, jump_day=5) > 0


def test_withdrawal_us_direct_under_exemption():
    """위탁 US_DIRECT: 연 실현차익이 250만 공제 이내(미미한 상승)면 CG세 0.

    100→101(1%) 상승, 월 20만 인출 → 연 실현차익 ~2.4만 ≪ 250만 → 비과세.
    인출 경로에서도 연 250만 공제가 매년 적용됨을 확인(배당엔진 daily touch로 연 리셋).
    """
    assert _run("위탁", US_DIRECT_CODE, jump=101.0) == 0.0


def test_withdrawal_kr_domestic_exempt():
    """위탁 KR_DOMESTIC: 국내주식형은 양도세 비과세 → 차익 커도 CG세 0."""
    assert _run("위탁", KR_DOMESTIC_CODE, jump=200.0) == 0.0


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
