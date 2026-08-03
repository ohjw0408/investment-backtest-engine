# -*- coding: utf-8 -*-
"""금리(yield) 시계열을 가격 프록시로 오용한 백필 탐지·정리·재생성.

배경 (2026-08-03, 0046A0 무결성 알림):
  backfill_engine은 채권 ETF면 bond_config로 얻은 금리 시계열을 build_bond_price_series에
  통과시켜 가격으로 바꾼다. 그런데 bond_config가 None(매핑 없음)이면 is_bond=False가 되고,
  INDEX_MAP이 그 카테고리를 금리 코드로 매핑해 두었을 경우 **금리(%)가 그대로 가격 프록시**로
  쓰였다. 예: US_TREASURY → DGS10. 3개월물 초단기채 ETF(0046A0)에 10년물 금리곡선이
  가격으로 들어가 1981년 17,951원 → 2020년 1,063원, 하루 +41.9% 같은 가짜 역사가 생성됐다.

탐지 시그니처:
  price_daily_source.source_type='backfill'
    AND source_code ∈ 금리 시계열
    AND confidence='B'
  (confidence는 backfill_engine이 "C" if leverage!=1 or is_bond else "B"로 기록한다.
   즉 금리 프록시인데 'B' = 채권 모델을 안 태웠다는 뜻 → 오염 확정.)

동작:
  1. 오염 코드 탐지
  2. volume=0 백필행 + 실데이터 이전 corporate_actions + provenance 행 삭제
  3. BackfillEngine.backfill() 재실행
     → 매핑이 생겼으면 올바른 채권 모델로 재생성,
       아직 없으면 rate-proxy 가드가 'rate_proxy_without_bond_model'로 거부(=안전, 무데이터)

실행:
  python scripts/fix_rate_proxy_backfill.py            # 탐지만 (dry-run)
  python scripts/fix_rate_proxy_backfill.py --apply    # 삭제 + 재생성
"""
import sqlite3
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

# 윈도우 콘솔(cp949)에서 em dash 등이 UnicodeEncodeError를 내는 것 방지 (서버는 UTF-8이라 무영향)
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                              # noqa: BLE001
    pass

PRICE_DB = BASE / "data" / "price_cache" / "price_daily.db"

from modules.backfill_engine import _RATE_SERIES_CODES  # noqa: E402


def find_corrupt(conn: sqlite3.Connection) -> list[tuple]:
    """[(code, source_code, rows, date_from, date_to)] — 금리 프록시 + 채권모델 미적용."""
    rates = sorted(_RATE_SERIES_CODES)
    q = (
        "SELECT code, source_code, COUNT(*), MIN(date), MAX(date) "
        "FROM price_daily_source "
        "WHERE source_type='backfill' AND confidence='B' "
        "  AND source_code IN (%s) "
        "GROUP BY code, source_code ORDER BY code" % ",".join("?" * len(rates))
    )
    return conn.execute(q, rates).fetchall()


def purge(conn: sqlite3.Connection, code: str) -> dict:
    """오염 백필행·상장전 분배금·provenance 삭제. 실데이터(volume>0)는 건드리지 않는다."""
    real_start = conn.execute(
        "SELECT MIN(date) FROM price_daily WHERE code=? AND volume>0", (code,)
    ).fetchone()[0]
    n_price = conn.execute(
        "DELETE FROM price_daily WHERE code=? AND (volume=0 OR volume IS NULL)", (code,)
    ).rowcount
    n_act = 0
    if real_start:
        n_act = conn.execute(
            "DELETE FROM corporate_actions WHERE code=? AND date < ?", (code, real_start)
        ).rowcount
    conn.execute("DELETE FROM price_daily_source WHERE code=? AND source_type='backfill'", (code,))
    conn.execute("DELETE FROM corporate_action_source WHERE code=? AND source_type='backfill'", (code,))
    conn.commit()
    return {"real_start": real_start, "price_rows": n_price, "action_rows": n_act}


def main() -> int:
    apply_ = "--apply" in sys.argv
    conn = sqlite3.connect(str(PRICE_DB))
    corrupt = find_corrupt(conn)

    if not corrupt:
        print("오염 없음 — 금리 프록시를 채권모델 없이 쓴 백필이 없습니다.")
        conn.close()
        return 0

    print(f"오염 {len(corrupt)}종 탐지:")
    for code, src, n, d0, d1 in corrupt:
        print(f"  {code:<9} proxy={src:<9} rows={n:>7}  {d0}~{d1}")

    if not apply_:
        print("\n(dry-run) 실제 정리하려면 --apply 를 붙여 실행하세요.")
        conn.close()
        return 0

    from modules.backfill_engine import BackfillEngine
    engine = BackfillEngine(verbose=True)
    print()
    for code, _src, _n, _d0, _d1 in corrupt:
        info = purge(conn, code)
        print(f"[{code}] 삭제 price={info['price_rows']:,} actions={info['action_rows']:,} "
              f"(실데이터 시작 {info['real_start']})")
        try:
            res = engine.backfill(code)
        except Exception as e:                                  # noqa: BLE001
            print(f"[{code}] 재생성 ERROR {type(e).__name__}: {e}")
            continue
        st = res.get("status")
        if st == "ok":
            print(f"[{code}] 재생성 ok rows={res.get('rows_added'):,}")
        else:
            print(f"[{code}] 재생성 안 함 status={st}  ← 매핑 없으면 정상(무데이터가 안전)")
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
