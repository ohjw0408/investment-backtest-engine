# -*- coding: utf-8 -*-
"""한국 ETF 백필 일괄 스윕 — 미실행분을 미리 채워 첫 조회 지연을 없앤다.

배경 (2026-08-03): 백필은 조회 시 `PriceLoader.ensure_full_history`가 지연 실행하는데,
prod에서 실제로 실행된 건 kr_etf_list 1,075종 중 27종뿐이었다. 나머지는 첫 사용자가
1~2초를 대신 기다린다. 이 스크립트로 미리 채워 둔다(결과는 지연 실행과 동일 — 선행 실행일 뿐).

대상 선별: backfill()이 어차피 거부할 종목(no_index_map / rate-proxy 가드 / 이름 불일치 /
지수 데이터 부족)은 **yfinance를 호출하지 않고** 건너뛴다. 1,075 → 실제 후보만 남는다.

⚠️ yfinance는 순차 호출 + 백오프. 병렬로 때리면 401/크럼 오류가 난다(2026-07-19 교훈).

실행:
  python scripts/sweep_kr_etf_backfill.py            # 대상만 집계 (dry-run)
  python scripts/sweep_kr_etf_backfill.py --apply    # 실제 스윕
  python scripts/sweep_kr_etf_backfill.py --apply --limit 50
"""
import csv
import sqlite3
import sys
import time
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                              # noqa: BLE001
    pass

PRICE_DB = BASE / "data" / "price_cache" / "price_daily.db"
INDEX_DB = BASE / "data" / "meta" / "index_master.db"
KR_ETF = BASE / "data" / "meta" / "kr_etf_list.csv"

from modules.backfill_engine import (                          # noqa: E402
    INDEX_MAP, ETF_PROXY_OVERRIDE, _GOLD_KRX_SPOT,
    _is_rate_series, _name_mismatches_index,
)
from modules.bond_model import bond_config, unsupported_currency  # noqa: E402

_MIN_INDEX_ROWS = 100


def _index_rows() -> dict:
    conn = sqlite3.connect(f"file:{INDEX_DB}?mode=ro", uri=True)
    out = {r[0]: r[1] for r in conn.execute(
        "SELECT code, COUNT(*) FROM index_daily GROUP BY code")}
    conn.close()
    return out


def candidates() -> tuple[list, dict]:
    """backfill()이 실제로 처리할 종목만. 반환 (대상 리스트, 스킵 사유별 집계)."""
    idx = _index_rows()
    skipped: dict[str, int] = {}
    todo = []
    with open(KR_ETF, encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        code, index_nm, name = r["code"], r["index"], r["name"]
        bcfg = bond_config(code, index_nm, name=name, etf_type="KR")
        if bcfg is not None and unsupported_currency(name):
            skipped["비USD 통화 채권"] = skipped.get("비USD 통화 채권", 0) + 1
            continue
        proxy = bcfg["rate"] if bcfg else INDEX_MAP.get(index_nm)
        if bcfg is None and code in ETF_PROXY_OVERRIDE:
            proxy = ETF_PROXY_OVERRIDE[code]
        if code in _GOLD_KRX_SPOT:
            proxy = "KRX_GOLD"
        if not proxy:
            skipped["매핑 없음"] = skipped.get("매핑 없음", 0) + 1
            continue
        if bcfg is None and _is_rate_series(proxy):
            skipped["금리 프록시 가드"] = skipped.get("금리 프록시 가드", 0) + 1
            continue
        if code not in ETF_PROXY_OVERRIDE and _name_mismatches_index(name, index_nm):
            skipped["이름-분류 불일치"] = skipped.get("이름-분류 불일치", 0) + 1
            continue
        if idx.get(proxy, 0) < _MIN_INDEX_ROWS:
            skipped["지수 데이터 부족"] = skipped.get("지수 데이터 부족", 0) + 1
            continue
        todo.append((code, name, index_nm, proxy))
    return todo, skipped


def already_backfilled() -> set:
    conn = sqlite3.connect(f"file:{PRICE_DB}?mode=ro", uri=True)
    out = {r[0] for r in conn.execute(
        "SELECT DISTINCT code FROM price_daily WHERE volume=0 OR volume IS NULL")}
    conn.close()
    return out


def main() -> int:
    apply_ = "--apply" in sys.argv
    limit = None
    if "--limit" in sys.argv:
        limit = int(sys.argv[sys.argv.index("--limit") + 1])

    todo, skipped = candidates()
    done = already_backfilled()
    pending = [t for t in todo if t[0] not in done]

    print(f"kr_etf_list 전체에서 백필 대상 {len(todo)}종 (이미 완료 {len(todo) - len(pending)}종)")
    for k, v in sorted(skipped.items(), key=lambda x: -x[1]):
        print(f"  스킵 {k:<18} {v:>5}종")
    print(f"\n남은 대상: {len(pending)}종")

    if not apply_:
        print("(dry-run) 실제 실행하려면 --apply")
        return 0

    if limit:
        pending = pending[:limit]

    from modules.portfolio_engine import PortfolioEngine
    loader = PortfolioEngine().loader
    ok = empty = fail = 0
    t0 = time.time()
    for i, (code, name, index_nm, proxy) in enumerate(pending, 1):
        try:
            loader.ensure_full_history(code)
            conn = sqlite3.connect(f"file:{PRICE_DB}?mode=ro", uri=True)
            n = conn.execute(
                "SELECT COUNT(*) FROM price_daily WHERE code=? AND (volume=0 OR volume IS NULL)",
                (code,)).fetchone()[0]
            conn.close()
            if n:
                ok += 1
                print(f"[{i}/{len(pending)}] {code} {name[:22]:<22} [{index_nm}<-{proxy}] 백필 {n:,}행")
            else:
                empty += 1
                print(f"[{i}/{len(pending)}] {code} {name[:22]:<22} 백필 0행 (실데이터 없음/상장전 지수 없음)")
        except Exception as e:                                  # noqa: BLE001
            fail += 1
            print(f"[{i}/{len(pending)}] {code} {name[:22]:<22} ERROR {type(e).__name__}: {e}")
        time.sleep(0.4)      # yfinance 백오프 — 병렬/무간격 호출은 401·크럼 유발
    print(f"\n완료: 백필됨={ok} 0행={empty} 실패={fail}  ({time.time() - t0:.0f}초)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
