"""투자 대가 13F 보유 → data/meta/guru_holdings.db 빌드(seed).

흐름: registry 각 대가 → 13F-HR **전체 이력**(EDGAR, XML 시대 2013H2+) →
정보테이블 파싱 → CUSIP→티커(OpenFIGI, 전 분기 공유 캐시) →
symbol_master 커버리지 대조 → 분기별 상위 TOP_STORE 저장.
최신 분기는 기존과 동일하게 UI(목록/상세)가 쓰고, 과거 분기는
NAV 사전계산(modules/gurus/nav.py)의 시점별 비중 소스.

영속 규칙: prod beat는 deploy reset로 되돌아가므로 갱신은 CI 커밋 경로로만.
사용: venv/Scripts/python.exe scripts/build_guru_db.py [--gurus slug,slug]
"""
import os
import sys
import sqlite3

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

from modules.gurus.registry import GURUS
from modules.gurus import edgar, figi

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(ROOT, "data", "meta", "guru_holdings.db")
SYMBOL_DB = os.path.join(ROOT, "data", "meta", "symbol_master.db")


def _us_tickers():
    """symbol_master의 미국 종목 티커 집합(커버리지 대조용)."""
    con = sqlite3.connect(SYMBOL_DB)
    rows = con.execute("SELECT code FROM symbols WHERE country='US'").fetchall()
    con.close()
    return {r[0].upper() for r in rows if r[0]}


TOP_STORE = 25   # 분기당 저장 상위 종목 수(값 기준). UI는 최신분기, NAV는 상위 10만 사용.


def _init_db(con):
    con.executescript(
        """
        DROP TABLE IF EXISTS gurus;
        DROP TABLE IF EXISTS filings;
        DROP TABLE IF EXISTS holdings;
        CREATE TABLE gurus (
            cik TEXT PRIMARY KEY, slug TEXT, name TEXT, fund TEXT,
            stance INTEGER, stance_label TEXT, monogram TEXT,
            latest_period TEXT, stale INTEGER DEFAULT 0
        );
        CREATE TABLE filings (
            cik TEXT, period TEXT, filed TEXT, accession TEXT, form TEXT,
            PRIMARY KEY (cik, period)
        );
        CREATE TABLE holdings (
            cik TEXT, period TEXT, rank INTEGER, cusip TEXT, ticker TEXT,
            name TEXT, shares REAL, value REAL, weight REAL, covered INTEGER
        );
        CREATE INDEX idx_holdings_cik ON holdings(cik, period);
        """
    )


def build(selected=None):
    us = _us_tickers()
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    _init_db(con)

    has_key = bool(os.environ.get("OPENFIGI_API_KEY", "").strip())
    print(f"OpenFIGI key: {'present' if has_key else 'MISSING (티커 미매핑)'}")

    # CUSIP→티커는 분기 간 대부분 겹침 — 전 대가·전 분기 공유 캐시(실패도 캐시)
    figi_cache = {}

    def _map_cached(cusips):
        unknown = [c for c in dict.fromkeys(cusips) if c and c not in figi_cache]
        if unknown:
            got = figi.map_cusips(unknown)
            for c in unknown:
                figi_cache[c] = got.get(c)
        return {c: figi_cache.get(c) for c in cusips}

    for slug, name, fund, cik, stance, stance_label, monogram in GURUS:
        if selected and slug not in selected:
            continue
        con.execute(
            "INSERT INTO gurus (cik,slug,name,fund,stance,stance_label,monogram) "
            "VALUES (?,?,?,?,?,?,?)",
            (cik, slug, name, fund, stance, stance_label, monogram),
        )
        try:
            filings = edgar.get_13f_filings(cik)
            if not filings:
                print(f"  [!] {name}: 13F 없음"); continue
            for meta in filings:
                try:
                    holds = edgar.fetch_holdings_merged(cik, meta.get("all") or [meta])
                    if not holds:
                        print(f"  [!] {name} {meta['period']}: 정보테이블 빈값"); continue
                    con.execute(
                        "INSERT OR REPLACE INTO filings VALUES (?,?,?,?,?)",
                        (cik, meta["period"], meta["filed"], meta["accession"], meta["form"]),
                    )
                    top = holds[:TOP_STORE]
                    tickers = _map_cached([h["cusip"] for h in top])
                    total = sum(h["value"] for h in holds) or 1.0   # 비중 분모 = 전체 13F
                    mapped = 0
                    for i, h in enumerate(top):
                        tic = tickers.get(h["cusip"])
                        if tic:
                            mapped += 1
                        covered = 1 if (tic and tic in us) else 0
                        con.execute(
                            "INSERT INTO holdings VALUES (?,?,?,?,?,?,?,?,?,?)",
                            (cik, meta["period"], i + 1, h["cusip"], tic, h["name"],
                             h["shares"], h["value"], h["value"] / total, covered),
                        )
                    cov = sum(1 for h in top if (tickers.get(h["cusip"]) in us))
                    print(f"  [ok] {name:22s} {meta['period']} | 보유 {len(holds):3d} | "
                          f"저장 {len(top):3d} | 매핑 {mapped:3d} | 커버 {cov:3d}")
                except Exception as e:
                    print(f"  [!] {name} {meta.get('period')}: ERR {e}")
                con.commit()
        except Exception as e:
            print(f"  [!] {name}: ERR {e}")
        con.commit()

    # staleness: 수년째(>730일=2년) 미공시인 죽은 필러만 stale=1 (자동 제외).
    # 1~2분기 지연(예: Scion/Burry)은 정상 유지 — 오너 기준(2026-06-25).
    con.execute(
        "UPDATE gurus SET latest_period=(SELECT MAX(period) FROM filings WHERE filings.cik=gurus.cik)"
    )
    periods = [r[0] for r in con.execute(
        "SELECT latest_period FROM gurus WHERE latest_period IS NOT NULL")]
    if periods:
        from datetime import date
        def d(s):
            y, m, dd = map(int, s.split("-")); return date(y, m, dd)
        newest = max(d(p) for p in periods)
        con.execute("""
            UPDATE gurus SET stale=1
            WHERE latest_period IS NULL
               OR (julianday(?) - julianday(latest_period)) > 730
        """, (newest.isoformat(),))
    stale = con.execute(
        "SELECT name, latest_period FROM gurus WHERE stale=1 ORDER BY stance").fetchall()
    con.commit()
    con.close()
    if stale:
        print("\n[stale 자동 제외] 2년↑ 미공시(죽은 필러):")
        for nm, p in stale:
            print(f"  - {nm} (최근 {p})")
    print(f"\n저장: {DB_PATH}")


if __name__ == "__main__":
    sel = None
    if "--gurus" in sys.argv:
        sel = set(sys.argv[sys.argv.index("--gurus") + 1].split(","))
    build(sel)
