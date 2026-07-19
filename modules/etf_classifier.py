# -*- coding: utf-8 -*-
"""ETF 통합 분류 엔진 — KR(이름규칙) + US(모닝스타 category 매핑 + 이름규칙 폴백).

symbols 테이블의 분류 컬럼을 채운다:
  asset_class : equity / bond / commodity / real_estate / multi_asset / currency
                / crypto / alt / other
  region      : 투자지역 — US / KR / CN / JP / EU / IN / VN / TW / global / dm
                / em / asia / latam / other
  bond_type   : treasury / corporate / aggregate / highyield / tips / mbs / muni
                / em_bond / loan / convertible / money / preferred / mixed
  bond_dur    : ultrashort / short / mid / long
  eq_style    : dividend / growth / value / covcall / momentum / quality / lowvol
  eq_size     : large / mid / small
  sector      : semi / battery / bio / tech / ai / robot / finance / bank /
                energy / gold_miners / defense / auto / game / media / consumer /
                materials / industrial / utility / telecom / nuclear / green /
                ship / travel / construction / reit_theme ... (통제 슬러그)
  cls_src     : rule_kr / yf / rule_us / manual

사용: scripts/classify_etfs.py 가 이 모듈을 불러 DB를 갱신한다.
"""
import re

CLS_COLS = ("asset_class", "region", "bond_type", "bond_dur",
            "eq_style", "eq_size", "sector", "cls_src")

# ---------------------------------------------------------------------------
# 공통 유틸
# ---------------------------------------------------------------------------

def _first_hit(text, table):
    """table = [(키워드 튜플, 값)] — 먼저 걸리는 값 반환."""
    for kws, val in table:
        for kw in kws:
            if kw in text:
                return val
    return None


# ---------------------------------------------------------------------------
# KR — 이름/index_name 규칙 (한국 ETF 이름은 사실상 스펙 시트)
# ---------------------------------------------------------------------------

_KR_REGION = [
    (("미국배당", "미국S&P", "S&P500", "스탠다드", "나스닥", "다우존스", "미국채",
      "미국30년", "미국10년", "미국단기", "미국종합", "미국투자등급", "미국하이일드",
      "미국테크", "미국빅테크", "미국반도체", "미국AI", "미국나스닥", "미국필라델피아",
      "미국리츠", "미국부동산", "러셀", "미국", "테슬라", "엔비디아", "애플",
      "마이크로소프트", "팔란티어", "브로드컴", "매그니피센트", "빅테크"), "US"),
    (("차이나", "중국", "항셍", "홍콩", "CSI", "과창판", "심천", "China"), "CN"),
    (("일본", "니케이", "닛케이", "TOPIX", "재팬", "Nikkei"), "JP"),
    (("유로", "유럽", "독일", "Euro", "STOXX"), "EU"),
    (("인도", "니프티", "Nifty"), "IN"),
    (("베트남", "VN30"), "VN"),
    (("대만", "TSMC"), "TW"),
    (("신흥국", "이머징", "MSCI EM"), "em"),
    (("선진국", "MSCI World", "월드"), "dm"),
    (("글로벌", "전세계", "ACWI"), "global"),
    (("아시아",), "asia"),
]

_KR_BOND_KWS = ("채권", "국고채", "국공채", "회사채", "은행채", "금융채", "단기채",
                "종합채", "국채", "물가채", "하이일드", "크레딧", "듀레이션",
                "KOFR", "CD금리", "SOFR", "머니마켓", "MMF", "금리액티브",
                "단기통안채", "통안채", "카머니", "발행어음")

_KR_BOND_TYPE = [
    (("국고채", "국공채", "국채", "미국채", "통안채", "TIPS", "물가"), "treasury"),
    (("회사채", "크레딧", "은행채", "금융채", "여전채", "카드채", "캐피탈"), "corporate"),
    (("하이일드",), "highyield"),
    (("종합채권", "종합채", "총합"), "aggregate"),
    (("KOFR", "CD금리", "SOFR", "머니마켓", "MMF", "초단기", "단기자금",
      "금리액티브", "발행어음"), "money"),
]

_KR_BOND_DUR = [
    (("KOFR", "CD금리", "SOFR", "머니마켓", "MMF", "초단기", "금리액티브",
      "3개월", "6개월", "발행어음"), "ultrashort"),
    (("30년", "20년", "장기", "10년초과"), "long"),
    (("단기",), "short"),
    (("10년", "3년", "5년", "중기", "중장기"), "mid"),
]

_KR_EQ_STYLE = [
    (("커버드콜", "프리미엄", "데일리옵션", "인컴프리미엄"), "covcall"),
    (("배당", "고배당", "배당성장", "배당귀족", "배당다우존스", "SCHD",
      "디비던드", "Dividend"), "dividend"),
    (("성장", "그로스"), "growth"),
    (("가치", "밸류", "Value"), "value"),
    (("모멘텀",), "momentum"),
    (("퀄리티", "우량"), "quality"),
    (("로우볼", "최소변동", "저변동"), "lowvol"),
]

_KR_SECTOR = [
    (("반도체", "필라델피아반도체", "SOX"), "semi"),
    (("2차전지", "이차전지", "배터리"), "battery"),
    (("바이오", "헬스케어", "제약", "의료"), "bio"),
    (("AI", "인공지능"), "ai"),
    (("로봇",), "robot"),
    (("은행",), "bank"),
    (("증권", "보험", "금융"), "finance"),
    (("에너지", "정유", "석유", "원유기업"), "energy"),
    (("금광", "골드마이너"), "gold_miners"),
    (("방산", "방위", "우주항공"), "defense"),
    (("자동차", "전기차", "모빌리티"), "auto"),
    (("게임",), "game"),
    (("엔터", "미디어", "콘텐츠", "K컬처"), "media"),
    (("소비", "필수소비", "화장품", "음식료"), "consumer"),
    (("철강", "소재", "화학"), "materials"),
    (("조선",), "ship"),
    (("원자력", "원전"), "nuclear"),
    (("태양광", "신재생", "친환경", "클린", "수소", "탄소"), "green"),
    (("여행", "레저", "항공"), "travel"),
    (("건설", "인프라"), "construction"),
    (("통신",), "telecom"),
    (("전력", "유틸리티", "전력기기"), "utility"),
    (("IT", "테크", "인터넷", "소프트웨어", "플랫폼"), "tech"),
]


def classify_kr(name, index_name=None, naver_category=None):
    """KR ETF 1건 분류. 반환 = CLS_COLS dict (cls_src='rule_kr')."""
    nm = name or ""
    out = {c: None for c in CLS_COLS}
    out["cls_src"] = "rule_kr"

    # ---- 자산군 ----
    if any(k in nm for k in ("금현물", "골드선물", "골드액티브", "은선물", "원유선물",
                             "구리", "원자재", "농산물", "천연가스", "팔라듐", "니켈")) \
            or (naver_category == "원자재"):
        out["asset_class"] = "commodity"
    elif any(k in nm for k in ("달러선물", "엔선물", "달러인버스", "엔화", "위안화")):
        out["asset_class"] = "currency"
    elif "리츠" in nm or "부동산" in nm:
        out["asset_class"] = "real_estate"
    elif any(k in nm for k in ("TDF", "TRF", "채권혼합", "주식혼합", "자산배분",
                               "멀티에셋", "밸런스", "70로우볼", "은퇴")) \
            or (naver_category == "혼합자산"):
        out["asset_class"] = "multi_asset"
    elif any(k in nm for k in _KR_BOND_KWS):
        out["asset_class"] = "bond"
    elif "비트코인" in nm or "이더리움" in nm or "블록체인" in nm:
        out["asset_class"] = "crypto" if ("비트코인" in nm or "이더리움" in nm) else "equity"
    else:
        out["asset_class"] = "equity"

    # ---- 투자지역 ----
    region = _first_hit(nm, _KR_REGION)
    if not region and index_name:
        idx = str(index_name)
        if idx.startswith(("SP500", "NASDAQ", "DOW", "RUSSELL", "US_", "SOX")):
            region = "US"
        elif idx.startswith(("KR_", "KOSPI", "KOSDAQ", "KRX")):
            region = "KR"
    out["region"] = region or "KR"

    # ---- 채권 세부 ----
    if out["asset_class"] == "bond":
        out["bond_type"] = _first_hit(nm, _KR_BOND_TYPE) or "aggregate"
        out["bond_dur"] = _first_hit(nm, _KR_BOND_DUR)
        if out["bond_type"] == "money" and not out["bond_dur"]:
            out["bond_dur"] = "ultrashort"

    # ---- 주식 세부 ----
    if out["asset_class"] == "equity":
        out["eq_style"] = _first_hit(nm, _KR_EQ_STYLE)
        out["sector"] = _first_hit(nm, _KR_SECTOR)
        if "중소형" in nm:
            out["eq_size"] = "mid"
        elif "대형" in nm or "TOP10" in nm or "Top10" in nm:
            out["eq_size"] = "large"

    return out


# ---------------------------------------------------------------------------
# US — 모닝스타(yfinance info.category) 매핑
# ---------------------------------------------------------------------------

# category 문자열 → (asset_class, region, bond_type, bond_dur, eq_style, eq_size)
_MS_MAP = {
    # ---- US 주식 스타일박스 ----
    "Large Blend":            ("equity", "US", None, None, None, "large"),
    "Large Growth":           ("equity", "US", None, None, "growth", "large"),
    "Large Value":            ("equity", "US", None, None, "value", "large"),
    "Mid-Cap Blend":          ("equity", "US", None, None, None, "mid"),
    "Mid-Cap Growth":         ("equity", "US", None, None, "growth", "mid"),
    "Mid-Cap Value":          ("equity", "US", None, None, "value", "mid"),
    "Small Blend":            ("equity", "US", None, None, None, "small"),
    "Small Growth":           ("equity", "US", None, None, "growth", "small"),
    "Small Value":            ("equity", "US", None, None, "value", "small"),
    # ---- 해외/글로벌 주식 ----
    "Foreign Large Blend":    ("equity", "dm", None, None, None, "large"),
    "Foreign Large Growth":   ("equity", "dm", None, None, "growth", "large"),
    "Foreign Large Value":    ("equity", "dm", None, None, "value", "large"),
    "Foreign Small/Mid Blend": ("equity", "dm", None, None, None, "mid"),
    "Foreign Small/Mid Growth": ("equity", "dm", None, None, "growth", "mid"),
    "Foreign Small/Mid Value": ("equity", "dm", None, None, "value", "mid"),
    "Global Large-Stock Blend": ("equity", "global", None, None, None, "large"),
    "Global Large-Stock Growth": ("equity", "global", None, None, "growth", "large"),
    "Global Large-Stock Value": ("equity", "global", None, None, "value", "large"),
    "Global Small/Mid Stock": ("equity", "global", None, None, None, "mid"),
    "World Large Stock":      ("equity", "global", None, None, None, "large"),
    "Diversified Emerging Mkts": ("equity", "em", None, None, None, None),
    "China Region":           ("equity", "CN", None, None, None, None),
    "Japan Stock":            ("equity", "JP", None, None, None, None),
    "India Equity":           ("equity", "IN", None, None, None, None),
    "Europe Stock":           ("equity", "EU", None, None, None, None),
    "Latin America Stock":    ("equity", "latam", None, None, None, None),
    "Pacific/Asia ex-Japan Stk": ("equity", "asia", None, None, None, None),
    "Diversified Pacific/Asia": ("equity", "asia", None, None, None, None),
    "Miscellaneous Region":   ("equity", "other", None, None, None, None),
    # ---- 채권 ----
    "Ultrashort Bond":        ("bond", "US", "money", "ultrashort", None, None),
    "Short-Term Bond":        ("bond", "US", "aggregate", "short", None, None),
    "Intermediate Core Bond": ("bond", "US", "aggregate", "mid", None, None),
    "Intermediate Core-Plus Bond": ("bond", "US", "aggregate", "mid", None, None),
    "Long-Term Bond":         ("bond", "US", "aggregate", "long", None, None),
    "Short Government":       ("bond", "US", "treasury", "short", None, None),
    "Intermediate Government": ("bond", "US", "treasury", "mid", None, None),
    "Long Government":        ("bond", "US", "treasury", "long", None, None),
    "Inflation-Protected Bond": ("bond", "US", "tips", None, None, None),
    "Corporate Bond":         ("bond", "US", "corporate", None, None, None),
    "High Yield Bond":        ("bond", "US", "highyield", None, None, None),
    "Bank Loan":              ("bond", "US", "loan", None, None, None),
    "Convertibles":           ("bond", "US", "convertible", None, None, None),
    "Emerging Markets Bond":  ("bond", "em", "em_bond", None, None, None),
    "Emerging-Markets Local-Currency Bond": ("bond", "em", "em_bond", None, None, None),
    "World Bond":             ("bond", "global", "aggregate", None, None, None),
    "World Bond-USD Hedged":  ("bond", "global", "aggregate", None, None, None),
    "Multisector Bond":       ("bond", "US", "mixed", None, None, None),
    "Nontraditional Bond":    ("bond", "US", "mixed", None, None, None),
    "Preferred Stock":        ("bond", "US", "preferred", None, None, None),
    "Muni National Short":    ("bond", "US", "muni", "short", None, None),
    "Muni National Interm":   ("bond", "US", "muni", "mid", None, None),
    "Muni National Long":     ("bond", "US", "muni", "long", None, None),
    "High Yield Muni":        ("bond", "US", "muni", None, None, None),
    # ---- 섹터 주식 (sector는 별도 테이블) ----
    "Technology":             ("equity", "US", None, None, None, None),
    "Health":                 ("equity", "US", None, None, None, None),
    "Financial":              ("equity", "US", None, None, None, None),
    "Consumer Cyclical":      ("equity", "US", None, None, None, None),
    "Consumer Defensive":     ("equity", "US", None, None, None, None),
    "Industrials":            ("equity", "US", None, None, None, None),
    "Communications":         ("equity", "US", None, None, None, None),
    "Utilities":              ("equity", "US", None, None, None, None),
    "Equity Energy":          ("equity", "US", None, None, None, None),
    "Energy Limited Partnership": ("equity", "US", None, None, None, None),
    "Natural Resources":      ("equity", "US", None, None, None, None),
    "Equity Precious Metals": ("equity", "global", None, None, None, None),
    "Infrastructure":         ("equity", "global", None, None, None, None),
    # ---- 부동산/원자재/대체 ----
    "Real Estate":            ("real_estate", "US", None, None, None, None),
    "Global Real Estate":     ("real_estate", "global", None, None, None, None),
    "Commodities Broad Basket": ("commodity", "global", None, None, None, None),
    "Commodities Focused":    ("commodity", "global", None, None, None, None),
    "Single Currency":        ("currency", "global", None, None, None, None),
    "Digital Assets":         ("crypto", "global", None, None, None, None),
    "Volatility":             ("alt", "US", None, None, None, None),
    "Trading--Leveraged Equity": ("equity", "US", None, None, None, None),
    "Trading--Inverse Equity": ("equity", "US", None, None, None, None),
    "Trading--Leveraged Debt": ("bond", "US", None, None, None, None),
    "Trading--Inverse Debt":  ("bond", "US", None, None, None, None),
    "Trading--Leveraged Commodities": ("commodity", "global", None, None, None, None),
    "Trading--Inverse Commodities": ("commodity", "global", None, None, None, None),
    "Trading--Miscellaneous": ("alt", "US", None, None, None, None),
    "Derivative Income":      ("equity", "US", None, None, "covcall", None),
    "Options Trading":        ("equity", "US", None, None, "covcall", None),
    "Equity Hedged":          ("alt", "US", None, None, None, None),
    "Event Driven":           ("alt", "US", None, None, None, None),
    "Long-Short Equity":      ("alt", "US", None, None, None, None),
    "Market Neutral":         ("alt", "US", None, None, None, None),
    "Multistrategy":          ("alt", "US", None, None, None, None),
    "Macro Trading":          ("alt", "US", None, None, None, None),
    "Systematic Trend":       ("alt", "US", None, None, None, None),
    "Relative Value Arbitrage": ("alt", "US", None, None, None, None),
    "World Allocation":       ("multi_asset", "global", None, None, None, None),
    "Tactical Allocation":    ("multi_asset", "US", None, None, None, None),
    "Global Allocation":      ("multi_asset", "global", None, None, None, None),
    "Moderate Allocation":    ("multi_asset", "US", None, None, None, None),
    "Moderately Conservative Allocation": ("multi_asset", "US", None, None, None, None),
    "Moderately Aggressive Allocation": ("multi_asset", "US", None, None, None, None),
    "Aggressive Allocation":  ("multi_asset", "US", None, None, None, None),
    "Conservative Allocation": ("multi_asset", "US", None, None, None, None),
    # ---- 실수집서 확인된 추가 카테고리 (2026-07 스윕) ----
    "Defined Outcome":        ("alt", "US", None, None, None, None),        # 버퍼형
    "Target Maturity":        ("bond", "US", None, None, None, None),       # 만기채(iBonds류)
    "Focused Region":         ("equity", "other", None, None, None, None),  # 이름규칙이 지역 보강
    "Miscellaneous Sector":   ("equity", "US", None, None, None, None),
    "Greater China Region":   ("equity", "CN", None, None, None, None),
    "Securitized Bond - Focused":     ("bond", "US", "mbs", None, None, None),
    "Securitized Bond - Diversified": ("bond", "US", "mbs", None, None, None),
    "Government Mortgage-Backed Bond": ("bond", "US", "mbs", None, None, None),
    "Muni Target Maturity":   ("bond", "US", "muni", None, None, None),
    "Equity Digital Assets":  ("equity", "US", None, None, None, None),     # 크립토 기업주
    "Multi-Asset Overlay":    ("multi_asset", "US", None, None, None, None),
    "Global Bond":            ("bond", "global", "aggregate", None, None, None),
    "Global Bond-USD Hedged": ("bond", "global", "aggregate", None, None, None),
    "Short-Term Inflation-Protected Bond": ("bond", "US", "tips", "short", None, None),
    "Money Market-Taxable":   ("bond", "US", "money", "ultrashort", None, None),
    "Prime Money Market":     ("bond", "US", "money", "ultrashort", None, None),
    "Equity Market Neutral":  ("alt", "US", None, None, None, None),
    "Miscellaneous Fixed Income": ("bond", "US", None, None, None, None),
    "Miscellaneous Allocation": ("multi_asset", "US", None, None, None, None),
}


def _ms_prefix_map(cat):
    """_MS_MAP 정확일치 실패 시 패턴 폴백 (Muni 주별·Target-Date 연도 등 롱테일)."""
    if not cat:
        return None
    if cat.startswith("Muni "):
        dur = ("short" if "Short" in cat
               else "long" if "Long" in cat
               else "mid" if "Interm" in cat else None)
        return ("bond", "US", "muni", dur, None, None)
    if cat.startswith("Target-Date"):
        return ("multi_asset", "US", None, None, None, None)
    if cat.endswith("Allocation"):
        return ("multi_asset", "global" if cat.startswith("Global") else "US",
                None, None, None, None)
    if "Money Market" in cat:
        return ("bond", "US", "money", "ultrashort", None, None)
    return None

_MS_SECTOR = {
    "Technology": "tech", "Health": "bio", "Financial": "finance",
    "Consumer Cyclical": "consumer", "Consumer Defensive": "consumer",
    "Industrials": "industrial", "Communications": "telecom",
    "Utilities": "utility", "Equity Energy": "energy",
    "Energy Limited Partnership": "energy", "Natural Resources": "materials",
    "Equity Precious Metals": "gold_miners", "Infrastructure": "construction",
}

# US 이름규칙 — 카테고리 없거나 카테고리가 못 주는 축(듀레이션 등) 보강
_US_NAME_BOND_DUR = [
    ((r"0-3 month", r"1-3 month", r"3-6 month", r"t-bill", r"ultra[- ]?short",
      r"floating rate", r"0-1 year"), "ultrashort"),
    ((r"20\+ year", r"25\+ year", r"10\+ year", r"long[- ]term", r"extended dur"), "long"),
    ((r"short[- ]term", r"1-3 year", r"0-5 year", r"1-5 year", r"short dur"), "short"),
    ((r"3-7 year", r"7-10 year", r"5-10 year", r"intermediate", r"3-10 year"), "mid"),
]

_US_NAME_REGION = [
    ((r"emerging market", r"\bem\b"), "em"),
    ((r"\beafe\b", r"developed market", r"international developed"), "dm"),
    ((r"\bchina\b", r"\bhong kong\b"), "CN"),
    ((r"\bjapan\b",), "JP"),
    ((r"\beurope\b", r"eurozone", r"\bgermany\b"), "EU"),
    ((r"\bindia\b",), "IN"),
    ((r"\bvietnam\b",), "VN"),
    ((r"\btaiwan\b",), "TW"),
    ((r"\bkorea\b",), "KR"),
    # "Global X"는 운용사 브랜드 — 지역 아님
    ((r"all country", r"\bacwi\b", r"\bglobal\b(?! x)", r"\bworld\b", r"total world"), "global"),
    ((r"latin america", r"\bbrazil\b", r"\bmexico\b"), "latam"),
    ((r"asia ex", r"pacific"), "asia"),
]


def _re_hit(text, table):
    for pats, val in table:
        for p in pats:
            if re.search(p, text):
                return val
    return None


def _us_leverage(nm_l):
    """이름에서 레버리지 배수 추출. 없으면 None.
    'ultrashort'(한 단어)·'ultrapro short'는 ProShares 인버스 브랜드."""
    inverse = ("inverse" in nm_l or "bear" in nm_l
               or "ultrapro short" in nm_l or "ultrashort" in nm_l
               or "proshares short" in nm_l)
    m = re.search(r"(-?\d(?:\.\d)?)x\b", nm_l)
    if m:
        v = float(m.group(1))
        return -abs(v) if inverse else v
    if "ultrapro short" in nm_l:
        return -3.0
    if "ultrashort" in nm_l:
        return -2.0
    if "ultrapro" in nm_l:
        return 3.0
    # "Ultra Short-Term Bond"(1배 초단기채) 오인 방지
    if re.search(r"\bultra\b(?! short)", nm_l):
        return 2.0
    if inverse:
        return -1.0
    return None


def classify_us(name, yf_category=None):
    """US ETF 1건 분류. yf_category 있으면 매핑 우선, 이름규칙으로 보강."""
    nm = name or ""
    nm_l = nm.lower()
    out = {c: None for c in CLS_COLS}

    _cat = (yf_category or "").strip()
    base = _MS_MAP.get(_cat) or _ms_prefix_map(_cat)
    if base:
        out["asset_class"], out["region"], out["bond_type"], \
            out["bond_dur"], out["eq_style"], out["eq_size"] = base
        out["sector"] = _MS_SECTOR.get(yf_category)
        out["cls_src"] = "yf"
    else:
        out["cls_src"] = "rule_us"
        # 이름규칙 폴백 — 자산군. 커버드콜류 먼저(= "Equity Premium Income"이
        # 채권 규칙에 걸리는 것 방지, 예: JEPI)
        if re.search(r"covered call|buywrite|premium income|option income", nm_l):
            out["asset_class"] = "equity"
            out["eq_style"] = "covcall"
        elif re.search(r"\bbond\b|treasur|\bt-bill\b|fixed income|corporate|"
                       r"municipal|\btips\b|high yield|credit", nm_l):
            out["asset_class"] = "bond"
        elif re.search(r"\bgold\b|\bsilver\b|\boil\b|commodit|natural gas|"
                       r"\bcopper\b|uranium trust|platinum", nm_l):
            out["asset_class"] = "commodity"
        elif re.search(r"\breit\b|real estate", nm_l):
            out["asset_class"] = "real_estate"
        elif re.search(r"bitcoin|ethereum|crypto|digital asset", nm_l):
            out["asset_class"] = "crypto"
        elif re.search(r"currency|\byen\b|\beuro trust\b|dollar index", nm_l):
            out["asset_class"] = "currency"
        else:
            out["asset_class"] = "equity"

    # ---- 이름규칙 보강 (카테고리 유무 무관) ----
    if out["asset_class"] == "bond":
        dur = _re_hit(nm_l, _US_NAME_BOND_DUR)
        if dur:
            out["bond_dur"] = dur
        if not out["bond_type"]:
            if re.search(r"\btips\b|inflation", nm_l):
                out["bond_type"] = "tips"
            elif re.search(r"treasur|t-bill|govern", nm_l):
                out["bond_type"] = "treasury"
            elif "muni" in nm_l:
                out["bond_type"] = "muni"
            elif re.search(r"high yield|junk", nm_l):
                out["bond_type"] = "highyield"
            elif re.search(r"corporate|credit", nm_l):
                out["bond_type"] = "corporate"
            elif re.search(r"aggregate|total bond", nm_l):
                out["bond_type"] = "aggregate"
        # 국채 이름이면 money(초단기 현금성)보다 구체 정보 우선
        if re.search(r"treasur|t-bill|govern", nm_l) and out["bond_type"] == "money":
            out["bond_type"] = "treasury"

    region = _re_hit(nm_l, _US_NAME_REGION)
    if region and (not out["region"] or out["region"] in ("US", "other")):
        out["region"] = region
    if not out["region"]:
        # 원자재·크립토·통화는 본질상 지역 무의미 → global 기본
        out["region"] = "global" if out["asset_class"] in (
            "commodity", "crypto", "currency") else "US"

    if out["asset_class"] == "equity":
        if not out["eq_style"]:
            if re.search(r"covered call|buywrite|premium income|option income", nm_l):
                out["eq_style"] = "covcall"
            elif re.search(r"dividend|yield\b", nm_l):
                out["eq_style"] = "dividend"
            elif "growth" in nm_l:
                out["eq_style"] = "growth"
            elif "value" in nm_l:
                out["eq_style"] = "value"
            elif "momentum" in nm_l:
                out["eq_style"] = "momentum"
            elif "quality" in nm_l:
                out["eq_style"] = "quality"
            elif re.search(r"low vol|min vol", nm_l):
                out["eq_style"] = "lowvol"
        if not out["sector"]:
            out["sector"] = _re_hit(nm_l, [
                ((r"semiconductor",), "semi"),
                ((r"biotech|health|pharma|medical",), "bio"),
                ((r"technolog|software|internet|cyber|cloud",), "tech"),
                ((r"artificial intelligence|\bai\b|robotic",), "ai"),
                ((r"\bbank\b|financial",), "finance"),
                ((r"energy|oil & gas|mlp",), "energy"),
                ((r"gold miner|silver miner",), "gold_miners"),
                ((r"aerospace|defense",), "defense"),
                ((r"utilit",), "utility"),
                ((r"industrial",), "industrial"),
                ((r"consumer",), "consumer"),
                ((r"materials|mining",), "materials"),
                ((r"communication|telecom|media",), "telecom"),
                ((r"solar|clean energy|carbon",), "green"),
                ((r"uranium|nuclear",), "nuclear"),
                ((r"battery|lithium",), "battery"),
                ((r"electric vehicle|autonomous",), "auto"),
            ])

    return out, _us_leverage(nm_l)
