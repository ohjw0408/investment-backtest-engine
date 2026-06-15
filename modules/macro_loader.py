# -*- coding: utf-8 -*-
"""
거시경제 지표 수집·저장 (FRED 공식 API + 한국은행 ECOS) → index_master.db.

- 미국: FRED `series/observations` (키 data/meta/fred_api_key.txt).
- 한국: ECOS `StatisticSearch` (키 data/meta/ecos_api_key.txt).
- 저장: macro_series(메타) + macro_observations(시계열). 둘 다 신규 테이블.

SERIES 레지스트리 = 단일 진실 원천. 신규 지표 추가 = 여기 dict 한 줄.
실행: python -m modules.macro_loader [--validate | --backfill [CODE ...]]
"""
import os
import sys
import time
import sqlite3
from pathlib import Path

import requests

BASE = Path(__file__).resolve().parent.parent
INDEX_DB = BASE / "data" / "meta" / "index_master.db"
FRED_KEY_FILE = BASE / "data" / "meta" / "fred_api_key.txt"
ECOS_KEY_FILE = BASE / "data" / "meta" / "ecos_api_key.txt"

CATEGORIES = ["주가지수", "금리", "인플레이션", "고용", "통화·유동성", "신용·리스크", "경기·성장", "시장·환율"]


def _fred(sid, freq, cat, name, unit, country="US"):
    return {"code": f"US_{sid}", "src": "fred", "sid": sid, "freq": freq,
            "category": cat, "name_ko": name, "unit": unit, "country": country}


def _ecos(code, stat, cyc, items, cat, name, unit):
    """items = [ITEM1] 또는 [ITEM1, ITEM2] (2차원 통계표)."""
    return {"code": f"KR_{code}", "src": "ecos", "stat": stat, "cyc": cyc,
            "items": items, "freq": cyc, "category": cat, "name_ko": name,
            "unit": unit, "country": "KR"}


def _yf(code, yfsym, country, name):
    """yfinance 시장 지수. country=US/KR/GL."""
    return {"code": f"IDX_{code}", "src": "yf", "yf": yfsym, "freq": "D",
            "category": "주가지수", "name_ko": name, "unit": "지수", "country": country}


# ── 지표 레지스트리 (오너 승인 2026-06-15, 코드 실호출 검증) ──────────────
SERIES = [
    # 미국 금리·통화정책
    _fred("FEDFUNDS", "M", "금리", "미 연방기금 실효금리", "%"),
    _fred("DFEDTARU", "D", "금리", "미 기준금리 목표 상단", "%"),
    _fred("DFEDTARL", "D", "금리", "미 기준금리 목표 하단", "%"),
    _fred("SOFR", "D", "금리", "SOFR(담보부 익일물)", "%"),
    _fred("EFFR", "D", "금리", "미 실효 연방기금금리(일별)", "%"),
    _fred("DGS1MO", "D", "금리", "미 국채 1개월", "%"),
    _fred("DGS3MO", "D", "금리", "미 국채 3개월", "%"),
    _fred("DGS6MO", "D", "금리", "미 국채 6개월", "%"),
    _fred("DGS1", "D", "금리", "미 국채 1년", "%"),
    _fred("DGS2", "D", "금리", "미 국채 2년", "%"),
    _fred("DGS3", "D", "금리", "미 국채 3년", "%"),
    _fred("DGS5", "D", "금리", "미 국채 5년", "%"),
    _fred("DGS7", "D", "금리", "미 국채 7년", "%"),
    _fred("DGS10", "D", "금리", "미 국채 10년", "%"),
    _fred("DGS20", "D", "금리", "미 국채 20년", "%"),
    _fred("DGS30", "D", "금리", "미 국채 30년", "%"),
    _fred("T10Y2Y", "D", "금리", "장단기 금리차 10년-2년", "%p"),
    _fred("T10Y3M", "D", "금리", "장단기 금리차 10년-3개월", "%p"),
    _fred("DFII10", "D", "금리", "미 10년 실질금리(TIPS)", "%"),
    _fred("DFII5", "D", "금리", "미 5년 실질금리(TIPS)", "%"),
    _fred("T10YIE", "D", "인플레이션", "10년 기대인플레(BEI)", "%"),
    _fred("T5YIE", "D", "인플레이션", "5년 기대인플레(BEI)", "%"),
    _fred("T5YIFR", "D", "인플레이션", "5년5년 선도 기대인플레", "%"),
    # 미국 인플레이션
    _fred("CPIAUCSL", "M", "인플레이션", "미 소비자물가 CPI", "지수"),
    _fred("CPILFESL", "M", "인플레이션", "미 근원 CPI", "지수"),
    _fred("PCEPI", "M", "인플레이션", "미 PCE 물가", "지수"),
    _fred("PCEPILFE", "M", "인플레이션", "미 근원 PCE(Fed 타깃)", "지수"),
    _fred("PPIACO", "M", "인플레이션", "미 생산자물가 PPI", "지수"),
    _fred("CPIENGSL", "M", "인플레이션", "미 에너지 CPI", "지수"),
    # 미국 고용
    _fred("UNRATE", "M", "고용", "미 실업률", "%"),
    _fred("U6RATE", "M", "고용", "미 U6 광의실업률", "%"),
    _fred("PAYEMS", "M", "고용", "미 비농업고용(레벨)", "천명"),
    _fred("ICSA", "W", "고용", "미 신규 실업수당 청구", "건"),
    _fred("CCSA", "W", "고용", "미 계속 실업수당 청구", "건"),
    _fred("CES0500000003", "M", "고용", "미 시간당 평균임금(전체)", "$/시간"),
    _fred("AHETPI", "M", "고용", "미 시간당 임금(생산직)", "$/시간"),
    _fred("CIVPART", "M", "고용", "미 경제활동참가율", "%"),
    _fred("JTSJOL", "M", "고용", "미 구인건수(JOLTS)", "천건"),
    # 미국 통화·유동성
    _fred("M1SL", "M", "통화·유동성", "미 M1", "십억$"),
    _fred("M2SL", "M", "통화·유동성", "미 M2", "십억$"),
    _fred("M2V", "Q", "통화·유동성", "미 M2 통화유통속도", "배"),
    _fred("WALCL", "W", "통화·유동성", "Fed 총자산(B/S)", "백만$"),
    _fred("RRPONTSYD", "D", "통화·유동성", "Fed 역레포 잔액", "십억$"),
    _fred("WRESBAL", "W", "통화·유동성", "미 지급준비금", "백만$"),
    # 미국 신용·리스크
    _fred("BAMLH0A0HYM2", "D", "신용·리스크", "미 하이일드 OAS", "%"),
    _fred("BAMLC0A0CM", "D", "신용·리스크", "미 IG 회사채 OAS", "%"),
    _fred("VIXCLS", "D", "신용·리스크", "VIX 변동성지수", "지수"),
    _fred("BAA10Y", "D", "신용·리스크", "Baa-10년 스프레드", "%p"),
    _fred("DBAA", "D", "신용·리스크", "Moody's Baa 회사채", "%"),
    _fred("DAAA", "D", "신용·리스크", "Moody's Aaa 회사채", "%"),
    _fred("STLFSI4", "W", "신용·리스크", "세인트루이스 금융스트레스", "지수"),
    _fred("DRSFRMACBS", "Q", "신용·리스크", "미 주택담보 연체율", "%"),
    _fred("DRCCLACBS", "Q", "신용·리스크", "미 신용카드 연체율", "%"),
    _fred("DRALACBS", "Q", "신용·리스크", "미 전체대출 연체율", "%"),
    # 미국 경기·성장
    _fred("GDPC1", "Q", "경기·성장", "미 실질 GDP", "십억$(2017)"),
    _fred("INDPRO", "M", "경기·성장", "미 산업생산지수", "지수"),
    _fred("TCU", "M", "경기·성장", "미 설비가동률", "%"),
    _fred("RSAFS", "M", "경기·성장", "미 소매판매", "백만$"),
    _fred("UMCSENT", "M", "경기·성장", "미시간대 소비자심리지수(전미)", "지수"),
    _fred("HOUST", "M", "경기·성장", "미 주택착공", "천호"),
    _fred("PERMIT", "M", "경기·성장", "미 건축허가", "천호"),
    _fred("CSUSHPINSA", "M", "경기·성장", "미 Case-Shiller 주택가격", "지수"),
    _fred("DGORDER", "M", "경기·성장", "미 내구재 주문", "백만$"),
    # 미국 시장·환율
    _fred("DCOILWTICO", "D", "시장·환율", "WTI 유가", "$/배럴"),
    _fred("DCOILBRENTEU", "D", "시장·환율", "Brent 유가", "$/배럴"),
    _fred("DTWEXBGS", "D", "시장·환율", "미 달러지수(broad)", "지수"),
    _fred("DEXKOUS", "D", "시장·환율", "원/달러 환율(FRED)", "원"),

    # 한국 금리
    _ecos("BASE_RATE", "722Y001", "D", ["0101000"], "금리", "한국은행 기준금리", "%"),
    _ecos("KTB1Y", "817Y002", "D", ["010190000"], "금리", "한국 국고채 1년", "%"),
    _ecos("KTB3Y", "817Y002", "D", ["010200000"], "금리", "한국 국고채 3년", "%"),
    _ecos("KTB10Y", "817Y002", "D", ["010210000"], "금리", "한국 국고채 10년", "%"),
    _ecos("CD91", "817Y002", "D", ["010502000"], "금리", "한국 CD 91일", "%"),
    # 한국 인플레이션
    _ecos("CPI", "901Y009", "M", ["0"], "인플레이션", "한국 소비자물가지수", "지수"),
    _ecos("PPI", "404Y014", "M", ["*AA"], "인플레이션", "한국 생산자물가지수", "지수"),
    _ecos("EXPORT_PRICE", "402Y014", "M", ["*AA"], "인플레이션", "한국 수출물가지수", "지수"),
    _ecos("IMPORT_PRICE", "401Y015", "M", ["*AA"], "인플레이션", "한국 수입물가지수", "지수"),
    # 한국 고용
    _ecos("UNRATE", "901Y027", "M", ["I61BC"], "고용", "한국 실업률", "%"),
    _ecos("EMPRATE", "901Y027", "M", ["I61E"], "고용", "한국 고용률", "%"),
    _ecos("PARTRATE", "901Y027", "M", ["I61D"], "고용", "한국 경제활동참가율", "%"),
    # 한국 통화
    _ecos("M2", "161Y005", "M", ["BBHS00"], "통화·유동성", "한국 M2(평잔, 계절조정)", "십억원"),
    # 한국 경기·성장
    _ecos("GDP", "200Y107", "Q", ["10601"], "경기·성장", "한국 실질 GDP(지출)", "십억원"),
    _ecos("LEADING", "901Y067", "M", ["I16A"], "경기·성장", "한국 선행종합지수", "지수"),
    _ecos("LEADING_CYCLE", "901Y067", "M", ["I16E"], "경기·성장", "한국 선행지수 순환변동치", "지수"),
    _ecos("INDPRO", "901Y033", "M", ["A00", "1"], "경기·성장", "한국 전산업생산지수", "지수"),
    _ecos("CSI", "511Y002", "M", ["FME"], "경기·성장", "한국 소비자심리지수", "지수"),
    _ecos("BSI", "512Y008", "M", ["BA", "99988"], "경기·성장", "한국 기업경기실사 업황전망(전산업)", "지수"),
    # 한국 시장·환율·대외
    _ecos("USDKRW", "731Y001", "D", ["0000001"], "시장·환율", "원/달러 매매기준율", "원"),
    _ecos("CURRENT_ACCT", "301Y013", "M", ["000000"], "시장·환율", "한국 경상수지", "백만$"),
    _ecos("HOUSE_PRICE", "901Y062", "M", ["P63A"], "경기·성장", "한국 주택매매가격지수(KB)", "지수"),
    _ecos("HOUSEHOLD_CREDIT", "151Y001", "Q", ["1000000"], "신용·리스크", "한국 가계신용", "십억원"),

    # 시장 대표 지수 (yfinance)
    _yf("SP500", "^GSPC", "US", "S&P 500"),
    _yf("DOW", "^DJI", "US", "다우존스 산업평균"),
    _yf("NASDAQ", "^IXIC", "US", "나스닥 종합"),
    _yf("NDX", "^NDX", "US", "나스닥 100"),
    _yf("RUSSELL2000", "^RUT", "US", "러셀 2000"),
    _yf("KOSPI", "^KS11", "KR", "코스피"),
    _yf("KOSDAQ", "^KQ11", "KR", "코스닥"),
    _yf("NIKKEI", "^N225", "GL", "닛케이 225 (일본)"),
    _yf("HANGSENG", "^HSI", "GL", "항셍 (홍콩)"),
    _yf("SHANGHAI", "000001.SS", "GL", "상해종합 (중국)"),
    _yf("TWSE", "^TWII", "GL", "대만 가권"),
    _yf("SENSEX", "^BSESN", "GL", "센섹스 (인도)"),
    _yf("FTSE", "^FTSE", "GL", "FTSE 100 (영국)"),
    _yf("DAX", "^GDAXI", "GL", "DAX (독일)"),
    _yf("ESTOXX", "^STOXX50E", "GL", "유로스톡스 50"),
]

SERIES_BY_CODE = {s["code"]: s for s in SERIES}

# ── 지표 설명 (교육·정보용, 1~2줄) ──────────────────────────────────────
DESCRIPTIONS = {
    # 미국 금리·통화정책
    "US_FEDFUNDS": "미국 은행 간 초단기 자금 거래에 적용되는 실효 금리. 연준(Fed) 통화정책의 핵심 기준으로, 오르면 시중 금리 전반이 따라 오릅니다.",
    "US_DFEDTARU": "연준이 정한 정책금리 목표 범위의 상단. FOMC가 인상·인하로 조정합니다.",
    "US_DFEDTARL": "연준 정책금리 목표 범위의 하단. 상단과 함께 통화정책 기조를 나타냅니다.",
    "US_SOFR": "미 국채 담보 1일물 금리. LIBOR를 대체한 달러 단기자금 시장의 기준 금리입니다.",
    "US_EFFR": "연방기금금리의 일별 실효치. 단기 자금시장의 실제 거래 금리를 보여줍니다.",
    "US_DGS1MO": "미 국채 1개월물 시장 수익률. 초단기 안전자산 금리입니다.",
    "US_DGS3MO": "미 국채 3개월물 수익률. 단기 금리 기준이자 장단기차 계산에 쓰입니다.",
    "US_DGS6MO": "미 국채 6개월물 수익률.",
    "US_DGS1": "미 국채 1년물 수익률. 단기 시장금리 지표.",
    "US_DGS2": "미 국채 2년물 수익률. 향후 기준금리 경로 기대를 민감하게 반영합니다.",
    "US_DGS3": "미 국채 3년물 수익률.",
    "US_DGS5": "미 국채 5년물 수익률. 중기 금리 기준.",
    "US_DGS7": "미 국채 7년물 수익률.",
    "US_DGS10": "미 국채 10년물 수익률. 전 세계 장기금리·자산가격의 벤치마크로 가장 많이 인용됩니다.",
    "US_DGS20": "미 국채 20년물 수익률. 초장기 금리.",
    "US_DGS30": "미 국채 30년물 수익률. 장기 성장·물가 기대를 반영합니다.",
    "US_T10Y2Y": "10년물 - 2년물 금리차. 마이너스(역전)는 과거 경기침체에 선행한 대표적 신호입니다.",
    "US_T10Y3M": "10년물 - 3개월물 금리차. 연준이 침체 예측에 중시하는 장단기 스프레드입니다.",
    "US_DFII10": "물가연동국채(TIPS) 기준 10년 실질금리. 명목금리에서 기대인플레를 뺀 실질 자금 비용입니다.",
    "US_DFII5": "5년 실질금리(TIPS).",
    "US_T10YIE": "10년 기대인플레이션(국채-TIPS 차, BEI). 시장이 보는 향후 10년 평균 물가상승 기대입니다.",
    "US_T5YIE": "5년 기대인플레이션(BEI).",
    "US_T5YIFR": "5년 후부터 5년간의 선도 기대인플레. 연준이 장기 물가기대 점검에 활용합니다.",
    # 미국 인플레이션
    "US_CPIAUCSL": "미국 소비자물가지수(CPI). 도시 소비자가 사는 상품·서비스 가격을 종합한 대표 물가 지표입니다.",
    "US_CPILFESL": "변동성 큰 식품·에너지를 뺀 근원 CPI. 기조적 물가 흐름을 봅니다.",
    "US_PCEPI": "개인소비지출(PCE) 물가지수. 소비 패턴 변화를 반영하는 광의의 물가 지표.",
    "US_PCEPILFE": "근원 PCE 물가. 연준이 2% 물가목표의 기준으로 삼는 핵심 지표입니다.",
    "US_PPIACO": "생산자물가지수(PPI). 생산자가 받는 출하가격으로, 소비자물가에 선행하는 경향이 있습니다.",
    "US_CPIENGSL": "에너지 부문 소비자물가. 유가·전기·가스 가격 변동을 반영합니다.",
    # 미국 고용
    "US_UNRATE": "미국 실업률. 경제활동인구 중 실업자 비율로, 고용시장 건강과 연준 정책의 핵심 변수입니다.",
    "US_U6RATE": "광의 실업률(U6). 불완전취업·구직단념자까지 포함해 체감 실업에 가깝습니다.",
    "US_PAYEMS": "비농업 취업자 수(레벨). 매월 발표되는 고용 증감의 기준으로 시장 영향이 큽니다.",
    "US_ICSA": "주간 신규 실업수당 청구건수. 고용시장 악화를 가장 빨리 보여주는 고빈도 지표입니다.",
    "US_CCSA": "계속 실업수당 청구건수. 재취업 속도(실업 지속)를 가늠합니다.",
    "US_CES0500000003": "민간 전체 시간당 평균임금. 임금발 인플레 압력을 봅니다.",
    "US_AHETPI": "생산·비관리직 시간당 임금. 일선 근로자 임금 추세 지표.",
    "US_CIVPART": "경제활동참가율. 생산가능인구 중 일하거나 구직 중인 비율입니다.",
    "US_JTSJOL": "구인건수(JOLTS). 기업의 채용 수요로, 노동 수급 긴장도를 보여줍니다.",
    # 미국 통화·유동성
    "US_M1SL": "협의통화 M1. 현금과 즉시 인출 가능한 예금 등 가장 유동적인 통화량입니다.",
    "US_M2SL": "광의통화 M2. M1에 정기예금 등을 더한 통화량으로, 유동성·인플레 압력을 봅니다.",
    "US_M2V": "M2 통화유통속도. 통화 한 단위가 거래에 쓰이는 빈도로, 낮으면 돈이 잘 돌지 않음을 뜻합니다.",
    "US_WALCL": "연준 총자산(대차대조표). 양적완화·긴축 규모를 나타내며 시장 유동성과 직결됩니다.",
    "US_RRPONTSYD": "연준 1일물 역레포 잔액. 단기자금 시장의 과잉 유동성 흡수 규모를 보여줍니다.",
    "US_WRESBAL": "은행 지급준비금 잔액. 금융시스템 내 유동성 수준 지표입니다.",
    # 미국 신용·리스크
    "US_BAMLH0A0HYM2": "미 하이일드(투기등급) 회사채 가산금리(OAS). 벌어지면 신용위험·경기불안이 커진 신호입니다.",
    "US_BAMLC0A0CM": "미 투자등급 회사채 가산금리(OAS). 우량 회사채의 신용 스프레드입니다.",
    "US_VIXCLS": "VIX 변동성지수. S&P500 옵션 기대변동성으로 '공포지수'라 불립니다. 급등은 시장 불안을 뜻합니다.",
    "US_BAA10Y": "Baa 회사채와 10년 국채의 금리차. 신용위험 프리미엄을 나타냅니다.",
    "US_DBAA": "무디스 Baa등급(중간 우량) 회사채 수익률.",
    "US_DAAA": "무디스 Aaa등급(최우량) 회사채 수익률.",
    "US_STLFSI4": "세인트루이스 연준 금융스트레스지수. 0이 평균, 높을수록 금융시장 스트레스가 큽니다.",
    "US_DRSFRMACBS": "주택담보대출 연체율(상업은행). 가계 상환능력·부동산 건전성 지표입니다.",
    "US_DRCCLACBS": "신용카드 대출 연체율. 가계 신용 스트레스를 보여줍니다.",
    "US_DRALACBS": "전체 대출 연체율(상업은행). 금융 건전성의 종합 지표.",
    # 미국 경기·성장
    "US_GDPC1": "실질 국내총생산(GDP). 물가 영향을 뺀 경제 규모로, 성장의 가장 종합적인 척도입니다.",
    "US_INDPRO": "산업생산지수. 제조·광업·전기가스 생산량으로 실물경기 흐름을 봅니다.",
    "US_TCU": "설비가동률. 생산설비가 얼마나 가동되는지로 수요·공급 여유를 가늠합니다.",
    "US_RSAFS": "소매판매. 소비 지출의 핵심 지표로 경기 방향을 빠르게 반영합니다.",
    "US_UMCSENT": "미시간대 소비자심리지수(전미 설문). 가계의 경기·소비 심리를 나타냅니다.",
    "US_HOUST": "신규 주택 착공 건수. 건설경기와 향후 주거투자 선행 지표입니다.",
    "US_PERMIT": "건축 허가 건수. 주택 착공에 선행하는 경기 신호입니다.",
    "US_CSUSHPINSA": "케이스-실러 전미 주택가격지수. 미국 집값 추세의 대표 지표입니다.",
    "US_DGORDER": "내구재 신규 주문. 설비투자·제조 수요의 선행 지표입니다.",
    # 미국 시장·환율
    "US_DCOILWTICO": "WTI 원유 가격(서부텍사스유). 미국 기준 유가로 물가·에너지 비용에 영향이 큽니다.",
    "US_DCOILBRENTEU": "브렌트유 가격(유럽 기준). 국제 유가의 글로벌 벤치마크입니다.",
    "US_DTWEXBGS": "광범위 달러지수(명목). 주요 교역상대 통화 대비 달러 가치로, 오르면 달러 강세입니다.",
    "US_DEXKOUS": "원/달러 환율(FRED 기준). 1달러당 원화 가격으로, 오르면 원화 약세입니다.",
    # 한국 금리
    "KR_BASE_RATE": "한국은행 기준금리. 한국 통화정책의 기준으로 예금·대출 금리 전반에 파급됩니다.",
    "KR_KTB1Y": "국고채 1년물 수익률. 단기 시장금리 지표.",
    "KR_KTB3Y": "국고채 3년물 수익률. 한국 시장금리의 대표 벤치마크로 많이 인용됩니다.",
    "KR_KTB10Y": "국고채 10년물 수익률. 한국 장기금리 기준입니다.",
    "KR_CD91": "CD(양도성예금증서) 91일 금리. 단기 자금시장과 변동대출 금리의 기준입니다.",
    # 한국 인플레이션
    "KR_CPI": "한국 소비자물가지수. 가계가 사는 상품·서비스 가격으로, 한국은행 물가목표의 기준입니다.",
    "KR_PPI": "한국 생산자물가지수. 생산자 출하가격으로 소비자물가에 선행합니다.",
    "KR_EXPORT_PRICE": "수출물가지수. 수출품 가격 변동으로 교역조건·기업 채산성을 봅니다.",
    "KR_IMPORT_PRICE": "수입물가지수. 원자재·에너지 등 수입가격으로 국내 물가에 영향을 줍니다.",
    # 한국 고용
    "KR_UNRATE": "한국 실업률. 경제활동인구 중 실업자 비율입니다.",
    "KR_EMPRATE": "한국 고용률. 15세 이상 인구 중 취업자 비율로 고용시장 활력을 봅니다.",
    "KR_PARTRATE": "한국 경제활동참가율. 생산가능인구 중 경제활동인구 비율입니다.",
    # 한국 통화·성장·심리
    "KR_M2": "한국 광의통화(M2, 평잔). 시중 유동성 규모로 인플레·자산가격과 관련이 큽니다.",
    "KR_GDP": "한국 실질 GDP(지출). 물가를 제거한 경제 규모로 성장의 종합 지표입니다.",
    "KR_LEADING": "선행종합지수. 향후 경기 국면을 예고하는 여러 지표를 합성한 지수입니다.",
    "KR_LEADING_CYCLE": "선행지수 순환변동치. 추세를 제거해 경기 전환점을 보기 쉽게 만든 지표입니다.",
    "KR_INDPRO": "전산업생산지수. 제조·서비스·건설 등 전체 생산활동 수준을 나타냅니다.",
    "KR_CSI": "소비자심리지수(CSI). 100 기준, 넘으면 소비자가 경기를 낙관함을 뜻합니다.",
    "KR_BSI": "기업경기실사지수(BSI, 업황전망). 100 기준, 넘으면 기업이 업황을 긍정적으로 봅니다.",
    "KR_USDKRW": "원/달러 매매기준율. 1달러당 원화 가격으로, 오르면 원화 약세입니다.",
    "KR_CURRENT_ACCT": "경상수지. 무역·서비스·소득 등 대외 거래 흑자/적자로 대외건전성을 봅니다.",
    "KR_HOUSE_PRICE": "주택매매가격지수(KB). 전국 집값 추세를 보여주는 대표 지표입니다.",
    "KR_HOUSEHOLD_CREDIT": "가계신용(가계부채). 가계 대출+판매신용 총액으로 금융 위험 점검에 쓰입니다.",
    # 시장 지수
    "IDX_SP500": "미국 대형주 500개로 구성된 대표 주가지수. 글로벌 증시의 기준점입니다.",
    "IDX_DOW": "다우존스 산업평균지수. 미국 대표 우량주 30종목의 가격가중 지수입니다.",
    "IDX_NASDAQ": "나스닥 종합지수. 나스닥 상장 전 종목으로 기술주 비중이 높습니다.",
    "IDX_NDX": "나스닥 100. 나스닥 대형 비금융주 100개로 기술주 흐름을 대표합니다.",
    "IDX_RUSSELL2000": "러셀 2000. 미국 소형주 지수로 내수·경기민감 흐름을 반영합니다.",
    "IDX_KOSPI": "코스피. 한국거래소 유가증권시장 대표 주가지수입니다.",
    "IDX_KOSDAQ": "코스닥. 한국 기술·중소형주 중심 시장의 지수입니다.",
    "IDX_NIKKEI": "닛케이 225. 일본 대표 주가지수입니다.",
    "IDX_HANGSENG": "항셍지수. 홍콩 증시 대표 지수로 중화권 흐름을 반영합니다.",
    "IDX_SHANGHAI": "상해종합지수. 중국 본토 증시(상하이)의 대표 지수입니다.",
    "IDX_TWSE": "대만 가권지수. 대만 증시 대표 지수로 반도체 업황과 연관이 큽니다.",
    "IDX_SENSEX": "센섹스. 인도 뭄바이 증시 대표 지수입니다.",
    "IDX_FTSE": "FTSE 100. 영국 런던증시 대형주 100개 지수입니다.",
    "IDX_DAX": "DAX. 독일 프랑크푸르트 증시 대표 지수입니다.",
    "IDX_ESTOXX": "유로스톡스 50. 유로존 대형주 50개로 구성된 대표 지수입니다.",
}


# ── 키 로드 ──────────────────────────────────────────────────────────────
def _fred_key():
    return os.environ.get("FRED_API_KEY") or (FRED_KEY_FILE.read_text().strip() if FRED_KEY_FILE.exists() else "")


def _ecos_key():
    return os.environ.get("ECOS_API_KEY") or (ECOS_KEY_FILE.read_text().strip() if ECOS_KEY_FILE.exists() else "")


# ── 스키마 ───────────────────────────────────────────────────────────────
def ensure_schema(conn):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS macro_series (
            code TEXT PRIMARY KEY, name_ko TEXT, category TEXT, country TEXT,
            unit TEXT, freq TEXT, source TEXT, description TEXT, last_update TEXT
        );
        CREATE TABLE IF NOT EXISTS macro_observations (
            code TEXT, date TEXT, value REAL, PRIMARY KEY (code, date)
        );
        CREATE INDEX IF NOT EXISTS idx_macro_obs_code ON macro_observations(code);
    """)
    conn.commit()


# ── 날짜 정규화 (ECOS TIME → ISO) ────────────────────────────────────────
def _ecos_time_to_iso(t, cyc):
    t = str(t)
    if cyc == "D":
        return f"{t[0:4]}-{t[4:6]}-{t[6:8]}"
    if cyc == "M":
        return f"{t[0:4]}-{t[4:6]}-01"
    if cyc == "Q":
        q = int(t[-1]); mm = {1: "01", 2: "04", 3: "07", 4: "10"}[q]
        return f"{t[0:4]}-{mm}-01"
    if cyc == "A":
        return f"{t[0:4]}-01-01"
    return t


def _ecos_period_bounds(cyc):
    if cyc == "D":
        return "19000101", "20261231"
    if cyc == "M":
        return "190001", "202612"
    if cyc == "Q":
        return "1900Q1", "2026Q4"
    if cyc == "A":
        return "1900", "2026"
    return "19000101", "20261231"


# ── fetch: FRED ──────────────────────────────────────────────────────────
def fetch_fred(sid, start="1900-01-01"):
    key = _fred_key()
    url = ("https://api.stlouisfed.org/fred/series/observations"
           f"?series_id={sid}&api_key={key}&file_type=json&observation_start={start}")
    obs = requests.get(url, timeout=30).json().get("observations", [])
    return [(o["date"], float(o["value"])) for o in obs if o["value"] not in (".", "")]


# ── fetch: ECOS ──────────────────────────────────────────────────────────
def fetch_yf(yfsym, start="1900-01-01"):
    import yfinance as yf
    h = yf.Ticker(yfsym).history(start=start, auto_adjust=False)
    out = []
    for idx, row in h.iterrows():
        v = row.get("Close")
        if v is None or v != v:   # NaN
            continue
        out.append((idx.strftime("%Y-%m-%d"), float(v)))
    return out


def fetch_ecos(stat, cyc, items, key=None):
    key = key or _ecos_key()
    s, e = _ecos_period_bounds(cyc)
    item_path = "/".join(items)
    rows_out, offset, batch = [], 1, 10000
    while True:
        url = (f"https://ecos.bok.or.kr/api/StatisticSearch/{key}/json/kr/"
               f"{offset}/{offset+batch-1}/{stat}/{cyc}/{s}/{e}/{item_path}")
        d = requests.get(url, timeout=30).json().get("StatisticSearch", {})
        rows = d.get("row", [])
        if not rows:
            break
        for r in rows:
            v = r.get("DATA_VALUE")
            if v in (None, "", "."):
                continue
            rows_out.append((_ecos_time_to_iso(r.get("TIME"), cyc), float(v)))
        total = int(d.get("list_total_count", 0))
        if offset + batch > total:
            break
        offset += batch
    return rows_out


# ── 한 시리즈 적재 ───────────────────────────────────────────────────────
def _upsert(conn, spec, rows):
    if not rows:
        return 0
    conn.executemany(
        "INSERT OR IGNORE INTO macro_observations (code, date, value) VALUES (?,?,?)",
        [(spec["code"], d, v) for d, v in rows],
    )
    last = max(d for d, _ in rows)
    if spec["src"] == "fred":
        src = f"fred:{spec['sid']}"
    elif spec["src"] == "yf":
        src = f"yf:{spec['yf']}"
    else:
        src = f"ecos:{spec['stat']}/{'/'.join(spec['items'])}"
    conn.execute(
        "INSERT OR REPLACE INTO macro_series "
        "(code,name_ko,category,country,unit,freq,source,description,last_update) "
        "VALUES (?,?,?,?,?,?,?,?,?)",
        (spec["code"], spec["name_ko"], spec["category"], spec["country"],
         spec["unit"], spec["freq"], src, DESCRIPTIONS.get(spec["code"], ""), last),
    )
    conn.commit()
    return len(rows)


def fetch_one(spec, start=None):
    if spec["src"] == "fred":
        return fetch_fred(spec["sid"], start=start or "1900-01-01")
    if spec["src"] == "yf":
        return fetch_yf(spec["yf"], start=start or "1900-01-01")
    rows = fetch_ecos(spec["stat"], spec["cyc"], spec["items"])
    if start:
        rows = [r for r in rows if r[0] >= start]
    return rows


def backfill(codes=None):
    conn = sqlite3.connect(str(INDEX_DB))
    ensure_schema(conn)
    specs = [SERIES_BY_CODE[c] for c in codes] if codes else SERIES
    print(f"백필 {len(specs)}종 → {INDEX_DB.name}")
    for spec in specs:
        try:
            rows = fetch_one(spec)
            n = _upsert(conn, spec, rows)
            last = max((d for d, _ in rows), default="-")
            print(f"  [{spec['code']:<22}] {n:>6}행  last={last}")
        except Exception as ex:
            print(f"  [{spec['code']:<22}] FAIL {str(ex)[:60]}")
        time.sleep(0.05)
    conn.close()


def seed_descriptions():
    """DESCRIPTIONS → macro_series.description 갱신 (멱등, 코드만 있으면 즉시)."""
    conn = sqlite3.connect(str(INDEX_DB))
    ensure_schema(conn)
    n = 0
    for code, desc in DESCRIPTIONS.items():
        cur = conn.execute("UPDATE macro_series SET description=? WHERE code=?", (desc, code))
        n += cur.rowcount
    conn.commit()
    conn.close()
    print(f"descriptions seeded: {n}")
    return n


def refresh():
    """증분 갱신 (Celery beat용): 각 시리즈 마지막 날짜 이후만 fetch·upsert."""
    conn = sqlite3.connect(str(INDEX_DB))
    ensure_schema(conn)
    updated = 0
    for spec in SERIES:
        last = conn.execute(
            "SELECT MAX(date) FROM macro_observations WHERE code=?", (spec["code"],)).fetchone()[0]
        try:
            rows = fetch_one(spec, start=last)
            if last:
                rows = [r for r in rows if r[0] >= last]
            n = _upsert(conn, spec, rows)
            updated += 1 if n else 0
        except Exception as ex:
            print(f"  refresh FAIL {spec['code']}: {str(ex)[:50]}")
        time.sleep(0.03)
    conn.close()
    print(f"macro refresh done ({updated}/{len(SERIES)})")
    return updated


def validate():
    """각 시리즈 최신 1개 관측치 존재 확인 (코드 검증)."""
    ok, bad = [], []
    for spec in SERIES:
        try:
            rows = fetch_one(spec)
            if rows:
                last = max(rows, key=lambda r: r[0])
                ok.append((spec["code"], len(rows), last[0], last[1]))
            else:
                bad.append((spec["code"], "empty"))
        except Exception as ex:
            bad.append((spec["code"], str(ex)[:50]))
        time.sleep(0.05)
    print(f"\nVALIDATE  OK {len(ok)}/{len(SERIES)}  BAD {len(bad)}")
    for c, why in bad:
        print(f"  BAD {c}: {why}")
    print("--- OK (code, rows, last_date, last_val) ---")
    for row in ok:
        print(" ", row)
    return ok, bad


# ── 한·미 비교쌍 (라벨, 미국코드, 한국코드) ──────────────────────────────
COMPARE_PAIRS = [
    ("기준금리", "US_FEDFUNDS", "KR_BASE_RATE"),
    ("국채 10년", "US_DGS10", "KR_KTB10Y"),
    ("국채 3년", "US_DGS3", "KR_KTB3Y"),
    ("국채 1년", "US_DGS1", "KR_KTB1Y"),
    ("소비자물가 CPI", "US_CPIAUCSL", "KR_CPI"),
    ("생산자물가 PPI", "US_PPIACO", "KR_PPI"),
    ("실업률", "US_UNRATE", "KR_UNRATE"),
    ("M2 통화량", "US_M2SL", "KR_M2"),
    ("실질 GDP", "US_GDPC1", "KR_GDP"),
    ("산업생산지수", "US_INDPRO", "KR_INDPRO"),
    ("소비자심리", "US_UMCSENT", "KR_CSI"),
    ("주택가격지수", "US_CSUSHPINSA", "KR_HOUSE_PRICE"),
]
# 원값 그대로 비교 가능한 단위 (정규화 불필요)
RAW_UNITS = {"%", "%p", "배"}


def _conn():
    c = sqlite3.connect(str(INDEX_DB))
    c.row_factory = sqlite3.Row
    return c


def _spark(conn, code, n=60):
    rows = conn.execute(
        "SELECT value FROM macro_observations WHERE code=? ORDER BY date DESC LIMIT ?",
        (code, n),
    ).fetchall()
    return [r[0] for r in rows][::-1]


def get_overview():
    """카테고리별 지표 목록 + 최신값·전기대비·스파크라인."""
    conn = _conn()
    ensure_schema(conn)  # 서버에 테이블 없을 때 크래시 방지 (빈 결과 반환)
    metas = conn.execute("SELECT * FROM macro_series").fetchall()
    by_code = {m["code"]: m for m in metas}
    cats = {}
    for spec in SERIES:
        m = by_code.get(spec["code"])
        if not m:
            continue
        last2 = conn.execute(
            "SELECT date, value FROM macro_observations WHERE code=? ORDER BY date DESC LIMIT 2",
            (spec["code"],),
        ).fetchall()
        if not last2:
            continue
        last = last2[0]
        prev = last2[1] if len(last2) > 1 else None
        chg = (last["value"] - prev["value"]) if prev else None
        chg_pct = ((last["value"] / prev["value"] - 1) * 100) if (prev and prev["value"]) else None
        item = {
            "code": spec["code"], "name_ko": spec["name_ko"], "country": spec["country"],
            "unit": spec["unit"], "freq": spec["freq"], "category": spec["category"],
            "desc": m["description"] or "",
            "last_date": last["date"], "last_val": last["value"],
            "change": chg, "change_pct": chg_pct, "spark": _spark(conn, spec["code"]),
        }
        cats.setdefault(spec["category"], []).append(item)
    conn.close()
    ordered = [{"category": c, "series": cats[c]} for c in CATEGORIES if c in cats]
    pairs = [{"label": lbl, "us": us, "kr": kr} for lbl, us, kr in COMPARE_PAIRS
             if us in by_code and kr in by_code]
    return {"categories": ordered, "compare_pairs": pairs}


def get_series(code, limit=None):
    conn = _conn()
    ensure_schema(conn)
    m = conn.execute("SELECT * FROM macro_series WHERE code=?", (code,)).fetchone()
    if not m:
        conn.close()
        return None
    q = "SELECT date, value FROM macro_observations WHERE code=? ORDER BY date"
    rows = conn.execute(q, (code,)).fetchall()
    conn.close()
    pts = [[r["date"], r["value"]] for r in rows]
    if limit:
        pts = pts[-limit:]
    return {"code": code, "name_ko": m["name_ko"], "unit": m["unit"],
            "country": m["country"], "freq": m["freq"], "desc": m["description"] or "",
            "points": pts}


def get_compare(code_a, code_b):
    a, b = get_series(code_a), get_series(code_b)
    if not a or not b:
        return None
    raw = (a["unit"] == b["unit"]) and (a["unit"] in RAW_UNITS)
    mode = "raw" if raw else "rebased"

    def rebase(points):
        if not points:
            return points
        base = next((v for _, v in points if v), None)
        if not base:
            return points
        return [[d, v / base * 100] for d, v in points]

    if mode == "rebased":
        a = {**a, "points": rebase(a["points"])}
        b = {**b, "points": rebase(b["points"])}
    return {"mode": mode, "unit": a["unit"] if raw else "지수(시작=100)", "a": a, "b": b}


def ensure_data():
    """배포 멱등 훅: 비어있으면 최초 백필. 1990 캡(구버전) 감지 시 전체 히스토리 재백필."""
    conn = sqlite3.connect(str(INDEX_DB))
    ensure_schema(conn)
    n = conn.execute("SELECT COUNT(*) FROM macro_observations").fetchone()[0]
    # US_DGS10은 1962년부터 존재 → min date가 1990 이후면 구버전 캡 데이터
    probe = conn.execute(
        "SELECT MIN(date) FROM macro_observations WHERE code='US_DGS10'").fetchone()[0]
    conn.close()
    seed_descriptions()  # 설명문 항상 최신화 (멱등)
    if n == 0:
        print("macro_observations empty - initial backfill")
        backfill()
        return
    if probe and probe >= "1990-01-01":
        print(f"history capped at {probe} - re-backfill full history")
        backfill()
        return
    # 신규 추가된 시리즈(행 0)만 채움 (예: 지수 추가)
    conn = sqlite3.connect(str(INDEX_DB))
    have = {r[0] for r in conn.execute(
        "SELECT DISTINCT code FROM macro_observations").fetchall()}
    conn.close()
    missing = [s["code"] for s in SERIES if s["code"] not in have]
    if missing:
        print(f"backfill {len(missing)} new series: {missing}")
        backfill(missing)
    else:
        print(f"macro_observations {n} rows, history from {probe} - skip")


backfill_if_empty = ensure_data  # 하위호환 별칭


if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else "--validate"
    if arg == "--validate":
        validate()
    elif arg == "--backfill":
        backfill(sys.argv[2:] or None)
    elif arg == "--ensure":
        ensure_data()
    elif arg == "--refresh":
        refresh()
    elif arg == "--seed-desc":
        seed_descriptions()
    else:
        print("usage: python -m modules.macro_loader [--validate | --backfill [CODE ...] | --ensure | --refresh]")
