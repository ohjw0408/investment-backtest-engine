"""
tests/test_l_save.py
절세액 표시 기능 결정론 검증 (L-SAVE — 손계산 ±1원 + 경계 + 불변식).
계획: 절세액표시_plan.md §6.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from modules.tax.saving_estimate import (
    estimate_brokerage_tax, estimate_gain_harvest_saving,
)
from modules.simulation.multi_account_loop import MultiAccountSimulationLoop
from tests.test_track_g_multi_account import _price_frame, _loop_account


def _run_single(ticker, frame, account_type="위탁", initial=10_000_000.0,
                isa_type="general", isa_renewal=False, gain_harvesting=False):
    acct = _loop_account(ticker, initial=initial, account_type=account_type,
                         isa_renewal=isa_renewal)
    acct["gain_harvesting"] = gain_harvesting
    return MultiAccountSimulationLoop().run(
        [acct], {ticker: frame}, list(frame.index),
        tax_enabled=True,
        user_settings={"earned_income": 0, "age": 40, "isa_type": isa_type},
    ).account_results[0]


# ── L-SAVE0: 순수함수 estimate_brokerage_tax ──

def test_l_save0_dividend_by_class():
    """배당세 = Σ class gross × rate. KR_FOREIGN 1,000,000·US 1,000,000·금 1,000,000."""
    tax = estimate_brokerage_tax(
        gross_div_by_class={"KR_FOREIGN": 1_000_000, "US_DIRECT": 1_000_000,
                            "KR_DOMESTIC": 1_000_000, "KRX_GOLD": 1_000_000},
        kr_foreign_gain=0.0,
        us_gain_by_year={},
    )
    # 0.154 + 0.15 + 0.154 + 0 = 0.458 백만
    assert abs(tax - (154_000 + 150_000 + 154_000 + 0)) < 1e-6


def test_l_save0_kr_foreign_gain():
    """KR_FOREIGN 양도세 = max(0, gain) × 15.4%, 이익분만(손익통산 없음)."""
    assert abs(estimate_brokerage_tax({}, 10_000_000, {}) - 1_540_000) < 1e-6
    # 손실은 0 (음수 → 과세 0)
    assert estimate_brokerage_tax({}, -5_000_000, {}) == 0.0


def test_l_save0_us_annual_exempt():
    """US 양도세 = Σ year max(0, gain−250만) × 22%. 연도별 250만 공제."""
    # 단일 연도 600만 → (600−250)만 × 0.22 = 350만 × 0.22 = 770,000
    assert abs(estimate_brokerage_tax({}, 0, {2025: 6_000_000}) - 770_000) < 1e-6
    # 2개 연도 각 300만 → 각 (300−250)만 × 0.22 = 50만×0.22=110,000 ×2 = 220,000
    assert abs(estimate_brokerage_tax({}, 0, {2024: 3_000_000, 2025: 3_000_000})
               - 220_000) < 1e-6


def test_l_save0_us_below_exempt_zero():
    """US 차익 250만 이하 → 세금 0 (경계)."""
    assert estimate_brokerage_tax({}, 0, {2025: 2_500_000}) == 0.0
    assert estimate_brokerage_tax({}, 0, {2025: 2_400_000}) == 0.0
    # 250만 초과 1원 → 0.22원
    assert abs(estimate_brokerage_tax({}, 0, {2025: 2_500_001}) - 0.22) < 1e-6


def test_l_save0_empty_and_gold_zero():
    """빈 입력·금만 → 0."""
    assert estimate_brokerage_tax({}, 0, {}) == 0.0
    assert estimate_brokerage_tax({"KRX_GOLD": 50_000_000}, 0, {}) == 0.0


def test_l_save0_combined():
    """배당+KRF+US 합산 손계산."""
    tax = estimate_brokerage_tax(
        gross_div_by_class={"US_DIRECT": 2_000_000},   # 300,000
        kr_foreign_gain=10_000_000,                     # 1,540,000
        us_gain_by_year={2025: 6_000_000},              # 770,000
    )
    assert abs(tax - (300_000 + 1_540_000 + 770_000)) < 1e-6


# ── L-SAVE5: 위탁 불변식 — 위탁 계좌 절세액 == 0 ──

def test_l_save5_brokerage_account_zero_saving():
    """위탁 KR_FOREIGN 차익 1,000원 → 위탁가정 == 실제 → 절세 0."""
    frame = _price_frame("2020-01-01", "2020-12-31", 100.0, 200.0)
    ar = _run_single("458730", frame, account_type="위탁", initial=1_000.0)
    assert abs(ar["liquidation_tax_paid"] - 154.0) < 1e-6     # 실제 (L3 회귀)
    assert abs(ar["brokerage_assumed_tax"] - 154.0) < 1e-6    # 위탁가정 동일
    assert ar["tax_saving"] == 0.0


# ── L-SAVE6: KRX 금 — 위탁가정 0·실제 0·절세 0 ──

def test_l_save6_gold_zero_everywhere():
    frame = _price_frame("2020-01-01", "2023-01-02", 100.0, 200.0)
    for atype in ("위탁", "ISA"):
        ar = _run_single("KRX_GOLD", frame, account_type=atype)
        assert ar["brokerage_assumed_tax"] == 0.0, atype
        assert ar["tax_saving"] == 0.0, atype


# ── L-SAVE1: ISA 단일사이클 절세 (손계산) ──

def test_l_save1_isa_us_direct_single_cycle():
    """ISA US_DIRECT, 순익 1,000만.
    실제(ISA 만기세) = (1000만−비과세200만)×9.9% = 792,000.
    위탁가정 = US 양도 (1000만−250만)×22% = 1,650,000.
    절세 = 858,000."""
    frame = _price_frame("2020-01-01", "2023-01-02", 100.0, 200.0)
    ar = _run_single("AAA", frame, account_type="ISA", initial=10_000_000.0)
    assert abs(ar["liquidation_tax_paid"] - 792_000.0) < 1e-6
    assert abs(ar["brokerage_assumed_tax"] - 1_650_000.0) < 1e-6
    assert abs(ar["tax_saving"] - 858_000.0) < 1e-6


def test_l_save1_isa_kr_foreign_with_dividend():
    """ISA KR_FOREIGN, 차익 1,000만 + 세전배당 100만.
    위탁가정 = 배당 100만×15.4% + 양도 1,000만×15.4% = 154,000 + 1,540,000 = 1,694,000.
    실제 = ISA 만기세 (순익 = 차익1000만+배당100만 = 1100만, −비과세200만)×9.9% = 891,000.
    절세 = 803,000."""
    frame = _price_frame("2020-01-01", "2023-01-02", 100.0, 200.0,
                         dividend_date="2020-06-01", dividend=10.0)
    ar = _run_single("458730", frame, account_type="ISA", initial=10_000_000.0)
    assert abs(ar["brokerage_assumed_tax"] - 1_694_000.0) < 1e-6
    assert abs(ar["liquidation_tax_paid"] - 891_000.0) < 1e-6
    assert abs(ar["tax_saving"] - 803_000.0) < 1e-6


def test_l_save1_isa_loss_zero_saving():
    """ISA 손실 → 위탁가정 0·실제 0·절세 0 (0 하한)."""
    frame = _price_frame("2020-01-01", "2023-01-02", 100.0, 50.0)
    ar = _run_single("AAA", frame, account_type="ISA", initial=10_000_000.0)
    assert ar["brokerage_assumed_tax"] == 0.0
    assert ar["tax_saving"] == 0.0


# ── L-SAVE2: ISA 풍차 다중사이클 누적 (만기별 실현 + 최종청산) ──

def test_l_save2_windmill_multi_cycle_accumulates():
    """ISA 풍차 2사이클(US_DIRECT). 만기가격·최종가격을 평탄구간에 떨궈 손계산.

    사이클1: 1천만@100 → 2천만@200, 만기 2023-01(idx36) 청산.
      만기세 = (1000만−비과세200만)×9.9% = 792,000. 목돈 19,208,000 → ISA 재가입(2천만 한도 내).
      위탁가정 누적: US 차익 10,000,000 (2023년).
    사이클2: 19,208,000@200 → ×2 @400, 최종청산 2025년.
      차익 19,208,000 (2025년). 최종 만기세 = (19,208,000−200만)×9.9% = 1,703,592.
      위탁가정 누적: US 차익 19,208,000 (2025년).
    위탁가정 = (1000만−250만)×22% + (19,208,000−250만)×22% = 1,650,000 + 3,675,760 = 5,325,760.
    실제 = 792,000 + 1,703,592 = 2,495,592.  절세 = 2,830,168.
    """
    import pandas as pd
    from modules.config.simulation_config import SimulationConfig
    from modules.rebalance.periodic import PeriodicRebalance
    from modules.tax.account_tax import DistributionDestination, DistributionPolicy

    seg1 = _price_frame("2020-01-01", "2022-12-15", 100.0, 200.0)
    seg2 = _price_frame("2022-12-16", "2023-03-31", 200.0, 200.0)   # 만기 2023-01 = 200
    seg3 = _price_frame("2023-04-01", "2025-11-15", 200.0, 400.0)
    seg4 = _price_frame("2025-11-16", "2025-12-31", 400.0, 400.0)   # 최종청산 = 400
    frame = pd.concat([seg1, seg2, seg3, seg4])
    dates = list(frame.index)

    config = SimulationConfig(
        start_date="2020-01-01", end_date="2026-01-01", tickers=["AAA"],
        target_weights={"AAA": 1.0}, initial_capital=10_000_000.0,
        monthly_contribution=0.0, contribution_end_months=None,
        withdrawal_amount=0, dividend_mode="hold",
        rebalance_frequency=None, inflation=0.0,
    )
    isa = {"type": "ISA", "config": config,
           "strategy": PeriodicRebalance({"AAA": 1.0}, rebalance_frequency=None),
           "isa_renewal": True}
    policy = DistributionPolicy(destinations=[DistributionDestination(account_id=0)])
    result = MultiAccountSimulationLoop(transfers_enabled=True).run(
        [isa], {"AAA": frame}, dates, tax_enabled=True,
        user_settings={"earned_income": 0, "age": 40, "isa_type": "general"},
        distribution_policy=policy,
    )
    ar = result.account_results[0]
    maturities = [t for t in result.transfer_log if t.get("type") == "maturity"]
    assert len(maturities) == 1, f"만기 1회 기대, 실제 {len(maturities)}"
    assert abs(ar["maturity_tax_paid"] - 792_000.0) < 1.0
    assert abs(ar["liquidation_tax_paid"] - 1_703_592.0) < 1.0
    assert abs(ar["brokerage_assumed_tax"] - 5_325_760.0) < 1.0
    assert abs(ar["tax_saving"] - 2_830_168.0) < 1.0


# ── L-SAVE3: 절세매도(GH) 위탁 불변식 — 연도별 250만 공제 정확 반영 ──

def test_l_save3_gain_harvest_brokerage_invariant():
    """위탁 US_DIRECT + 절세매도 ON. 매년 harvest + 최종청산이 모두 연도별 위탁가정에
    기록되므로 위탁가정 == 실제 → 절세 0 (GH on/off 모두)."""
    import pandas as pd
    from modules.config.simulation_config import SimulationConfig
    from modules.rebalance.periodic import PeriodicRebalance

    frame = _price_frame("2020-01-01", "2024-12-31", 100.0, 500.0)
    dates = list(frame.index)

    def _run(gh):
        config = SimulationConfig(
            start_date="2020-01-01", end_date="2025-01-01", tickers=["AAA"],
            target_weights={"AAA": 1.0}, initial_capital=10_000_000.0,
            monthly_contribution=0.0, contribution_end_months=None,
            withdrawal_amount=0, dividend_mode="hold",
            rebalance_frequency=None, inflation=0.0,
        )
        acct = {"type": "위탁", "config": config,
                "strategy": PeriodicRebalance({"AAA": 1.0}, rebalance_frequency=None),
                "gain_harvesting": gh}
        return MultiAccountSimulationLoop().run(
            [acct], {"AAA": frame}, dates, tax_enabled=True,
            user_settings={"earned_income": 0, "age": 40},
        ).account_results[0]

    for gh in (False, True):
        ar = _run(gh)
        # 위탁 계좌: 위탁가정(껍데기) == 실제 → 껍데기 절세 0 (±1원).
        assert ar["tax_saving"] < 1.0, f"gh={gh} saving={ar['tax_saving']}"
        assert abs(ar["brokerage_assumed_tax"] - ar["tax_paid"]) < 1.0, \
            f"gh={gh} brk={ar['brokerage_assumed_tax']} actual={ar['tax_paid']}"


# ── L-SAVE3b: GH 절세(절세매도 자체 효과) — 순수함수 + 엔진 손계산 ──

def test_l_save3b_gh_saving_pure_function():
    """GH off면 차익 5,000,000이 최종연도 단일실현 → (500만−250만)×22% = 550,000.
    GH on이면 연도별 분산(harvest 미과세) → on=0. GH 절세 = 550,000."""
    # on 기준 us_by_year = {최종: 0} (harvest로 기준리셋, 최종 미실현 0), harvested 500만.
    sav = estimate_gain_harvest_saving({2022: 0.0}, 5_000_000.0, 2022)
    assert abs(sav - 550_000.0) < 1e-6
    # harvest 없으면 절세 0
    assert estimate_gain_harvest_saving({2022: 0.0}, 0.0, 2022) == 0.0


def test_l_save3b_gh_saving_engine():
    """위탁 US_DIRECT + GH ON. 2년간 매년 250만씩 harvest(기준리셋), 총 500만.
    GH off였으면 최종 단일실현 (500만−250만)×22% = 550,000.
    가격: 2020-12 평탄 125(harvest@125, 차익25×10만=250만), 2021-12 평탄 150(harvest@150,
    차익25×10만=250만), 2022-01 최종 150(미실현 0). → GH 절세 = 550,000."""
    import pandas as pd
    from modules.config.simulation_config import SimulationConfig
    from modules.rebalance.periodic import PeriodicRebalance

    seg1 = _price_frame("2020-01-01", "2020-11-30", 100.0, 125.0)
    seg2 = _price_frame("2020-12-01", "2020-12-31", 125.0, 125.0)   # 12월 harvest @125
    seg3 = _price_frame("2021-01-01", "2021-11-30", 125.0, 150.0)
    seg4 = _price_frame("2021-12-01", "2021-12-31", 150.0, 150.0)   # 12월 harvest @150
    seg5 = _price_frame("2022-01-01", "2022-01-31", 150.0, 150.0)   # 최종청산 @150
    frame = pd.concat([seg1, seg2, seg3, seg4, seg5])
    dates = list(frame.index)
    config = SimulationConfig(
        start_date="2020-01-01", end_date="2022-02-01", tickers=["AAA"],
        target_weights={"AAA": 1.0}, initial_capital=10_000_000.0,
        monthly_contribution=0.0, contribution_end_months=None,
        withdrawal_amount=0, dividend_mode="hold",
        rebalance_frequency=None, inflation=0.0,
    )
    acct = {"type": "위탁", "config": config,
            "strategy": PeriodicRebalance({"AAA": 1.0}, rebalance_frequency=None),
            "gain_harvesting": True}
    ar = MultiAccountSimulationLoop().run(
        [acct], {"AAA": frame}, dates, tax_enabled=True,
        user_settings={"earned_income": 0, "age": 40},
    ).account_results[0]
    assert abs(ar["gain_harvest_saving"] - 550_000.0) < 1.0, ar["gain_harvest_saving"]
    assert ar["tax_saving"] < 1.0   # 껍데기 절세는 여전히 0(위탁)


# ── L-SAVE7: 합산 = 계좌별 p50의 단순합 ──

def test_l_save7_combined_is_sum_of_account_p50():
    """ISA(AAA, 절세 858,000) + 위탁(458730, 절세 0). 단일윈도우.
    합산 절세 = ISA p50 + 위탁 p50 = 858,000 + 0."""
    import numpy as np
    from modules.retirement.multi_account_analyzer import MultiAccountAnalyzer
    from tests.test_track_g_multi_account import _account, _provider_from_frames

    frames = {
        "AAA": _price_frame("2020-01-01", "2023-01-02", 100.0, 200.0),
        "458730": _price_frame("2020-01-01", "2023-01-02", 100.0, 200.0),
    }
    accounts = [
        _account("AAA", initial=10_000_000.0, account_type="ISA"),
        _account("458730", initial=1_000.0, account_type="위탁"),
    ]
    analyzer = MultiAccountAnalyzer(
        portfolio_engine=None, accounts=accounts,
        data_start="2020-01-01", data_end="2023-01-02",
        accumulation_years=3, step_months=12, tax_enabled=True,
        user_settings={"earned_income": 0, "age": 40, "isa_type": "general"},
        price_provider=_provider_from_frames(frames),
    )
    result = analyzer.run()
    sav = result["savings"]
    isa_sav = sav["accounts"][0]["tax_saving"]
    broker_sav = sav["accounts"][1]["tax_saving"]
    # ISA 절세 ≈ 858,000 (정확값은 L-SAVE1이 엔진레벨로 잠금; 여기선 bdate 윈도우 근사).
    assert abs(isa_sav - 858_000.0) < 5_000.0
    assert broker_sav == 0.0
    # 합산 = 계좌별 p50의 단순합
    assert abs(sav["combined"]["tax_saving"] - (isa_sav + broker_sav)) < 1e-6
    assert abs(sav["combined"]["brokerage_assumed_tax"]
               - sum(a["brokerage_assumed_tax"] for a in sav["accounts"])) < 1e-6


def test_l_save8_account_saving_is_p50_median():
    """다중 케이스: 계좌별 표시 절세액 = 케이스 분포의 p50(중앙값)."""
    import numpy as np
    from modules.retirement.multi_account_analyzer import MultiAccountAnalyzer
    from tests.test_track_g_multi_account import _account, _provider_from_frames

    frames = {"AAA": _price_frame("2020-01-01", "2024-12-31", 100.0, 300.0)}
    accounts = [_account("AAA", initial=10_000_000.0, account_type="ISA")]
    analyzer = MultiAccountAnalyzer(
        portfolio_engine=None, accounts=accounts,
        data_start="2020-01-01", data_end="2024-12-31",
        accumulation_years=3, step_months=12, tax_enabled=True,
        user_settings={"earned_income": 0, "age": 40, "isa_type": "general"},
        price_provider=_provider_from_frames(frames),
    )
    result = analyzer.run()
    case_savings = [c["tax_saving"] for c in result["accounts"][0]["cases"]]
    assert len(case_savings) >= 2
    expected_p50 = float(np.percentile(np.array(case_savings, dtype=float), 50))
    assert abs(result["savings"]["accounts"][0]["tax_saving"] - expected_p50) < 1e-6


# ── L-SAVE4: 연금/IRP 절세 (투자계산기 — 현행 5.5% 청산세 적용) ──

def test_l_save4_pension_us_direct():
    """연금/IRP US_DIRECT, 차익 1,000만(초기 1천만@100→2천만@200).
    실제 = 연금 청산세 전액×5.5% = 20,000,000×0.055 = 1,100,000.
    위탁가정 = US 양도 (1,000만−250만)×22% = 1,650,000.
    절세 = 550,000."""
    frame = _price_frame("2020-01-01", "2023-01-02", 100.0, 200.0)
    for atype in ("연금저축", "IRP"):
        ar = _run_single("AAA", frame, account_type=atype, initial=10_000_000.0)
        assert abs(ar["liquidation_tax_paid"] - 1_100_000.0) < 1.0, atype
        assert abs(ar["brokerage_assumed_tax"] - 1_650_000.0) < 1.0, atype
        assert abs(ar["tax_saving"] - 550_000.0) < 1.0, atype


# ── L-SAVE-DCA: 월적립 위탁 불변식 (위탁가정 == 실제 → 절세 0) ──

def test_l_save_dca_brokerage_invariant():
    """월 적립(DCA) 위탁 US_DIRECT — 매수단가 여러개여도 위탁가정==실제 → 절세 0."""
    import pandas as pd
    from modules.config.simulation_config import SimulationConfig
    from modules.rebalance.periodic import PeriodicRebalance

    frame = _price_frame("2020-01-01", "2023-12-31", 100.0, 300.0)
    dates = list(frame.index)
    config = SimulationConfig(
        start_date="2020-01-01", end_date="2024-01-01", tickers=["AAA"],
        target_weights={"AAA": 1.0}, initial_capital=5_000_000.0,
        monthly_contribution=500_000.0, contribution_end_months=None,
        withdrawal_amount=0, dividend_mode="hold",
        rebalance_frequency=None, inflation=0.0,
    )
    acct = {"type": "위탁", "config": config,
            "strategy": PeriodicRebalance({"AAA": 1.0}, rebalance_frequency=None),
            "gain_harvesting": False}
    ar = MultiAccountSimulationLoop().run(
        [acct], {"AAA": frame}, dates, tax_enabled=True,
        user_settings={"earned_income": 0, "age": 40},
    ).account_results[0]
    assert ar["brokerage_assumed_tax"] > 0   # 차익 존재
    assert ar["tax_saving"] < 1.0            # 위탁 → 절세 0
    assert abs(ar["brokerage_assumed_tax"] - ar["tax_paid"]) < 1.0


# ── L-SAVE-REINVEST: 배당 재투자 모드 위탁 불변식 ──

def test_l_save_reinvest_brokerage_invariant():
    """배당 재투자 모드 위탁 KR_FOREIGN — 배당세+양도세 위탁가정==실제 → 절세 0."""
    import pandas as pd
    from modules.config.simulation_config import SimulationConfig
    from modules.rebalance.periodic import PeriodicRebalance

    frame = _price_frame("2020-01-01", "2022-12-31", 100.0, 180.0,
                         dividend_date="2020-06-01", dividend=5.0)
    dates = list(frame.index)
    config = SimulationConfig(
        start_date="2020-01-01", end_date="2023-01-01", tickers=["458730"],
        target_weights={"458730": 1.0}, initial_capital=10_000_000.0,
        monthly_contribution=0.0, contribution_end_months=None,
        withdrawal_amount=0, dividend_mode="reinvest",
        rebalance_frequency=None, inflation=0.0,
    )
    acct = {"type": "위탁", "config": config,
            "strategy": PeriodicRebalance({"458730": 1.0}, rebalance_frequency=None),
            "gain_harvesting": False}
    ar = MultiAccountSimulationLoop().run(
        [acct], {"458730": frame}, dates, tax_enabled=True,
        user_settings={"earned_income": 0, "age": 40},
    ).account_results[0]
    assert ar["brokerage_assumed_tax"] > 0
    assert ar["tax_saving"] < 1.0
    assert abs(ar["brokerage_assumed_tax"] - ar["tax_paid"]) < 1.0


# ── L-SAVE-MULTITICKER: 다종목 혼합 분류 위탁 불변식 ──

def test_l_save_multiticker_brokerage_invariant():
    """한 계좌에 US_DIRECT + KR_FOREIGN + KRX금 혼합 — 분류별 위탁가정==실제 → 절세 0."""
    import pandas as pd
    from modules.config.simulation_config import SimulationConfig
    from modules.rebalance.periodic import PeriodicRebalance

    frames = {
        "AAA": _price_frame("2020-01-01", "2022-12-31", 100.0, 200.0),       # US
        "458730": _price_frame("2020-01-01", "2022-12-31", 100.0, 150.0),    # KR_FOREIGN
        "KRX_GOLD": _price_frame("2020-01-01", "2022-12-31", 100.0, 250.0),  # 금(0%)
    }
    dates = list(frames["AAA"].index)
    weights = {"AAA": 0.34, "458730": 0.33, "KRX_GOLD": 0.33}
    config = SimulationConfig(
        start_date="2020-01-01", end_date="2023-01-01", tickers=list(frames),
        target_weights=weights, initial_capital=30_000_000.0,
        monthly_contribution=0.0, contribution_end_months=None,
        withdrawal_amount=0, dividend_mode="hold",
        rebalance_frequency=None, inflation=0.0,
    )
    acct = {"type": "위탁", "config": config,
            "strategy": PeriodicRebalance(weights, rebalance_frequency=None),
            "gain_harvesting": False}
    ar = MultiAccountSimulationLoop().run(
        [acct], frames, dates, tax_enabled=True,
        user_settings={"earned_income": 0, "age": 40},
    ).account_results[0]
    assert ar["brokerage_assumed_tax"] > 0
    assert ar["tax_saving"] < 1.0
    assert abs(ar["brokerage_assumed_tax"] - ar["tax_paid"]) < 1.0


# ── L-SAVE-COMP: 종합과세 가산 — 위탁 절세 0 유지(0 하한) ──

def test_l_save_comprehensive_keeps_zero():
    """고소득자 위탁 KR_FOREIGN 청산이익 > 2천만 → 실제에 종합과세 가산.
    위탁가정(15.4% 평면, 가산 생략)은 실제보다 작음 → 절세 = max(0, 음수) = 0."""
    frame = _price_frame("2020-01-01", "2022-12-31", 100.0, 400.0)  # 차익 3천만
    ar = _run_single("458730", frame, account_type="위탁", initial=10_000_000.0)
    # 실제 ≥ 위탁가정 (가산 때문). 절세 0.
    assert ar["tax_paid"] >= ar["brokerage_assumed_tax"] - 1.0
    assert ar["tax_saving"] == 0.0
    ar_hi = MultiAccountSimulationLoop().run(
        [_loop_account("458730", initial=10_000_000.0, account_type="위탁")],
        {"458730": frame}, list(frame.index), tax_enabled=True,
        user_settings={"earned_income": 100_000_000, "age": 40},
    ).account_results[0]
    assert ar_hi["tax_saving"] == 0.0  # 고소득 가산에도 0 하한 유지


# ── L-SAVE-LOGIC: calculator_logic savings 매핑(라운딩·None) ──

def test_l_save_logic_mapping():
    from calculator_logic import _build_savings_summary
    assert _build_savings_summary({}) is None          # combined 없으면 None
    assert _build_savings_summary({'accounts': []}) is None
    raw = {
        'combined': {'brokerage_assumed_tax': 1650000.4, 'actual_tax': 792000.6,
                     'tax_saving': 858000.5, 'gain_harvest_saving': 0.0},
        'accounts': [
            {'account_id': 0, 'type': 'ISA', 'brokerage_assumed_tax': 1650000.4,
             'actual_tax': 792000.6, 'tax_saving': 858000.5},  # gain_harvest_saving 누락 → 0
        ],
    }
    out = _build_savings_summary(raw)
    assert out['combined'] == {'brokerage_assumed_tax': 1650000, 'actual_tax': 792001,
                               'tax_saving': 858000, 'gain_harvest_saving': 0}
    assert out['accounts'][0]['gain_harvest_saving'] == 0
    assert out['accounts'][0]['tax_saving'] == 858000


# ── L-SAVE-ANALYZER-WINDMILL: 풍차+transfers 절세 surfacing ──

def test_l_save_analyzer_windmill_surfaced():
    """풍차(transfers ON, 정책배선) ISA 절세액이 analyzer savings로 도달."""
    import pandas as pd
    from modules.retirement.multi_account_analyzer import MultiAccountAnalyzer
    from modules.tax.account_tax import DistributionDestination, DistributionPolicy
    from tests.test_track_g_multi_account import _account, _provider_from_frames

    seg1 = _price_frame("2020-01-01", "2022-12-15", 100.0, 200.0)
    seg2 = _price_frame("2022-12-16", "2023-03-31", 200.0, 200.0)
    seg3 = _price_frame("2023-04-01", "2025-11-15", 200.0, 400.0)
    seg4 = _price_frame("2025-11-16", "2026-01-31", 400.0, 400.0)
    frame = pd.concat([seg1, seg2, seg3, seg4])
    frames = {"AAA": frame}
    accounts = [_account("AAA", initial=10_000_000.0, account_type="ISA", isa_renewal=True)]
    policy = DistributionPolicy(destinations=[DistributionDestination(account_id=0)])
    analyzer = MultiAccountAnalyzer(
        portfolio_engine=None, accounts=accounts,
        data_start="2020-01-01", data_end="2026-01-31",
        accumulation_years=6, step_months=12, tax_enabled=True,
        user_settings={"earned_income": 0, "age": 40, "isa_type": "general"},
        price_provider=_provider_from_frames(frames),
        transfers_enabled=True, distribution_policy=policy,
    )
    result = analyzer.run()
    sav = result["savings"]
    assert sav["accounts"][0]["tax_saving"] > 0       # 풍차 ISA 절세 surfaced
    assert sav["accounts"][0]["brokerage_assumed_tax"] > 0
    assert abs(sav["combined"]["tax_saving"]
               - sum(a["tax_saving"] for a in sav["accounts"])) < 1e-6


# ── BUG-TAX-1 회귀: 단일경로(TaxableSimulationRunner) 배당세 실제 차감 ──

def _run_taxable(dividend_mode, tax_enabled):
    """단일경로. 458730(KR_FOREIGN), 가격 평탄 100, 초기 1000(=10주), 배당 10/주."""
    from modules.config.simulation_config import SimulationConfig
    from modules.rebalance.periodic import PeriodicRebalance
    from modules.simulation.taxable_runner import TaxableSimulationRunner
    from modules.tax.base_tax import TaxEngine

    frame = _price_frame("2020-01-01", "2020-12-31", 100.0, 100.0,
                         dividend_date="2020-06-01", dividend=10.0)
    config = SimulationConfig(
        start_date="2020-01-01", end_date="2021-01-01", tickers=["458730"],
        target_weights={"458730": 1.0}, initial_capital=1000.0,
        monthly_contribution=0.0, withdrawal_amount=0,
        dividend_mode=dividend_mode, rebalance_frequency=None, inflation=0.0,
    )
    strategy = PeriodicRebalance({"458730": 1.0}, rebalance_frequency=None)
    te = TaxEngine({"earned_income": 0, "age": 40}) if tax_enabled else None
    return TaxableSimulationRunner().run(
        config, {"458730": frame}, list(frame.index), strategy,
        tax_enabled=tax_enabled, account_type="위탁", tax_engine=te,
        user_settings={"earned_income": 0, "age": 40},
    ).end_value


def test_bug_tax1_single_path_dividend_taxed_hold():
    """배당 보유 모드: 세전배당 100 → 위탁 배당세 15.4% = 15.4 차감.
    가격 평탄(양도세 0) → 세금 차이 = 배당세뿐."""
    no_tax = _run_taxable("hold", False)
    taxed = _run_taxable("hold", True)
    assert abs(no_tax - 1100.0) < 1e-6        # 1000 + 배당 100(gross)
    assert abs(taxed - 1084.6) < 1e-6         # 1000 + net 84.6 (배당세 15.4 차감)
    assert abs((no_tax - taxed) - 15.4) < 1e-6   # 배당세 실제 차감 확인 (버그면 0이었음)


def test_bug_tax1_single_path_dividend_taxed_reinvest():
    """배당 재투자 모드도 배당세 차감(net만 재투자)."""
    no_tax = _run_taxable("reinvest", False)
    taxed = _run_taxable("reinvest", True)
    # 평탄가격이라 재투자분도 가치증가 없음 → 세금 차이 = 배당세 15.4
    assert abs((no_tax - taxed) - 15.4) < 1e-6


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
