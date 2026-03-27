import sqlite3
import pandas as pd
import os
from config import SYMBOL_DB_PATH


class InfoEngine:

    def __init__(self):
        self.db_path = SYMBOL_DB_PATH

    # -----------------------------
    # DB 연결 (안전)
    # -----------------------------
    def _connect(self):

        if not os.path.exists(self.db_path):
            raise FileNotFoundError(f"DB 없음: {self.db_path}")

        return sqlite3.connect(self.db_path)

    # -----------------------------
    # symbol_master 검색
    # -----------------------------
    def _search_symbol_master(self, keyword: str):

        conn = self._connect()

        like = f"%{keyword}%"
        exact = keyword.upper()
        prefix = f"{keyword.upper()}%"

        query = """
        SELECT *
        FROM symbols
        WHERE code LIKE ?
        OR name LIKE ?
        ORDER BY
            CASE
                WHEN code = ? THEN 1
                WHEN code LIKE ? THEN 2
                WHEN name LIKE ? THEN 3
                ELSE 4
            END
        LIMIT 50
        """

        df = pd.read_sql(
            query,
            conn,
            params=(like, like, exact, prefix, like)
        )

        conn.close()

        return df

    # -----------------------------
    # ETF CSV 로드 (🔥 meta 폴더 기준)
    # -----------------------------
    def _load_etf_csv(self):

        BASE_DIR = os.path.dirname(os.path.dirname(__file__))

        kr_path = os.path.join(BASE_DIR, "data", "meta", "kr_etf_list.csv")
        us_path = os.path.join(BASE_DIR, "data", "meta", "us_etf_list.csv")

        if not os.path.exists(kr_path):
            raise FileNotFoundError(f"KR ETF 없음: {kr_path}")

        if not os.path.exists(us_path):
            raise FileNotFoundError(f"US ETF 없음: {us_path}")

        kr = pd.read_csv(kr_path)
        us = pd.read_csv(us_path)

        return pd.concat([kr, us], ignore_index=True)

    # -----------------------------
    # ETF 검색
    # -----------------------------
    def _search_etf_csv(self, keyword: str):

        etf = self._load_etf_csv()

        mask = (
            etf["code"].str.contains(keyword, case=False, na=False) |
            etf["name"].str.contains(keyword, case=False, na=False)
        )

        return etf[mask]

    # -----------------------------
    # 🔥 최종 검색 (중복 제거)
    # -----------------------------
    def search_fuzzy(self, keyword: str):

        if not keyword:
            return pd.DataFrame()

        # 1️⃣ symbol_master
        base_df = self._search_symbol_master(keyword)

        # 2️⃣ ETF CSV
        etf_df = self._search_etf_csv(keyword)

        # 3️⃣ symbol_master 우선
        existing_codes = set(base_df["code"].str.upper())

        etf_df = etf_df[
            ~etf_df["code"].str.upper().isin(existing_codes)
        ]

        # 4️⃣ 병합
        result = pd.concat([base_df, etf_df], ignore_index=True)

        return result.head(20)

    # -----------------------------
    # 전체 조회
    # -----------------------------
    def get_all_symbols(self):

        conn = self._connect()
        df = pd.read_sql("SELECT * FROM symbols", conn)
        conn.close()

        return df

    # -----------------------------
    # 티커 조회
    # -----------------------------
    def get_symbol_by_ticker(self, ticker: str):

        conn = self._connect()

        df = pd.read_sql(
            "SELECT * FROM symbols WHERE code = ?",
            conn,
            params=(ticker.upper(),)
        )

        conn.close()

        return df