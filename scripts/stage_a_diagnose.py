# -*- coding: utf-8 -*-
"""
Stage A step 2 사전 진단 — 삭제 전 현황 파악.

목적: SCHD/458730의 price_daily volume=0 행이 '백필'인지 '합성(GBM)'인지 구분.
- 백필: DJUSDIV_PROXY 스케일 가격. price_daily에 volume=0로 저장.
- 합성: 별도 테이블 price_daily_synthetic (커밋 374f0a5로 분리됨).
삭제 안전성 확인 후 step 2 진행.

실행: python scripts/stage_a_diagnose.py
"""
import sqlite3
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

BASE = Path(__file__).resolve().parent.parent
PRICE_DB = BASE / "data" / "price_cache" / "price_daily.db"
CODES = ["SCHD", "458730"]
SEP = "=" * 80


def main():
    c = sqlite3.connect(str(PRICE_DB))
    tabs = [r[0] for r in c.execute(
        "SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    print("tables:", tabs)

    for code in CODES:
        print(f"\n{SEP}\n{code}\n{SEP}")

        # price_daily: volume=0 vs volume>0
        row = c.execute(
            "SELECT COUNT(*), "
            "SUM(CASE WHEN volume=0 THEN 1 ELSE 0 END), "
            "SUM(CASE WHEN volume>0 THEN 1 ELSE 0 END), "
            "MIN(date), MAX(date), "
            "MIN(CASE WHEN volume>0 THEN date END), "
            "MAX(CASE WHEN volume=0 THEN date END) "
            "FROM price_daily WHERE code=?", (code,)).fetchone()
        print(f"price_daily: total={row[0]} vol0(백필추정)={row[1]} vol>0(실데이터)={row[2]}")
        print(f"  전체기간 {row[3]}~{row[4]}")
        print(f"  실데이터 시작(vol>0 MIN)={row[5]}  백필 끝(vol=0 MAX)={row[6]}")

        # price_daily_synthetic (별도 합성 테이블)
        if "price_daily_synthetic" in tabs:
            r = c.execute(
                "SELECT COUNT(*), MIN(date), MAX(date) "
                "FROM price_daily_synthetic WHERE code=?", (code,)).fetchone()
            print(f"price_daily_synthetic: rows={r[0]} {r[1]}~{r[2]}")
        else:
            print("price_daily_synthetic: (테이블 없음)")

        # provenance
        for t in ("price_daily_source", "backfill_runs"):
            if t in tabs:
                n = c.execute(f"SELECT COUNT(*) FROM {t} WHERE code=?", (code,)).fetchone()[0]
                print(f"{t}: {n} rows")

        # 합성 행이 price_daily의 volume=0와 날짜 겹치나? (오염 여부)
        if "price_daily_synthetic" in tabs:
            overlap = c.execute(
                "SELECT COUNT(*) FROM price_daily p "
                "JOIN price_daily_synthetic s ON p.code=s.code AND p.date=s.date "
                "WHERE p.code=? AND p.volume=0", (code,)).fetchone()[0]
            print(f"⚠️ price_daily(vol=0) ∩ price_daily_synthetic 날짜겹침: {overlap}건")

        # corporate_actions 배당 (실측 vs 백필구간)
        r = c.execute(
            "SELECT COUNT(*), MIN(CASE WHEN dividend>0 THEN date END), "
            "MAX(CASE WHEN dividend>0 THEN date END) "
            "FROM corporate_actions WHERE code=? AND dividend>0", (code,)).fetchone()
        print(f"corporate_actions 배당>0: {r[0]}건  {r[1]}~{r[2]}")

    print(f"\n{SEP}\n판정 가이드\n{SEP}")
    print("- vol0 행 날짜범위가 실데이터 시작 이전이고, price_daily_synthetic 겹침=0이면")
    print("  → price_daily vol=0 = 순수 백필 → 해당 code만 삭제 안전.")
    print("- 겹침>0이면 합성 행이 price_daily에 섞인 것 → 삭제 시 주의 필요.")
    c.close()


if __name__ == "__main__":
    main()
