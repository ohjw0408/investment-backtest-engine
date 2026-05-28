"""
cleanup_synthetic_contamination.py
서버에서 1회 실행: price_daily / corporate_actions에 오염된 합성 데이터 삭제 후
해당 종목 합법적 백필 재실행.

실행 방법:
  python scripts/cleanup_synthetic_contamination.py [--dry-run]
"""
import sys
import sqlite3
from pathlib import Path

BASE_DIR   = Path(__file__).resolve().parent.parent
PRICE_DB   = BASE_DIR / "data" / "price_cache" / "price_daily.db"
DRY_RUN    = "--dry-run" in sys.argv

conn = sqlite3.connect(str(PRICE_DB))

# 1. backfill_runs 테이블 존재 여부 확인
tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
if "backfill_runs" not in tables:
    print("backfill_runs 테이블 없음 → 오염 이력 없음. 종료.")
    conn.close()
    sys.exit(0)

# 2. synthetic 실행 이력 수집
synth_runs = conn.execute(
    "SELECT code, date_from, date_to FROM backfill_runs WHERE method='synthetic_gbm_v1'"
).fetchall()

if not synth_runs:
    print("synthetic 실행 이력 없음. 종료.")
    conn.close()
    sys.exit(0)

print(f"synthetic 오염 종목 {len(set(r[0] for r in synth_runs))}개 발견:")
for code, date_from, date_to in synth_runs:
    print(f"  {code}: {date_from} ~ {date_to}")

if DRY_RUN:
    print("\n[DRY RUN] 실제 삭제 안 함.")
    conn.close()
    sys.exit(0)

# 3. price_daily / corporate_actions 에서 synthetic 구간 volume=0 행 삭제
deleted_price = 0
deleted_action = 0
affected_codes = set()
for code, date_from, date_to in synth_runs:
    if not date_from or not date_to:
        continue
    c1 = conn.execute(
        "DELETE FROM price_daily WHERE code=? AND date BETWEEN ? AND ? AND volume=0",
        (code, date_from, date_to)
    ).rowcount
    c2 = conn.execute(
        "DELETE FROM corporate_actions WHERE code=? AND date BETWEEN ? AND ?",
        (code, date_from, date_to)
    ).rowcount
    if c1 > 0 or c2 > 0:
        print(f"  {code}: price_daily {c1}행 삭제, corporate_actions {c2}행 삭제")
        deleted_price  += c1
        deleted_action += c2
        affected_codes.add(code)

conn.commit()
print(f"\n삭제 완료: price_daily {deleted_price}행, corporate_actions {deleted_action}행")

# 4. 영향받은 종목 합법적 백필 재실행
if affected_codes:
    print(f"\n백필 재실행 ({len(affected_codes)}개):")
    sys.path.insert(0, str(BASE_DIR))
    from modules.backfill_engine import BackfillEngine
    be = BackfillEngine(verbose=True)
    for code in sorted(affected_codes):
        result = be.backfill(code)
        print(f"  {code}: {result.get('status')} (rows_added={result.get('rows_added', 0)})")

conn.close()
print("\n완료.")
