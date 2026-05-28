"""
cleanup_synthetic_contamination.py
price_daily 에 섞인 합성 데이터 전부 제거 후 합법적 백필 재실행.

전략:
  price_daily 의 volume=0 행 = 백필 또는 합성 (둘 다 같은 마커).
  전부 삭제 후 BackfillEngine 재실행 → 백필은 복원, 합성은 이제 price_daily_synthetic 으로 가서 안 돌아옴.

실행:
  python scripts/cleanup_synthetic_contamination.py [--dry-run]
"""
import sys
import sqlite3
from pathlib import Path

BASE_DIR  = Path(__file__).resolve().parent.parent
PRICE_DB  = BASE_DIR / "data" / "price_cache" / "price_daily.db"
DRY_RUN   = "--dry-run" in sys.argv
FORCE     = "--force"   in sys.argv

conn = sqlite3.connect(str(PRICE_DB))

# ── 1. volume=0 행이 있는 종목 목록 ──────────────────────────────
candidates = conn.execute(
    "SELECT DISTINCT code FROM price_daily WHERE volume=0"
).fetchall()
candidates = [r[0] for r in candidates]

if not candidates:
    print("volume=0 행 없음. 오염 없음.")
    conn.close()
    sys.exit(0)

# FX/지수 티커는 volume=0이 정상 → 제외
EXCLUDE = {c for c in candidates if c.startswith("^") or c.endswith("=X") or "/" in c}
candidates = [c for c in candidates if c not in EXCLUDE]
if EXCLUDE:
    print(f"제외 (FX/지수, volume=0 정상): {sorted(EXCLUDE)}")

print(f"\nvolume=0 행 보유 종목 {len(candidates)}개:")
for code in candidates:
    cnt = conn.execute(
        "SELECT COUNT(*) FROM price_daily WHERE code=? AND volume=0", (code,)
    ).fetchone()[0]
    listing = conn.execute(
        "SELECT MIN(date) FROM price_daily WHERE code=? AND volume>0", (code,)
    ).fetchone()[0]
    print(f"  {code}: volume=0 {cnt}행, 실제상장일 {listing}")

if DRY_RUN:
    print("\n[DRY RUN] 실제 삭제 안 함.")
    conn.close()
    sys.exit(0)

if not FORCE:
    input("\n위 종목의 volume=0 행을 전부 삭제하고 백필 재실행합니다. Enter 확인, Ctrl+C 취소: ")

# ── 2. volume=0 행 삭제 ──────────────────────────────────────────
total_price   = 0
total_actions = 0
for code in candidates:
    # 실제 상장일 이전 구간만 삭제 (상장일 이후 volume=0은 거래량 없는 정상 날)
    listing = conn.execute(
        "SELECT MIN(date) FROM price_daily WHERE code=? AND volume>0", (code,)
    ).fetchone()[0]
    if not listing:
        # 실측 데이터 없는 종목 (전부 합성) → 전체 삭제
        c1 = conn.execute("DELETE FROM price_daily WHERE code=?", (code,)).rowcount
        c2 = conn.execute("DELETE FROM corporate_actions WHERE code=?", (code,)).rowcount
    else:
        c1 = conn.execute(
            "DELETE FROM price_daily WHERE code=? AND volume=0 AND date < ?",
            (code, listing)
        ).rowcount
        c2 = conn.execute(
            "DELETE FROM corporate_actions WHERE code=? AND date < ?",
            (code, listing)
        ).rowcount
    if c1 or c2:
        print(f"  {code}: price_daily {c1}행, corporate_actions {c2}행 삭제")
    total_price   += c1
    total_actions += c2

conn.commit()
print(f"\n삭제 완료: price_daily {total_price}행, corporate_actions {total_actions}행")

# ── 3. 백필 재실행 (index 매핑 있는 종목만 복원) ──────────────────
print(f"\n백필 재실행 ({len(candidates)}개 시도):")
sys.path.insert(0, str(BASE_DIR))
from modules.backfill_engine import BackfillEngine
be = BackfillEngine(verbose=False)
ok = skip = fail = 0
for code in sorted(candidates):
    result = be.backfill(code)
    status = result.get("status", "")
    if status == "ok":
        print(f"  ✅ {code}: {result.get('rows_added', 0)}행 백필 복원")
        ok += 1
    elif status in ("no_meta", "no_index_map", "no_pre_data", "no_etf_data"):
        print(f"  — {code}: 백필 불가 ({status}) → 합성 전용 종목이었음")
        skip += 1
    else:
        print(f"  ⚠️  {code}: {status}")
        fail += 1

conn.close()
print(f"\n완료. 백필복원 {ok}개, 스킵 {skip}개, 실패 {fail}개")
