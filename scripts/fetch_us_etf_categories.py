# -*- coding: utf-8 -*-
"""US ETF 분류 원천 수집 — yfinance info의 category/fundFamily.

symbol_master.db의 US ETF 전 종목을 대상으로 data/meta/us_etf_categories.csv에
누적 기록한다(append, 재실행 시 이미 수집한 코드는 스킵 = 중단 후 재개 가능).

CSV: code,category,family,status,fetched_at
  status: ok(카테고리 있음) / empty(응답엔 성공, 카테고리 없음) / err(요청 실패)
err 행은 재실행 시 재시도한다(empty는 재시도 안 함 — 야후에 진짜 없는 것).
"""
import csv
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from config import SYMBOL_DB_PATH  # noqa: E402

OUT_CSV = ROOT / "data" / "meta" / "us_etf_categories.csv"
BASE_SLEEP = 0.3          # 정상 응답 간 간격 (야후 레이트리밋 회피)
ERR_BACKOFF = (20, 60, 180, 300)   # 연속 오류 시 점증 대기(초)
GIVEUP_STREAK = 40        # 백오프 다 쓰고도 이만큼 연속 실패면 중단(차단 상태)


def _load_done():
    done = set()
    if OUT_CSV.exists():
        with open(OUT_CSV, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if row.get("status") in ("ok", "empty"):
                    done.add(row["code"])
    return done


def _fetch_one(code):
    import yfinance as yf
    try:
        info = yf.Ticker(code).info or {}
        cat = (info.get("category") or "").strip()
        fam = (info.get("fundFamily") or "").strip()
        return (code, cat, fam, "ok" if cat else "empty")
    except Exception:
        return (code, "", "", "err")


def main():
    conn = sqlite3.connect(str(SYMBOL_DB_PATH))
    codes = [r[0] for r in conn.execute(
        "SELECT code FROM symbols WHERE is_etf=1 AND country!='KR' ORDER BY code")]
    conn.close()

    done = _load_done()
    todo = [c for c in codes if c not in done]
    print(f"total={len(codes)} done={len(done)} todo={len(todo)}", flush=True)
    if not todo:
        return

    new_file = not OUT_CSV.exists()
    n_ok = n_empty = n_err = 0
    streak = 0
    t0 = time.time()
    with open(OUT_CSV, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new_file:
            w.writerow(["code", "category", "family", "status", "fetched_at"])
        for i, c in enumerate(todo, 1):
            code, cat, fam, status = _fetch_one(c)
            if status == "err":
                n_err += 1
                streak += 1
                back = ERR_BACKOFF[min(streak - 1, len(ERR_BACKOFF) - 1)]
                if streak > GIVEUP_STREAK:
                    print(f"ABORT: {streak} consecutive errors — blocked. "
                          f"resume later.", flush=True)
                    break
                time.sleep(back)
            else:
                streak = 0
                if status == "ok":
                    n_ok += 1
                else:
                    n_empty += 1
                time.sleep(BASE_SLEEP)
            w.writerow([code, cat, fam, status,
                        datetime.now(timezone.utc).isoformat(timespec="seconds")])
            f.flush()
            if i % 100 == 0:
                rate = i / max(time.time() - t0, 1)
                eta_min = (len(todo) - i) / max(rate, 0.01) / 60
                print(f"[{i}/{len(todo)}] ok={n_ok} empty={n_empty} err={n_err} "
                      f"rate={rate:.1f}/s eta={eta_min:.0f}m", flush=True)
    print(f"DONE ok={n_ok} empty={n_empty} err={n_err} elapsed={(time.time()-t0)/60:.1f}m",
          flush=True)


if __name__ == "__main__":
    main()
