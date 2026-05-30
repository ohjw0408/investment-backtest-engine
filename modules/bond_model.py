# -*- coding: utf-8 -*-
"""
modules/bond_model.py
Stage B — 채권 듀레이션 가격 모델 + 쿠폰(이자) 분배금.

원칙 (Stage A와 동일): price-return 가격 + 명시적 분배금 분리.
- 가격: 금리 변화로부터 -듀레이션 × Δyield (캐리=이자 제외 → 쿠폰으로 분리, 이중계산 방지).
- 쿠폰: 해당 시점 yield를 월 분배금으로 명시 주입.

US 국채부터. 한국 국채/회사채/MMF는 _BOND_ETF_CONFIG에 rate 시계열 + 듀레이션(+스프레드)
행 추가로 확장한다 (코드 수정 없이 매핑 추가).
"""

import pandas as pd

# ETF별 명시 매핑 (etf_proxy_map 씨앗).
#   rate     : 금리 시계열 코드 (index_master.db index_daily, 단위 = %)
#   duration : 표준 듀레이션(년)
_BOND_ETF_CONFIG: dict[str, dict] = {
    # ── US 국채 ──
    "TLT":  {"rate": "DGS30",  "duration": 17.0},   # 20+yr
    "VGLT": {"rate": "DGS30",  "duration": 16.0},   # long
    "SPTL": {"rate": "DGS30",  "duration": 16.0},   # long
    "IEF":  {"rate": "DGS10",  "duration": 7.5},    # 7-10yr
    "GOVT": {"rate": "DGS10",  "duration": 6.0},    # broad treasury
    "AGG":  {"rate": "DGS10",  "duration": 6.0},    # aggregate (국채 근사)
    "BND":  {"rate": "DGS10",  "duration": 6.0},    # total bond (국채 근사)
    "SHY":  {"rate": "DGS3MO", "duration": 1.9},    # 1-3yr
    "SCHO": {"rate": "DGS3MO", "duration": 1.9},    # short
}

COUPON_FREQ_PER_YEAR = 12  # 채권 ETF는 보통 월 분배

# 일일 가격수익 클리핑 (금리 데이터 이상치 방어)
_DAILY_RET_CLIP = 0.10


def bond_config(code: str) -> dict | None:
    """채권 ETF면 {rate, duration} 반환, 아니면 None."""
    return _BOND_ETF_CONFIG.get(code)


def build_bond_price_series(yield_series: pd.Series, duration: float) -> pd.Series:
    """yield(%, 예: 4.27) 시계열 → 상대 price-return 지수(시작값 1.0).

    일일 가격수익 = -duration × Δyield(decimal). 캐리(이자)는 제외 — 쿠폰으로 분리.
    반환 시계열은 _scale_to_etf로 ETF 상장가에 앵커링해 사용한다.
    """
    y = yield_series.dropna().sort_index().astype(float)
    if y.empty:
        return pd.Series(dtype=float)
    dy = y.diff().fillna(0.0) / 100.0          # %p → decimal
    daily_ret = (-float(duration)) * dy
    daily_ret = daily_ret.clip(-_DAILY_RET_CLIP, _DAILY_RET_CLIP)
    price = (1.0 + daily_ret).cumprod()
    return price.rename("bond_price")
