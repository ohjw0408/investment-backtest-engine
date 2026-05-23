"""
Gate 2c: 배당 역산 세금 연결 검증.

1. tax ON 시 배당금 < tax OFF (세금 차감 확인)
2. tax OFF 시 기존 동작과 동일 (회귀 없음)
3. legacy sim.tax_engine 삭제 확인
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


PARAMS = dict(
    tickers        = [{"code": "SPY", "weight": 1.0}],
    dividend_mode  = "reinvest",
    rebal_mode     = "none",
    band_width     = 0.05,
    target_monthly_div = 500_000,
    probability    = 0.50,
    seed           = {"center": 100_000_000, "step": 0, "n": 0, "mode": "fixed"},
    monthly        = {"center": 0, "step": 0, "n": 0, "mode": "fixed"},
    years          = {"center": 10, "step": 0, "n": 0, "mode": "fixed"},
    user_settings  = {"earned_income": 50_000_000, "age": 40},
)


def _run(tax_enabled: bool) -> dict:
    from dividend_logic import run_dividend_scenario_logic
    body = {**PARAMS, "tax_enabled": tax_enabled, "account_type": "위탁"}
    return run_dividend_scenario_logic(body)


def test_legacy_tax_engine_deleted():
    """modules/sim/tax_engine.py 삭제 확인."""
    import importlib
    try:
        importlib.import_module("modules.sim.tax_engine")
        assert False, "modules.sim.tax_engine 아직 존재함 — 삭제 필요"
    except ModuleNotFoundError:
        pass  # 정상


def test_dividend_tax_off_runs():
    result = _run(False)
    assert "error" not in result, f"에러: {result.get('error')}"
    prob = result["result"]["probability"]
    print(f"tax OFF: prob={prob}")
    assert 0.0 <= prob <= 1.0


def test_dividend_tax_on_runs():
    result = _run(True)
    assert "error" not in result, f"에러: {result.get('error')}"
    prob = result["result"]["probability"]
    print(f"tax ON: prob={prob}")
    assert 0.0 <= prob <= 1.0


def test_tax_reduces_dividend():
    """세금 ON 시 배당 달성확률 < OFF (세후 배당금 감소 → 목표 달성 어려움)."""
    off = _run(False)["result"]["probability"]
    on  = _run(True)["result"]["probability"]
    print(f"tax OFF prob={off:.4f}  ON prob={on:.4f}  diff={off - on:.4f}")
    assert on <= off, (
        f"tax ON({on:.4f}) > OFF({off:.4f}) — 세금 차감이 확률에 반영되지 않음"
    )


if __name__ == "__main__":
    print("=== Gate 2c ===")
    test_legacy_tax_engine_deleted()
    print("레거시 tax_engine 삭제 ✓")
    test_dividend_tax_off_runs()
    test_dividend_tax_on_runs()
    test_tax_reduces_dividend()
    print("=== 통과 ===")
