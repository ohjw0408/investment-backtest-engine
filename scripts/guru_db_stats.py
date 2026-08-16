"""guru_holdings.db 품질 지표 출력 / 리빌드 전후 비교.

분기 자동 갱신(guru-resync-13f.yml)이 **망가진 DB를 커밋하는 것**을 막는 안전망이다.
OpenFIGI 키가 빠지면 CUSIP→티커가 전멸해 보유가 전부 미매핑이 되는데, 그대로 커밋되면
prod의 대가 카드·비교 곡선·시점별 백테가 통째로 죽는다.

사용:
  python scripts/guru_db_stats.py                       # 현재 DB 지표(JSON)
  python scripts/guru_db_stats.py --before /tmp/old.db  # 리빌드 전후 비교, 퇴행이면 exit 1
"""
import argparse
import json
import sqlite3
import sys


def stats(path):
    con = sqlite3.connect(path)
    try:
        total = con.execute("SELECT COUNT(*) FROM holdings").fetchone()[0]
        mapped = con.execute(
            "SELECT COUNT(*) FROM holdings WHERE ticker IS NOT NULL").fetchone()[0]
        return {
            "filings": con.execute("SELECT COUNT(*) FROM filings").fetchone()[0],
            "holdings": total,
            "mapped_ratio": round(mapped / total, 4) if total else 0.0,
            "gurus": con.execute("SELECT COUNT(*) FROM gurus").fetchone()[0],
            "with_period": con.execute(
                "SELECT COUNT(*) FROM gurus WHERE latest_period IS NOT NULL").fetchone()[0],
            "latest": con.execute("SELECT MAX(period) FROM filings").fetchone()[0],
        }
    finally:
        con.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="data/meta/guru_holdings.db")
    ap.add_argument("--before", help="리빌드 직전 DB 사본. 주면 퇴행 검사")
    ap.add_argument("--max-drop", type=float, default=0.05,
                    help="허용 매핑률 하락폭(기본 5%p)")
    args = ap.parse_args()

    now = stats(args.db)
    print(json.dumps(now, ensure_ascii=False))
    if not args.before:
        return 0

    old = stats(args.before)
    print(json.dumps(old, ensure_ascii=False), file=sys.stderr)

    fails = []
    if now["holdings"] == 0 or now["filings"] == 0:
        fails.append("빈 DB")
    if now["filings"] < old["filings"]:
        fails.append(f"filings 감소 {old['filings']}→{now['filings']}")
    if now["with_period"] < old["with_period"]:
        fails.append(f"공시 있는 대가 감소 {old['with_period']}→{now['with_period']}")
    if now["mapped_ratio"] < old["mapped_ratio"] - args.max_drop:
        fails.append(f"티커 매핑률 하락 {old['mapped_ratio']:.2%}→{now['mapped_ratio']:.2%} "
                     "(OPENFIGI_API_KEY 확인)")
    if fails:
        print("REGRESSION: " + " / ".join(fails), file=sys.stderr)
        return 1
    print("OK: 퇴행 없음", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
