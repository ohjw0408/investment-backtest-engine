"""
tests/test_krx_gold.py
KRX 금현물 거래가능 시계열 + 위탁 전용 규칙 검증.
계획: 금데이터백필_plan.md (Phase 1).
"""

import os
import sys

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from modules.tax.account_tax import validate_account_portfolio
from modules.tax.base_tax import TaxEngine

_INDEX_DB = os.path.join(os.path.dirname(__file__), "..", "data", "meta", "index_master.db")


# ── 위탁 전용 규칙 (순수, DB 무관) ──

def test_krx_gold_only_brokerage():
    """KRX_GOLD는 위탁만 허용, ISA·연금저축·IRP는 거부."""
    te = TaxEngine({"earned_income": 0, "age": 40})
    w = {"KRX_GOLD": 1.0}
    assert validate_account_portfolio("위탁", ["KRX_GOLD"], w, te)["valid"] is True
    for atype in ("ISA", "연금저축", "IRP"):
        res = validate_account_portfolio(atype, ["KRX_GOLD"], w, te)
        assert res["valid"] is False, atype
        assert any("금현물" in v for v in res["violations"]), atype


# ── 연속 시계열 + 시뮬 (index_master 있을 때만) ──

def test_krx_gold_series_continuity():
    if not os.path.exists(_INDEX_DB):
        return  # CI에 index_master 없으면 skip
    from modules.price_loader import PriceLoader
    L = PriceLoader()
    s = L._build_krx_gold_series()
    # 2014 경계 점프 없음(일변동 수준, ±5% 이내).
    b = pd.Timestamp("2014-03-24")
    pre = s[s.index < b]
    post = s[s.index >= b]
    assert len(pre) > 0 and len(post) > 0
    gap = abs(float(post.iloc[0]) - float(pre.iloc[-1])) / float(pre.iloc[-1])
    assert gap < 0.05, f"2014 경계 점프 {gap:.1%}"
    # 2024년 KRW/g 현실 범위(7만~10만).
    v2024 = float(s[s.index <= pd.Timestamp("2024-01-02")].iloc[-1])
    assert 70_000 < v2024 < 100_000, v2024


def test_krx_gold_brokerage_sim_runs_and_tax_zero():
    if not os.path.exists(_INDEX_DB):
        return
    from modules.price_loader import PriceLoader
    from modules.config.simulation_config import SimulationConfig
    from modules.rebalance.periodic import PeriodicRebalance
    from modules.simulation.taxable_runner import TaxableSimulationRunner

    L = PriceLoader()
    df = L.get_price("KRX_GOLD", "2018-01-01", "2024-01-01")
    assert not df.empty and len(df) > 100
    df = df.copy(); df["date"] = pd.to_datetime(df["date"]); df = df.set_index("date")
    pdata = {"KRX_GOLD": df}; dates = list(df.index)
    cfg = SimulationConfig(
        start_date="2018-01-01", end_date="2024-01-01", tickers=["KRX_GOLD"],
        target_weights={"KRX_GOLD": 1.0}, initial_capital=10_000_000.0,
        monthly_contribution=0.0, withdrawal_amount=0, dividend_mode="hold",
        rebalance_frequency=None, inflation=0.0,
    )
    strat = PeriodicRebalance({"KRX_GOLD": 1.0}, rebalance_frequency=None)
    r0 = TaxableSimulationRunner().run(cfg, pdata, dates, strat, tax_enabled=False, account_type="위탁")
    r1 = TaxableSimulationRunner().run(
        cfg, pdata, dates, strat, tax_enabled=True, account_type="위탁",
        tax_engine=TaxEngine({"earned_income": 0, "age": 40}),
        user_settings={"earned_income": 0, "age": 40},
    )
    assert r0.end_value > 0          # 에러 없이 시뮬 완료
    assert abs(r0.end_value - r1.end_value) < 1.0   # 금 양도세 0 (비과세)


# ── 금 ETF 상장전 백필 프록시 라우팅 (Phase 2) ──

def test_gold_etf_backfill_proxy_routing():
    """현물·국제금(unhedged) ETF는 KRX_GOLD, 환헤지 선물 ETF는 GC=F로 백필."""
    from modules.backfill_engine import _GOLD_KRX_SPOT, INDEX_MAP
    # 현물/국제금 → KRX_GOLD 프록시
    for code in ("411060", "0072R0", "0064K0", "0066W0"):
        assert code in _GOLD_KRX_SPOT, code
    # 환헤지 선물은 KRX_GOLD 오버라이드 대상 아님 → GOLD→GC=F 유지
    for code in ("132030", "319640", "139320"):
        assert code not in _GOLD_KRX_SPOT, code
    assert INDEX_MAP["GOLD"] == "GC=F"


def test_backfill_krx_gold_proxy_matches_price_loader():
    """BackfillEngine과 PriceLoader가 동일한 KRX_GOLD KRW/g 시계열을 쓴다(공유 빌더)."""
    if not os.path.exists(_INDEX_DB):
        return
    from modules.price_loader import PriceLoader
    from modules.backfill_engine import BackfillEngine
    pl_series = PriceLoader()._build_krx_gold_series()
    bf_series = BackfillEngine(verbose=False)._load_index("KRX_GOLD")
    assert bf_series is not None and len(bf_series) > 100
    assert len(bf_series) == len(pl_series)
    assert abs(float(bf_series.iloc[-1]) - float(pl_series.iloc[-1])) < 1.0


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
