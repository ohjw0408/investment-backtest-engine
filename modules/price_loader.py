import sqlite3
import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta
from pathlib import Path

# -------------------------------------------------
# 경로 설정
# -------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
PRICE_CACHE_DIR = DATA_DIR / "price_cache"
DB_PATH = PRICE_CACHE_DIR / "price_daily.db"


class PriceLoader:

    def __init__(self):

        # price_cache 폴더 생성
        PRICE_CACHE_DIR.mkdir(parents=True, exist_ok=True)

        # SQLite 연결
        self.conn = sqlite3.connect(str(DB_PATH))

        # 테이블 생성
        self.create_table()

    # -------------------------------------------------
    # 가격 테이블 생성
    # -------------------------------------------------
    def create_table(self):

        query = """
        CREATE TABLE IF NOT EXISTS price_daily (
            code TEXT,
            date TEXT,
            close REAL,
            dividend REAL,
            PRIMARY KEY (code, date)
        )
        """

        self.conn.execute(query)
        self.conn.commit()

    # -------------------------------------------------
    # DB에 저장된 날짜 범위 조회
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
    # API로 가격 다운로드
    # -------------------------------------------------
    def fetch_from_api(self, code, start, end):

        df = yf.download(
            code,
            start=start,
            end=end,
            progress=False,
            auto_adjust=False,
        )

        if df.empty:
            return df

        # 🔥 MultiIndex 컬럼 평탄화 (중요)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        df = df.reset_index()

        # -----------------------------
        # 배당 데이터 가져오기
        # -----------------------------
        ticker = yf.Ticker(code)
        div = ticker.dividends

        if not div.empty:
            div = div.reset_index()
            div["Date"] = div["Date"].dt.strftime("%Y-%m-%d")
            div = div.rename(columns={"Dividends": "dividend"})
        else:
            div = pd.DataFrame(columns=["Date", "dividend"])

        # -----------------------------
        # 가격 데이터 정리
        # -----------------------------
        df["Date"] = df["Date"].dt.strftime("%Y-%m-%d")

        df = df.rename(columns={
            "Date": "date",
            "Close": "close"
        })

        df["code"] = code

        df = df[["code", "date", "close"]]

        # -----------------------------
        # 배당 merge
        # -----------------------------
        df = df.merge(
            div.rename(columns={"Date": "date"}),
            on="date",
            how="left",
        )

        df["dividend"] = df["dividend"].fillna(0)

        return df[["code", "date", "close", "dividend"]]

    # -------------------------------------------------
    # 핵심 함수: 필요한 구간만 API 호출
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
        # 필요한 구간만 API 호출
        # -------------------------------------------------
        for s, e in api_calls:

            df_new = self.fetch_from_api(
                code,
                s.strftime("%Y-%m-%d"),
                e.strftime("%Y-%m-%d"),
            )

            if not df_new.empty:

                df_new.to_sql(
                    "price_daily",
                    self.conn,
                    if_exists="append",
                    index=False,
                )

        # -------------------------------------------------
        # 최종 데이터 반환
        # -------------------------------------------------
        query = """
        SELECT date, close, dividend
        FROM price_daily
        WHERE code = ?
        AND date BETWEEN ? AND ?
        ORDER BY date
        """

        df = pd.read_sql(
            query,
            self.conn,
            params=(
                code,
                start_date.strftime("%Y-%m-%d"),
                end_date.strftime("%Y-%m-%d"),
            ),
        )

        return df


# -------------------------------------------------
# 단독 실행 테스트
# -------------------------------------------------
if __name__ == "__main__":

    loader = PriceLoader()

    df = loader.get_price(
        code="QQQ",
        start_date="2015-01-01",
        end_date="2020-12-31",
    )

    print(df.head())
    print(df.tail())
    print("행 수:", len(df))