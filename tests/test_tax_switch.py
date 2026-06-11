"""세금 전환 계산기(위탁 유지 vs ISA 분할 이전) 엔진 결정론 테스트.

세금계산기_plan.md v1 검증 설계:
- 손계산 ±1원 (A/B 종료값, 전환세)
- 경계: 전환세 0(손실), flat+차익0 → A==B 불변식, ISA 총 1억 한도, breakeven
- 기존 경로 무변경은 Gate 2a/2b/2c + phase2f + trackG 회귀로 별도 보장.
"""
import pandas as pd
import pytest

from modules.config.simulation_config import SimulationConfig
from modules.rebalance.periodic import PeriodicRebalance
from modules.simulation.multi_account_loop import MultiAccountSimulationLoop

TKR = "SWTEST"  # isalpha → US_DIRECT 기본 분류. KR_FOREIGN은 테스트에서 강제.
USER = {"age": 40, "earned_income": 50_000_000, "isa_type": "general"}


def _flat_prices(years: int, price: float = 10_000.0):
    dates = pd.bdate_range("2020-01-02", periods=252 * years)
    px = pd.DataFrame({"close": price, "dividend": 0.0}, index=dates)
    return {TKR: px}, list(dates)


def _account(atype: str, init: float, carried=None, isa_years: int = 3):
    cfg = SimulationConfig(
        start_date="2020-01-02", end_date="2099-01-01",
        tickers=[TKR], target_weights={TKR: 1.0},
        initial_capital=init, monthly_contribution=0.0,
        withdrawal_amount=0, dividend_mode="reinvest",
        rebalance_frequency="monthly", inflation=0.0,
    )
    acct = {
        "type": atype, "config": cfg,
        "strategy": PeriodicRebalance({TKR: 1.0}, rebalance_frequency="monthly"),
        "gain_harvesting": False, "isa_years_held": isa_years,
    }
    if carried is not None:
        acct["carried_cost_basis"] = carried
    return acct


def _run_a(price_data, dates, init, carried, user=USER):
    return MultiAccountSimulationLoop(yearly_after_tax_snapshot=True).run(
        accounts=[_account("위탁", init, carried)],
        price_data=price_data, dates=dates,
        tax_enabled=True, user_settings=user,
    )


def _run_b(price_data, dates, init, carried, user=USER, isa_years=3):
    return MultiAccountSimulationLoop(
        switch_policy={"source_id": 0, "dest_id": 1},
        yearly_after_tax_snapshot=True,
    ).run(
        accounts=[_account("위탁", init, carried),
                  _account("ISA", 0.0, isa_years=isa_years)],
        price_data=price_data, dates=dates,
        tax_enabled=True, user_settings=user,
    )


# ── 1) A 손계산: US_DIRECT 일괄 청산 ────────────────────────────────────
def test_a_lump_sum_hand_calc():
    """flat·평가액 5천만·취득가 3천만 → 청산세 = (2,000만−250만)×22% = 385만."""
    price_data, dates = _flat_prices(3)
    ra = _run_a(price_data, dates, 50_000_000, 30_000_000)
    assert ra.combined_end_value == pytest.approx(46_150_000, abs=1)


# ── 2) B 손계산: 연도분할로 250만 공제 3회 ──────────────────────────────
def test_b_split_hand_calc():
    """y1: 2,000만 매도 차익 800만 → (800−250)×22%=121만, 이전 1,879만.
    y2 동일. y3: 1,000만 매도 차익 400만 → 33만, 이전 967만.
    ISA 합계 4,725만(이익 0 → 만기세 0). 분할로 공제 2회 추가 = A 대비 +110만."""
    price_data, dates = _flat_prices(3)
    rb = _run_b(price_data, dates, 50_000_000, 30_000_000)
    assert rb.combined_end_value == pytest.approx(47_250_000, abs=1)
    assert rb.switch_cg_tax_total == pytest.approx(2_750_000, abs=1)
    log = rb.switch_log
    assert len(log) == 3
    assert log[0]["cg_tax"] == pytest.approx(1_210_000, abs=1)
    assert log[0]["transferred"] == pytest.approx(18_790_000, abs=1)
    assert log[2]["cg_tax"] == pytest.approx(330_000, abs=1)
    assert log[2]["transferred"] == pytest.approx(9_670_000, abs=1)
    # 위탁 전량 소진 → ISA가 전부 보유
    by_type = {r["type"]: r for r in rb.account_results}
    assert by_type["위탁"]["end_value"] == pytest.approx(0, abs=1)
    assert by_type["ISA"]["end_value"] == pytest.approx(47_250_000, abs=1)


# ── 3) KR_FOREIGN flat: 분리과세 구간에선 A==B (공제효과 없음) ──────────
def test_kr_foreign_flat_a_equals_b(monkeypatch):
    """KR_FOREIGN 15.4%는 공제·구간 없음(2천만 이하 분리과세) → 분할해도 총세 동일.
    A: 차익 2,000만(임계 초과 아님) → 308만. B: 308만 분할 납부. A==B."""
    from modules.tax import base_tax
    monkeypatch.setattr(
        base_tax.TaxEngine, "classify_asset", lambda self, t: "KR_FOREIGN"
    )
    price_data, dates = _flat_prices(3)
    ra = _run_a(price_data, dates, 50_000_000, 30_000_000)
    rb = _run_b(price_data, dates, 50_000_000, 30_000_000)
    assert ra.combined_end_value == pytest.approx(46_920_000, abs=1)
    assert rb.combined_end_value == pytest.approx(ra.combined_end_value, abs=1)


# ── 4) 차익 0 → 전환세 0 + A==B 불변식 ─────────────────────────────────
def test_zero_gain_invariant():
    """취득가=평가액·flat·배당0 → 전환세 0, ISA 만기세 0, A==B==평가액."""
    price_data, dates = _flat_prices(3)
    ra = _run_a(price_data, dates, 50_000_000, 50_000_000)
    rb = _run_b(price_data, dates, 50_000_000, 50_000_000)
    assert ra.combined_end_value == pytest.approx(50_000_000, abs=1)
    assert rb.combined_end_value == pytest.approx(50_000_000, abs=1)
    assert rb.switch_cg_tax_total == pytest.approx(0, abs=1)


# ── 5) 손실 보유분 전환: 전환세 0 ───────────────────────────────────────
def test_loss_position_no_switch_tax():
    price_data, dates = _flat_prices(2)
    rb = _run_b(price_data, dates, 50_000_000, 60_000_000)
    assert rb.switch_cg_tax_total == pytest.approx(0, abs=1)
    assert all(e["cg_tax"] == pytest.approx(0, abs=1) for e in rb.switch_log)


# ── 6) ISA 총 1억 한도: 5년 채우면 이전 중단, 잔여 영구 위탁 ────────────
def test_isa_total_limit_caps_transfers():
    """차익 0(세금 노이즈 제거)·평가액 1.5억·7년 → 연 2,000만×5 = 총 1억에서 중단.
    잔여 5,000만은 위탁 유지. flat이라 A==B."""
    price_data, dates = _flat_prices(7)
    rb = _run_b(price_data, dates, 150_000_000, 150_000_000, isa_years=7)
    transferred = sum(e["transferred"] for e in rb.switch_log)
    assert transferred == pytest.approx(100_000_000, abs=2)
    # 6·7년차 이전 없음 (총한도 소진)
    assert len([e for e in rb.switch_log if e["transferred"] > 0]) == 5
    by_type = {r["type"]: r for r in rb.account_results}
    assert by_type["위탁"]["end_value"] == pytest.approx(50_000_000, abs=2)
    assert by_type["ISA"]["end_value"] == pytest.approx(100_000_000, abs=2)


# ── 7) 연말 세후 스냅샷: 손계산 정합 ────────────────────────────────────
def test_after_tax_snapshot_hand_calc():
    """B 1년차 말(US_DIRECT): 위탁 3,000만(차익 1,200만, 공제 소진) → 세 264만.
    ISA 1,879만(이익0) → 합 4,615만. 2년차 말: 1,000만(차익 400만→88만) + 3,758만 = 4,670만."""
    price_data, dates = _flat_prices(3)
    rb = _run_b(price_data, dates, 50_000_000, 30_000_000)
    snaps = sorted(rb.after_tax_by_year.items())
    assert snaps[0][1] == pytest.approx(46_150_000, abs=1)
    assert snaps[1][1] == pytest.approx(46_700_000, abs=1)
    assert snaps[2][1] == pytest.approx(47_250_000, abs=1)


# ── 8) 기본 OFF 무변경: switch 미사용 시 신규 필드 비활성 ───────────────
def test_defaults_off_no_behavior_change():
    price_data, dates = _flat_prices(2)
    r = MultiAccountSimulationLoop().run(
        accounts=[_account("위탁", 50_000_000)],
        price_data=price_data, dates=dates,
        tax_enabled=True, user_settings=USER,
    )
    assert r.after_tax_by_year == {}
    assert r.switch_log == []
    assert r.switch_cg_tax_total == 0.0
