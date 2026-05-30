# -*- coding: utf-8 -*-
"""
Stage B 재백필 — 채권 백필(가격 volume=0 + 백필구간 쿠폰)을 삭제 후 현재 config로 재생성.

듀레이션/모델/쿠폰보정 변경 시 사용. 실데이터(volume>0)·실측 분배는 보존.
실행(서버): python scripts/stage_b_rebackfill.py [TICKER ...]
"""
import sys
from pathlib import Path
import sqlite3

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))
from modules.bond_model import _BOND_ETF_CONFIG

PRICE_DB = BASE / "data" / "price_cache" / "price_daily.db"
CODES = sys.argv[1:] or list(_BOND_ETF_CONFIG.keys())


def main():
    conn = sqlite3.connect(str(PRICE_DB))
    print("=" * 60)
    print("Stage B 재백필 (백필 삭제 → 현재 config로 재생성)")
    print("=" * 60)

    # 1) 삭제: volume=0 가격 + 실데이터 시작 이전 쿠폰
    for code in CODES:
        rs = conn.execute(
            "SELECT MIN(date) FROM price_daily WHERE code=? AND volume>0", (code,)).fetchone()[0]
        if rs is None:
            print(f"[{code}] 실데이터 없음 — 스킵 (요청 시 로드 필요)")
            continue
        d_px = conn.execute(
            "DELETE FROM price_daily WHERE code=? AND volume=0", (code,)).rowcount
        d_cp = conn.execute(
            "DELETE FROM corporate_actions WHERE code=? AND date < ?", (code, rs)).rowcount
        conn.commit()
        print(f"[{code}] 실데이터 시작={rs}  삭제: 백필가격 {d_px}행, 백필쿠폰 {d_cp}행")
    conn.close()

    # 2) 재백필
    from modules.backfill_engine import BackfillEngine
    eng = BackfillEngine(verbose=True)
    print("\n재백필:")
    for code in CODES:
        res = eng.backfill(code)
        print(f"  {code}: {res.get('status')} rows={res.get('rows_added')} coupons={res.get('div_rows')} "
              f"{res.get('date_from')}~{res.get('date_to')} dur/model via config")


if __name__ == "__main__":
    main()
