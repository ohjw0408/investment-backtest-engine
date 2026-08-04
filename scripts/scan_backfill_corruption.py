# -*- coding: utf-8 -*-
"""백필/합성 구간 손상 스캔 (출시완성도 B-1).

price_daily의 vol=0(백필/합성) 구간을 실데이터 구간과 비교해 손상 종목을 찾는다.
판정 기준 (risk_return_logic._clean_deep_points 게이트와 동일 철학 + 오탐 보정):
  - 합성 일수익률 std가 실데이터의 SYNTH_VOL_RATIO_MAX(2.5)배 초과
    (단 실데이터 std는 REAL_STD_FLOOR로 하한 — 아래 참조)
  - 또는 합성 구간 단일일 |수익률| > SYNTH_DAILY_MAX(50%)
  - 또는 close<=0 행 존재 (SHY 구세대 잔재 패턴)
  수익률은 **연속 거래일(갭<=7일)만** 계산 — 산재 vol=0 행(000660 등 실데이터 사이
  드문드문 낀 행)을 몇 달 갭 건너 비교해 가짜 점프를 만드는 오탐 방지.
  ※ 30%대 단일일은 실제 역사(1980 금파동 +37.8%, 걸프전 유가 -33.4%)가 있어 50%로.

용도:
  1) B-1 일회성 진단/재생성 검증:  python scripts/scan_backfill_corruption.py
  2) 특정 종목만:                  python scripts/scan_backfill_corruption.py SHY IEF
  3) B-2 일일 무결성 beat에서 재사용(모듈 import: scan_all(conn))

출력: 종목별 [ratio, max|ret|, 판정]. exit 1 = 손상 존재.
"""
import sqlite3
import sys
from pathlib import Path

import numpy as np
import pandas as pd

BASE_DIR = Path(__file__).resolve().parent.parent
PRICE_DB = BASE_DIR / "data" / "price_cache" / "price_daily.db"

SYNTH_VOL_RATIO_MAX = 2.5
SYNTH_DAILY_MAX = 0.50
# 실데이터 std 하한. 비율은 "합성이 이 종목답지 않게 요동치나"를 보려는 것인데, 분모가
# 0에 가까우면 정상 합성도 무조건 배수를 넘는다. 만기매칭형 회사채 ETF(`26-04`·`만기자동연장`)
# 20종은 만기가 다가와 실데이터 std가 0.0003~0.0014(사실상 정지)라 합성 std 0.0031
# (= 일반 채권 ETF 0.002~0.0037과 같은 정상 수준)에도 비율 2.6~9.7로 매일 오탐이 났다.
# 하한 통과선 = 0.0018×2.5 = 일변동성 0.0045(연 7%) — 이 아래로는 가짜 역사를 만들 수 없다.
# SHY 구손상(합성 std 0.016)은 하한을 써도 8.9배로 여전히 검출된다.
REAL_STD_FLOOR = 0.0018
MAX_GAP_DAYS = 7           # 이 이상 날짜 갭 건너면 수익률 계산 제외(산재 행 오탐 방지)
MIN_SEG_ROWS = 30          # 세그먼트가 이보다 짧으면 통계 불충분 → 스킵


def _is_nonequity_code(code: str) -> bool:
    """FX/지수/선물/금현물은 volume=0이 정상 — 스캔 제외."""
    return (code.startswith("^") or code.endswith("=X") or code.endswith("=F")
            or "/" in code or code == "KRX_GOLD")


def scan_code(conn: sqlite3.Connection, code: str):
    """단일 종목 손상 판정. 반환 None=합성 없음/판정불가, dict=측정치."""
    df = pd.read_sql_query(
        "SELECT date, close, volume FROM price_daily "
        "WHERE code=? AND close IS NOT NULL ORDER BY date", conn, params=(code,))
    if df.empty:
        return None
    # 휴장일 복제행 제외: yfinance가 KR 휴장일에 전일 종가를 vol=0으로 복제해 뱉는다.
    # 이 행이 며칠 간격으로 산재하면 실제 주간 변동(예: 005380 2000-06 +42%)이
    # 합성 점프로 오판됨(2026-07-14 오탐). 전일 종가와 동일한 vol=0 행은 정보 0 → 제거.
    vol0 = (df["volume"] == 0) | (df["volume"].isna())
    df = df[~(vol0 & (df["close"] == df["close"].shift(1)))]
    synth = df[(df["volume"] == 0) | (df["volume"].isna())].copy()
    real = df[df["volume"] > 0].copy()
    if len(synth) < MIN_SEG_ROWS or len(real) < MIN_SEG_ROWS:
        return None
    n_nonpos = int((synth["close"] <= 0).sum())  # close<=0 = 무조건 손상
    synth = synth[synth["close"] > 0]

    def _contiguous_rets(seg: pd.DataFrame) -> pd.Series:
        """연속 거래일(갭<=MAX_GAP_DAYS)끼리만 수익률 — 산재 행 갭 점프 오탐 방지."""
        d = pd.to_datetime(seg["date"])
        ret = seg["close"].pct_change(fill_method=None)
        gap_ok = d.diff().dt.days <= MAX_GAP_DAYS
        return ret[gap_ok].dropna()

    s_ret = _contiguous_rets(synth)
    r_ret = _contiguous_rets(real)
    # 실데이터 std가 0이어도 하한(REAL_STD_FLOOR)으로 판정 가능 — 분모 0만 피하면 된다.
    if len(s_ret) < MIN_SEG_ROWS or np.isnan(r_ret.std()):
        if n_nonpos:
            return {"code": code, "synth_rows": len(synth), "real_rows": len(real),
                    "real_std": float("nan"), "synth_std": float("nan"),
                    "vol_ratio": float("nan"), "max_daily_ret": float("nan"),
                    "nonpos_rows": n_nonpos, "corrupt": True}
        return None
    ratio = float(s_ret.std() / max(float(r_ret.std()), REAL_STD_FLOOR))
    max_abs = float(s_ret.abs().max())
    return {
        "code": code,
        "synth_rows": len(synth),
        "real_rows": len(real),
        "real_std": float(r_ret.std()),
        "synth_std": float(s_ret.std()),
        "vol_ratio": ratio,
        "max_daily_ret": max_abs,
        "nonpos_rows": n_nonpos,
        "corrupt": (ratio > SYNTH_VOL_RATIO_MAX or max_abs > SYNTH_DAILY_MAX
                    or n_nonpos > 0),
    }


def scan_all(conn: sqlite3.Connection, codes=None):
    if codes is None:
        codes = [r[0] for r in conn.execute(
            "SELECT DISTINCT code FROM price_daily WHERE volume=0 OR volume IS NULL")]
        codes = [c for c in codes if not _is_nonequity_code(c)]
    results = []
    for code in sorted(codes):
        r = scan_code(conn, code)
        if r is not None:
            results.append(r)
    return results


def main() -> int:
    codes = sys.argv[1:] or None
    conn = sqlite3.connect(str(PRICE_DB))
    results = scan_all(conn, codes)
    conn.close()
    corrupt = [r for r in results if r["corrupt"]]
    print(f"{'code':<10} {'synth':>7} {'real':>7} {'r_std':>8} {'s_std':>8} {'volx':>7} "
          f"{'max|ret|':>9} {'close<=0':>8}  판정")
    for r in results:
        flag = "CORRUPT" if r["corrupt"] else "OK"
        print(f"{r['code']:<10} {r['synth_rows']:>7} {r['real_rows']:>7} "
              f"{r.get('real_std', float('nan')):>8.5f} {r.get('synth_std', float('nan')):>8.5f} "
              f"{r['vol_ratio']:>7.2f} {r['max_daily_ret']:>9.1%} {r.get('nonpos_rows',0):>8}  {flag}")
    print(f"\n스캔 {len(results)}종목, 손상 {len(corrupt)}종목: {[r['code'] for r in corrupt]}")
    return 1 if corrupt else 0


if __name__ == "__main__":
    sys.exit(main())
