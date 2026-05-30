# -*- coding: utf-8 -*-
"""
Stage B 한국 채권 ETF 일괄 롤아웃 — 실데이터 로드 + 백필 재생성(stale 정리).

대상: kr_etf_list 중 _BOND_CATEGORY_CONFIG에 매핑된 카테고리 ETF 전부.
종목별: get_price(실데이터 로드) → volume=0 백필 + 실데이터 이전 쿠폰 삭제 → backfill() 재생성.
실데이터 없는(yfinance 미커버/상장폐지) 종목은 스킵.

실행(서버): python scripts/stage_b_kr_rollout.py
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
CATS = set(_BOND_CATEGORY_CONFIG.keys())


def _codes():
    out = []
    with open(KR_ETF, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            if r.get("index") in CATS:
                out.append((r["code"], r["index"], r.get("name", r["code"])))
    return out


def main():
    from modules.portfolio_engine import PortfolioEngine
    from modules.backfill_engine import BackfillEngine
    pe = PortfolioEngine()
    eng = BackfillEngine(verbose=False)
    codes = _codes()
    print(f"대상 {len(codes)}종 (매핑 카테고리)")
    ok = skip = fail = 0
    for i, (code, cat, name) in enumerate(codes, 1):
        try:
            pe.loader.get_price(code, "1990-01-01", "2026-12-31", allow_synthetic=False)
        except Exception:
            pass
        conn = sqlite3.connect(str(PRICE_DB))
        rs = conn.execute(
            "SELECT MIN(date) FROM price_daily WHERE code=? AND volume>0", (code,)).fetchone()[0]
        if rs is None:
            conn.close(); skip += 1
            print(f"[{i}/{len(codes)}] {code} {name[:18]} — 실데이터 없음 SKIP")
            continue
        conn.execute("DELETE FROM price_daily WHERE code=? AND volume=0", (code,))
        conn.execute("DELETE FROM corporate_actions WHERE code=? AND date < ?", (code, rs))
        conn.commit(); conn.close()
        try:
            res = eng.backfill(code)
            st = res.get("status")
            if st == "ok":
                ok += 1
                print(f"[{i}/{len(codes)}] {code} {name[:18]} [{cat}] ok rows={res.get('rows_added')} coupons={res.get('div_rows')}")
            else:
                fail += 1
                print(f"[{i}/{len(codes)}] {code} {name[:18]} backfill={st}")
        except Exception as e:
            fail += 1
            print(f"[{i}/{len(codes)}] {code} {name[:18]} ERROR {type(e).__name__}: {e}")
    print(f"\n완료: ok={ok} skip(실데이터없음)={skip} fail={fail}")


if __name__ == "__main__":
    main()
