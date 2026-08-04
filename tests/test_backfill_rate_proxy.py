"""금리(yield) 시계열 오용 가드 — 2026-08-03 0046A0 사고 재발 방지.

사고 요약: `_BOND_CATEGORY_CONFIG`에 US_TREASURY 매핑이 없어 bond_config가 None →
is_bond=False → INDEX_MAP["US_TREASURY"]="DGS10"이 그대로 프록시로 쓰였다.
DGS10은 **10년물 금리(%)**라 가격이 아니다. 3개월물 초단기채 ETF(0046A0)에
1981년 15.84% ~ 2020년 0.52%인 금리곡선이 가격으로 들어가 prod에 15,233행,
1981년 17,951원 → 2020-03-09 1,063원 → 다음날 1,509원(+41.9%)인 가짜 역사가 생성됐다.
(일일 무결성 스캔이 "합성 백필 손상"으로 검출)
"""
import csv
from pathlib import Path

import pytest

from modules.backfill_engine import (INDEX_MAP, ETF_PROXY_OVERRIDE, _is_rate_series,
                                     _name_mismatches_index)
from modules.bond_model import (bond_config, classify_kr_listed_us_bond_etf,
                                is_target_maturity)

BASE = Path(__file__).resolve().parents[1]
KR_ETF_CSV = BASE / "data" / "meta" / "kr_etf_list.csv"


@pytest.mark.parametrize("code", ["DGS10", "DGS30", "DGS3MO", "KTB3Y", "KTB10Y", "CD91", "CORPAA3Y"])
def test_rate_series_detected(code):
    """금리(%) 시계열은 반드시 금리로 인식돼야 가드가 작동한다."""
    assert _is_rate_series(code) is True


@pytest.mark.parametrize("code", ["^GSPC", "^NDX", "^SOX", "GC=F", "KRX_GOLD", "KS200", "DJUSDIV_PROXY"])
def test_price_series_not_flagged_as_rate(code):
    """가격/지수 시계열을 금리로 오인하면 정상 백필이 막힌다(과잉 차단 방지)."""
    assert _is_rate_series(code) is False


@pytest.mark.parametrize("code,rate", [
    ("0046A0", "DGS3MO"),   # TIGER 미국초단기(3개월이하)국채
    ("329750", "DGS3MO"),   # TIGER 미국달러단기채권액티브
    ("440650", "DGS3MO"),   # ACE 미국달러단기채권액티브
])
def test_short_us_treasury_etfs_use_short_rate(code, rate):
    """단기물 ETF에 장기 금리를 물리면 변동성이 통째로 틀린다(0046A0가 DGS10을 썼던 사고)."""
    cfg = bond_config(code, "US_TREASURY", name="", etf_type="KR")
    assert cfg is not None, f"{code}: bond_config 없음 → 금리가 가격으로 둔갑한다"
    assert cfg["rate"] == rate
    assert cfg["duration"] <= 1.0, "3개월~1년물인데 듀레이션이 과대"


def test_us_treasury_10y_category_mapped():
    """만기가 특정되는 카테고리는 카테고리 매핑으로 커버(신규 상장 자동 대응)."""
    cfg = bond_config("_new_code_", "US_TREASURY_10Y", name="", etf_type="KR")
    assert cfg is not None
    assert cfg["rate"] == "DGS10"
    assert 5.0 <= cfg["duration"] <= 10.0


def test_ambiguous_us_treasury_category_has_no_blanket_mapping():
    """US_TREASURY는 3개월물~30년물이 섞인 카테고리 → 카테고리 단위 듀레이션이 존재할 수 없다.
       미등록 코드는 매핑을 주지 말고 가드가 거부하게 둔다(틀린 역사보다 없는 역사)."""
    assert bond_config("_unknown_new_etf_", "US_TREASURY", name="", etf_type="KR") is None


def _kr_etf_rows():
    with open(KR_ETF_CSV, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def test_no_kr_etf_gets_a_rate_proxy_without_bond_model():
    """전수 회귀: 한국 ETF 중 '채권모델 없이 금리 프록시'가 되는 종목이 하나도 없어야 한다.

    backfill_engine.backfill()이 index_code를 정하는 순서를 그대로 재현한다.
    여기 걸리는 종목은 백필 시 금리곡선이 가격으로 저장된다.
    """
    offenders = []
    for r in _kr_etf_rows():
        code, index_nm = r["code"], r["index"]
        if bond_config(code, index_nm, name=r.get("name", ""), etf_type="KR") is not None:
            continue                                   # 채권 모델 통과 → 안전
        index_code = ETF_PROXY_OVERRIDE.get(code, INDEX_MAP.get(index_nm))
        if _is_rate_series(index_code):
            offenders.append((code, r.get("name", ""), index_nm, index_code))
    assert offenders == [], (
        "금리 시계열이 가격 프록시로 쓰인다 — bond_model에 매핑을 추가하거나 "
        f"INDEX_MAP에서 금리 매핑을 제거할 것: {offenders}"
    )


# ── 분류-이름 불일치 가드 (2026-08-03) ────────────────────────────────────────
# kr_etf_list의 index 컬럼은 자동 분류라 오염돼 있다. 실측: KOSPI200 110종에 섹터
# (`TIGER 200 헬스케어`)·커버드콜·팩터(`KODEX 성장주`)·**미국 ETF**(`ACE 미국WideMoat동일가중`)가,
# SP500 40종에 `KODEX 미국서학개미`·`TIGER 미국S&P500동일가중`이 섞여 있었다.
# 그대로 백필하면 2026-07-21 QQQ=^GSPC 사고와 같은 종류가 대규모로 재현된다.

@pytest.mark.parametrize("name,cat", [
    ("TIGER 200 헬스케어", "KOSPI200"),          # 섹터 — KOSPI200과 다른 지수
    ("TIGER 200커버드콜", "KOSPI200"),           # 수익구조가 다름
    ("KODEX 200타겟위클리커버드콜", "KOSPI200"),
    ("KODEX 성장주", "KOSPI200"),                # 팩터
    ("KODEX 200동일가중", "KOSPI200"),           # 가중이 다름
    ("ACE 미국WideMoat동일가중", "KOSPI200"),    # 한국 지수 버킷에 들어온 미국 ETF
    ("TIGER 코리아TOP10", "KOSPI200"),           # 10종목 집중
    ("TIGER 미국S&P500동일가중", "SP500"),
    ("KODEX 미국서학개미", "SP500"),
    ("ACE 미국대형성장주액티브", "SP500"),
    ("KCGI 미국S&P500 TOP10", "SP500"),
    ("RISE 미국S&P500데일리고정커버드콜", "SP500"),
    ("KODEX 미국S&P500산업재(합성)", "SP500"),
    ("ACE 글로벌반도체TOP4 Plus", "US_SEMICONDUCTOR"),   # 집중 바스켓은 섹터지수도 아님
    ("RISE 미국30년국채커버드콜액티브(H)", "US_TREASURY_30Y"),
])
def test_mismatched_names_are_refused(name, cat):
    assert _name_mismatches_index(name, cat) != [], f"{name} 이 {cat} 프록시를 받으면 안 된다"


@pytest.mark.parametrize("name,cat", [
    ("KODEX 200", "KOSPI200"),
    ("KODEX 200TR", "KOSPI200"),                 # TR = 배당재투자, 같은 지수
    ("KODEX 레버리지", "KOSPI200"),              # 레버리지는 meta.leverage가 처리
    ("KODEX 200선물인버스2X", "KOSPI200"),
    ("TIGER MSCI Korea TR", "KOSPI200"),
    ("TIGER 미국S&P500", "SP500"),
    ("KODEX 미국S&P500(H)", "SP500"),            # 환헤지도 같은 지수
    ("TIGER 미국S&P500선물(H)", "SP500"),
    ("KODEX 미국S&P500액티브", "SP500"),
    ("TIGER 미국나스닥100", "NASDAQ100"),
    ("TIGER 미국배당다우존스", "DJ_US_DIVIDEND"),  # 배당이 카테고리 정의 자체
    ("KODEX 미국달러선물", "USD"),
])
def test_legit_trackers_pass(name, cat):
    assert _name_mismatches_index(name, cat) == [], f"{name} 은 {cat} 정상 추종인데 차단됐다"


# ── 신규 매핑 (2026-08-03) ────────────────────────────────────────────────────

def test_usd_futures_etfs_mapped_to_fx():
    """USD/KRW가 1964년부터 있는데 미국달러선물 ETF 11종이 못 쓰고 있었다."""
    assert INDEX_MAP["USD"] == "USD/KRW"


def test_usd_category_is_not_double_fx_converted():
    """market이 US가 아니어야 backfill의 fx_applied가 꺼진다(환율 이중적용 방지)."""
    with open(KR_ETF_CSV, encoding="utf-8-sig") as f:
        usd = [r for r in csv.DictReader(f) if r["index"] == "USD"]
    assert usd, "USD 카테고리 종목이 없다"
    assert all(r["market"] != "US" for r in usd), \
        "market=US 면 USD/KRW 프록시에 환율이 한 번 더 곱해진다"


@pytest.mark.parametrize("name,expect", [
    ("TIGER 미국투자등급회사채액티브(H)", "DBAA"),
    ("RISE 미국단기투자등급회사채액티브", "DBAA"),
    ("PLUS 미국장기우량회사채", "DBAA"),
])
def test_kr_listed_us_corporate_mapped(name, expect):
    cfg = classify_kr_listed_us_bond_etf(name)
    assert cfg is not None and cfg["rate"] == expect


@pytest.mark.parametrize("name", [
    "KODEX iShares미국하이일드액티브",        # 신용스프레드 모델 없음
    "ACE 미국하이일드액티브(H)",
    "KODEX iShares미국인플레이션국채액티브",  # 물가연동(TIPS)
])
def test_kr_listed_unmodelable_bonds_refused(name):
    """모델 불가 채권에 회사채 역사를 붙이면 안 된다 — 안전 스킵."""
    assert classify_kr_listed_us_bond_etf(name) is None


@pytest.mark.parametrize("cat,rate", [
    ("US_BOND_AGGREGATE", "DGS10"),
    ("US_MONEY_MARKET", "DGS3MO"),
    ("KR_TREASURY_5Y", "KTB3Y"),
])
def test_newly_mapped_bond_categories(cat, rate):
    cfg = bond_config("_x_", cat, name="", etf_type="KR")
    assert cfg is not None and cfg["rate"] == rate


# ── 비가격 시계열 가드 (2026-08-03, 백필 스윕에서 검출) ──────────────────────
# INDEX_MAP["JAPAN_TOPIX"]="TPX.F" 인데 TPX.F는 값이 -7.53~29.60 이고 4,925행 중
# 2,551행(52%)이 0 이하다 — TOPIX 지수(약 2,700pt)가 아니라 가격 시계열 자체가 아니다.
# 0을 넘나들면 pct_change가 폭발한다(하루 -2,380%). 인버스 ETF(205720)에 곱해져
# **하루 +465.3%** 짜리 합성 역사가 만들어졌다. DGS10 사건과 같은 종류.
#
# 단 CL=F는 10,135행 중 1행만 음수 — 2020-04-20 WTI 마이너스 유가라는 **실제 역사**라
# 죽이면 안 된다. 그래서 절대값이 아니라 **비율**로 구분한다.

INDEX_DB = BASE / "data" / "meta" / "index_master.db"
_NONPRICE_RATIO = 0.01
_NONPRICE_FLOOR = 5


def _nonpositive_rejects(nonpos: int, total: int) -> bool:
    """backfill()의 비가격 판정과 동일한 임계."""
    return nonpos > max(_NONPRICE_FLOOR, total * _NONPRICE_RATIO)


def test_structurally_nonpositive_series_rejected():
    """TPX.F 실측(2,551/4,925)은 거부돼야 한다."""
    assert _nonpositive_rejects(2551, 4925) is True


def test_single_real_negative_tick_survives():
    """CL=F 실측(1/10,135 = 2020-04-20 마이너스 유가)은 통과해야 한다 — 실제 역사."""
    assert _nonpositive_rejects(1, 10135) is False


@pytest.mark.skipif(not INDEX_DB.exists(), reason="index_master.db 없음(로컬 전용 데이터)")
def test_no_mapped_price_proxy_is_structurally_nonpositive():
    """전수 회귀: 가격 프록시로 매핑된 지수 중 구조적으로 0 이하인 게 없어야 한다."""
    import sqlite3
    conn = sqlite3.connect(f"file:{INDEX_DB}?mode=ro", uri=True)
    offenders = []
    for proxy in sorted(set(INDEX_MAP.values())):
        if _is_rate_series(proxy):
            continue                                   # 금리는 0·음수가 정상
        row = conn.execute(
            "SELECT COUNT(*), SUM(CASE WHEN close <= 0 THEN 1 ELSE 0 END) "
            "FROM index_daily WHERE code=? AND close IS NOT NULL", (proxy,)).fetchone()
        total, nonpos = row[0], (row[1] or 0)
        if total and _nonpositive_rejects(nonpos, total):
            offenders.append((proxy, nonpos, total))
    conn.close()
    assert offenders == [], (
        "가격이 아닌 시계열이 가격 프록시로 매핑돼 있다 — INDEX_MAP에서 제거하거나 "
        f"올바른 지수로 교체할 것: {offenders}"
    )


# ── 만기매칭(타겟만기)형 가드 (2026-08-04, 오너 결정) ─────────────────────────
# `TIGER 26-04 회사채`처럼 만기에 청산되거나 `ACE 2월만기자동연장`처럼 만기마다 갈아타는
# 상품은 상장 전 과거가 정의되지 않는다. 듀레이션도 만기까지 남은 기간에 따라 매일 줄어
# 고정값 모델이 성립하지 않는다(실측 함의 0.2~0.9 vs 모델 2.0 → 합성이 3~5배 요동).

@pytest.mark.parametrize("name,etf_type", [
    ("TIGER 26-04 회사채(A+이상)액티브", "KR"),
    ("KODEX 27-12 회사채(AA-이상)액티브", "KR"),
    ("HANARO 32-10 국고채액티브", "KR"),
    ("KODEX 53-09 국고채액티브", "KR"),
    ("BNK 26-06 특수채(AAA이상)액티브", "KR"),          # 분류가 equity로 오배정된 종목
    ("ACE 2월만기자동연장회사채AA-이상액티브", "KR"),
    ("TIGER 12월자동연장금융채(AA-이상)액티브", "KR"),   # `만기` 없이 `자동연장`만
    ("Invesco BulletShares 2026 Corporate Bond ETF", "US"),
    ("iShares iBonds Dec 2027 Term Corporate ETF", "US"),
])
def test_target_maturity_refused(name, etf_type):
    assert is_target_maturity(name, etf_type) is True, f"{name} 은 백필하면 안 된다"


@pytest.mark.parametrize("name,etf_type", [
    ("KODEX 종합채권(AA-이상)액티브", "KR"),
    ("TIGER 우량회사채액티브", "KR"),
    ("RISE 중기우량회사채", "KR"),                       # 만기 없는 상시형 — 백필 대상
    ("PLUS 우량회사채50", "KR"),
    ("ACE 국고채10년", "KR"),
    ("KODEX 미국30년국채액티브(H)", "KR"),
    ("Global X NASDAQ 100 Collar 95-110 ETF", "US"),     # 숫자쌍 오탐(영문은 YY-MM 규칙 아님)
    ("iShares 10-20 Year Treasury Bond ETF", "US"),
])
def test_non_target_maturity_passes(name, etf_type):
    assert is_target_maturity(name, etf_type) is False, f"{name} 은 정상 백필 대상인데 차단됐다"


def test_target_maturity_guard_does_not_hit_equity_etfs():
    """전수 회귀: 만기 규칙(YY-MM)이 주식형 ETF 이름을 잘못 잡지 않아야 한다."""
    equity_cats = {"KOSPI200", "KOSPI", "KOSDAQ150", "KRX300", "SP500", "NASDAQ100",
                   "DOW30", "US_SEMICONDUCTOR", "JAPAN_TOPIX"}
    hits = [(r["code"], r["name"], r["index"]) for r in _kr_etf_rows()
            if is_target_maturity(r.get("name", ""), "KR") and r["index"] in equity_cats]
    assert hits == [], f"주식형 ETF가 만기매칭으로 오판됐다: {hits}"
