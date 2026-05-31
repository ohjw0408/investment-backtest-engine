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
#   duration : 유효 듀레이션(년). 실측 회귀 중앙값으로 보정(stage_b_full_verify D).
#   model    : "duration" = 가격 -dur×Δy / "carry" = 가격 평평·수익은 이자(MMF·CD·초단기)
# 듀레이션 값은 stage_b_full_verify의 실측 유효듀레이션(연도별 회귀 중앙값)에 맞춤.
_BOND_ETF_CONFIG: dict[str, dict] = {
    # ── US 국채 (장/중기) — duration 모델 ──
    "TLT":  {"rate": "DGS30",  "duration": 17.0, "model": "duration"},  # 실측 17.1
    "VGLT": {"rate": "DGS30",  "duration": 16.0, "model": "duration"},  # 실측 16.0
    "SPTL": {"rate": "DGS30",  "duration": 16.0, "model": "duration"},  # 실측 16.1
    "IEF":  {"rate": "DGS10",  "duration": 7.5,  "model": "duration"},  # 실측 7.4
    "GOVT": {"rate": "DGS10",  "duration": 5.3,  "model": "duration"},  # 실측 5.3 (구 6.0)
    "AGG":  {"rate": "DGS10",  "duration": 4.4,  "model": "duration"},  # 실측 4.2 (구 6.0; 회사채/MBS 섞임)
    "BND":  {"rate": "DGS10",  "duration": 4.4,  "model": "duration"},  # 실측 4.4 (구 6.0)
    # ── US 초단기 — duration 작음(가격 거의 평평, 수익 carry 위주) ──
    "SHY":  {"rate": "DGS3MO", "duration": 0.8,  "model": "duration"},  # 실측 0.8 (구 1.9)
    "SCHO": {"rate": "DGS3MO", "duration": 0.8,  "model": "duration"},  # 실측 0.8
    # ── US T-bill(MMF 성격) — carry 모델(가격 평평, 수익=이자). 한국 CD/MMF 검증용 ──
    "BIL":  {"rate": "DGS3MO", "duration": 0.0,  "model": "carry"},
}

# 카테고리(meta.index) 기반 매핑 — 한국 채권 ETF는 index 필드가 이미 세분 카테고리라 코드별 대신
# 카테고리로 매핑(신규 ETF 자동 커버). duration은 실측 검증 후 보정 대상(초기 표준 추정).
#   FX/헤지는 backfill_engine의 meta(market/hedge)가 처리 — 한국상장 미국채는 ×환율 or 헤지.
_BOND_CATEGORY_CONFIG: dict[str, dict] = {
    # ── 한국 국고채 (KRW, 무FX) — 실측 유효듀레이션으로 통일 (운용사 일관: σ≤0.3) ──
    "KR_TREASURY_3Y":   {"rate": "KTB3Y",    "duration": 2.6,  "model": "duration"},  # 실측 2.50~3.01 중앙 2.54
    "KR_TREASURY_10Y":  {"rate": "KTB10Y",   "duration": 7.7,  "model": "duration"},  # 실측 7.42~8.08 중앙 7.68
    "KR_TREASURY_30Y":  {"rate": "KTB30Y",   "duration": 18.0, "model": "duration"},  # ⚠️ 흩어짐(순수17 vs 스트립/Enhanced 23~27) — 별도 검토
    "KR_BOND_AGGREGATE":{"rate": "KTB3Y",    "duration": 4.2,  "model": "duration"},  # 종합채권, 실측 3.63~4.89 중앙 4.17
    "KR_CORPORATE":     {"rate": "CORPAA3Y", "duration": 2.0,  "model": "duration"},  # 2.6→2.0 하향(만기형 실측 0.7~1.0 반영, CAGR차 축소). 상시형 실측 2.59
    # ── 한국 CD/KOFR/MMF/단기 — carry(가격 평평, 수익=이자) ──
    "KR_MONEY_MARKET":  {"rate": "CD91",     "duration": 0.0,  "model": "carry"},
    # ── 한국상장 미국채 (USD 금리 + FX/헤지는 meta가 처리) ──
    "US_TREASURY_30Y":  {"rate": "DGS30",    "duration": 17.0, "model": "duration"},
}

COUPON_FREQ_PER_YEAR = 12  # 채권 ETF는 보통 월 분배

# 스트립(무이표) 채권 = 듀레이션 ≈ 만기. 이표채 대비 길어 ETF명에 '스트립'/strip 있으면 듀레이션 가산.
STRIP_DURATION_MULT = 1.6

# 모델 쿠폰(현재 시장금리 기반)을 실측 분배(book yield = 보수 차감 + 평균 매입금리)에 맞추는 보정.
# stage_b_full_verify B: 국채 ETF 모델/실측 분배yield 비 ≈ 1.13~1.19 → 약 0.87.
COUPON_BOOK_FACTOR = 0.87

# 일일 가격수익 클리핑 (금리 데이터 이상치 방어)
_DAILY_RET_CLIP = 0.10


# ── 미국 채권 ETF 키워드 분류기 ─────────────────────────────
# us_etf_list category가 "US Fixed Income"으로 561종 뭉쳐 듀레이션 구분 불가 →
# ETF 영문명 키워드로 카테고리·듀레이션 추론(결정론적). 모델 불가 유형(HY/TIPS/Muni/MBS/
# 해외채)은 None=안전스킵(틀린 역사보다 없는 역사). rate는 index_master 코드.
#   국채: DGS30/DGS10/DGS3MO,  회사채 IG: DBAA(Moody's Baa, 장기).
_US_BOND_SKIP_KW = (
    "high yield", "high-yield", "junk",
    "tips", "inflation", "municipal", "muni", "tax-exempt", "tax exempt",
    "mortgage", "mbs", "convertible", "preferred", "senior loan", "bank loan",
    "emerging", "international", "global", "ex-u.s", "ex u.s", "world bond",
    "local currency",
)


def classify_us_bond_etf(name: str) -> dict | None:
    """미국 채권 ETF 영문명 → {rate, duration, model}. 모델 불가/미지면 None(안전스킵)."""
    n = name.lower()
    if any(k in n for k in _US_BOND_SKIP_KW):
        return None
    # 회사채(IG) — DBAA. 만기 키워드로 듀레이션 분기.
    if "corporate" in n or "investment grade" in n or "credit" in n:
        if any(k in n for k in ("short", "1-5", "1-3", "0-5")):
            dur = 2.7
        elif "long" in n:
            dur = 13.0
        elif "intermediate" in n or "5-10" in n:
            dur = 6.0
        else:
            dur = 8.0
        return {"rate": "DBAA", "duration": dur, "model": "duration"}
    # 국채 — 만기 버킷(긴 것부터). 단기(1-3/0-3 등)만 DGS3MO, 중기는 DGS10 듀레이션 차등.
    if "treasury" in n or "t-bill" in n or "tbill" in n or "t bill" in n:
        if any(k in n for k in ("20+", "25+", "long", "30 year", "30-year")):
            return {"rate": "DGS30", "duration": 17.0, "model": "duration"}
        if any(k in n for k in ("10-20", "10-25", "15+")):
            return {"rate": "DGS10", "duration": 9.0, "model": "duration"}
        if any(k in n for k in ("7-10", "10 year", "10-year", "intermediate")):
            return {"rate": "DGS10", "duration": 7.5, "model": "duration"}
        if any(k in n for k in ("3-7", "5-10", "5-7")):
            return {"rate": "DGS10", "duration": 4.5, "model": "duration"}
        if any(k in n for k in ("1-3", "0-3", "0-1", "short", "ultra",
                                "bill", "floating", "2 year", "2-year")):
            return {"rate": "DGS3MO", "duration": 1.0, "model": "duration"}
        return {"rate": "DGS10", "duration": 6.0, "model": "duration"}  # generic
    # 종합/토탈 본드
    if any(k in n for k in ("aggregate", "total bond", "core bond", "core total", "core u.s. bond")):
        return {"rate": "DGS10", "duration": 6.0, "model": "duration"}
    # 광범위 IG 본드펀드(국채+회사채 혼합, 예: Vanguard Short/Intermediate/Long-Term Bond) —
    # 금리 프록시 DGS10 + 만기별 듀레이션(AGG와 동일 처리, Grade C).
    if "bond" in n or "income" in n:
        if "short" in n:
            return {"rate": "DGS10", "duration": 2.7, "model": "duration"}
        if "long" in n:
            return {"rate": "DGS10", "duration": 13.0, "model": "duration"}
        return {"rate": "DGS10", "duration": 6.0, "model": "duration"}  # intermediate/generic
    return None


# ── 통화 가드 ───────────────────────────────────────────────
# 우리 엔진 FX/헤지는 USD/KRW만 모델링(DGS3MO−CD91). 비USD/비KRW 통화 노출 채권
# (엔화·유로·위안 등)은 라벨이 'US Treasury'로 맞아도 USD로 둔갑 백필되면 FX 틀림 →
# 이름에 외화 마커 있으면 채권백필 거부(안전스킵). 라벨 정확성과 무관한 엔진 한계 방어.
_FOREIGN_CCY_KW = (
    "엔화", "엔노출", "엔 노출", "엔(h)", "jpy", "yen",
    "유로", "eur", "euro", "위안", "위안화", "cny", "yuan", "파운드", "gbp",
)


def unsupported_currency(name: str) -> bool:
    """채권 ETF 이름에 비USD/KRW 통화 마커가 있으면 True(USD 백필 거부 대상)."""
    n = name.lower()
    return any(m in n for m in _FOREIGN_CCY_KW)


def bond_config(code: str, index_category: str | None = None,
                name: str | None = None, etf_type: str = "KR",
                us_category: str | None = None) -> dict | None:
    """채권 ETF면 {rate, duration, model} 반환, 아니면 None.

    우선순위: ETF 코드별 명시 매핑(US 수동) > index 카테고리 매핑(한국) >
    US 영문명 키워드 분류기(자동, category="US Fixed Income"일 때만). 셋 다 없으면 None.

    us_category로 게이트: 채권 카테고리 ETF만 이름 분류 → 주식 ETF명 오탐 방지.
    """
    if code in _BOND_ETF_CONFIG:
        return _BOND_ETF_CONFIG[code]
    if index_category and index_category in _BOND_CATEGORY_CONFIG:
        return _BOND_CATEGORY_CONFIG[index_category]
    if etf_type == "US" and name and us_category == "US Fixed Income":
        return classify_us_bond_etf(name)
    return None


def build_bond_price_series(yield_series: pd.Series, duration: float,
                            model: str = "duration",
                            hedge_cost_pct: pd.Series | None = None) -> pd.Series:
    """yield(%, 예: 4.27) 시계열 → 상대 price-return 지수(시작값 1.0).

    model="duration": 일일 가격수익 = -duration × Δyield(decimal). 캐리(이자)는 제외(쿠폰 분리).
    model="carry":    가격 평평(NAV ~ 일정). 모든 수익은 쿠폰(이자)으로 — MMF·CD·초단기.

    hedge_cost_pct: 환헤지 비용(연율 %, 예: 2.5) 시계열. 환헤지 ETF는 선물환 비용 =
        미-한 단기금리차(DGS3MO − CD91)만큼 수익이 깎인다(covered interest parity).
        일일 차감 = hedge_cost_pct/100/252. 금리 역전 시 음수 → 헤지 프리미엄(가산)으로 자동 처리.
        None이면 무적용. 해당 날짜 데이터 없으면(예: CD91 시작 1995 이전) 0으로 채워 무적용.
    반환 시계열은 _scale_to_etf로 ETF 상장가에 앵커링해 사용한다.
    """
    y = yield_series.dropna().sort_index().astype(float)
    if y.empty:
        return pd.Series(dtype=float)
    if model == "carry":
        return pd.Series(1.0, index=y.index, name="bond_price")
    dy = y.diff().fillna(0.0) / 100.0          # %p → decimal
    daily_ret = (-float(duration)) * dy
    if hedge_cost_pct is not None:
        hc = hedge_cost_pct.reindex(y.index).ffill().fillna(0.0) / 100.0 / 252.0
        daily_ret = daily_ret - hc
    daily_ret = daily_ret.clip(-_DAILY_RET_CLIP, _DAILY_RET_CLIP)
    price = (1.0 + daily_ret).cumprod()
    return price.rename("bond_price")
