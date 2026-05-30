# -*- coding: utf-8 -*-
"""
Stage A step 2 — 영향 코드의 백필 가격 재생성 + 배당 분리 주입.

전제:
- DJUSDIV_PROXY가 price-return으로 재구축됨 (step 1, build_djdiv_proxy.py).
- _NO_DIVIDEND_INDICES에서 DJUSDIV_PROXY 제거 + DJUSDIV_PROXY→DJUSDIV100 yield 별칭 추가.

동작 (코드별):
1. price_daily의 volume=0(백필) 행 삭제. 실데이터(volume>0)는 보존.
2. corporate_actions에서 실데이터 시작 이전 배당 행 삭제 (idempotent — 기존 백필 배당 정리).
3. BackfillEngine.backfill(code) 재실행 → 새 price-return proxy로 가격 재생성 +
   DJUSDIV100 yield 기반 분기 배당 주입 + provenance 기록.
4. 검증 출력.

진단(stage_a_diagnose.py)으로 vol=0 = 순수 백필(합성 0건) 확인 완료. 삭제 안전.

실행: python scripts/stage_a_rebackfill.py
"""
import sqlite3
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))
PRICE_DB = BASE / "data" / "price_cache" / "price_daily.db"
CODES = ["SCHD", "458730"]
SEP = "=" * 80


def real_start(conn, code):
    r = conn.execute(
        "SELECT MIN(date) FROM price_daily WHERE code=? AND volume>0", (code,)).fetchone()
    return r[0]


def snapshot(conn, code):
    pd = conn.execute(
        "SELECT COUNT(*), SUM(CASE WHEN volume=0 THEN 1 ELSE 0 END), "
        "SUM(CASE WHEN volume>0 THEN 1 ELSE 0 END), MIN(date), MAX(date) "
        "FROM price_daily WHERE code=?", (code,)).fetchone()
    div = conn.execute(
        "SELECT COUNT(*), MIN(date), MAX(date) "
        "FROM corporate_actions WHERE code=? AND dividend>0", (code,)).fetchone()
    return pd, div


def main():
    conn = sqlite3.connect(str(PRICE_DB))

    print(f"{SEP}\nStage A step 2 — 재백필 + 배당 주입\n{SEP}")

    # 삭제 단계
    for code in CODES:
        rs = real_start(conn, code)
        pd_before, div_before = snapshot(conn, code)
        print(f"\n[{code}] 실데이터 시작 = {rs}")
        print(f"  삭제 전: price_daily total={pd_before[0]} vol0={pd_before[1]} vol>0={pd_before[2]}")
        print(f"           corp_actions 배당>0={div_before[0]} ({div_before[1]}~{div_before[2]})")

        del_px = conn.execute(
            "DELETE FROM price_daily WHERE code=? AND volume=0", (code,)).rowcount
        # 실데이터 시작 이전 배당 정리 (재현성). 실측 배당(>=rs)은 보존.
        del_div = conn.execute(
            "DELETE FROM corporate_actions WHERE code=? AND date < ?", (code, rs)).rowcount
        conn.commit()
        print(f"  삭제: price_daily vol0 {del_px}행, corp_actions(<{rs}) {del_div}행")

    conn.close()

    # 재백필 (BackfillEngine은 자체 연결 사용)
    from modules.backfill_engine import BackfillEngine
    eng = BackfillEngine(verbose=True)
    print(f"\n{SEP}\n재백필 실행\n{SEP}")
    results = {}
    for code in CODES:
        res = eng.backfill(code)
        results[code] = res
        print(f"  {code}: {res}")

    # 검증
    conn = sqlite3.connect(str(PRICE_DB))
    print(f"\n{SEP}\n검증 (삭제 후 재생성 결과)\n{SEP}")
    for code in CODES:
        pd_after, div_after = snapshot(conn, code)
        rs = real_start(conn, code)
        print(f"\n[{code}] 실데이터 시작 = {rs}")
        print(f"  price_daily total={pd_after[0]} vol0={pd_after[1]} vol>0={pd_after[2]} ({pd_after[3]}~{pd_after[4]})")
        print(f"  corp_actions 배당>0={div_after[0]} ({div_after[1]}~{div_after[2]})")
        # 백필 구간 배당 / 실데이터 구간 배당 분리 확인
        bf = conn.execute(
            "SELECT COUNT(*) FROM corporate_actions WHERE code=? AND dividend>0 AND date<?",
            (code, rs)).fetchone()[0]
        rl = conn.execute(
            "SELECT COUNT(*) FROM corporate_actions WHERE code=? AND dividend>0 AND date>=?",
            (code, rs)).fetchone()[0]
        print(f"  배당 분리: 백필구간(<{rs})={bf}건  실데이터구간(>={rs})={rl}건")

    # provenance
    for t in ("backfill_runs", "corporate_action_source", "price_daily_source"):
        try:
            rows = conn.execute(
                f"SELECT code, COUNT(*) FROM {t} WHERE code IN ('SCHD','458730') GROUP BY code"
            ).fetchall()
            print(f"  {t}: {dict(rows) if rows else '없음'}")
        except Exception as e:
            print(f"  {t}: ERR {e}")
    conn.close()
    print("\nDone. 다음: debug_dividend.py로 배당 지표 p50>0 확인.")


if __name__ == "__main__":
    main()
