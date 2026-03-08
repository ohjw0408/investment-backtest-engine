import sqlite3
import pandas as pd
import yfinance as yf
import logging

from datetime import datetime, timedelta
from pathlib import Path


# yfinance 로그 제거
logging.getLogger("yfinance").setLevel(logging.CRITICAL)


# -------------------------------------------------
# 경로 설정
# -------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent.parent

DATA_DIR = BASE_DIR / "data"

PRICE_CACHE_DIR = DATA_DIR / "price_cache"

DB_PATH = PRICE_CACHE_DIR / "price_daily.db"


class PriceLoader:

    def __init__(self):

        PRICE_CACHE_DIR.mkdir(parents=True, exist_ok=True)

        # ✅ 수정 1 : thread-safe 옵션 추가
        self.conn = sqlite3.connect(
            str(DB_PATH),
            check_same_thread=False
        )

        self.create_tables()

    # -------------------------------------------------
    # 프로그램 종료 시 DB 연결 종료
    # -------------------------------------------------

    def __del__(self):
        try:
            self.conn.close()
        except Exception:
            pass

    # -------------------------------------------------
    # 테이블 생성
    # -------------------------------------------------

    def create_tables(self):

        price_table = """

        CREATE TABLE IF NOT EXISTS price_daily (

            code TEXT,

            date TEXT,

            open REAL,

            high REAL,

            low REAL,

            close REAL,

            volume REAL,

            PRIMARY KEY (code, date)

        )

        """

        action_table = """

        CREATE TABLE IF NOT EXISTS corporate_actions (

            code TEXT,

            date TEXT,

            dividend REAL,

            split REAL,

            PRIMARY KEY (code, date)

        )

        """

        self.conn.execute(price_table)

        self.conn.execute(action_table)

        self.conn.commit()

    # -------------------------------------------------
    # DB 날짜 범위 조회
    # -------------------------------------------------

    def get_date_range_in_db(self, code):

        query = """

        SELECT MIN(date), MAX(date)

        FROM price_daily

        WHERE code = ?

        """

        cur = self.conn.execute(query, (code,))

        return cur.fetchone()

    # -------------------------------------------------
    # API 다운로드
    # -------------------------------------------------

    def fetch_from_api(self, code, start, end):

        df = yf.download(

            code,

            start=start,

            end=end,

            progress=False,

            auto_adjust=False,

            actions=True,

            threads=False

        )

        if df.empty:

            return None, None

        if isinstance(df.columns, pd.MultiIndex):

            df.columns = df.columns.get_level_values(0)

        df = df.reset_index()

        df["Date"] = df["Date"].dt.strftime("%Y-%m-%d")

        df = df.rename(columns={

            "Date": "date",

            "Open": "open",

            "High": "high",

            "Low": "low",

            "Close": "close",

            "Volume": "volume",

            "Dividends": "dividend",

            "Stock Splits": "split"

        })

        if "dividend" not in df.columns:

            df["dividend"] = 0

        if "split" not in df.columns:

            df["split"] = 1

        df["dividend"] = df["dividend"].fillna(0)

        df["split"] = df["split"].replace(0, 1).fillna(1)

        df["code"] = code

        price_df = df[

            ["code", "date", "open", "high", "low", "close", "volume"]

        ]

        action_df = df[

            ["code", "date", "dividend", "split"]

        ]

        return price_df, action_df

    # -------------------------------------------------
    # 핵심 함수
    # -------------------------------------------------

    def get_price(self, code, start_date, end_date):

        start_date = datetime.strptime(start_date, "%Y-%m-%d").date()

        end_date = datetime.strptime(end_date, "%Y-%m-%d").date()

        db_min, db_max = self.get_date_range_in_db(code)

        api_calls = []

        if db_min is None:

            api_calls.append((start_date, end_date))

        else:

            db_min = datetime.strptime(db_min, "%Y-%m-%d").date()

            db_max = datetime.strptime(db_max, "%Y-%m-%d").date()

            if start_date < db_min:

                api_calls.append((start_date, db_min - timedelta(days=1)))

            if end_date > db_max:

                api_calls.append((db_max + timedelta(days=1), end_date))

        # -------------------------------------------------
        # API 호출
        # -------------------------------------------------

        for s, e in api_calls:

            price_df, action_df = self.fetch_from_api(

                code,

                s.strftime("%Y-%m-%d"),

                e.strftime("%Y-%m-%d"),

            )

            if price_df is not None:

                price_df.to_sql(

                    "price_daily",

                    self.conn,

                    if_exists="append",

                    index=False,

                )

                action_df.to_sql(

                    "corporate_actions",

                    self.conn,

                    if_exists="append",

                    index=False,

                )

        # -------------------------------------------------
        # DB 조회
        # -------------------------------------------------

        price_query = """

        SELECT date, open, high, low, close, volume

        FROM price_daily

        WHERE code = ?

        AND date BETWEEN ? AND ?

        """

        action_query = """

        SELECT date, dividend, split

        FROM corporate_actions

        WHERE code = ?

        AND date BETWEEN ? AND ?

        """

        price_df = pd.read_sql(

            price_query,

            self.conn,

            params=(code, start_date, end_date),

        )

        action_df = pd.read_sql(

            action_query,

            self.conn,

            params=(code, start_date, end_date),

        )

        df = price_df.merge(action_df, on="date", how="left")

        df["dividend"] = df["dividend"].fillna(0)

        df["split"] = df["split"].fillna(1)

        return df