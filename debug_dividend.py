# -*- coding: utf-8 -*-
"""
배당 0원 버그 디버그 스크립트.

증상: TIGER 미국배당다우존스(458730) 배당 전부 0, SCHD 0 많음.
가설: 백필 가격 구간에 corporate_actions 배당 row 없음 → 시뮬 윈도우 대부분 배당=0.

이 스크립트는 추정 안 하고 DB + 로더 + 분석기를 실측한다.
실행: python debug_dividend.py
"""
import sqlite3
import sys
import pandas as pd
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

pd.set_option("display.width", 200)
pd.set_option("display.max_rows", 80)

BASE = Path(__file__).resolve().parent
PRICE_DB = BASE / "data" / "price_cache" / "price_daily.db"

# 조사 대상 — 사용자 보고 종목 + 프록시 체인
CODES = ["458730", "SCHD", "SDY", "DVY", "DJUSDIV_PROXY", "DJUSDIV100"]

SEP = "=" * 90


def hdr(t):
    print(f"\n{SEP}\n{t}\n{SEP}")


def section_db():
    hdr("[1] price_daily.db 직접 조사")
    conn = sqlite3.connect(str(PRICE_DB))

    # 어떤 테이블 있나
    tabs = [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    print("테이블:", tabs)

    for code in CODES:
        print(f"\n--- {code} ---")
        # price_daily
        row = conn.execute(
            "SELECT COUNT(*), MIN(date), MAX(date), "
            "SUM(CASE WHEN volume=0 THEN 1 ELSE 0 END) "
            "FROM price_daily WHERE code=?", (code,)).fetchone()
        print(f"  price_daily   : rows={row[0]}  {row[1]}~{row[2]}  volume0(백필추정)={row[3]}")

        # corporate_actions (실측)
        row = conn.execute(
            "SELECT COUNT(*), SUM(CASE WHEN dividend>0 THEN 1 ELSE 0 END), "
            "MIN(CASE WHEN dividend>0 THEN date END), "
            "MAX(CASE WHEN dividend>0 THEN date END), "
            "SUM(dividend) "
            "FROM corporate_actions WHERE code=?", (code,)).fetchone()
        print(f"  corp_actions  : rows={row[0]}  div>0={row[1]}  div기간={row[2]}~{row[3]}  div합={row[4]}")

        # corporate_actions_synthetic
        try:
            row = conn.execute(
                "SELECT COUNT(*), SUM(CASE WHEN dividend>0 THEN 1 ELSE 0 END), "
                "MIN(CASE WHEN dividend>0 THEN date END), "
                "MAX(CASE WHEN dividend>0 THEN date END) "
                "FROM corporate_actions_synthetic WHERE code=?", (code,)).fetchone()
            print(f"  corp_synth    : rows={row[0]}  div>0={row[1]}  div기간={row[2]}~{row[3]}")
        except sqlite3.OperationalError:
            print("  corp_synth    : (테이블 없음)")

        # 연도별 배당 row 개수 (실측 테이블)
        yr = conn.execute(
            "SELECT substr(date,1,4) yr, COUNT(*), ROUND(SUM(dividend),4) "
            "FROM corporate_actions WHERE code=? AND dividend>0 "
            "GROUP BY yr ORDER BY yr", (code,)).fetchall()
        if yr:
            print("  연도별 배당(실측): " + ", ".join(f"{y}:{c}건/{s}" for y, c, s in yr))

    # provenance (백필 이력)
    if "backfill_runs" in tabs:
        print("\n--- backfill_runs (백필 이력) ---")
        try:
            df = pd.read_sql(
                "SELECT code, proxy_code, confidence, date_from, date_to, "
                "rows_written, div_rows_written FROM backfill_runs "
                "WHERE code IN ({}) ORDER BY code".format(
                    ",".join("?" * len(CODES))), conn, params=CODES)
            print(df.to_string(index=False) if not df.empty else "  (해당 code 백필 이력 없음)")
        except Exception as e:
            print("  backfill_runs 조회 실패:", e)

    conn.close()


def section_getprice():
    hdr("[2] PriceLoader.get_price — 시뮬이 실제로 받는 배당")
    from modules.price_loader import PriceLoader
    pl = PriceLoader()

    # 20년 윈도우 가정
    start, end = "2004-01-01", "2024-01-01"
    for code in ["458730", "SCHD"]:
        for allow_syn in (False, True):
            try:
                df = pl.get_price(code, start, end, allow_synthetic=allow_syn)
            except Exception as e:
                print(f"\n{code} allow_synthetic={allow_syn}: get_price 실패 — {e}")
                continue
            if "dividend" not in df.columns:
                print(f"\n{code} allow_synthetic={allow_syn}: dividend 컬럼 없음! cols={list(df.columns)}")
                continue
            df["date"] = pd.to_datetime(df["date"])
            div_total = float(df["dividend"].sum())
            div_days = int((df["dividend"] > 0).sum())
            print(f"\n{code} allow_synthetic={allow_syn}: "
                  f"rows={len(df)} {df['date'].min().date()}~{df['date'].max().date()} "
                  f"배당합={div_total:.4f} 배당일수={div_days}")
            if div_days:
                by_yr = (df[df["dividend"] > 0]
                         .assign(yr=df["date"].dt.year)
                         .groupby("yr")["dividend"].agg(["count", "sum"]))
                print("  연도별:", dict(zip(by_yr.index, by_yr["count"])))


def section_analyzer():
    hdr("[3] 단일계좌 계산기 실행 — 실제 결과 배당 필드")
    from calculator_logic import run_calculator_logic
    for code in ["458730", "SCHD"]:
        body = {
            "accounts": [{
                "initial_capital": 0,
                "monthly_contribution": 500000,
                "tickers": [{"code": code, "weight": 1.0}],
                "account_type": "위탁",
            }],
            "tickers": [{"code": code, "weight": 1.0}],
            "initial_capital": 0,
            "monthly_contribution": 500000,
            "years": 20,
            "dividend_mode": "reinvest",
            "tax_enabled": False,
            "rebal_mode": "monthly",
        }
        try:
            res = run_calculator_logic(body)
        except Exception as e:
            print(f"\n{code}: run_calculator_logic 실패 — {type(e).__name__}: {e}")
            continue
        dist = res.get("distribution", {})
        print(f"\n{code}:")
        print(f"  no_dividend={dist.get('no_dividend')}  div_data_start={dist.get('div_data_start')}  "
              f"div_cases_count={dist.get('div_cases_count')}")
        for k in ("total_dividend", "last_year_dividend", "dividend_cagr",
                  "dividend_yield_on_cost", "dividend_mdd"):
            v = dist.get(k)
            if isinstance(v, dict):
                print(f"  {k}: p50={v.get('p50')}")
            else:
                print(f"  {k}: {v}")


if __name__ == "__main__":
    section_db()
    section_getprice()
    section_analyzer()
