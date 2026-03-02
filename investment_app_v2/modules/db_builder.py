import sqlite3
import pandas as pd
import FinanceDataReader as fdr
import os


DB_PATH = "data/symbol_master.db"
ETF_CSV_PATH = "data/us_etf_list.csv"


class SymbolDBBuilder:

    def __init__(self):
        os.makedirs("data", exist_ok=True)
        self.conn = sqlite3.connect(DB_PATH)

    # -------------------------------------------------
    # 테이블 생성
    # -------------------------------------------------
    def create_table(self):
        query = """
        CREATE TABLE IF NOT EXISTS symbols (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT UNIQUE,
            name TEXT,
            market TEXT,
            country TEXT,
            is_etf INTEGER
        )
        """
        self.conn.execute(query)
        self.conn.commit()

    # -------------------------------------------------
    # 한국 시장 (지금은 스킵)
    # -------------------------------------------------
    def build_krx(self):
        print("KRX 수집 스킵 (미국 먼저 진행)")
        return

    # -------------------------------------------------
    # 미국 주식 + 미국 ETF
    # -------------------------------------------------
    def build_us(self):

        print("US 수집 중...")

        # ---------- 미국 주식 ----------
        nasdaq = fdr.StockListing("NASDAQ")
        nyse = fdr.StockListing("NYSE")

        nasdaq = nasdaq.rename(columns={"Symbol": "code", "Name": "name"})
        nyse = nyse.rename(columns={"Symbol": "code", "Name": "name"})

        nasdaq["market"] = "NASDAQ"
        nyse["market"] = "NYSE"

        nasdaq["country"] = "US"
        nyse["country"] = "US"

        nasdaq["is_etf"] = 0
        nyse["is_etf"] = 0

        stocks = pd.concat(
            [
                nasdaq[["code", "name", "market", "country", "is_etf"]],
                nyse[["code", "name", "market", "country", "is_etf"]],
            ],
            ignore_index=True
        )

        # ---------- 미국 ETF (CSV 기반) ----------
        if not os.path.exists(ETF_CSV_PATH):
            raise FileNotFoundError(
                f"ETF 리스트 파일이 없습니다: {ETF_CSV_PATH}"
            )

        etf = pd.read_csv(ETF_CSV_PATH)

        etf["market"] = "US_ETF"
        etf["country"] = "US"
        etf["is_etf"] = 1

        etf = etf[["code", "name", "market", "country", "is_etf"]]

        print(f"미국 ETF {len(etf)}개 로드")

        # ---------- 합치기 ----------
        us = pd.concat([stocks, etf], ignore_index=True)

        us.to_sql("symbols", self.conn, if_exists="append", index=False)
        print("US 완료")

    # -------------------------------------------------
    # 중복 제거
    # -------------------------------------------------
    def remove_duplicates(self):
        query = """
        DELETE FROM symbols
        WHERE id NOT IN (
            SELECT MIN(id)
            FROM symbols
            GROUP BY code
        )
        """
        self.conn.execute(query)
        self.conn.commit()

    # -------------------------------------------------
    # 전체 실행
    # -------------------------------------------------
    def build_all(self):
        self.create_table()
        self.build_krx()
        self.build_us()
        self.remove_duplicates()
        print("DB 구축 완료")


# -------------------------------------------------
# 실행 엔트리
# -------------------------------------------------
if __name__ == "__main__":
    builder = SymbolDBBuilder()
    builder.build_all()