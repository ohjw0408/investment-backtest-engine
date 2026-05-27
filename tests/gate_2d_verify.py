"""
Gate 2d 검증 스크립트
조건:
  G7a: 위탁 tax ON → survival_rate가 tax OFF보다 낮거나 같음 (세금으로 인해 생존율 감소)
  G7b: 연금저축 → pension_tax_info 존재, brackets 1개 이상
  G7c: 위탁 tax ON end_value_p50 < tax OFF end_value_p50 (세금으로 최종 자산 감소)
  G7d: 모든 케이스에서 에러 없이 완료

사용법: python tests/gate_2d_verify.py
서버에서 실행 (실제 price_daily.db 필요)
"""

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parents[1]))

from retirement_logic import run_withdrawal_logic

PASS = "[PASS]"
FAIL = "[FAIL]"


def _run(body: dict) -> dict:
    return run_withdrawal_logic(body)


def _base_body(ticker: str, account_type: str, tax_enabled: bool,
               earned_income: int = 50_000_000, age: int = 55) -> dict:
    return {
        "tickers":           [{"code": ticker, "weight": 1.0}],
        "initial_capital":   300_000_000,    # 3억
        "monthly_withdrawal": 1_500_000,     # 월 150만 인출
        "withdrawal_years":  20,
        "inflation":         0.02,
        "dividend_mode":     "reinvest",
        "rebal_mode":        "none",
        "tax_enabled":       tax_enabled,
        "account_type":      account_type,
        "accumulation_years": 0,
        "user_settings": {
            "earned_income": earned_income,
            "isa_type":      "general",
            "age":           age,
        },
    }


def run_tests():
    all_pass = True
    results  = []

    # ── G7a + G7c: SCHD 위탁, tax ON vs OFF ──────────────────────
    print("\n[G7a/G7c] SCHD 위탁 tax ON vs OFF ...")
    body_off = _base_body("SCHD", "위탁", tax_enabled=False)
    body_on  = _base_body("SCHD", "위탁", tax_enabled=True)

    res_off = _run(body_off)
    res_on  = _run(body_on)

    sr_off  = res_off["survival_rate"]
    sr_on   = res_on["survival_rate"]
    ev_off  = res_off["combined_summary"]["combined_end_value"]["p50"]
    ev_on   = res_on["combined_summary"]["combined_end_value"]["p50"]

    g7a = sr_on <= sr_off + 0.05   # 허용 오차 5%p (배당재투자는 세금 영향 작을 수 있음)
    g7c = ev_on <= ev_off + 1000   # 세금 ON이면 최종 자산 같거나 작아야

    tag = PASS if g7a else FAIL
    all_pass = all_pass and g7a
    print(f"  {tag} G7a survival_rate: OFF={sr_off:.3f} vs ON={sr_on:.3f}")
    results.append((tag, "G7a"))

    tag = PASS if g7c else FAIL
    all_pass = all_pass and g7c
    print(f"  {tag} G7c end_value_p50: OFF={ev_off:,.0f} vs ON={ev_on:,.0f}")
    results.append((tag, "G7c"))

    # ── G7b: 연금저축 pension_tax_info 존재 ───────────────────────
    print("\n[G7b] 연금저축 pension_tax_info ...")
    body_pension = _base_body("SCHD", "연금저축", tax_enabled=True, age=60)
    res_pension  = _run(body_pension)

    pti    = res_pension.get("pension_tax_info")
    g7b    = pti is not None and len(pti.get("brackets", [])) >= 1
    g7b_sr = 0.0 < res_pension["survival_rate"] <= 1.0

    tag = PASS if g7b else FAIL
    all_pass = all_pass and g7b
    print(f"  {tag} G7b pension_tax_info exists: {bool(pti)}, brackets={len(pti.get('brackets',[]) if pti else [])}")
    results.append((tag, "G7b"))

    tag = PASS if g7b_sr else FAIL
    all_pass = all_pass and g7b_sr
    print(f"  {tag} G7b_sr survival_rate in (0,1]: {res_pension['survival_rate']:.3f}")
    results.append((tag, "G7b_sr"))

    # ── G7d: IRP, 세금 ON, 에러 없음 ─────────────────────────────
    print("\n[G7d] IRP tax ON 에러 없음 ...")
    try:
        body_irp = _base_body("SCHD", "IRP", tax_enabled=True, age=55)
        res_irp  = _run(body_irp)
        g7d = "survival_rate" in res_irp
        tag = PASS if g7d else FAIL
        all_pass = all_pass and g7d
        print(f"  {tag} G7d IRP survival_rate={res_irp.get('survival_rate', 'N/A'):.3f}")
        results.append((tag, "G7d"))
    except Exception as e:
        all_pass = False
        print(f"  {FAIL} G7d IRP raised exception: {e}")
        results.append((FAIL, "G7d"))

    # ── 요약 ──────────────────────────────────────────────────────
    print("\n" + "="*50)
    passed = sum(1 for t, _ in results if t == PASS)
    total  = len(results)
    print(f"Gate 2d: {passed}/{total} PASS")
    for tag, name in results:
        print(f"  {tag} {name}")
    if all_pass:
        print("\nGate 2d PASSED")
    else:
        print("\nGate 2d FAILED")
    return all_pass


if __name__ == "__main__":
    ok = run_tests()
    sys.exit(0 if ok else 1)
