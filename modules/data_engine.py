import sqlite3
import pandas as pd
import yfinance as yf
from pathlib import Path

BASE_DIR       = Path(__file__).resolve().parent
DATA_DIR       = BASE_DIR / "data"
META_DIR       = DATA_DIR / "meta"
INDEX_DB_PATH  = META_DIR / "index_master.db"


class DataEngine:

    def __init__(self, start_date="1950-01-01"):
        self.start_date = start_date
        self._cache = {}

        # index_master.db 연결
        if INDEX_DB_PATH.exists():
            self._index_conn = sqlite3.connect(str(INDEX_DB_PATH), check_same_thread=False)
        else:
            self._index_conn = None
            print(f"[DataEngine] index_master.db 없음: {INDEX_DB_PATH}")

    def __del__(self):
        try:
            if self._index_conn:
                self._index_conn.close()
        except:
            pass

    def get_symbol_data(self, ticker):
        """
        index_master.db에서 먼저 조회,
        없으면 yfinance에서 다운로드 (메모리 캐시만, CSV 저장 안 함)
        """

        # ── 메모리 캐시 ──────────────────────────────────
        if ticker in self._cache:
            return self._cache[ticker]

        # ── index_master.db 조회 ─────────────────────────
        if self._index_conn:
            try:
                df = pd.read_sql(
                    "SELECT date, close FROM index_daily WHERE code=? ORDER BY date",
                    self._index_conn,
                    params=(ticker,)
                )
                if not df.empty:
                    df["date"] = pd.to_datetime(df["date"])
                    series = df.set_index("date")["close"].astype(float)
                    self._cache[ticker] = series
                    return series
            except Exception as e:
                print(f"[DataEngine] DB 조회 오류 ({ticker}): {e}")

        # ── yfinance 다운로드 (DB에 없는 경우) ──────────
        try:
            df = yf.download(
                ticker,
                start=self.start_date,
                auto_adjust=True,
                progress=False
            )
            if not df.empty:
                series = df["Close"].squeeze()
                self._cache[ticker] = series
                return series
        except Exception as e:
            print(f"[DataEngine] yfinance 오류 ({ticker}): {e}")

        return pd.Series(dtype=float)