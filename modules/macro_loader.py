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
        "VALUES (?,?,?,?,?,?,?,COALESCE((SELECT description FROM macro_series WHERE code=?),''),?)",
        (spec["code"], spec["name_ko"], spec["category"], spec["country"],
         spec["unit"], spec["freq"], src, spec["code"], last),
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
    else:
        print("usage: python -m modules.macro_loader [--validate | --backfill [CODE ...] | --ensure | --refresh]")
