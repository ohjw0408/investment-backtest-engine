"""
modules/tax/saving_estimate.py
절세액 표시 — "전체 위탁 가정 세금" 순수 추정 함수 (P1~P3 공통).

세제혜택계좌(ISA/연금/IRP)가 만약 일반 위탁계좌였다면 냈을 세금을, 계좌의
실제 세전 흐름(자산분류별 배당·실현차익)으로부터 역산한다. 실제 세금과의 차이가
절세액이다.

세율(위탁 기준, `order_executor.py`/`base_tax.py`와 일치):
  배당   KR_FOREIGN 15.4% · US_DIRECT 15% · KR_DOMESTIC/STOCK 15.4% · KRX_GOLD 0%
  양도   KR_FOREIGN 15.4%(손익통산 없음, 이익분만) · US_DIRECT 연 250만 공제 후 22%(손익통산)
         KR_DOMESTIC/STOCK 0% · KRX_GOLD 0%

종합과세 가산(금융소득 2천만 초과분)은 러프 단계에서 생략한다(UI 명시).
"""

from __future__ import annotations

# 배당소득세율 (자산분류별)
DIV_RATES = {
    "KR_FOREIGN": 0.154,
    "US_DIRECT": 0.15,
    "KR_DOMESTIC": 0.154,
    "STOCK": 0.154,
    "KRX_GOLD": 0.0,
}

KR_FOREIGN_CG_RATE = 0.154   # 국내상장 해외ETF 양도세 (손익통산 없음)
US_CG_RATE = 0.22            # 미국 직접상장 양도세 (지방세 포함)
US_CG_EXEMPT = 2_500_000     # 미국 직접상장 연 250만 기본공제


def _us_cg_tax(us_gain_by_year: dict[int, float]) -> float:
    """US_DIRECT 양도세 = Σ year max(0, gain − 250만) × 22% (연도별 공제)."""
    return sum(
        max(0.0, float(gain) - US_CG_EXEMPT) * US_CG_RATE
        for gain in (us_gain_by_year or {}).values()
    )


def estimate_gain_harvest_saving(
    us_gain_by_year: dict[int, float],
    harvested_total: float,
    final_year: int,
) -> float:
    """절세매도(GH) 자체로 아낀 세금 (위탁계좌 + GH ON 전용).

    GH 절세 = (GH 안 했으면 냈을 US 양도세) − (GH 하고 낸 US 양도세).
    GH는 매년 250만 공제를 소진하며 기준단가를 리셋한다. GH가 없었으면 그 차익이
    최종 청산 때 한꺼번에 실현(단일 250만 공제)됐을 것으로 근사한다.

    Args:
        us_gain_by_year : GH ON 기준 US 양도차익 연도별(harvest분 제외 = 기준리셋 후 잔여).
        harvested_total : GH로 실현·기준리셋한 누적차익(GH 없었으면 미실현으로 남았을 분).
        final_year      : 최종 청산 연도(harvest 안 했을 때 단일실현 가정 연도).
    """
    on_tax = _us_cg_tax(us_gain_by_year)
    off_by_year = dict(us_gain_by_year or {})
    off_by_year[final_year] = off_by_year.get(final_year, 0.0) + float(harvested_total)
    off_tax = _us_cg_tax(off_by_year)
    return max(0.0, off_tax - on_tax)


def estimate_brokerage_tax(
    gross_div_by_class: dict[str, float],
    kr_foreign_gain: float,
    us_gain_by_year: dict[int, float],
) -> float:
    """위탁 가정 세금 추정.

    Args:
        gross_div_by_class : 자산분류별 세전 배당 누계(전 기간).
        kr_foreign_gain    : KR_FOREIGN 실현+미실현 차익 누계(이익분만 과세).
        us_gain_by_year    : US_DIRECT 양도차익 연도별 누계(연 250만 공제 적용).

    Returns:
        추정 위탁 세금(원). 음수 불가.
    """
    div_tax = 0.0
    for cls, gross in (gross_div_by_class or {}).items():
        div_tax += max(0.0, float(gross)) * DIV_RATES.get(cls, 0.0)

    krf_tax = max(0.0, float(kr_foreign_gain)) * KR_FOREIGN_CG_RATE

    return div_tax + krf_tax + _us_cg_tax(us_gain_by_year)
