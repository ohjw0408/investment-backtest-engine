# BUG-WD-MULTI-LIVE 로컬 재현 — E2E D2 구성 그대로 run_withdrawal_logic 멀티 경로 직접 호출.
# 조사용(읽기 전용). 수정 없음.
import json
import sys

sys.path.insert(0, ".")

from retirement_logic import run_withdrawal_logic

BODY = {
    "tickers": [{"code": "458730", "name": "TIGER 미국배당다우존스", "weight": 1.0}],
    "initial_capital": 300_000_000,
    "monthly_withdrawal": 2_000_000,
    "withdrawal_years": 30,
    "inflation": 0.02,
    "pension_start_age": 65,
    "dividend_mode": "reinvest",
    "rebal_mode": "none",
    "band_width": 0.05,
    "target_percentile": 0.90,
    "tax_enabled": True,
    "account_type": "위탁",
    "gain_harvesting": True,
    "user_settings": {"age": 40, "earned_income": 50_000_000, "isa_type": "general", "pension_age": 65},
    "_withdrawal_only": True,
    "accounts": [
        {
            "type": "위탁",
            "initial_capital": 300_000_000,
            "unrealized_gain": 100_000_000,
            "tickers": [{"code": "458730", "name": "TIGER 미국배당다우존스", "weight": 1.0}],
            "rebal_mode": "none", "band_width": 0.05, "dividend_mode": "reinvest",
            "priority": 1,
        },
        {
            "type": "연금저축",
            "initial_capital": 200_000_000,
            "unrealized_gain": 0,
            "tickers": [{"code": "360750", "name": "TIGER 미국S&P500", "weight": 1.0}],
            "rebal_mode": "none", "band_width": 0.05, "dividend_mode": "reinvest",
            "priority": 2,
        },
    ],
    "distribution_policy": {"destinations": [{"account_id": 0}, {"account_id": 1}]},
}

res = run_withdrawal_logic(BODY)
out = {
    "survival_rate": res.get("survival_rate"),
    "combined_summary": res.get("combined_summary"),
    "median_pension_tax": res.get("median_pension_tax"),
    "n_real": res.get("n_real"),
    "n_synthetic": res.get("n_synthetic"),
    "data_start": res.get("data_start"),
    "per_account": res.get("multi_account", {}).get("accounts"),
}
print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
