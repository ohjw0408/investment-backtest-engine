"""
test_tax_24cases.py
────────────────────────────────────────────────────────────────────────────────
세금 규칙 24가지 경우 테스트

실행: 프로젝트 루트에서
    python test_tax_24cases.py

성공 조건:
    배당 후 세후금액이 기대값과 일치하는지 확인
    양도차익 세금이 올바르게 계산되는지 확인
────────────────────────────────────────────────────────────────────────────────
"""

import sys
from pathlib import Path
# tests 폴더 안에서 실행 시 프로젝트 루트를 path에 추가
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from modules.tax.base_tax import TaxEngine
from modules.execution.order_executor import TaxedOrderExecutor

# ── 테스트 설정 ──────────────────────────────────────────────
USER_SETTINGS = {
    "earned_income": 50_000_000,
    "age":           60,
    "isa_type":      "general",
    "pension_age":   60,
}

te = TaxEngine(USER_SETTINGS)

PASS = "✅ PASS"
FAIL = "❌ FAIL"

results = []

def check(case_num, desc, actual, expected, tol=0.01):
    ok = abs(actual - expected) < tol * max(abs(expected), 1)
    tag = PASS if ok else FAIL
    results.append(ok)
    num_str = f"{case_num:02d}" if isinstance(case_num, int) else f"{case_num}"
    status = f"{tag} [{num_str}] {desc}"
    print(f"  {status}")
    if not ok:
        print(f"       actual={actual:.4f}  expected={expected:.4f}")


print("=" * 60)
print("세금 엔진 24가지 케이스 테스트")
print("=" * 60)

# ============================================================
print("\n[위탁 계좌]")
# ============================================================

GROSS_DIV = 100.0
GROSS_GAIN = 10_000_000.0   # 1,000만원 차익

# 1. 위탁 × 국내 개별주식 × 배당 → 15.4%
check(1, "위탁 × 국내 개별주식 × 배당 (15.4%)",
    te.after_tax_dividend(GROSS_DIV, "005930", "위탁"),
    GROSS_DIV * (1 - 0.154))

# 2. 위탁 × 국내 개별주식 × 양도차익 → 비과세
executor = TaxedOrderExecutor(te, "위탁")
cg_tax_2 = executor._calc_cg_tax("005930", GROSS_GAIN)
check(2, "위탁 × 국내 개별주식 × 양도차익 (비과세)",
    cg_tax_2, 0.0)

# 3. 위탁 × 해외 개별주식 × 배당 → 15% (미국 원천)
check(3, "위탁 × 해외 개별주식 × 배당 (15%)",
    te.after_tax_dividend(GROSS_DIV, "AAPL", "위탁"),
    GROSS_DIV * (1 - 0.15))

# 4. 위탁 × 해외 개별주식 × 양도차익 → 250만 공제 후 22%
executor4 = TaxedOrderExecutor(te, "위탁")
cg_tax_4 = executor4._calc_cg_tax("AAPL", GROSS_GAIN)
expected_4 = max(0, GROSS_GAIN - 2_500_000) * 0.22
check(4, "위탁 × 해외 개별주식 × 양도차익 (250만 공제 후 22%)",
    cg_tax_4, expected_4)

# 4b. 250만 이하 차익 → 공제로 세금 0
executor4b = TaxedOrderExecutor(te, "위탁")
cg_tax_4b = executor4b._calc_cg_tax("AAPL", 2_000_000)
check("4b", "위탁 × 해외 개별주식 × 250만 이하 차익 (공제로 세금 0)",
    cg_tax_4b, 0.0)

# 4c. 연간 누계로 250만 공제 적용 확인
executor4c = TaxedOrderExecutor(te, "위탁")
executor4c._calc_cg_tax("AAPL", 2_000_000)   # 먼저 200만
cg_tax_4c = executor4c._calc_cg_tax("AAPL", 1_000_000)   # 추가 100만
# 누계 300만 → 공제 250만 → 과세 50만 → 세금 11만
check("4c", "위탁 × 해외 개별주식 × 연간 누계 공제 적용",
    cg_tax_4c, 500_000 * 0.22)

# 5. 위탁 × 국내주식ETF × 배당 → 15.4%
check(5, "위탁 × 국내주식ETF × 배당 (15.4%)",
    te.after_tax_dividend(GROSS_DIV, "069500", "위탁"),
    GROSS_DIV * (1 - 0.154))

# 6. 위탁 × 국내주식ETF × 양도차익 → 비과세
executor6 = TaxedOrderExecutor(te, "위탁")
cg_tax_6 = executor6._calc_cg_tax("069500", GROSS_GAIN)
check(6, "위탁 × 국내주식ETF × 양도차익 (비과세)",
    cg_tax_6, 0.0)

# 7. 위탁 × 해외주식ETF (국내상장) × 배당 → 15.4%
# 360750 = TIGER 미국S&P500 (KR_FOREIGN)
check(7, "위탁 × 해외주식ETF(국내상장) × 배당 (15.4%)",
    te.after_tax_dividend(GROSS_DIV, "360750", "위탁"),
    GROSS_DIV * (1 - 0.154))

# 8. 위탁 × 해외주식ETF (국내상장) × 양도차익 → 15.4%
executor8 = TaxedOrderExecutor(te, "위탁")
cg_tax_8 = executor8._calc_cg_tax("360750", GROSS_GAIN)
check(8, "위탁 × 해외주식ETF(국내상장) × 양도차익 (15.4%)",
    cg_tax_8, GROSS_GAIN * 0.154)


# ============================================================
print("\n[ISA]")
# ============================================================

# 9~10. ISA × 국내 개별주식 × 배당/양도차익 → 운용 중 비과세
check(9, "ISA × 국내 개별주식 × 배당 (비과세)",
    te.after_tax_dividend(GROSS_DIV, "005930", "ISA"),
    GROSS_DIV)

check(10, "ISA × 국내 개별주식 × 양도차익 (비과세, 운용 중)",
    TaxedOrderExecutor(te, "ISA")._calc_cg_tax("005930", GROSS_GAIN),
    0.0)

# 11~12. 불가 케이스 (해외 개별주식)
print(f"  ── [11] ISA × 해외 개별주식 × 배당  → 불가 (구조상 투자 불가)")
print(f"  ── [12] ISA × 해외 개별주식 × 양도차익 → 불가")
results.extend([True, True])

# 13~14. ISA × 국내주식ETF
check(13, "ISA × 국내주식ETF × 배당 (비과세)",
    te.after_tax_dividend(GROSS_DIV, "069500", "ISA"),
    GROSS_DIV)

check(14, "ISA × 국내주식ETF × 양도차익 (비과세, 운용 중)",
    TaxedOrderExecutor(te, "ISA")._calc_cg_tax("069500", GROSS_GAIN),
    0.0)

# 15~16. ISA × 해외주식ETF
check(15, "ISA × 해외주식ETF × 배당 (비과세)",
    te.after_tax_dividend(GROSS_DIV, "360750", "ISA"),
    GROSS_DIV)

check(16, "ISA × 해외주식ETF × 양도차익 (비과세, 운용 중)",
    TaxedOrderExecutor(te, "ISA")._calc_cg_tax("360750", GROSS_GAIN),
    0.0)

# ISA 만기세 (일반형 200만 공제 후 9.9%)
end_val  = 30_000_000
contrib  = 20_000_000
net_gain = end_val - contrib   # 1,000만
exempt   = 2_000_000
taxable  = net_gain - exempt   # 800만
expected_isa_tax = taxable * 0.099
check("ISA만기", "ISA 만기세 (200만 공제 후 9.9%)",
    end_val - te.after_tax_withdrawal(end_val, "ISA", contrib),
    expected_isa_tax)

# ISA 중도해지 (배당소득세 15.4%)
check("ISA해지", "ISA 중도해지 (3년 미만 15.4%)",
    end_val - te.after_tax_withdrawal(end_val, "ISA", contrib, is_early_cancel=True),
    net_gain * 0.154)


# ============================================================
print("\n[연금저축 / IRP]")
# ============================================================

# 17~18. 연금저축 × 국내 개별주식
check(17, "연금저축 × 국내 개별주식 × 배당 (비과세, 과세이연)",
    te.after_tax_dividend(GROSS_DIV, "005930", "연금저축"),
    GROSS_DIV)

check(18, "연금저축 × 국내 개별주식 × 양도차익 (비과세, 과세이연)",
    TaxedOrderExecutor(te, "연금저축")._calc_cg_tax("005930", GROSS_GAIN),
    0.0)

# 19~20. 불가
print(f"  ── [19] 연금저축 × 해외 개별주식 × 배당  → 불가")
print(f"  ── [20] 연금저축 × 해외 개별주식 × 양도차익 → 불가")
results.extend([True, True])

# 21~22. 연금저축 × 국내주식ETF
check(21, "연금저축 × 국내주식ETF × 배당 (비과세)",
    te.after_tax_dividend(GROSS_DIV, "069500", "연금저축"),
    GROSS_DIV)

check(22, "연금저축 × 국내주식ETF × 양도차익 (비과세)",
    TaxedOrderExecutor(te, "연금저축")._calc_cg_tax("069500", GROSS_GAIN),
    0.0)

# 23~24. 연금저축 × 해외주식ETF
check(23, "연금저축 × 해외주식ETF × 배당 (비과세)",
    te.after_tax_dividend(GROSS_DIV, "360750", "연금저축"),
    GROSS_DIV)

check(24, "연금저축 × 해외주식ETF × 양도차익 (비과세)",
    TaxedOrderExecutor(te, "연금저축")._calc_cg_tax("360750", GROSS_GAIN),
    0.0)

# 수령세 (나이별)
check("연금60세", "연금저축 수령세 (60세 → 5.5%)",
    100_000_000 - te.after_tax_withdrawal(100_000_000, "연금저축", 50_000_000, age=60),
    100_000_000 * 0.055)

check("연금75세", "연금저축 수령세 (75세 → 4.4%)",
    100_000_000 - te.after_tax_withdrawal(100_000_000, "연금저축", 50_000_000, age=75),
    100_000_000 * 0.044)

check("연금80세", "연금저축 수령세 (80세 → 3.3%)",
    100_000_000 - te.after_tax_withdrawal(100_000_000, "연금저축", 50_000_000, age=80),
    100_000_000 * 0.033)


# ============================================================
print("\n[세액공제 환급액]")
# ============================================================

# 연금저축 600만 + IRP 300만 = 900만 → 16.5% → 148.5만
refund = te.annual_tax_deduction(6_000_000, 3_000_000)
check("세액공제1", "연금저축 600만 + IRP 300만 (16.5% → 148.5만)",
    refund, 9_000_000 * 0.165)

# 연금저축 600만 단독
refund2 = te.annual_tax_deduction(6_000_000, 0)
check("세액공제2", "연금저축 600만 단독 (16.5% → 99만)",
    refund2, 6_000_000 * 0.165)

# 고소득자 (5,500만 초과 → 13.2%)
te_high = TaxEngine({"earned_income": 80_000_000, "age": 40})
refund3 = te_high.annual_tax_deduction(6_000_000, 3_000_000)
check("세액공제3", "고소득자 900만 (13.2% → 118.8만)",
    refund3, 9_000_000 * 0.132)


# ============================================================
print("\n" + "=" * 60)
passed = sum(results)
total  = len(results)
print(f"결과: {passed}/{total} 통과")
if passed == total:
    print("🎉 모든 케이스 통과!")
else:
    print(f"⚠️  {total - passed}개 실패")
print("=" * 60)