# -*- coding: utf-8 -*-
"""ETF 패싯 검색 검증 — 별칭 파싱 + /api/search 자연어·ETF 모드.
실행: python tests/test_etf_search.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_p = _f = 0


def ok(name, cond):
    global _p, _f
    if cond:
        _p += 1
        print("PASS  " + name)
    else:
        _f += 1
        print("FAIL  " + name)


# ── 1. parse_query ──
from modules.etf_facets import parse_query, facet_subtitle

res, fc = parse_query("미국 단기채 etf")
ok("미국 단기채 etf → region US", fc.get("region") == {"US"})
ok("미국 단기채 etf → bond", fc.get("asset_class") == {"bond"})
ok("미국 단기채 etf → dur short+ultrashort",
   fc.get("bond_dur") == {"short", "ultrashort"})
ok("미국 단기채 etf → 잔여 없음", res == "")

res, fc = parse_query("미국단기채")   # 붙여쓰기 분해
ok("미국단기채 붙여쓰기 → US+bond", fc.get("region") == {"US"} and fc.get("asset_class") == {"bond"})

res, fc = parse_query("삼성전자")     # 패싯 아님
ok("삼성전자 → 패싯 없음", fc == {} and res == "삼성전자")

res, fc = parse_query("미국 배당 다우존스")
ok("미국 배당 다우존스 → dividend + 잔여 다우존스",
   fc.get("eq_style") == {"dividend"} and res == "다우존스")

res, fc = parse_query("커버드콜")
ok("커버드콜 → covcall", fc.get("eq_style") == {"covcall"})

res, fc = parse_query("미국채권")
ok("미국채권 → US bond (국채 한정 아님)",
   fc.get("region") == {"US"} and fc.get("asset_class") == {"bond"}
   and "bond_type" not in fc)

res, fc = parse_query("미국채")
ok("미국채 → US treasury", fc.get("bond_type") == {"treasury"})

res, fc = parse_query("장기 국채 인버스")
ok("장기 국채 인버스 → long+treasury+inv",
   fc.get("bond_dur") == {"long"} and fc.get("bond_type") == {"treasury"}
   and fc.get("_lev") == "inv")

# ── 2. API ──
from app import app

c = app.test_client()

# 자연어: 양시장 동시 히트
r = c.get("/api/search?q=" + "미국 단기채 etf" + "&page=1&per=50").get_json()
badges = {it["badge"] for it in r["items"]}
codes = {it["code"] for it in r["items"]}
ok("자연어: 총건수 > 10", r["total"] > 10)
ok("자연어: KR ETF + US ETF 혼재", {"KR ETF", "US ETF"} <= badges)
ok("자연어: KR 대표(329750 TIGER 미국달러단기채권액티브) 포함", "329750" in codes)
us_short = {"SGOV", "BIL", "SHV", "SHY", "VGSH"} & codes
ok("자연어: US 대표 단기채 포함 " + str(us_short), len(us_short) >= 2)
ok("자연어: 부제목 한국어 패싯", any("채권" in (it.get("subtitle") or "") for it in r["items"]))

# 자연어 미매칭 검색은 기존 경로 그대로
r2 = c.get("/api/search?q=삼성전자&limit=5").get_json()
ok("기존 검색 회귀: 삼성전자", any(it["code"] == "005930" for it in r2))

# ETF 모드: 명시 패싯 (미국채권 단기·초단기, 시장 무관)
r3 = c.get("/api/search?etf=1&asset=bond&region=US&bdur=short,ultrashort&page=1&per=100").get_json()
codes3 = {it["code"] for it in r3["items"]}
ok("ETF 모드: 결과 있음", r3["total"] > 5)
ok("ETF 모드: KR 상장 우선 정렬", r3["items"][0]["badge"] == "KR ETF")
ok("ETF 모드: US 단기채 포함", len({"SGOV", "BIL", "SHV"} & codes3) >= 1)

# ETF 모드: 상장시장 필터
r4 = c.get("/api/search?etf=1&market=KR&asset=bond&region=US&bdur=short,ultrashort&page=1&per=100").get_json()
ok("ETF 모드 market=KR: 전부 KR ETF",
   r4["total"] > 0 and all(it["badge"] == "KR ETF" for it in r4["items"]))

# ETF 모드: 검색어 없이 브라우즈
r5 = c.get("/api/search?etf=1&asset=commodity&page=1").get_json()
ok("ETF 모드 브라우즈(q 없음): 원자재", r5["total"] > 5)

# ETF 모드: 자연어 병합 (탭에서 '단기채'만 쳐도)
r6 = c.get("/api/search?etf=1&q=단기채&market=KR&page=1&per=100").get_json()
ok("ETF 모드 q=단기채+market=KR", r6["total"] > 0
   and all(it["badge"] == "KR ETF" for it in r6["items"]))

# 인버스 필터
r7 = c.get("/api/search?etf=1&asset=bond&lev=inv&page=1&per=100").get_json()
ok("ETF 모드 채권 인버스", r7["total"] > 0)

print(f"\n{_p} passed, {_f} failed")
sys.exit(1 if _f else 0)
