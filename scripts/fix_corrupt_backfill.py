# -*- coding: utf-8 -*-
"""구세대(pre-bond_model/pre-FX캡) 손상 백필 수술 (출시완성도 B-1, 2026-07-02).

진단 근거 (scan_backfill_corruption.py + 수동 검증):
  1) SHY/IEF/HYG/LQD/TLT — provenance(backfill_runs) 0건 = bond_model(Stage B) 이전
     구세대 잔재. 금리 시계열을 가격처럼 스케일링 → 방향 반대(TLT Volcker 1979-81
     금리 9→15%에 +67.5%, 진짜면 폭락) + SHY close=0 행 + IEF QE일 -16.9% 등.
     INSERT OR IGNORE라 신형 엔진이 못 덮어씀 → DELETE 후 재생성이 유일한 길.
  2) KR 상장 미국지수 ETF 6종 — USD_KRW_START(1964-05-04) 이전 환율 미적용 행 잔존
     → 경계 봉합점 +25572% 점프. 이전 행 삭제만 필요(신형 엔진은 FX 시작일 이후만 생성).

동작:
  BOND_REGEN : 상장 전 합성행 삭제 → BackfillEngine 재생성(bond_model 듀레이션+쿠폰)
  DELETE_ONLY: 삭제만 (HYG — bond_config 없음, 실측 검증 없는 즉석 모델 추가 금지)
  KR_PREFX   : 1964-05-04 이전 행만 삭제
  공통       : ticker_return_stats 캐시 무효화(손상 데이터 기반 mu/sigma 오염)

실행: python scripts/fix_corrupt_backfill.py [--dry-run]
검증: 스캔 재실행(손상 0) + 봉합점 연속성 + TLT 방향 재확인을 내장.
"""
import sqlite3
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
PRICE_DB = BASE_DIR / "data" / "price_cache" / "price_daily.db"

BOND_REGEN = ["SHY", "IEF", "TLT", "LQD"]
DELETE_ONLY = ["HYG"]
KR_PREFX = ["360200", "360750", "379800", "402970", "446720", "458730"]
FX_START = "1964-05-04"
DRY = "--dry-run" in sys.argv


def main() -> int:
    conn = sqlite3.connect(str(PRICE_DB))

    # ── 1. 채권군: 상장 전(실데이터 이전) 합성행 삭제 ──
    for code in BOND_REGEN + DELETE_ONLY:
        first_real = conn.execute(
            "SELECT MIN(date) FROM price_daily WHERE code=? AND volume>0", (code,)
        ).fetchone()[0]
        if not first_real:
            print(f"[{code}] 실데이터 없음 — 스킵")
            continue
        n = conn.execute(
            "SELECT COUNT(*) FROM price_daily WHERE code=? AND date<? AND (volume=0 OR volume IS NULL)",
            (code, first_real)).fetchone()[0]
        print(f"[{code}] 상장전({first_real} 이전) 합성 {n}행 삭제")
        if not DRY:
            conn.execute(
                "DELETE FROM price_daily WHERE code=? AND date<? AND (volume=0 OR volume IS NULL)",
                (code, first_real))
            # 구세대가 상장 전 배당을 심었으면 같이 제거(현재 0건 확인, 방어적)
            conn.execute("DELETE FROM corporate_actions WHERE code=? AND date<?",
                         (code, first_real))

    # ── 2. KR 6종: FX 시작일 이전 잔재 삭제 ──
    for code in KR_PREFX:
        n = conn.execute(
            "SELECT COUNT(*) FROM price_daily WHERE code=? AND date<?",
            (code, FX_START)).fetchone()[0]
        print(f"[{code}] pre-FX({FX_START} 이전) {n}행 삭제")
        if not DRY:
            conn.execute("DELETE FROM price_daily WHERE code=? AND date<?", (code, FX_START))
            conn.execute("DELETE FROM corporate_actions WHERE code=? AND date<?", (code, FX_START))

    # ── 3. 오염된 통계 캐시 무효화 ──
    all_codes = BOND_REGEN + DELETE_ONLY + KR_PREFX
    ph = ",".join("?" * len(all_codes))
    try:
        n = conn.execute(f"SELECT COUNT(*) FROM ticker_return_stats WHERE code IN ({ph})",
                         all_codes).fetchone()[0]
        print(f"[stats] ticker_return_stats {n}행 무효화")
        if not DRY:
            conn.execute(f"DELETE FROM ticker_return_stats WHERE code IN ({ph})", all_codes)
    except sqlite3.OperationalError:
        pass  # 테이블 없으면 무시
    if not DRY:
        conn.commit()
    conn.close()

    if DRY:
        print("[DRY RUN] 삭제/재생성 안 함.")
        return 0

    # ── 4. bond_model 재생성 ──
    from modules.backfill_engine import BackfillEngine
    engine = BackfillEngine(verbose=True)
    for code in BOND_REGEN:
        res = engine.backfill(code)
        print(f"[regen {code}] {res.get('status')} rows={res.get('rows_written')}")

    # ── 5. 내장 검증 ──
    print("\n=== 검증 1: 손상 재스캔 ===")
    from scripts.scan_backfill_corruption import scan_all
    conn = sqlite3.connect(str(PRICE_DB))
    results = scan_all(conn, BOND_REGEN + DELETE_ONLY + KR_PREFX)
    bad = [r for r in results if r["corrupt"]]
    for r in results:
        print(f"  {r['code']}: volx={r['vol_ratio']:.2f} max={r['max_daily_ret']:.1%} "
              f"{'CORRUPT' if r['corrupt'] else 'OK'}")

    print("=== 검증 2: TLT 방향(Volcker 금리급등 → 하락이어야) ===")
    import pandas as pd
    tlt = pd.read_sql_query(
        "SELECT date, close FROM price_daily WHERE code='TLT' "
        "AND date BETWEEN '1979-06-01' AND '1981-09-30' ORDER BY date", conn)
    direction_ok = True
    if len(tlt) > 10:
        chg = tlt["close"].iloc[-1] / tlt["close"].iloc[0] - 1
        direction_ok = chg < 0
        print(f"  TLT 1979-06→1981-09: {chg:+.1%} ({'OK 하락' if direction_ok else 'FAIL 상승'})")

    print("=== 검증 3: 합성/실데이터 봉합점 연속성 ===")
    seam_ok = True
    for code in BOND_REGEN + KR_PREFX:
        rows = conn.execute(
            "SELECT date, close, volume FROM price_daily WHERE code=? AND close IS NOT NULL "
            "ORDER BY date", (code,)).fetchall()
        prev = None
        worst = 0.0
        for d, c_, v in rows:
            if prev and prev[1]:
                is_seam = (prev[2] in (0, None)) != (v in (0, None))
                if is_seam:
                    worst = max(worst, abs(c_ / prev[1] - 1))
            prev = (d, c_, v)
        ok = worst < 0.20
        seam_ok &= ok
        print(f"  {code}: 봉합점 최대 |ret|={worst:.1%} {'OK' if ok else 'FAIL'}")
    conn.close()

    all_ok = not bad and direction_ok and seam_ok
    print(f"\n{'ALL PASS' if all_ok else 'FAIL — 재검토 필요'}")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
