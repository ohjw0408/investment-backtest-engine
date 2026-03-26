"""
test_usdkrw_autoupdate.py
────────────────────────────────────────────────────────────────────────────────
USD/KRW 자동 업데이트 테스트

테스트 항목:
1. ecos_api_key.txt 존재 확인
2. PriceLoader 생성 시 자동 업데이트 실행 확인
3. DB 최신 날짜가 오늘(또는 최근 거래일)인지 확인
4. 최신 환율값 정상 범위 확인
────────────────────────────────────────────────────────────────────────────────
"""

import sys
import sqlite3
from datetime import date, timedelta
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from modules.price_loader import PriceLoader

BASE_DIR     = Path(__file__).resolve().parent.parent
META_DIR     = BASE_DIR / "data" / "meta"
INDEX_DB     = META_DIR / "index_master.db"
KEY_PATH     = META_DIR / "ecos_api_key.txt"

print("=" * 65)
print("USD/KRW 자동 업데이트 테스트")
print("=" * 65)

# ── 1. API 키 파일 확인 ────────────────────────────────────
print("\n[1] ecos_api_key.txt 확인")
if KEY_PATH.exists():
    key = KEY_PATH.read_text().strip()
    print(f"  ✅ 키 파일 존재: {key[:6]}{'*' * (len(key)-6)}")
else:
    print(f"  ❌ 키 파일 없음: {KEY_PATH}")
    print("  → data/meta/ecos_api_key.txt 파일을 만들고 ECOS API 키를 넣어주세요.")

# ── 2. 업데이트 전 DB 최신 날짜 ───────────────────────────
print("\n[2] 업데이트 전 DB 상태")
conn = sqlite3.connect(str(INDEX_DB))
before = conn.execute(
    "SELECT MAX(date), COUNT(*) FROM index_daily WHERE code='USD/KRW'"
).fetchone()
conn.close()
print(f"  업데이트 전 최신일: {before[0]}, 행수: {before[1]:,}")

# ── 3. PriceLoader 생성 (자동 업데이트 실행) ──────────────
print("\n[3] PriceLoader 생성 → 자동 업데이트 실행")
loader = PriceLoader()

# ── 4. 업데이트 후 DB 최신 날짜 ───────────────────────────
print("\n[4] 업데이트 후 DB 상태")
conn = sqlite3.connect(str(INDEX_DB))
after = conn.execute(
    "SELECT MAX(date), COUNT(*) FROM index_daily WHERE code='USD/KRW'"
).fetchone()
conn.close()
print(f"  업데이트 후 최신일: {after[0]}, 행수: {after[1]:,}")

added = after[1] - before[1]
print(f"  추가된 행수: {added:,}")

# ── 5. 최신일 검증 ────────────────────────────────────────
print("\n[5] 최신일 검증")
today      = date.today()
latest     = date.fromisoformat(after[0])
# 주말/공휴일 고려해서 5영업일 이내면 정상
diff_days  = (today - latest).days

if diff_days <= 5:
    print(f"  ✅ 최신 환율일: {latest} (오늘로부터 {diff_days}일 전, 정상)")
else:
    print(f"  ⚠️  최신 환율일: {latest} (오늘로부터 {diff_days}일 전, 오래됨)")

# ── 6. 최신 환율값 정상 범위 확인 ─────────────────────────
print("\n[6] 최신 환율값 확인")
rate = loader.get_usdkrw(after[0])
print(f"  {after[0]} 환율: {rate:,.2f}원/달러")
if 900 < rate < 2000:
    print("  ✅ 정상 범위 (900~2000원)")
else:
    print("  ⚠️  범위 이상")

# ── 7. 오늘 날짜로 환율 조회 (ffill 확인) ─────────────────
print("\n[7] 오늘 날짜 환율 조회 (주말이면 ffill)")
try:
    today_rate = loader.get_usdkrw(today.strftime("%Y-%m-%d"))
    print(f"  오늘({today}) 환율: {today_rate:,.2f}원/달러")
    print("  ✅ ffill 정상 동작")
except Exception as e:
    print(f"  ❌ {e}")

print("\n" + "=" * 65)
print("테스트 완료")