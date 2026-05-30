# -*- coding: utf-8 -*-
"""
채권 백필 삭제 — volume=0(백필 가격) + 상장 이전 쿠폰만 삭제. 실데이터(volume>0)·실측 분배 보존.

config 변경(듀레이션 등)으로 기존 백필이 stale일 때 정리용. 삭제 후엔 on-demand로 현재 config 재생성.
인자 없으면 kr_etf_list 중 _BOND_CATEGORY_CONFIG 매핑 카테고리 전부(한국 채권 ETF).

실행(서버): python scripts/stage_b_clear_backfill.py [TICKER ...]
"""
import sys
import csv
from pathlib import Path
import sqlite3

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))
from modules.bond_model import _BOND_CATEGORY_CONFIG

PRICE_DB = BASE / "data" / "price_cache" / "price_daily.db"
KR_ETF = BASE / "data" / "meta" / "kr_etf_list.csv"


def _kr_bond_codes():
    cats = set(_BOND_CATEGORY_CONFIG.keys())
    out = []
    with open(KR_ETF, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            if r.get("index") in cats:
                out.append(r["code"])
    return out


def main():
    codes = sys.argv[1:] or _kr_bond_codes()
    conn = sqlite3.connect(str(PRICE_DB))
    print(f"대상 {len(codes)}종 — 백필 삭제 (실데이터 보존)")
    tot_px = tot_cp = cleared = 0
    for code in codes:
        rs = conn.execute(
            "SELECT MIN(date) FROM price_daily WHERE code=? AND volume>0", (code,)).fetchone()[0]
        d_px = conn.execute(
            "DELETE FROM price_daily WHERE code=? AND volume=0", (code,)).rowcount
        d_cp = 0
        if rs:
            d_cp = conn.execute(
                "DELETE FROM corporate_actions WHERE code=? AND date < ?", (code, rs)).rowcount
        conn.commit()
        if d_px or d_cp:
            cleared += 1
            tot_px += d_px; tot_cp += d_cp
    conn.close()
    print(f"완료: {cleared}종 정리, 백필가격 {tot_px}행 + 백필쿠폰 {tot_cp}행 삭제. 실데이터 보존.")


if __name__ == "__main__":
    main()
