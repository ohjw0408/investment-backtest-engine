import sqlite3
import pandas as pd
import os
from config import SYMBOL_DB_PATH

_COLS = "code, name, market, country, is_etf, category, index_name, issuer, leverage, hedge"


class InfoEngine:

    def __init__(self):
        self.db_path = SYMBOL_DB_PATH

    def _connect(self):
        if not os.path.exists(self.db_path):
            raise FileNotFoundError(f"DB 없음: {self.db_path}")
        return sqlite3.connect(self.db_path)

    # ------------------------------------------------------------------
    # 검색
    # ------------------------------------------------------------------
    def search_fuzzy(self, keyword: str, limit: int = 20):
        if not keyword or not keyword.strip():
            return pd.DataFrame()

        kw = keyword.strip()

        # 1. 기본 LIKE 검색 (정규화 포함)
        results = self._search_like(kw, limit)
        if not results.empty:
            return results

        # 2. 토큰 AND 검색: "sk 하이닉스" → 두 토큰 모두 포함
        tokens = kw.split()
        if len(tokens) > 1:
            results = self._search_tokens(tokens, limit)
            if not results.empty:
                return results

        # 3. 공백 제거 검색: "s k" → "sk"
        collapsed = kw.replace(' ', '')
        if collapsed != kw:
            results = self._search_like(collapsed, limit)
            if not results.empty:
                return results

        # 4. rapidfuzz fallback
        results = self._search_rapidfuzz(kw, limit)
        return results

    def _search_like(self, kw: str, limit: int) -> pd.DataFrame:
        conn = self._connect()
        like     = f"%{kw}%"
        exact    = kw.upper()
        nprefix  = f"{kw}%"          # 이름 prefix(대소문자 무관 — 한글)
        cprefix  = f"{kw.upper()}%"  # 코드 prefix
        wordmid  = f"% {kw}%"        # 단어 시작(공백 뒤) — "KODEX 삼성그룹" 등 ETF
        query = f"""
        SELECT {_COLS} FROM symbols
        WHERE code LIKE ? OR name LIKE ?
        ORDER BY
            CASE
                WHEN code = ?       THEN 1
                WHEN name = ?       THEN 2
                WHEN name LIKE ?    THEN 3   -- 이름 prefix (삼성전자)
                WHEN code LIKE ?    THEN 4   -- 코드 prefix
                WHEN name LIKE ?    THEN 5   -- 단어 시작 (KODEX 삼성그룹)
                ELSE 6                       -- 중간 포함
            END,
            length(name)
        LIMIT ?
        """
        df = pd.read_sql(query, conn,
                         params=(like, like, exact, kw, nprefix, cprefix, wordmid, limit))
        conn.close()
        return df

    def _search_tokens(self, tokens: list, limit: int) -> pd.DataFrame:
        """모든 토큰이 code 또는 name에 포함된 종목 검색 (AND)"""
        conn = self._connect()
        conditions = " AND ".join(
            ["(code LIKE ? OR name LIKE ?)"] * len(tokens)
        )
        params = []
        for t in tokens:
            like = f"%{t}%"
            params += [like, like]

        # 합쳐진 쿼리로 name 완전 포함 여부 우선 정렬
        joined = ''.join(tokens)
        params += [f"%{joined}%", limit]

        query = f"""
        SELECT {_COLS} FROM symbols
        WHERE {conditions}
        ORDER BY
            CASE WHEN name LIKE ? THEN 1 ELSE 2 END,
            length(name)
        LIMIT ?
        """
        df = pd.read_sql(query, conn, params=params)
        conn.close()
        return df

    def _search_rapidfuzz(self, kw: str, limit: int) -> pd.DataFrame:
        """편집거리 기반 fuzzy 검색 — 결과 없을 때 최후 수단"""
        try:
            from rapidfuzz import process, fuzz
        except ImportError:
            return pd.DataFrame()

        conn = self._connect()
        all_df = pd.read_sql(f"SELECT {_COLS} FROM symbols", conn)
        conn.close()

        if all_df.empty:
            return pd.DataFrame()

        # 코드+이름 합쳐서 유사도 계산
        choices = (all_df['code'].fillna('') + ' ' + all_df['name'].fillna('')).tolist()
        matches = process.extract(kw, choices, scorer=fuzz.partial_ratio,
                                  limit=limit, score_cutoff=60)
        if not matches:
            return pd.DataFrame()

        indices = [m[2] for m in matches]
        return all_df.iloc[indices].reset_index(drop=True)

    # ------------------------------------------------------------------
    # 티커 단건 조회
    # ------------------------------------------------------------------
    def get_symbol_by_ticker(self, ticker: str):
        conn = self._connect()
        df = pd.read_sql(
            "SELECT * FROM symbols WHERE code = ?",
            conn,
            params=(ticker.upper(),)
        )
        conn.close()
        return df

    # ------------------------------------------------------------------
    # 전체 조회
    # ------------------------------------------------------------------
    def get_all_symbols(self):
        conn = self._connect()
        df = pd.read_sql("SELECT * FROM symbols", conn)
        conn.close()
        return df

    # ------------------------------------------------------------------
    # ETF만 조회
    # ------------------------------------------------------------------
    def get_etf_list(self, country: str = None):
        conn = self._connect()
        if country:
            df = pd.read_sql(
                "SELECT * FROM symbols WHERE is_etf=1 AND country=?",
                conn,
                params=(country.upper(),)
            )
        else:
            df = pd.read_sql("SELECT * FROM symbols WHERE is_etf=1", conn)
        conn.close()
        return df
