import sqlite3
import pandas as pd
import os
from config import SYMBOL_DB_PATH


class InfoEngine:

    def __init__(self):
        self.db_path = SYMBOL_DB_PATH

    # -----------------------------
    # DB 연결
    # -----------------------------
    def _connect(self):
        if not os.path.exists(self.db_path):
            raise FileNotFoundError(f"DB 없음: {self.db_path}")
        return sqlite3.connect(self.db_path)

    # -----------------------------
    # 검색 (DB 단일 소스)
    # -----------------------------
    def search_fuzzy(self, keyword: str, limit: int = 20):
        """
        code 또는 name으로 검색.
        우선순위: 완전일치 > 코드 전방일치 > 나머지
        """
        if not keyword:
            return pd.DataFrame()

        conn = self._connect()

        like   = f"%{keyword}%"
        exact  = keyword.upper()
        prefix = f"{keyword.upper()}%"

        query = """
        SELECT
            code,
            name,
            market,
            country,
            is_etf,
            category,
            index_name,
            issuer,
            leverage,
            hedge
        FROM symbols
        WHERE code LIKE ?
           OR name LIKE ?
        ORDER BY
            CASE
                WHEN code = ?       THEN 1
                WHEN code LIKE ?    THEN 2
                WHEN name LIKE ?    THEN 3
                ELSE 4
            END
        LIMIT ?
        """

        df = pd.read_sql(
            query,
            conn,
            params=(like, like, exact, prefix, like, limit)
        )

        conn.close()
        return df

    # -----------------------------
    # 티커 단건 조회
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

    # -----------------------------
    # 전체 조회
    # -----------------------------
    def get_all_symbols(self):
        conn = self._connect()
        df = pd.read_sql("SELECT * FROM symbols", conn)
        conn.close()
        return df

    # -----------------------------
    # ETF만 조회
    # -----------------------------
    def get_etf_list(self, country: str = None):
        conn = self._connect()
        if country:
            df = pd.read_sql(
                "SELECT * FROM symbols WHERE is_etf=1 AND country=?",
                conn,
                params=(country.upper(),)
            )
        else:
            df = pd.read_sql(
                "SELECT * FROM symbols WHERE is_etf=1",
                conn
            )
        conn.close()
        return df
