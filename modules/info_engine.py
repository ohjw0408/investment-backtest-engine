import sqlite3
import pandas as pd
from config import SYMBOL_DB_PATH


class InfoEngine:
    def __init__(self):
        self.db_path = SYMBOL_DB_PATH

    def _connect(self):
        return sqlite3.connect(self.db_path)

    # ---------------------------------------------------
    # 전체 종목 조회
    # ---------------------------------------------------
    def get_all_symbols(self):
        conn = self._connect()
        query = "SELECT * FROM symbols"
        df = pd.read_sql(query, conn)
        conn.close()
        return df

    # ---------------------------------------------------
    # 티커 정확 검색
    # ---------------------------------------------------
    def get_symbol_by_ticker(self, ticker: str):
        conn = self._connect()
        query = "SELECT * FROM symbols WHERE code = ?"
        df = pd.read_sql(query, conn, params=(ticker.upper(),))
        conn.close()
        return df

    # ---------------------------------------------------
    # 기본 부분 검색
    # ---------------------------------------------------
    def search_symbol(self, keyword: str):
        if not keyword:
            return pd.DataFrame()

        conn = self._connect()
        query = """
        SELECT *
        FROM symbols
        WHERE code LIKE ?
        OR name LIKE ?
        """
        like_keyword = f"%{keyword}%"
        df = pd.read_sql(query, conn, params=(like_keyword, like_keyword))
        conn.close()
        return df

    # ---------------------------------------------------
    # Fuzzy 검색 (app.py 호환)
    # ---------------------------------------------------
    def search_fuzzy(self, keyword: str):
        if not keyword:
            return pd.DataFrame()

        conn = self._connect()
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
        LIMIT 20
        """

        exact = keyword.upper()
        like_code_prefix = f"{keyword.upper()}%"
        like_name = f"%{keyword}%"

        df = pd.read_sql(
            query,
            conn,
            params=(like_name, like_name, exact, like_code_prefix, like_name),
        )

        conn.close()
        return df

    # ---------------------------------------------------
    # ETF만 조회
    # ---------------------------------------------------
    def get_etfs(self):
        conn = self._connect()
        query = "SELECT * FROM symbols WHERE is_etf = 1"
        df = pd.read_sql(query, conn)
        conn.close()
        return df