import sqlite3
import argparse
import requests
import pandas as pd
from pathlib import Path
from datetime import datetime, timedelta

# ─────────────────────────────
# 경로 (프로젝트 루트 기준)
# ─────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent.parent
META_DIR = BASE_DIR / "data" / "meta"
INDEX_DB = META_DIR / "index_master.db"
KEY_PATH = META_DIR / "krx_api_key.txt"


# ─────────────────────────────
# KRX CLIENT
# ─────────────────────────────
class KRXClient:

    def __init__(self, debug=False):
        self.auth_key = self._load_key()
        self.debug = debug

    def _load_key(self):
        if not KEY_PATH.exists():
            raise FileNotFoundError(f"API 키 없음: {KEY_PATH}")
        return KEY_PATH.read_text().strip()

    def _get(self, date):
        url = "https://data-dbg.krx.co.kr/svc/apis/gen/gold_bydd_trd"

        headers = {
            "AUTH_KEY": self.auth_key,
            "User-Agent": "Mozilla/5.0"
        }

        r = requests.get(url, headers=headers, params={"basDd": date}, timeout=30)

        if self.debug:
            print(f"[DEBUG] {date} → {r.status_code}")

        if r.status_code != 200:
            return None

        try:
            return r.json()
        except:
            return None

    def get_gold(self, date):
        data = self._get(date)
        if not data:
            return pd.DataFrame()

        rows = data.get("OutBlock_1", [])
        if not rows:
            return pd.DataFrame()

        records = []
        for r in rows:

            # 🔥 금 1kg만
            if r.get("ISU_CD") != "04020000":
                continue

            records.append({
                "date": r.get("BAS_DD"),
                "close": float(str(r.get("TDD_CLSPRC", "0")).replace(",", ""))
            })

        return pd.DataFrame(records)


# ─────────────────────────────
# DB
# ─────────────────────────────
def init_db():
    META_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(INDEX_DB)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS index_daily (
            code TEXT,
            date TEXT,
            close REAL,
            PRIMARY KEY (code, date)
        )
    """)

    conn.commit()
    return conn


def reset_gold_data(conn):
    print("🧨 기존 금 데이터 삭제")
    conn.execute("DELETE FROM index_daily WHERE code='KRX_GOLD'")
    conn.commit()


def save(conn, df):
    if df.empty:
        return 0

    rows = []
    for _, r in df.iterrows():
        raw = r["date"].replace("-", "")[:8]
        fmt = f"{raw[:4]}-{raw[4:6]}-{raw[6:8]}"
        rows.append(("KRX_GOLD", fmt, r["close"]))

    conn.executemany(
        "INSERT OR REPLACE INTO index_daily VALUES (?,?,?)",
        rows
    )
    conn.commit()

    return len(rows)


# ─────────────────────────────
# 전체 재수집 (핵심)
# ─────────────────────────────
def collect_all(client, conn):

    # 🔥 초기화
    reset_gold_data(conn)

    start = datetime(2014, 3, 24)
    end   = datetime.today() - timedelta(days=1)

    print(f"🚀 전체 재수집: {start.strftime('%Y-%m-%d')} ~ {end.strftime('%Y-%m-%d')}")

    total = 0
    cur = start

    while cur <= end:
        d = cur.strftime("%Y%m%d")

        try:
            df = client.get_gold(d)

            if not df.empty:
                n = save(conn, df)
                total += n
                print(f"{d} → {n}")

        except Exception as e:
            print(f"{d} ERROR: {e}")

        cur += timedelta(days=1)

    print(f"🔥 완료: {total}개 저장")


# ─────────────────────────────
# MAIN
# ─────────────────────────────
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--date", type=str, default=None)
    args = parser.parse_args()

    client = KRXClient(debug=False)
    conn = init_db()

    if args.all:
        collect_all(client, conn)
    else:
        d = args.date or datetime.today().strftime("%Y%m%d")
        df = client.get_gold(d)
        n = save(conn, df)
        print(f"{d} → {n}")

    conn.close()


if __name__ == "__main__":
    main()