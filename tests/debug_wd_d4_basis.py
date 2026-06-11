# D4 무효과 조사 — 미실현차익 0 vs 2억 로컬 비교 + 분류·CG세·취득가 스케일 계측. 읽기 전용.
import json
import sys

sys.path.insert(0, ".")

from retirement_logic import _run_multi_account_withdrawal_logic
from modules.tax.base_tax import TaxEngine
import modules.retirement.multi_account_withdrawal as mw

# ① 자산분류 확인
te = TaxEngine({"age": 40, "earned_income": 50_000_000, "isa_type": "general", "pension_age": 65})
print("classify 458730:", te.classify_asset("458730"))
print("classify 360750:", te.classify_asset("360750"))

# ② 런타임 빌드 계측 — 취득가 스케일 적용 여부 + 윈도우별 CG세 합
_orig_build = mw._build_account_runtime
_first_dump = {"done": False}

def _patched_build(spec, first_price_dict, tax_engine, session):
    rt = _orig_build(spec, first_price_dict, tax_engine, session)
    if not _first_dump["done"] and spec["type"] == "위탁":
        pf = rt["portfolio"]
        avg = dict(getattr(pf, "_avg_costs", {}) or {})
        print(f"[build] 위탁 cost_basis={spec.get('cost_basis')} avg_costs={avg} "
              f"first_prices={ {t: round(p,1) for t, p in first_price_dict.items()} }")
        _first_dump["done"] = True
    return rt

mw._build_account_runtime = _patched_build

_orig_sim = mw.simulate_household_window
_cg_totals = []

def _patched_sim(accounts, price_data, dates, monthly_net, **kw):
    res = _orig_sim(accounts, price_data, dates, monthly_net, **kw)
    # 윈도우 끝에 executor 접근 불가(내부 생성) — 대신 결과만 수집
    return res

def run(unrealized):
    _first_dump["done"] = False
    body = {
        "tickers": [{"code": "458730", "weight": 1.0}],
        "initial_capital": 300_000_000,
        "monthly_withdrawal": 2_000_000,
        "withdrawal_years": 30,
        "inflation": 0.02,
        "pension_start_age": 65,
        "dividend_mode": "reinvest",
        "rebal_mode": "none",
        "band_width": 0.05,
        "tax_enabled": True,
        "account_type": "위탁",
        "user_settings": {"age": 40, "earned_income": 50_000_000, "isa_type": "general", "pension_age": 65},
        "accounts": [
            {"type": "위탁", "initial_capital": 300_000_000, "unrealized_gain": unrealized,
             "tickers": [{"code": "458730", "weight": 1.0}],
             "rebal_mode": "none", "band_width": 0.05, "dividend_mode": "reinvest", "priority": 1},
            {"type": "연금저축", "initial_capital": 200_000_000, "unrealized_gain": 0,
             "tickers": [{"code": "360750", "weight": 1.0}],
             "rebal_mode": "none", "band_width": 0.05, "dividend_mode": "reinvest", "priority": 2},
        ],
    }
    res = _run_multi_account_withdrawal_logic(body)
    return {
        "unrealized": unrealized,
        "survival": res["survival_rate"],
        "combined_p50": res["combined_summary"]["combined_end_value"]["p50"],
        "pension_tax": res["median_pension_tax"],
        "위탁_p50": res["multi_account"]["accounts"][0]["distribution"]["end_value"]["p50"],
        "연금_p50": res["multi_account"]["accounts"][1]["distribution"]["end_value"]["p50"],
    }

r0 = run(0)
r2 = run(200_000_000)
print(json.dumps(r0, ensure_ascii=False))
print(json.dumps(r2, ensure_ascii=False))
print("동일여부:", r0["combined_p50"] == r2["combined_p50"], "/ 차이:", r0["combined_p50"] - r2["combined_p50"])
