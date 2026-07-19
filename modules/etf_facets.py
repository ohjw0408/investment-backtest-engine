# -*- coding: utf-8 -*-
"""ETF 패싯 검색 — 자연어 별칭 파싱 + SQL 필터 + 한국어 라벨.

두 진입점:
  parse_query(q)      : "미국 단기채 etf" → (잔여텍스트, 패싯 dict) — 메인 검색창용
  build_where(facets) : 패싯 dict → (SQL WHERE 조각, params) — /api/search ETF 모드 공용

패싯 dict 형식: {컬럼: set(허용값)}. 특수 키:
  _lev   : 'lev'(레버리지>1) / 'inv'(인버스<0) / 'plain'(1배)
  _hedge : 'hedge' / 'unhedged'
  _etf   : True (etf 토큰 존재 — 검색을 ETF로 한정)
"""

# ---------------------------------------------------------------------------
# 한국어 라벨 (UI·카드 부제목 공용)
# ---------------------------------------------------------------------------

LABELS = {
    "asset_class": {
        "equity": "주식", "bond": "채권", "commodity": "원자재",
        "real_estate": "부동산", "multi_asset": "자산배분", "currency": "통화",
        "crypto": "크립토", "alt": "대체", "other": "기타",
    },
    "region": {
        "US": "미국", "KR": "한국", "CN": "중국", "JP": "일본", "EU": "유럽",
        "IN": "인도", "VN": "베트남", "TW": "대만", "global": "글로벌",
        "dm": "선진국", "em": "신흥국", "asia": "아시아", "latam": "중남미",
        "other": "기타",
    },
    "bond_type": {
        "treasury": "국채", "corporate": "회사채", "aggregate": "종합채권",
        "highyield": "하이일드", "tips": "물가연동", "mbs": "MBS",
        "muni": "지방채", "em_bond": "신흥국채", "loan": "뱅크론",
        "convertible": "전환사채", "money": "금리·현금성", "preferred": "우선주",
        "mixed": "멀티섹터",
    },
    "bond_dur": {
        "ultrashort": "초단기", "short": "단기", "mid": "중기", "long": "장기",
    },
    "eq_style": {
        "dividend": "배당", "growth": "성장", "value": "가치",
        "covcall": "커버드콜", "momentum": "모멘텀", "quality": "퀄리티",
        "lowvol": "저변동",
    },
    "eq_size": {"large": "대형", "mid": "중형", "small": "소형"},
    "sector": {
        "semi": "반도체", "battery": "2차전지", "bio": "바이오·헬스케어",
        "tech": "테크", "ai": "AI", "robot": "로봇", "finance": "금융",
        "bank": "은행", "energy": "에너지", "gold_miners": "금광",
        "defense": "방산·우주", "auto": "자동차", "game": "게임",
        "media": "미디어·엔터", "consumer": "소비재", "materials": "소재",
        "industrial": "산업재", "utility": "유틸리티", "telecom": "통신",
        "nuclear": "원자력", "green": "친환경", "ship": "조선",
        "travel": "여행·레저", "construction": "건설·인프라",
    },
}

_FACET_COLS = ("asset_class", "region", "bond_type", "bond_dur",
               "eq_style", "eq_size", "sector")

# ---------------------------------------------------------------------------
# 자연어 별칭 — 토큰(또는 토큰 접두어) → 패싯 제약
# 긴 키부터 그리디 매칭. 값 = {컬럼: (허용값,...)} 또는 특수키.
# ---------------------------------------------------------------------------

ALIAS = {
    # ETF 한정 토큰
    "이티에프": {"_etf": True}, "etf": {"_etf": True},
    # 지역
    "미국": {"region": ("US",)}, "한국": {"region": ("KR",)},
    "국내": {"region": ("KR",)},
    "중국": {"region": ("CN",)}, "차이나": {"region": ("CN",)},
    "일본": {"region": ("JP",)}, "유럽": {"region": ("EU",)},
    "인도": {"region": ("IN",)}, "베트남": {"region": ("VN",)},
    "대만": {"region": ("TW",)},
    "글로벌": {"region": ("global",)}, "전세계": {"region": ("global",)},
    "신흥국": {"region": ("em",)}, "이머징": {"region": ("em",)},
    "선진국": {"region": ("dm",)},
    # 채권 복합(긴 키 우선 매칭)
    "초단기채권": {"asset_class": ("bond",), "bond_dur": ("ultrashort",)},
    "초단기채": {"asset_class": ("bond",), "bond_dur": ("ultrashort",)},
    "단기채권": {"asset_class": ("bond",), "bond_dur": ("short", "ultrashort")},
    "단기채": {"asset_class": ("bond",), "bond_dur": ("short", "ultrashort")},
    "중기채권": {"asset_class": ("bond",), "bond_dur": ("mid",)},
    "중기채": {"asset_class": ("bond",), "bond_dur": ("mid",)},
    "장기채권": {"asset_class": ("bond",), "bond_dur": ("long",)},
    "장기채": {"asset_class": ("bond",), "bond_dur": ("long",)},
    "종합채권": {"asset_class": ("bond",), "bond_type": ("aggregate",)},
    # "미국채권"은 그리디가 "미국채"+"권"으로 오분해 → 명시 등록(국채 아님, 채권 전체)
    "미국채권": {"asset_class": ("bond",), "region": ("US",)},
    "미국채": {"asset_class": ("bond",), "bond_type": ("treasury",), "region": ("US",)},
    "국고채": {"asset_class": ("bond",), "bond_type": ("treasury",)},
    "국공채": {"asset_class": ("bond",), "bond_type": ("treasury",)},
    "국채": {"asset_class": ("bond",), "bond_type": ("treasury",)},
    "회사채": {"asset_class": ("bond",), "bond_type": ("corporate",)},
    "하이일드": {"asset_class": ("bond",), "bond_type": ("highyield",)},
    "물가연동": {"asset_class": ("bond",), "bond_type": ("tips",)},
    "물가채": {"asset_class": ("bond",), "bond_type": ("tips",)},
    "머니마켓": {"asset_class": ("bond",), "bond_type": ("money",)},
    "mmf": {"asset_class": ("bond",), "bond_type": ("money",)},
    "채권": {"asset_class": ("bond",)},
    "treasury": {"asset_class": ("bond",), "bond_type": ("treasury",)},
    "bond": {"asset_class": ("bond",)},
    # 듀레이션 단독
    "초단기": {"bond_dur": ("ultrashort",)},
    "단기": {"bond_dur": ("short", "ultrashort")},
    "중기": {"bond_dur": ("mid",)},
    "장기": {"bond_dur": ("long",)},
    # 자산군
    "주식형": {"asset_class": ("equity",)}, "주식": {"asset_class": ("equity",)},
    "원자재": {"asset_class": ("commodity",)},
    "리츠": {"asset_class": ("real_estate",)},
    "부동산": {"asset_class": ("real_estate",)},
    "자산배분": {"asset_class": ("multi_asset",)},
    "혼합": {"asset_class": ("multi_asset",)},
    # 주식 스타일
    "배당성장": {"eq_style": ("dividend",)},
    "고배당": {"eq_style": ("dividend",)},
    "배당주": {"eq_style": ("dividend",)},
    "배당": {"eq_style": ("dividend",)},
    "dividend": {"eq_style": ("dividend",)},
    "성장주": {"eq_style": ("growth",)}, "성장": {"eq_style": ("growth",)},
    "가치주": {"eq_style": ("value",)}, "가치": {"eq_style": ("value",)},
    "커버드콜": {"eq_style": ("covcall",)},
    "모멘텀": {"eq_style": ("momentum",)},
    "퀄리티": {"eq_style": ("quality",)},
    "로우볼": {"eq_style": ("lowvol",)}, "저변동성": {"eq_style": ("lowvol",)},
    # 사이즈
    "대형주": {"eq_size": ("large",)}, "대형": {"eq_size": ("large",)},
    "중소형주": {"eq_size": ("mid", "small")}, "중소형": {"eq_size": ("mid", "small")},
    "소형주": {"eq_size": ("small",)},
    # 섹터·테마
    "반도체": {"sector": ("semi",)},
    "이차전지": {"sector": ("battery",)}, "2차전지": {"sector": ("battery",)},
    "배터리": {"sector": ("battery",)},
    "바이오": {"sector": ("bio",)}, "헬스케어": {"sector": ("bio",)},
    "인공지능": {"sector": ("ai",)},
    "로봇": {"sector": ("robot",)},
    "은행주": {"sector": ("bank",)},
    "금융주": {"sector": ("finance",)},
    "에너지": {"sector": ("energy",)},
    "방산": {"sector": ("defense",)},
    "테크": {"sector": ("tech",)}, "기술주": {"sector": ("tech",)},
    "원자력": {"sector": ("nuclear",)}, "원전": {"sector": ("nuclear",)},
    "친환경": {"sector": ("green",)},
    # 레버리지·헤지
    "레버리지": {"_lev": "lev"},
    "인버스": {"_lev": "inv"}, "곱버스": {"_lev": "inv"},
    "환헤지": {"_hedge": "hedge"},
    "환노출": {"_hedge": "unhedged"}, "언헤지": {"_hedge": "unhedged"},
}

_ALIAS_KEYS = sorted(ALIAS.keys(), key=len, reverse=True)


def _merge(facets, add):
    for k, v in add.items():
        if k.startswith("_"):
            facets[k] = v
        else:
            facets.setdefault(k, set()).update(v)


def _segment_token(tok):
    """토큰을 별칭 접두어로 그리디 분해. 전부 소진되면 제약 목록, 아니면 None.
    예: '미국단기채' → [미국, 단기채]."""
    hits, rest = [], tok
    while rest:
        for key in _ALIAS_KEYS:
            if rest.startswith(key):
                hits.append(ALIAS[key])
                rest = rest[len(key):]
                break
        else:
            return None
    return hits


def parse_query(q):
    """검색어 → (잔여 텍스트, 패싯 dict). 패싯 없으면 ({}, 원문 그대로)."""
    facets = {}
    residual = []
    for tok in (q or "").strip().split():
        segs = _segment_token(tok.lower() if tok.isascii() else tok)
        if segs:
            for s in segs:
                _merge(facets, s)
        else:
            residual.append(tok)
    # etf 토큰만 있고 실제 제약이 없으면 패싯 검색으로 볼 것 없음
    real = {k: v for k, v in facets.items() if k != "_etf"}
    if not real:
        return " ".join(residual), {}
    return " ".join(residual), facets


def build_where(facets):
    """패싯 dict → (WHERE 조각 리스트, params). is_etf=1은 호출측에서."""
    where, params = [], []
    for col in _FACET_COLS:
        vals = facets.get(col)
        if vals:
            vv = sorted(vals)
            where.append(f"{col} IN ({','.join('?' * len(vv))})")
            params.extend(vv)
    lev = facets.get("_lev")
    if lev == "lev":
        where.append("leverage > 1.0")
    elif lev == "inv":
        where.append("leverage < 0")
    elif lev == "plain":
        where.append("(leverage IS NULL OR (leverage > 0 AND leverage <= 1.0))")
    hedge = facets.get("_hedge")
    if hedge:
        where.append("hedge = ?")
        params.append(hedge)
    markets = facets.get("_market")
    if markets:
        mm = sorted(markets)
        where.append(f"country IN ({','.join('?' * len(mm))})")
        params.extend(mm)
    return where, params


def facet_subtitle(row):
    """분류 컬럼 → 카드 부제목 '채권 · 미국 · 초단기 · 국채' (dict/Series 겸용)."""
    get = row.get if hasattr(row, "get") else lambda k: row[k]
    parts = []
    ac = get("asset_class")
    if not ac:
        return ""
    parts.append(LABELS["asset_class"].get(ac, ac))
    reg = get("region")
    if reg:
        parts.append(LABELS["region"].get(reg, reg))
    if ac == "bond":
        for col in ("bond_dur", "bond_type"):
            v = get(col)
            if v:
                parts.append(LABELS[col].get(v, v))
    elif ac == "equity":
        for col in ("eq_style", "eq_size", "sector"):
            v = get(col)
            if v:
                parts.append(LABELS[col].get(v, v))
    try:
        lev = get("leverage")
        if lev is not None and float(lev) != 1.0:
            parts.append(f"{float(lev):g}x")
    except (TypeError, ValueError, KeyError):
        pass
    if get("hedge") == "hedge":
        parts.append("환헤지")
    return " · ".join(parts)
