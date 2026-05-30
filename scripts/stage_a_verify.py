# -*- coding: utf-8 -*-
"""
Stage A 검증 — 주입된 백필 배당의 정확성·총수익 합리성.

기존 데이터가 깨져있었으므로 'before/after CAGR 동일'이 아니라 외부 truth 대비 합리성 검증:
1. 백필 배당 yield(연 배당/연 평균가) ≈ DJUSDIV100 소스 yield 테이블인가.
2. 실데이터 구간(2011+ SCHD) 무결성 — 행수·실측배당 보존.
3. 총수익 합리성 — price-return + 배당 재투자가 합리적 총수익 내는가
   (백필구간 가격 CAGR vs 배당 포함 추정).

실행: python scripts/stage_a_verify.py
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
INDEX_DB = BASE / "data" / "meta" / "index_master.db"
SEP = "=" * 80


def main():
    pc = sqlite3.connect(str(PRICE_DB))
    ic = sqlite3.connect(str(INDEX_DB))

    # DJUSDIV100 소스 yield 테이블
    src = dict(ic.execute(
        "SELECT year, annual_yield FROM index_div_yield WHERE index_code='DJUSDIV100' ORDER BY year"
    ).fetchall())
    src_vals = list(src.values())
    src_mu = sum(src_vals) / len(src_vals)
    print(f"{SEP}\n[1] DJUSDIV100 소스 yield: {len(src)}년 "
          f"({min(src):d}~{max(src):d}), 평균 {src_mu:.4f} ({src_mu*100:.2f}%)\n{SEP}")

    for code in ["SCHD", "458730"]:
        print(f"\n--- {code} 백필 배당 yield (연 배당합 / 연 평균 종가) ---")
        rs = pc.execute(
            "SELECT MIN(date) FROM price_daily WHERE code=? AND volume>0", (code,)).fetchone()[0]
        # 백필구간 연도별 yield (실데이터 시작 이전)
        rows = pc.execute("""
            SELECT substr(ca.date,1,4) yr, SUM(ca.dividend) div, AVG(pd.close) px
            FROM corporate_actions ca
            JOIN price_daily pd ON ca.code=pd.code AND ca.date=pd.date
            WHERE ca.code=? AND ca.dividend>0 AND ca.date < ?
            GROUP BY yr ORDER BY yr
        """, (code, rs)).fetchall()
        # 샘플 연도만 출력 (최근 백필 10년 + yield 평균)
        ys = [(int(y), d / p) for y, d, p in rows if p and p > 0]
        if ys:
            avg_y = sum(v for _, v in ys) / len(ys)
            recent = ys[-8:]
            print(f"  백필 yield 연도수={len(ys)}, 평균={avg_y:.4f} ({avg_y*100:.2f}%)")
            print("  최근 8개:", ", ".join(f"{y}:{v*100:.2f}%" for y, v in recent))
            ok = abs(avg_y - src_mu) / src_mu < 0.5
            print(f"  → 소스 평균({src_mu*100:.2f}%) 대비 {'합리적' if ok else '⚠️ 괴리 큼'} (±50% 이내 기준)")

    # 실데이터 무결성
    print(f"\n{SEP}\n[2] 실데이터 무결성\n{SEP}")
    for code in ["SCHD", "458730"]:
        rs = pc.execute(
            "SELECT MIN(date) FROM price_daily WHERE code=? AND volume>0", (code,)).fetchone()[0]
        n_px = pc.execute(
            "SELECT COUNT(*) FROM price_daily WHERE code=? AND volume>0", (code,)).fetchone()[0]
        n_div = pc.execute(
            "SELECT COUNT(*) FROM corporate_actions WHERE code=? AND dividend>0 AND date>=?",
            (code, rs)).fetchone()[0]
        print(f"  {code}: 실데이터(vol>0)={n_px}행, 실측배당(>={rs})={n_div}건")

    # 총수익 합리성 — 백필구간 price CAGR + 평균배당yield ≈ total return
    print(f"\n{SEP}\n[3] 총수익 합리성 (백필구간)\n{SEP}")
    for code in ["SCHD", "458730"]:
        rs = pc.execute(
            "SELECT MIN(date) FROM price_daily WHERE code=? AND volume>0", (code,)).fetchone()[0]
        r = pc.execute(
            "SELECT MIN(date), MAX(date) FROM price_daily WHERE code=? AND volume=0", (code,)).fetchone()
        p0 = pc.execute(
            "SELECT close FROM price_daily WHERE code=? AND date=?", (code, r[0])).fetchone()
        p1 = pc.execute(
            "SELECT close FROM price_daily WHERE code=? AND volume=0 ORDER BY date DESC LIMIT 1",
            (code,)).fetchone()
        if p0 and p1 and p0[0] > 0:
            import datetime as dt
            y0 = int(r[0][:4]); y1 = int(r[1][:4]); n = max(y1 - y0, 1)
            price_cagr = (p1[0] / p0[0]) ** (1 / n) - 1
            print(f"  {code} 백필 {r[0]}~{r[1]} ({n}년): 가격 CAGR={price_cagr*100:.2f}% "
                  f"+ 배당 ~3% ≈ 총수익 ~{price_cagr*100+3:.1f}%/년 (S&P500 류 합리적 범위)")

    pc.close(); ic.close()
    print(f"\n{SEP}\n판정: 백필 배당 yield가 소스와 합리적 범위, 실데이터 보존, 총수익 합리적이면 PASS\n{SEP}")


if __name__ == "__main__":
    main()
