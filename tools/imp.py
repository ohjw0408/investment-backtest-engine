"""
migrate_symbols.py
------------------
symbol_master.db에 kr_etf_list.csv, us_etf_list.csv를 통합하는 마이그레이션 스크립트.

실행 방법:
    python migrate_symbols.py

완료 후:
    - symbol_master.db : 통합된 DB (모든 ETF 정보 포함)
    - symbol_master_backup.db : 실행 전 원본 백업
    - kr_etf_list.csv, us_etf_list.csv : 삭제해도 됨
"""

import sqlite3
import pandas as pd
import shutil
import os
import sys

# -----------------------------------------------
# 경로 설정 (이 스크립트 위치 기준)
# -----------------------------------------------
BASE_DIR    = os.path.dirname(os.path.abspath(__file__))
DB_PATH     = os.path.join(BASE_DIR, "data", "meta", "symbol_master.db")
KR_CSV      = os.path.join(BASE_DIR, "data", "meta", "kr_etf_list.csv")
US_CSV      = os.path.join(BASE_DIR, "data", "meta", "us_etf_list.csv")
BACKUP_PATH = DB_PATH.replace(".db", "_backup.db")

# -----------------------------------------------
# 경로 확인
# -----------------------------------------------
for path in [DB_PATH, KR_CSV, US_CSV]:
    if not os.path.exists(path):
        print(f"[ERROR] 파일 없음: {path}")
        sys.exit(1)

# -----------------------------------------------
# 1. 백업
# -----------------------------------------------
print(f"[1/5] 백업 생성: {BACKUP_PATH}")
shutil.copy2(DB_PATH, BACKUP_PATH)

# -----------------------------------------------
# 2. 새 컬럼 추가 (없으면 추가, 있으면 스킵)
# -----------------------------------------------
print("[2/5] 스키마 업그레이드 중...")

conn = sqlite3.connect(DB_PATH)
cur  = conn.cursor()

# 현재 컬럼 목록
cur.execute("PRAGMA table_info(symbols)")
existing_cols = {row[1] for row in cur.fetchall()}

new_cols = {
    "category":    "TEXT",   # US ETF 카테고리 (e.g. "US Equity - Large Cap Blend")
    "index_name":  "TEXT",   # KR ETF 추종 지수 (e.g. "KOSPI200")
    "issuer":      "TEXT",   # KR ETF 운용사 (e.g. "KODEX")
    "leverage":    "REAL",   # 레버리지 배수 (1.0, 2.0, -1.0 ...)
    "hedge":       "TEXT",   # 환헤지 여부 (none / hedged / unhedged)
}

for col, dtype in new_cols.items():
    if col not in existing_cols:
        cur.execute(f"ALTER TABLE symbols ADD COLUMN {col} {dtype}")
        print(f"  + 컬럼 추가: {col} ({dtype})")
    else:
        print(f"  · 이미 존재: {col} (스킵)")

conn.commit()

# -----------------------------------------------
# 3. US ETF CSV → DB 병합
#    컬럼: code, name, category
#    중복(code): DB 우선 + category만 업데이트
# -----------------------------------------------
print("[3/5] US ETF CSV 병합 중...")

us_df = pd.read_csv(US_CSV)
us_df["code"] = us_df["code"].str.strip().str.upper()
us_df["name"] = us_df["name"].str.strip()

inserted_us = 0
updated_us  = 0

for _, row in us_df.iterrows():
    code     = row["code"]
    name     = row["name"]
    category = row.get("category", None)

    cur.execute("SELECT id FROM symbols WHERE code = ?", (code,))
    existing = cur.fetchone()

    if existing:
        # 이미 있으면 category만 보완
        cur.execute(
            "UPDATE symbols SET category=?, is_etf=1 WHERE code=?",
            (category, code)
        )
        updated_us += 1
    else:
        # 새로 추가
        cur.execute("""
            INSERT INTO symbols (code, name, market, country, is_etf, category)
            VALUES (?, ?, 'US_ETF', 'US', 1, ?)
        """, (code, name, category))
        inserted_us += 1

conn.commit()
print(f"  → US ETF: {inserted_us}개 추가, {updated_us}개 보완")

# -----------------------------------------------
# 4. KR ETF CSV → DB 병합
#    컬럼: code, name, issuer, index, market(KR), leverage, hedge
#    중복(code): 없음 (KR ETF는 DB에 없었음)
# -----------------------------------------------
print("[4/5] KR ETF CSV 병합 중...")

kr_df = pd.read_csv(KR_CSV)
kr_df["code"] = kr_df["code"].astype(str).str.strip().str.zfill(6)  # 6자리 패딩

inserted_kr = 0
updated_kr  = 0

for _, row in kr_df.iterrows():
    code       = row["code"]
    name       = row["name"].strip()
    issuer     = row.get("issuer", None)
    index_name = row.get("index", None)
    leverage   = row.get("leverage", None)
    hedge      = row.get("hedge", None)

    cur.execute("SELECT id FROM symbols WHERE code = ?", (code,))
    existing = cur.fetchone()

    if existing:
        cur.execute("""
            UPDATE symbols
            SET issuer=?, index_name=?, leverage=?, hedge=?, is_etf=1
            WHERE code=?
        """, (issuer, index_name, leverage, hedge, code))
        updated_kr += 1
    else:
        cur.execute("""
            INSERT INTO symbols
                (code, name, market, country, is_etf, issuer, index_name, leverage, hedge)
            VALUES (?, ?, 'KRX', 'KR', 1, ?, ?, ?, ?)
        """, (code, name, issuer, index_name, leverage, hedge))
        inserted_kr += 1

conn.commit()
print(f"  → KR ETF: {inserted_kr}개 추가, {updated_kr}개 보완")

# -----------------------------------------------
# 5. KRX 전체 종목 (코스피 + 코스닥) — fdr
# -----------------------------------------------
print("[5/6] KRX 종목 (코스피 + 코스닥) 추가 중...")

try:
    import FinanceDataReader as fdr

    inserted_stock = 0
    updated_stock  = 0

    for market in ["KOSPI", "KOSDAQ"]:
        print(f"  · {market} 불러오는 중...")
        df = fdr.StockListing(market)

        # 컬럼명 정규화
        df.columns = [c.strip() for c in df.columns]
        code_col = next((c for c in df.columns if c in ("Code", "code", "Symbol")), None)
        name_col = next((c for c in df.columns if c in ("Name", "name")), None)

        if not code_col or not name_col:
            print(f"  [WARN] {market} 컬럼 인식 실패: {df.columns.tolist()}")
            continue

        for _, row in df.iterrows():
            code = str(row[code_col]).strip().zfill(6)
            name = str(row[name_col]).strip()

            if not code or not name:
                continue

            cur.execute("SELECT id, is_etf FROM symbols WHERE code = ?", (code,))
            existing = cur.fetchone()

            if existing:
                cur.execute(
                    "UPDATE symbols SET name=?, market=?, country='KR' WHERE code=?",
                    (name, market, code)
                )
                updated_stock += 1
            else:
                cur.execute(
                    "INSERT INTO symbols (code, name, market, country, is_etf) VALUES (?, ?, ?, 'KR', 0)",
                    (code, name, market)
                )
                inserted_stock += 1

    conn.commit()
    print(f"  → KRX 종목: {inserted_stock}개 추가, {updated_stock}개 보완")

except ImportError:
    print("  [SKIP] FinanceDataReader 미설치 — pip install finance-datareader")
except Exception as e:
    print(f"  [ERROR] KRX 종목 추가 실패: {e}")

# -----------------------------------------------
# 6. 결과 요약
# -----------------------------------------------
print("[6/6] 완료!")

cur.execute("SELECT COUNT(*) FROM symbols")
total = cur.fetchone()[0]

cur.execute("SELECT COUNT(*) FROM symbols WHERE is_etf=1")
etf_total = cur.fetchone()[0]

cur.execute("SELECT COUNT(*) FROM symbols WHERE country='KR'")
kr_total = cur.fetchone()[0]

cur.execute("SELECT COUNT(*) FROM symbols WHERE country='US'")
us_total = cur.fetchone()[0]

cur.execute("SELECT COUNT(*) FROM symbols WHERE market='KOSPI'")
kospi_total = cur.fetchone()[0]

cur.execute("SELECT COUNT(*) FROM symbols WHERE market='KOSDAQ'")
kosdaq_total = cur.fetchone()[0]

conn.close()

print(f"""
  ┌─────────────────────────────┐
  │   symbol_master.db 통합 완료 │
  ├─────────────────────────────┤
  │ 전체 종목      : {total:>6}개    │
  │ ETF 합계       : {etf_total:>6}개    │
  │ 한국 (KR)      : {kr_total:>6}개    │
  │   - KOSPI      : {kospi_total:>6}개    │
  │   - KOSDAQ     : {kosdaq_total:>6}개    │
  │   - KR ETF     : {kr_total - kospi_total - kosdaq_total:>6}개    │
  │ 미국 (US)      : {us_total:>6}개    │
  └─────────────────────────────┘
  백업: {BACKUP_PATH}
""")
print("kr_etf_list.csv, us_etf_list.csv 는 이제 삭제하셔도 됩니다.")