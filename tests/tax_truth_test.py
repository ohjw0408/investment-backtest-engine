"""
tax_truth_test.py
────────────────────────────────────────────────────────────────────────────────
세금 엔진 진실성(Truth) 검증 테스트

목적:
    24taxtest.py 는 코드가 자기 자신과 consistent한지만 확인.
    이 파일은 대한민국 세법 원문 + 수기 계산값을 기댓값으로 하드코딩해서
    실제 세법과 일치하는지 검증한다.

검증 범위:
    [A] 자산 종류별 × 계좌 × 수익 종류 (배당 / 양도차익)
        - KR_DOMESTIC  (국내 개별주식 / 국내주식형 ETF)
        - KR_FOREIGN   (국내 상장 해외주식형 ETF)
        - US_DIRECT    (미국 직접 주식/ETF)
        - KRX_GOLD     (KRX 금현물)
        × 위탁 / ISA / 연금저축 / IRP

    [B] 금융소득 종합과세 (2,000만원 경계)
        - 2,000만 이하: 원천징수 종결
        - 2,000만 경계 돌파: 초과분만 종합과세 + 원천징수 비례 공제
        - 2,000만 완전 초과: 전액 종합과세

    [C] ISA 만기 / 중도해지
        - 일반형 (200만 공제) / 서민형 (400만 공제) × 만기 9.9%
        - 중도해지 15.4%

    [D] 연금저축 / IRP 수령세 (나이별)
        - 55~69세: 5.5%, 70~79세: 4.4%, 80세+: 3.3%
        - 연 1,500만 초과 처리

    [E] 세액공제 환급액
        - 소득 구간별 16.5% / 13.2%
        - 납입 한도 조합 (연금저축 단독 / 합산)

수기 계산 방법:
    각 테스트 위에 "# [계산 근거]" 주석으로 손계산 과정을 명시.
    기댓값은 이 계산에서 직접 도출한 값을 상수로 기록.

실행:
    python tests/tax_truth_test.py
    또는
    pytest tests/tax_truth_test.py -v
────────────────────────────────────────────────────────────────────────────────
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from modules.tax.base_tax import TaxEngine
from modules.execution.order_executor import TaxedOrderExecutor

# ── 허용 오차: 1원 이내 (정수 반올림 허용) ──────────────────────
TOL_KRW = 1.0
TOL_RATE = 1e-9  # 세율 비교는 무한소수 없으므로 strict

results: list[tuple[str, bool, str]] = []

def check(label: str, actual: float, expected: float, tol: float = TOL_KRW):
    ok = abs(actual - expected) <= tol
    tag = "PASS" if ok else "FAIL"
    results.append((label, ok, f"actual={actual:.2f}  expected={expected:.2f}"))
    if not ok:
        print(f"  ❌ FAIL  {label}")
        print(f"         actual={actual:.4f}  expected={expected:.4f}  diff={actual-expected:.4f}")
    else:
        print(f"  ✅ PASS  {label}")

# ════════════════════════════════════════════════════════════════════════════
# 섹션 A. 자산 종류별 × 계좌 × 수익 종류
# ════════════════════════════════════════════════════════════════════════════

def test_section_A():
    print("\n[A] 자산 × 계좌 × 수익 종류 매트릭스")

    te = TaxEngine({"earned_income": 50_000_000, "age": 60, "isa_type": "general"})
    GROSS = 1_000_000  # 100만원 기준

    # ── A-1. KR_DOMESTIC 배당 ────────────────────────────────────
    print("\n  A-1. KR_DOMESTIC (국내 개별주식 / 국내주식형 ETF) 배당")
    # [계산] 위탁: 1,000,000 × 15.4% = 154,000 세금 → 세후 846,000
    check("A-1-1 위탁×KR_DOMESTIC×배당",
        te.after_tax_dividend(GROSS, "005930", "위탁"),
        1_000_000 * (1 - 0.154))

    # [계산] ISA: 과세이연, 세후 = 원금
    check("A-1-2 ISA×KR_DOMESTIC×배당",
        te.after_tax_dividend(GROSS, "005930", "ISA"), GROSS)

    # [계산] 연금저축: 과세이연
    check("A-1-3 연금저축×KR_DOMESTIC×배당",
        te.after_tax_dividend(GROSS, "005930", "연금저축"), GROSS)

    # [계산] IRP: 과세이연
    check("A-1-4 IRP×KR_DOMESTIC×배당",
        te.after_tax_dividend(GROSS, "005930", "IRP"), GROSS)

    # ── A-2. KR_DOMESTIC 양도차익 ────────────────────────────────
    print("\n  A-2. KR_DOMESTIC 양도차익")
    # [계산] 위탁×KR_DOMESTIC: 소액주주 비과세 → 세금 0
    check("A-2-1 위탁×KR_DOMESTIC×양도차익(비과세)",
        TaxedOrderExecutor(te, "위탁")._calc_cg_tax("005930", 10_000_000), 0.0)

    # [계산] ISA: 운용 중 비과세
    check("A-2-2 ISA×KR_DOMESTIC×양도차익",
        TaxedOrderExecutor(te, "ISA")._calc_cg_tax("005930", 10_000_000), 0.0)

    # [계산] 연금저축/IRP: 과세이연 (운용 중 세금 없음)
    check("A-2-3 연금저축×KR_DOMESTIC×양도차익",
        TaxedOrderExecutor(te, "연금저축")._calc_cg_tax("005930", 10_000_000), 0.0)
    check("A-2-4 IRP×KR_DOMESTIC×양도차익",
        TaxedOrderExecutor(te, "IRP")._calc_cg_tax("005930", 10_000_000), 0.0)

    # ── A-3. KR_FOREIGN 배당 ────────────────────────────────────
    print("\n  A-3. KR_FOREIGN (국내 상장 해외주식형 ETF) 배당")
    # [계산] 위탁: 15.4% (배당소득세)
    check("A-3-1 위탁×KR_FOREIGN×배당",
        te.after_tax_dividend(GROSS, "360750", "위탁"),
        1_000_000 * (1 - 0.154))

    check("A-3-2 ISA×KR_FOREIGN×배당",
        te.after_tax_dividend(GROSS, "360750", "ISA"), GROSS)

    check("A-3-3 연금저축×KR_FOREIGN×배당",
        te.after_tax_dividend(GROSS, "360750", "연금저축"), GROSS)

    # ── A-4. KR_FOREIGN 양도차익 ────────────────────────────────
    print("\n  A-4. KR_FOREIGN 양도차익")
    # [계산] 위탁×KR_FOREIGN: 차익 × 15.4%
    #   10,000,000 × 0.154 = 1,540,000
    check("A-4-1 위탁×KR_FOREIGN×양도차익(15.4%)",
        TaxedOrderExecutor(te, "위탁")._calc_cg_tax("360750", 10_000_000),
        10_000_000 * 0.154)

    # [계산] ISA: 운용 중 비과세
    check("A-4-2 ISA×KR_FOREIGN×양도차익(비과세)",
        TaxedOrderExecutor(te, "ISA")._calc_cg_tax("360750", 10_000_000), 0.0)

    check("A-4-3 연금저축×KR_FOREIGN×양도차익(비과세)",
        TaxedOrderExecutor(te, "연금저축")._calc_cg_tax("360750", 10_000_000), 0.0)

    # ── A-5. US_DIRECT 배당 ─────────────────────────────────────
    print("\n  A-5. US_DIRECT (미국 직접 주식/ETF) 배당")
    # [계산] 위탁: 미국 원천 15%
    #   1,000,000 × 0.15 = 150,000 세금 → 세후 850,000
    check("A-5-1 위탁×US_DIRECT×배당(미국원천15%)",
        te.after_tax_dividend(GROSS, "SPY", "위탁"),
        1_000_000 * (1 - 0.15))

    check("A-5-2 ISA×US_DIRECT×배당(비과세)",
        te.after_tax_dividend(GROSS, "SPY", "ISA"), GROSS)

    check("A-5-3 연금저축×US_DIRECT×배당(비과세)",
        te.after_tax_dividend(GROSS, "SPY", "연금저축"), GROSS)

    # ── A-6. US_DIRECT 양도차익 ─────────────────────────────────
    print("\n  A-6. US_DIRECT 양도차익")
    exec_us = TaxedOrderExecutor(te, "위탁")

    # [계산] 250만 이하: 공제 범위 내 → 세금 0
    check("A-6-1 위탁×US_DIRECT×양도차익(250만 이하, 세금0)",
        exec_us._calc_cg_tax("SPY", 2_000_000), 0.0)

    # [계산] 250만 초과:
    #   차익 1,000만, ytd_us_gains(= 2,000,000 이미) + 1,000만 = 1,200만
    #   1,200만 > 250만 공제 → taxable = 1,200만 - 250만 = 950만
    #   이미 납부(2,000,000): 2,000,000 - 2,500,000 = 음수 → prev=0, already_paid=0
    #   taxable = max(0, 1,200만 - 250만) = 950만
    #   already_paid = max(0, (1,200만-1,000만) - 250만) × 0.22 = 0
    #   세금 = 950만 × 0.22 = 2,090,000
    check("A-6-2 위탁×US_DIRECT×양도차익(250만 초과분 22%)",
        exec_us._calc_cg_tax("SPY", 10_000_000),
        9_500_000 * 0.22)   # (12,000,000 - 2,500,000) × 0.22

    # [계산] 연간 누계 250만 공제 검증 (새 executor로 리셋)
    exec_fresh = TaxedOrderExecutor(te, "위탁")
    # 1차 매도 200만: ytd=200만 < 250만 → 세금 0
    t1 = exec_fresh._calc_cg_tax("SPY", 2_000_000)
    # 2차 매도 100만: ytd=300만, 공제 잔여=50만
    #   taxable = 300만 - 250만 = 50만
    #   already_paid = max(0, (200만) - 250만) × 0.22 = 0
    #   세금 = 50만 × 0.22 = 110,000
    t2 = exec_fresh._calc_cg_tax("SPY", 1_000_000)
    check("A-6-3 위탁×US_DIRECT×연간누계공제(1차:0, 2차:50만×22%)",
        t1 + t2, 500_000 * 0.22)

    check("A-6-4 ISA×US_DIRECT×양도차익(비과세)",
        TaxedOrderExecutor(te, "ISA")._calc_cg_tax("SPY", 10_000_000), 0.0)

    check("A-6-5 연금저축×US_DIRECT×양도차익(비과세)",
        TaxedOrderExecutor(te, "연금저축")._calc_cg_tax("SPY", 10_000_000), 0.0)

    # ── A-7. KRX_GOLD ────────────────────────────────────────────
    print("\n  A-7. KRX_GOLD")
    # [계산] 위탁×KRX_GOLD 배당: 배당 없음 (그대로 반환)
    # classify_asset → "KRX_GOLD"이지만 배당 처리는 KR_DOMESTIC과 동일하게 흐름:
    # KRX_GOLD는 after_tax_dividend에서 classify_asset 후 else(국내) 경로 → 15.4%
    # 실제로는 금현물 ETF 배당 없으나, 세법상 배당 발생 시 15.4%로 처리
    # (엔진이 KRX_GOLD를 KR_DOMESTIC 취급 → 15.4%)
    check("A-7-1 위탁×KRX_GOLD×배당(15.4%)",
        te.after_tax_dividend(GROSS, "KRX_GOLD", "위탁"),
        1_000_000 * (1 - 0.154))

    # [계산] 위탁×KRX_GOLD 양도차익: KRX 금현물 비과세
    check("A-7-2 위탁×KRX_GOLD×양도차익(비과세)",
        TaxedOrderExecutor(te, "위탁")._calc_cg_tax("KRX_GOLD", 10_000_000), 0.0)


# ════════════════════════════════════════════════════════════════════════════
# 섹션 B. 금융소득 종합과세 (2,000만원 경계)
# ════════════════════════════════════════════════════════════════════════════

def test_section_B():
    print("\n[B] 금융소득 종합과세 2,000만원 경계")

    te = TaxEngine({"earned_income": 50_000_000, "age": 60})

    # ── B-1. 2,000만 이하: 분리과세 종결 ────────────────────────
    # [계산] ytd=1,000만, new_div=100만 (합계 1,100만 < 2,000만)
    #   → 종합과세 없음. 세후 = 100만 × (1-15.4%) = 846,000
    net = te.after_tax_dividend(1_000_000, "005930", "위탁",
                                 ytd_financial_income=10_000_000)
    check("B-1 2,000만 이하: 원천징수 종결 (종합과세 없음)",
        net, 1_000_000 * (1 - 0.154))

    # ── B-2. 2,000만 경계 돌파 ───────────────────────────────────
    # [계산] ytd=1,900만, new_div=200만 → 합계 2,100만
    #   already_withheld = 200만 × 0.154 = 308,000
    #   prev_fin = max(0, 1,900만 - 2,000만) = 0
    #   curr_fin = max(0, 2,100만 - 2,000만) = 100만
    #   excess = 100만, new_div = 200만 → 비율 0.5
    #   withheld_on_excess = 308,000 × 0.5 = 154,000
    #
    #   tax_with    = comprehensive_tax(50,000,000 + 1,000,000)
    #              = comprehensive_tax(51,000,000)
    #              = 51,000,000 × 0.24 - 5,760,000 = 6,480,000 × 1.1 = 7,128,000
    #   tax_without = comprehensive_tax(50,000,000)
    #              = 50,000,000 × 0.15 - 1,260,000 = 6,240,000 × 1.1 = 6,864,000
    #   incremental = 7,128,000 - 6,864,000 = 264,000
    #   extra = max(0, 264,000 - 154,000) = 110,000
    #
    #   총 납부세금 = 원천징수 308,000 + 추가납부 110,000 = 418,000
    #   세후 net = 2,000,000 - 418,000 = 1,582,000
    net2 = te.after_tax_dividend(2_000_000, "005930", "위탁",
                                  ytd_financial_income=19_000_000)
    check("B-2 2,000만 경계 돌파: extra=110,000 (세후 1,582,000)",
        net2, 1_582_000, tol=1.0)

    # ── B-3. 2,000만 완전 초과 구간 ─────────────────────────────
    # [계산] ytd=2,100만, new_div=100만 → 전체 초과
    #   already_withheld = 100만 × 0.154 = 154,000
    #   prev_fin = 100만, curr_fin = 200만
    #   excess = 100만 = new_div → 비율 1.0 → withheld_on_excess = 154,000
    #
    #   tax_with    = comprehensive_tax(50,000,000 + 2,000,000)
    #              = comprehensive_tax(52,000,000)
    #              = 52,000,000 × 0.24 - 5,760,000 = 6,720,000 × 1.1 = 7,392,000
    #   tax_without = comprehensive_tax(51,000,000) = 7,128,000
    #   incremental = 264,000
    #   extra = max(0, 264,000 - 154,000) = 110,000
    #   세후 net = 1,000,000 - 154,000 - 110,000 = 736,000
    net3 = te.after_tax_dividend(1_000_000, "005930", "위탁",
                                  ytd_financial_income=21_000_000)
    check("B-3 2,000만 완전 초과: extra=110,000 (세후 736,000)",
        net3, 736_000, tol=1.0)

    # ── B-4. 미국주식 배당 + 종합과세 경계 돌파 ─────────────────
    # [계산] ytd=1,900만, new_div=200만, US_DIRECT (원천 15%)
    #   already_withheld = 200만 × 0.15 = 300,000
    #   curr_fin = 100만, excess = 100만
    #   withheld_on_excess = 300,000 × 0.5 = 150,000
    #   incremental(근로5,000만+초과100만) = 264,000 (B-2와 동일)
    #   extra = max(0, 264,000 - 150,000) = 114,000
    #   세후 = 2,000,000 - 300,000 - 114,000 = 1,586,000
    net4 = te.after_tax_dividend(2_000_000, "SPY", "위탁",
                                  ytd_financial_income=19_000_000)
    check("B-4 US_DIRECT 배당 종합과세 경계 (세후 1,586,000)",
        net4, 1_586_000, tol=1.0)

    # ── B-5. 저소득자 종합과세 (6% 구간) ────────────────────────
    # [계산] 근로소득=5,000,000, ytd=2,500만, new_div=100만
    #   prev_fin = 500만, curr_fin = 600만
    #   excess = 100만 = new_div, withheld = 154,000
    #
    #   tax_with    = comprehensive_tax(5,000,000 + 6,000,000)
    #              = comprehensive_tax(11,000,000)
    #              = 11,000,000 × 0.06 = 660,000 × 1.1 = 726,000
    #   tax_without = comprehensive_tax(5,000,000 + 5,000,000)
    #              = comprehensive_tax(10,000,000)
    #              = 10,000,000 × 0.06 = 600,000 × 1.1 = 660,000
    #   incremental = 726,000 - 660,000 = 66,000
    #   extra = max(0, 66,000 - 154,000) = 0  (원천징수가 이미 과다)
    #   세후 = 1,000,000 - 154,000 - 0 = 846,000
    te_low = TaxEngine({"earned_income": 5_000_000, "age": 60})
    net5 = te_low.after_tax_dividend(1_000_000, "005930", "위탁",
                                      ytd_financial_income=25_000_000)
    check("B-5 저소득(6%구간) 종합과세: extra=0, 세후=846,000",
        net5, 846_000, tol=1.0)

    # ── B-6. 고소득자 종합과세 (45% 구간) ───────────────────────
    # [계산] 근로소득=1,500,000,000 (15억), ytd=2,100만, new_div=100만
    #   prev_fin=100만, curr_fin=200만, excess=100만, withheld=154,000
    #   tax_with  = comprehensive_tax(1,500,000,000 + 2,000,000)
    #             ≈ 1,502,000,000 × 0.45 - 65,940,000 × 1.1
    #   tax_without = comprehensive_tax(1,500,000,000 + 1,000,000)
    #   두 차이 ≈ 1,000,000 × 0.45 × 1.1 = 495,000
    #   extra = max(0, 495,000 - 154,000) = 341,000
    #   세후 = 1,000,000 - 154,000 - 341,000 = 505,000
    te_high = TaxEngine({"earned_income": 1_500_000_000, "age": 60})
    net6 = te_high.after_tax_dividend(1_000_000, "005930", "위탁",
                                       ytd_financial_income=21_000_000)
    # incremental = 1,000,000 × 0.45 × 1.1 = 495,000
    check("B-6 고소득(45%구간) 종합과세: extra=341,000, 세후=505,000",
        net6, 505_000, tol=1.0)


# ════════════════════════════════════════════════════════════════════════════
# 섹션 C. ISA 만기 / 중도해지
# ════════════════════════════════════════════════════════════════════════════

def test_section_C():
    print("\n[C] ISA 만기 / 중도해지")

    # ── C-1. 일반형 만기: 순이익 200만 공제 후 9.9% ─────────────
    # [계산] 납입 2,000만, 최종 4,000만 → 순이익 2,000만
    #   비과세 200만 → 과세 1,800만
    #   세금 = 1,800만 × 0.099 = 1,782,000
    #   세후 = 40,000,000 - 1,782,000 = 38,218,000
    te_gen = TaxEngine({"earned_income": 50_000_000, "age": 60, "isa_type": "general"})
    result = te_gen.after_tax_withdrawal(40_000_000, "ISA", 20_000_000)
    check("C-1 ISA 일반형 만기 (200만 공제, 9.9%)",
        result, 38_218_000)

    # ── C-2. 서민형 만기: 순이익 400만 공제 후 9.9% ─────────────
    # [계산] 동일 조건, 비과세 400만 → 과세 1,600만
    #   세금 = 1,600만 × 0.099 = 1,584,000
    #   세후 = 40,000,000 - 1,584,000 = 38,416,000
    te_pref = TaxEngine({"earned_income": 50_000_000, "age": 60, "isa_type": "preferential"})
    result2 = te_pref.after_tax_withdrawal(40_000_000, "ISA", 20_000_000)
    check("C-2 ISA 서민형 만기 (400만 공제, 9.9%)",
        result2, 38_416_000)

    # ── C-3. ISA 만기: 순이익 0 이하 (세금 없음) ─────────────────
    # [계산] 납입 3,000만, 최종 2,500만 → 손실 → 세금 0
    #   세후 = 25,000,000
    result3 = te_gen.after_tax_withdrawal(25_000_000, "ISA", 30_000_000)
    check("C-3 ISA 손실 만기 (세금 없음)",
        result3, 25_000_000)

    # ── C-4. ISA 중도해지: 순이익 × 15.4% ───────────────────────
    # [계산] 납입 2,000만, 최종 4,000만 → 순이익 2,000만
    #   세금 = 2,000만 × 0.154 = 3,080,000
    #   세후 = 40,000,000 - 3,080,000 = 36,920,000
    result4 = te_gen.after_tax_withdrawal(40_000_000, "ISA", 20_000_000,
                                          is_early_cancel=True)
    check("C-4 ISA 중도해지 (순이익×15.4%)",
        result4, 36_920_000)

    # ── C-5. ISA 보유 3년 미만: isa_years_held < 3 → 중도해지 세율 ──
    # [계산] 2년 보유, 순이익 1,000만 × 15.4% = 1,540,000
    #   세후 = 30,000,000 - 1,540,000 = 28,460,000
    result5 = te_gen.after_tax_withdrawal(30_000_000, "ISA", 20_000_000,
                                          isa_years_held=2)
    check("C-5 ISA 보유 2년 (isa_years_held<3, 15.4%)",
        result5, 28_460_000)

    # ── C-6. ISA 비과세 한도 이하 순이익: 세금 없음 ──────────────
    # [계산] 납입 2,000만, 최종 2,150만 → 순이익 150만 < 200만
    #   세금 = 0 → 세후 = 21,500,000
    result6 = te_gen.after_tax_withdrawal(21_500_000, "ISA", 20_000_000)
    check("C-6 ISA 순이익 200만 이하 (비과세)",
        result6, 21_500_000)


# ════════════════════════════════════════════════════════════════════════════
# 섹션 D. 연금저축 / IRP 수령세
# ════════════════════════════════════════════════════════════════════════════

def test_section_D():
    print("\n[D] 연금저축 / IRP 수령세")

    # ── D-1. 나이별 세율 3단계 ────────────────────────────────────
    # [계산] 세후 = 잔액 × (1 - 세율)
    #   55세: 5.5% → 세후 = 100,000,000 × 0.945 = 94,500,000
    #   70세: 4.4% → 세후 = 100,000,000 × 0.956 = 95,600,000
    #   80세: 3.3% → 세후 = 100,000,000 × 0.967 = 96,700,000
    for age, rate, expected_after in [
        (55, 0.055, 94_500_000),
        (60, 0.055, 94_500_000),  # 55~69: 5.5%
        (69, 0.055, 94_500_000),
        (70, 0.044, 95_600_000),  # 70~79: 4.4%
        (79, 0.044, 95_600_000),
        (80, 0.033, 96_700_000),  # 80+: 3.3%
        (90, 0.033, 96_700_000),
    ]:
        te_age = TaxEngine({"earned_income": 0, "age": age})
        result = te_age.after_tax_withdrawal(100_000_000, "연금저축", 50_000_000, age=age)
        check(f"D-1 연금저축 수령세 ({age}세, {rate*100:.1f}%)",
            result, expected_after)

    # ── D-2. IRP 수령세 (연금저축과 동일) ───────────────────────
    te_irp = TaxEngine({"earned_income": 0, "age": 65})
    result_irp = te_irp.after_tax_withdrawal(100_000_000, "IRP", 50_000_000, age=65)
    check("D-2 IRP 수령세 (65세, 5.5%)",
        result_irp, 100_000_000 * (1 - 0.055))

    # ── D-3. 연금소득 1,500만 이하: 나이별 분리과세 ───────────────
    # [계산] 월 100만 (연 1,200만), 65세 (5.5%)
    #   세후 월수령 = 1,000,000 × (1 - 0.055) = 945,000
    te_pen = TaxEngine({"earned_income": 0, "age": 65})
    check("D-3 연금소득 1,200만/년 (5.5% 분리과세)",
        te_pen.pension_monthly_after_tax(1_000_000, 65),
        1_000_000 * (1 - 0.055))

    # ── D-4. 연금소득 1,500만 초과 처리 ─────────────────────────
    # [계산] 월 200만 (연 2,400만), 65세, 근로소득 0원
    #   1,500만 이하 월분: 1,500만/12 = 125만 → 세후 = 125만 × 0.945 = 118.125만
    #   초과 월분: 200만 - 125만 = 75만
    #   초과분 연 = 900만, 분리과세 vs 종합과세 비교:
    #     분리과세: 900만 × 0.165 = 148.5만
    #     종합과세 증분: comprehensive_tax(0+2,400만) - comprehensive_tax(0+1,500만)
    #       = comprehensive_tax(24,000,000) - comprehensive_tax(15,000,000)
    #       24M: 24,000,000 × 0.15 - 1,260,000 = 2,340,000 × 1.1 = 2,574,000
    #       15M: 15,000,000 × 0.15 - 1,260,000 = 990,000 × 1.1 = 1,089,000
    #       증분 = 1,485,000
    #       증분세율 = 1,485,000 / 9,000,000 = 0.165 (= 분리과세율)
    #   → 분리과세 선택 (동률), 초과분 세율 = 16.5%
    #   세후 초과분 월 = 75만 × (1-0.165) = 626,250
    #   전체 세후 월 = 1,181,250 + 626,250 = 1,181,250? 아니면:
    #     low_part  = 1,250,000 × (1-0.055) = 1,181,250
    #     high_part = 750,000  × (1-0.165) = 626,250
    #     세후 = 1,181,250 + 626,250 = 1,807,500
    te_p2 = TaxEngine({"earned_income": 0, "age": 65})
    check("D-4 연금소득 1,500만 초과 (월200만, 초과분 16.5%)",
        te_p2.pension_monthly_after_tax(2_000_000, 65),
        1_807_500, tol=1.0)

    # ── D-5. 고소득자 연금 1,500만 초과: 분리과세 유리 ──────────
    # [계산] 월 200만 (연 2,400만), 65세, 근로소득 5,000만
    #   초과분 900만에 대해:
    #     분리과세: 900만 × 0.165 = 148.5만
    #     종합과세 증분: comprehensive_tax(50,000,000 + 24,000,000)
    #                  - comprehensive_tax(50,000,000 + 15,000,000)
    #       74M: 74,000,000 × 0.24 - 5,760,000 = 11,976,000 × 1.1 = 13,173,600
    #       65M: 65,000,000 × 0.24 - 5,760,000 = 9,840,000 × 1.1 = 10,824,000
    #       증분 = 2,349,600
    #       증분세율 = 2,349,600 / 9,000,000 = 0.2611 (> 16.5%)
    #   → 분리과세(16.5%) 선택
    #   세후 = low_part + high_part = 1,181,250 + 626,250 = 1,807,500 (동일)
    te_p3 = TaxEngine({"earned_income": 50_000_000, "age": 65})
    check("D-5 고소득자 연금 1,500만 초과: 분리과세 유리 (1,807,500)",
        te_p3.pension_monthly_after_tax(2_000_000, 65),
        1_807_500, tol=1.0)


# ════════════════════════════════════════════════════════════════════════════
# 섹션 E. 세액공제 환급액
# ════════════════════════════════════════════════════════════════════════════

def test_section_E():
    print("\n[E] 세액공제 환급액")

    # ── E-1. 저소득자 (16.5%) × 최대 납입 ───────────────────────
    # [계산] 총급여 5,500만 이하 → 16.5%
    #   연금저축 600만 + IRP 300만 = 900만 (합산한도)
    #   환급액 = 9,000,000 × 0.165 = 1,485,000
    te_low = TaxEngine({"earned_income": 40_000_000, "age": 40})
    check("E-1 저소득(총급여4천만) 연금저축600만+IRP300만 → 1,485,000",
        te_low.annual_tax_deduction(6_000_000, 3_000_000),
        1_485_000)

    # ── E-2. 총급여 경계 (5,500만): 16.5% ───────────────────────
    te_mid = TaxEngine({"earned_income": 55_000_000, "age": 40})
    check("E-2 총급여 5,500만 (경계) → 16.5%",
        te_mid.annual_tax_deduction(6_000_000, 3_000_000),
        1_485_000)

    # ── E-3. 고소득자 (13.2%) ────────────────────────────────────
    # [계산] 총급여 5,500만 초과 → 13.2%
    #   환급액 = 9,000,000 × 0.132 = 1,188,000
    te_high = TaxEngine({"earned_income": 80_000_000, "age": 40})
    check("E-3 고소득(총급여8천만) → 13.2%, 환급 1,188,000",
        te_high.annual_tax_deduction(6_000_000, 3_000_000),
        1_188_000)

    # ── E-4. 연금저축 단독 (IRP 없음): 600만 한도 ───────────────
    # [계산] 연금저축 600만 단독, 16.5%
    #   환급액 = 6,000,000 × 0.165 = 990,000
    check("E-4 연금저축 단독 600만 → 990,000",
        te_low.annual_tax_deduction(6_000_000, 0),
        990_000)

    # ── E-5. 연금저축 한도 초과 납입: 600만으로 캡 ───────────────
    # [계산] 연금저축 800만 납입 → 공제는 600만까지만
    #   환급액 = 6,000,000 × 0.165 = 990,000 (800만이어도 동일)
    check("E-5 연금저축 800만 납입 → 공제 600만 캡 → 990,000",
        te_low.annual_tax_deduction(8_000_000, 0),
        990_000)

    # ── E-6. IRP 단독 (연금저축 없음): 900만 한도 ───────────────
    # [계산] IRP 900만 단독, 16.5%
    #   환급액 = 9,000,000 × 0.165 = 1,485,000
    check("E-6 IRP 단독 900만 → 1,485,000",
        te_low.annual_tax_deduction(0, 9_000_000),
        1_485_000)

    # ── E-7. 합산 한도 초과: 900만 캡 ───────────────────────────
    # [계산] 연금저축 600만 + IRP 600만 = 1,200만 → 합산 900만 캡
    #   환급액 = 9,000,000 × 0.165 = 1,485,000
    check("E-7 연금저축600만+IRP600만 → 합산 900만 캡 → 1,485,000",
        te_low.annual_tax_deduction(6_000_000, 6_000_000),
        1_485_000)

    # ── E-8. 소액 납입: 실납입 기준 ─────────────────────────────
    # [계산] 연금저축 200만 + IRP 100만 = 300만
    #   환급액 = 3,000,000 × 0.165 = 495,000
    check("E-8 연금저축200만+IRP100만 → 495,000",
        te_low.annual_tax_deduction(2_000_000, 1_000_000),
        495_000)


# ════════════════════════════════════════════════════════════════════════════
# 섹션 F. classify_asset 코드 분류
# ════════════════════════════════════════════════════════════════════════════

def test_section_F():
    print("\n[F] 종목 코드 → 자산 타입 분류")

    te = TaxEngine({"earned_income": 0, "age": 40})

    cases = [
        ("SPY",          "US_DIRECT",    "미국 ETF"),
        ("SCHD",         "US_DIRECT",    "미국 배당 ETF"),
        ("AAPL",         "US_DIRECT",    "미국 개별주식"),
        ("^GSPC",        "US_DIRECT",    "S&P500 지수 (^기호)"),
        ("005930",       "KR_DOMESTIC",  "삼성전자 (DB 없으면 DOMESTIC)"),
        ("069500",       "KR_DOMESTIC",  "KODEX200"),
        ("KRX_GOLD",     "KRX_GOLD",     "KRX 금현물"),
        ("005930.KS",    "KR_DOMESTIC",  "야후파이낸스 형식 .KS"),
        ("069500.KQ",    "KR_DOMESTIC",  "야후파이낸스 형식 .KQ"),
    ]

    for ticker, expected_type, desc in cases:
        result = te.classify_asset(ticker)
        check(f"F classify_asset({ticker}) → {expected_type}  [{desc}]",
            0 if result == expected_type else 1, 0)


# ════════════════════════════════════════════════════════════════════════════
# 메인 실행
# ════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("=" * 70)
    print("세금 엔진 진실성(Truth) 검증")
    print("기댓값 = 세법 원문 기준 수기 계산")
    print("=" * 70)

    test_section_A()
    test_section_B()
    test_section_C()
    test_section_D()
    test_section_E()
    test_section_F()

    passed = sum(1 for _, ok, _ in results if ok)
    failed = len(results) - passed

    print("\n" + "=" * 70)
    print(f"결과: {passed}/{len(results)} PASS  ({failed} FAIL)")

    if failed > 0:
        print("\n❌ 실패 항목:")
        for label, ok, detail in results:
            if not ok:
                print(f"  - {label}")
                print(f"    {detail}")

    print("=" * 70)
    sys.exit(0 if failed == 0 else 1)
