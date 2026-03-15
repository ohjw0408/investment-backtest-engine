"""
crawl_kr_etf_list.py
────────────────────────────────────────────────────────────────────────────────
FinanceDataReader로 KRX 전체 ETF 목록 가져오기
메타데이터 파싱:
  - 기초지수 (S&P500, 나스닥100, 코스피200, 미국채 등)
  - 환노출 여부 (환헤지 H, 환노출)
  - 레버리지 배수 (1x, 2x, -1x, -2x)
  - 운용사 (KODEX, TIGER, KBSTAR 등)
────────────────────────────────────────────────────────────────────────────────
"""

import sys
import re
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

import pandas as pd
import FinanceDataReader as fdr

OUTPUT = Path(__file__).resolve().parent.parent / "data" / "meta" / "kr_etf_list.csv"

# ── 기초지수 매핑 키워드 ─────────────────────────────────
INDEX_MAP = [
    # 미국 주식
    (["S&P500", "S&P 500", "미국S&P", "미국 S&P"],           "SP500",        "US"),
    (["나스닥100", "나스닥 100", "Nasdaq100", "QQQ",
      "미국나스닥100", "미국 나스닥100"],                       "NASDAQ100",    "US"),
    (["나스닥",  "Nasdaq"],                                    "NASDAQ",       "US"),
    (["다우",    "DOW"],                                       "DOW",          "US"),
    (["러셀2000", "Russell2000"],                              "RUSSELL2000",  "US"),
    (["미국빅테크", "미국테크", "미국 테크", "빅테크"],           "US_TECH",      "US"),
    (["미국AI", "미국 AI"],                                    "US_AI",        "US"),
    (["미국배당", "미국 배당"],                                  "US_DIVIDEND",  "US"),
    (["미국리츠", "미국 리츠"],                                  "US_REIT",      "US"),
    (["미국대형", "미국 대형"],                                  "SP500",        "US"),
    (["미국소형", "미국 소형"],                                  "RUSSELL2000",  "US"),

    # 한국 주식 - 주요 지수
    (["코스피200", "KOSPI200", "코스피 200", " 200TR",
      "MSCI Korea", " 200 ", "KODEX 200", "TIGER 200",
      "RISE 200", "ACE 200", "PLUS 200", "KIWOOM 200",
      "Top5Plus", "KoreaTop10", "코리아TOP"],                  "KOSPI200",     "KR"),
    (["코스피",    "KOSPI"],                                    "KOSPI",        "KR"),
    (["코스닥150", "KOSDAQ150"],                                "KOSDAQ150",    "KR"),
    (["코스닥",    "KOSDAQ"],                                   "KOSDAQ",       "KR"),
    (["KRX300"],                                               "KRX300",       "KR"),

    # 한국 주식 - 섹터/테마
    (["반도체", "Semiconductor", "SEMICONDUCTOR"],              "KR_SEMICONDUCTOR", "KR"),
    (["2차전지", "배터리", "Battery"],                          "KR_BATTERY",   "KR"),
    (["AI반도체", "AI 반도체"],                                  "KR_AI_CHIP",   "KR"),
    (["AI전력", "AI 전력"],                                     "KR_AI_POWER",  "KR"),
    (["인공지능", "AI액티브"],                                   "KR_AI",        "KR"),
    (["방산", "K방산", "방위"],                                  "KR_DEFENSE",   "KR"),
    (["조선"],                                                  "KR_SHIPBUILDING","KR"),
    (["바이오", "Bio"],                                        "KR_BIO",       "KR"),
    (["헬스케어", "Healthcare"],                                "KR_HEALTHCARE","KR"),
    (["로봇", "Robot"],                                        "KR_ROBOT",     "KR"),
    (["자동차", "미래차"],                                      "KR_AUTO",      "KR"),
    (["삼성그룹", "삼성전자"],                                   "KR_SAMSUNG",   "KR"),
    (["고배당", "배당주", "배당"],                               "KR_DIVIDEND",  "KR"),
    (["리츠", "부동산인프라"],                                   "KR_REIT",      "KR"),
    (["커버드콜"],                                              "KR_COVERED_CALL","KR"),
    (["레버리지"],                                              "KOSPI200",     "KR"),
    (["인버스"],                                               "KOSPI200",     "KR"),

    # 한국 채권/단기 (구체적인 것 먼저)
    (["단기통안채", "단기국공채", "단기채권액티브",
      "단기채권PLUS", "초단기채권", "전단채",
      "머니마켓", "MoneyMarket", "CD금리"],                    "KR_MONEY_MARKET","KR"),
    (["종합채권"],                                              "KR_BOND_AGGREGATE","KR"),
    (["국고채30", "국고채 30"],                                  "KR_TREASURY_30Y","KR"),
    (["국고채10", "국고채 10"],                                  "KR_TREASURY_10Y","KR"),
    (["국고채",   "국채", "통안채", "특수채"],                    "KR_TREASURY",  "KR"),
    (["회사채"],                                               "KR_CORPORATE", "KR"),

    (["원자력", "원자력SMR", "SMR"],                           "KR_NUCLEAR",   "KR"),
    (["밸류업", "코리아밸류업", "Value Up"],                     "KR_VALUEUP",   "KR"),
    (["TDF"],                                                  "TDF",          "KR"),
    (["우주항공", "항공우주", "UAM"],                            "AEROSPACE",    "GLOBAL"),
    (["양자컴퓨팅", "양자컴"],                                   "QUANTUM",      "GLOBAL"),
    (["구리"],                                                  "COPPER",       "COMMODITY"),
    (["증권"],                                                  "KR_SECURITIES","KR"),
    (["화장품", "뷰티"],                                        "KR_BEAUTY",    "KR"),
    (["지주회사"],                                              "KR_HOLDING",   "KR"),
    (["성장주"],                                               "KR_GROWTH",    "KR"),
    (["자산배분", "TRF"],                                       "ASSET_ALLOCATION","GLOBAL"),
    (["토탈월드", "Total World"],                               "MSCI_WORLD",   "GLOBAL"),
    (["미국달러", "달러"],                                       "USD",          "CURRENCY"),
    (["채권혼합"],                                              "KR_BOND_MIX",  "KR"),
    (["테슬라"],                                               "TESLA",        "US"),
    (["엔비디아"],                                              "NVIDIA",       "US"),
    (["구글"],                                                  "GOOGLE",       "US"),
    (["현대차", "기아"],                                        "KR_AUTO",      "KR"),
    (["한화그룹"],                                              "KR_HANWHA",    "KR"),
    (["미국서학개미"],                                           "US_POPULAR",   "US"),
    (["ESG"],                                                  "KR_ESG",       "KR"),
    (["네트워크인프라", "인프라"],                                "INFRASTRUCTURE","GLOBAL"),
    (["신재생에너지", "클린에너지"],                              "CLEAN_ENERGY", "GLOBAL"),
    (["단기채권"],                                              "KR_MONEY_MARKET","KR"),
    (["골드선물"],                                              "GOLD",         "COMMODITY"),
    (["수소"],                                                  "HYDROGEN",     "GLOBAL"),
    (["메타버스"],                                              "METAVERSE",    "GLOBAL"),
    (["소프트웨어"],                                            "KR_SOFTWARE",  "KR"),
    (["건설"],                                                  "KR_CONSTRUCTION","KR"),
    (["하이일드", "HighYield"],                                  "US_HIGH_YIELD","US"),
    (["자율주행"],                                              "AUTONOMOUS",   "GLOBAL"),
    (["4차산업", "혁신기술"],                                    "TECH_INNOVATION","GLOBAL"),
    (["미디어", "컨텐츠", "KPOP", "K-POP"],                    "KR_CULTURE",   "KR"),
    (["여행", "레저"],                                          "KR_LEISURE",   "KR"),
    (["전력", "에너지"],                                        "KR_ENERGY",    "KR"),
    (["중장기국공채"],                                           "KR_TREASURY",  "KR"),
    (["국공채"],                                               "KR_TREASURY",  "KR"),
    (["주주환원", "밸류"],                                       "KR_VALUE",     "KR"),
    (["IT플러스", "코리아테크", "메가테크"],                      "KR_TECH",      "KR"),
    (["포스코"],                                               "KR_POSCO",     "KR"),
    (["SK하이닉스"],                                            "KR_SKHYNIX",   "KR"),
    (["희토류", "전략자원"],                                     "RARE_EARTH",   "GLOBAL"),
    (["버크셔"],                                               "BERKSHIRE",    "US"),
    (["소버린AI"],                                              "KR_AI",        "KR"),
    ([" 200"],                                                 "KOSPI200",     "KR"),
    (["미국채30", "미국 30년", "장기미국채"],                    "US_TREASURY_30Y","US"),
    (["미국채10", "미국 10년", "중기미국채"],                    "US_TREASURY_10Y","US"),
    (["미국채",   "미국 국채"],                                  "US_TREASURY",  "US"),

    # 원자재
    (["금"],                                                   "GOLD",         "COMMODITY"),
    (["은"],                                                   "SILVER",       "COMMODITY"),
    (["원유", "WTI", "Oil"],                                   "OIL",          "COMMODITY"),

    # 글로벌
    (["선진국", "MSCI World", "글로벌AI", "글로벌 AI"],          "MSCI_WORLD",   "GLOBAL"),
    (["신흥국", "EM", "이머징"],                                 "MSCI_EM",      "GLOBAL"),
    (["일본"],                                                  "JAPAN",        "JAPAN"),
    (["중국", "차이나", "China"],                               "CHINA",        "CHINA"),
    (["유럽"],                                                  "EUROPE",       "EUROPE"),
    (["인도"],                                                  "INDIA",        "INDIA"),
    (["베트남"],                                               "VIETNAM",      "VIETNAM"),
    (["브라질"],                                               "BRAZIL",       "BRAZIL"),
]

# ── 운용사 파싱 ───────────────────────────────────────────
ISSUER_MAP = {
    "KODEX":   "삼성자산운용",
    "TIGER":   "미래에셋자산운용",
    "KBSTAR":  "KB자산운용",
    "ARIRANG": "한화자산운용",
    "KOSEF":   "키움투자자산운용",
    "HANARO":  "NH아문디자산운용",
    "SOL":     "신한자산운용",
    "ACE":     "한국투자신탁운용",
    "PLUS":    "우리자산운용",
    "TIMEFOLIO": "타임폴리오자산운용",
    "KINDEX":  "한국투자신탁운용",
    "SMART":   "스마트자산운용",
}

def parse_leverage(name: str) -> float:
    """레버리지 배수 파싱"""
    name_upper = name.upper()
    if "인버스2X" in name or "곱버스" in name or "-2X" in name_upper:
        return -2.0
    if "인버스" in name or "-1X" in name_upper:
        return -1.0
    if "레버리지" in name or "2X" in name_upper:
        return 2.0
    if "3X" in name_upper:
        return 3.0
    return 1.0

def parse_hedge(name: str, market: str) -> str:
    """환헤지 여부 파싱"""
    if "(H)" in name or "환헤지" in name or "_H" in name:
        return "hedge"
    # 한국 자산은 환율 무관
    if market == "KR":
        return "none"
    return "unhedged"  # 해외 자산 기본값: 환노출

def parse_index(name: str):
    """기초지수 파싱 - 구체적인 것 먼저 매칭"""
    # 미국 자산 명시적 키워드 먼저 체크
    us_explicit = ["미국", "US ", "America", "S&P", "나스닥", "Nasdaq",
                   "다우", "DOW", "러셀", "Russell", "MSCI"]
    is_us_asset = any(kw in name for kw in us_explicit)

    for keywords, index_code, market in INDEX_MAP:
        for kw in keywords:
            if kw in name:
                # 미국 자산인데 KR market으로 분류된 경우 US로 보정
                if is_us_asset and market == "KR":
                    # 단, 순수 한국 섹터/테마는 KR 유지 (예: KODEX 미국반도체 → 미국반도체)
                    # 채권/배당/머니마켓은 기초자산 시장 기준
                    if index_code in ["KR_TREASURY", "KR_MONEY_MARKET",
                                      "KR_BOND_AGGREGATE", "KR_CORPORATE",
                                      "KR_REIT", "KR_DIVIDEND"]:
                        return index_code.replace("KR_", "US_"), "US"
                    # 반도체/AI 등 섹터는 미국 자산이면 US
                    if index_code in ["KR_SEMICONDUCTOR", "KR_NUCLEAR",
                                      "KR_ROBOT", "KR_DEFENSE", "KR_BIO",
                                      "KR_HEALTHCARE", "KR_ENERGY"]:
                        return index_code.replace("KR_", "US_"), "US"
                return index_code, market
    return "UNKNOWN", "UNKNOWN"

def parse_issuer(name: str) -> str:
    """운용사 파싱"""
    for brand, issuer in ISSUER_MAP.items():
        if name.upper().startswith(brand):
            return brand
    return name.split()[0] if name else "UNKNOWN"

def main():
    print("KRX ETF 목록 가져오는 중...")
    
    try:
        etf_list = fdr.StockListing("ETF/KR")
        print(f"총 {len(etf_list)}개 ETF 발견")
        print(f"컬럼: {etf_list.columns.tolist()}")
        print(etf_list.head())
    except Exception as e:
        print(f"ETF 목록 가져오기 실패: {e}")
        return

    # 컬럼명 표준화
    col_map = {}
    for col in etf_list.columns:
        col_lower = col.lower()
        if "code" in col_lower or "symbol" in col_lower or col_lower in ["종목코드"]:
            col_map[col] = "code"
        elif "name" in col_lower or col_lower in ["종목명", "etf명"]:
            col_map[col] = "name"

    etf_list = etf_list.rename(columns=col_map)

    if "code" not in etf_list.columns or "name" not in etf_list.columns:
        print(f"컬럼 매핑 실패. 현재 컬럼: {etf_list.columns.tolist()}")
        return

    # 메타데이터 파싱
    records = []
    for _, row in etf_list.iterrows():
        code = str(row["code"]).zfill(6)
        name = str(row["name"])

        index_code, market = parse_index(name)
        leverage           = parse_leverage(name)
        hedge              = parse_hedge(name, market)
        issuer             = parse_issuer(name)

        records.append({
            "code":        code,
            "name":        name,
            "issuer":      issuer,
            "index":       index_code,
            "market":      market,
            "leverage":    leverage,
            "hedge":       hedge,
        })

    result_df = pd.DataFrame(records)

    # 저장
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    result_df.to_csv(OUTPUT, index=False, encoding="utf-8-sig")

    print(f"\n저장 완료: {OUTPUT}")
    print(f"총 {len(result_df)}개 ETF")
    print()

    # 통계 출력
    print("── 운용사별 ─────────────────────────────")
    print(result_df["issuer"].value_counts().head(15).to_string())
    print()
    print("── 기초지수별 ───────────────────────────")
    print(result_df["index"].value_counts().head(20).to_string())
    print()
    print("── 레버리지별 ───────────────────────────")
    print(result_df["leverage"].value_counts().to_string())
    print()
    print("── 환헤지별 ─────────────────────────────")
    print(result_df["hedge"].value_counts().to_string())
    print()
    print("── UNKNOWN 샘플 (50개) ──────────────────")
    unknown = result_df[result_df["index"] == "UNKNOWN"]["name"]
    print(f"UNKNOWN 총 {len(unknown)}개")
    print(unknown.head(50).to_string())


if __name__ == "__main__":
    main()