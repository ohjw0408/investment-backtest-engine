"""
index_loader.py
────────────────────────────────────────────────────────────────────────────────
지수/환율 데이터 로더 및 백필링용 DB 관리

저장 위치: data/meta/index_master.db
용도: ETF 백필링용 지수 데이터 (한 번 다운로드 후 영구 보관)

지원 지수:
  주식: ^GSPC, ^NDX, ^SOX, ^DJITR, ^DJI, KS200, KQ150, ^URTH, EEM,
        ^N225, ^TOPX, ^RUT, ^NSEI, ^STOXX50E, 000300.SS, ^HSCE
  채권: DGS30, DGS10 (FRED API)
  원자재: GC=F, SI=F, CL=F, HG=F
  환율: USD/KRW (FinanceDataReader)
────────────────────────────────────────────────────────────────────────────────
"""

import sqlite3
import logging
import time
from datetime import datetime
from pathlib import Path

import pandas as pd

logging.getLogger("yfinance").setLevel(logging.CRITICAL)

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH  = BASE_DIR / "data" / "meta" / "index_master.db"

# ── 지수 메타데이터 ────────────────────────────────────────
# (code, source, description, start_date)
INDEX_META = [
    # 주식 지수 - yfinance
    ("^GSPC",     "yfinance", "S&P 500",                    "1928-01-01"),
    ("^NDX",      "yfinance", "Nasdaq 100",                  "1985-01-01"),
    ("^SOX",      "yfinance", "Philadelphia Semiconductor",  "1994-01-01"),
    ("^DJI",      "yfinance", "Dow Jones Industrial",        "1928-01-01"),
    ("^RUT",      "yfinance", "Russell 2000",                "1987-01-01"),
    ("ACWI",      "yfinance", "MSCI World (ACWI proxy)",     "2008-01-01"),
    ("EEM",       "yfinance", "MSCI Emerging Markets",       "2003-01-01"),
    ("^N225",     "yfinance", "Nikkei 225",                  "1965-01-01"),
    ("TPX.F",     "yfinance", "TOPIX (Frankfurt)",           "2007-01-01"),
    ("^NSEI",     "yfinance", "Nifty 50",                    "1999-01-01"),
    ("^STOXX50E", "yfinance", "Euro Stoxx 50",               "1987-01-01"),
    ("000300.SS", "yfinance", "CSI 300",                     "2005-01-01"),
    ("^HSCE",     "yfinance", "Hang Seng China Enterprises", "1994-01-01"),

    # 다우존스 배당 - yfinance (SCHD 기초지수 프록시)
    ("SCHD",      "yfinance", "DJ US Dividend 100 (proxy)", "2011-01-01"),

    # 한국 지수 - FinanceDataReader
    ("KS200",     "fdr_kr",   "KOSPI 200",                   "1990-01-01"),
    ("KQ150",     "fdr_kr",   "KOSDAQ 150",                  "2001-01-01"),

    # 채권 - FRED
    ("DGS30",     "fred",     "US 30Y Treasury Yield",       "1977-01-01"),
    ("DGS10",     "fred",     "US 10Y Treasury Yield",       "1962-01-01"),
    ("DGS3MO",    "fred",     "US 3M Treasury Yield",        "1982-01-01"),

    # 원자재 - yfinance
    ("GC=F",      "yfinance", "Gold Futures",                "1975-01-01"),
    ("SI=F",      "yfinance", "Silver Futures",              "1975-01-01"),
    ("CL=F",      "yfinance", "WTI Crude Oil",               "1983-01-01"),
    ("HG=F",      "yfinance", "Copper Futures",              "1988-01-01"),

    # 환율 - FinanceDataReader
    ("USD/KRW",   "fdr",      "USD/KRW Exchange Rate",       "1990-01-01"),
    ("USD/JPY",   "fdr",      "USD/JPY Exchange Rate",       "1971-01-01"),
]

# ── IndexLoader ────────────────────────────────────────────
class IndexLoader:

    def __init__(self):
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
        self._create_tables()

    def __del__(self):
        try:
            self.conn.close()
        except Exception:
            pass

    # ── 테이블 생성 ────────────────────────────────────────
    def _create_tables(self):
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS index_daily (
                code  TEXT,
                date  TEXT,
                close REAL,
                PRIMARY KEY (code, date)
            )
        """)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS index_meta (
                code        TEXT PRIMARY KEY,
                source      TEXT,
                description TEXT,
                start_date  TEXT,
                last_update TEXT
            )
        """)
        self.conn.commit()

    # ── DB 날짜 범위 조회 ──────────────────────────────────
    def get_date_range(self, code: str):
        cur = self.conn.execute(
            "SELECT MIN(date), MAX(date) FROM index_daily WHERE code = ?",
            (code,)
        )
        return cur.fetchone()

    # ── 데이터 조회 ────────────────────────────────────────
    def get(self, code: str, start_date: str, end_date: str) -> pd.DataFrame:
        """
        지수 데이터 조회. 없으면 자동 다운로드.
        Returns: DataFrame with columns [date, close]
        """
        db_min, db_max = self.get_date_range(code)

        # 필요한 구간 다운로드
        needs_download = []
        if db_min is None:
            needs_download.append((start_date, end_date))
        else:
            if start_date < db_min:
                needs_download.append((start_date, db_min))
            if end_date > db_max:
                needs_download.append((db_max, end_date))

        for s, e in needs_download:
            self._download_and_save(code, s, e)

        # DB 조회
        df = pd.read_sql(
            "SELECT date, close FROM index_daily WHERE code = ? AND date BETWEEN ? AND ? ORDER BY date",
            self.conn,
            params=(code, start_date, end_date),
        )
        return df

    # ── 전체 지수 다운로드 ─────────────────────────────────
    def download_all(self, force: bool = False):
        """
        INDEX_META에 정의된 모든 지수 다운로드.
        force=True면 이미 있어도 다시 다운로드.
        """
        print(f"총 {len(INDEX_META)}개 지수 다운로드 시작")
        print("=" * 60)

        success, skipped, failed = 0, 0, []

        for code, source, desc, start in INDEX_META:
            try:
                db_min, db_max = self.get_date_range(code)

                if not force and db_min is not None:
                    print(f"  ✅ 스킵: {code:12s} ({db_min}~{db_max})")
                    skipped += 1
                    continue

                end = datetime.today().strftime("%Y-%m-%d")
                df = self._fetch(code, source, start, end)

                if df is None or df.empty:
                    print(f"  ⚠️  데이터 없음: {code}")
                    failed.append(code)
                else:
                    self._save(code, df)
                    db_min, db_max = self.get_date_range(code)
                    print(f"  ✅ {code:12s} {desc:40s} ({db_min}~{db_max}, {len(df)}행)")
                    success += 1

                # meta 업데이트
                self.conn.execute("""
                    INSERT OR REPLACE INTO index_meta (code, source, description, start_date, last_update)
                    VALUES (?, ?, ?, ?, ?)
                """, (code, source, desc, start, datetime.today().strftime("%Y-%m-%d")))
                self.conn.commit()

                time.sleep(0.3)

            except Exception as e:
                print(f"  ❌ 실패: {code:12s} {e}")
                failed.append(code)
                time.sleep(0.3)

        print("\n" + "=" * 60)
        print(f"완료: {success}개 성공 / {skipped}개 스킵 / {len(failed)}개 실패")
        if failed:
            print(f"실패 목록: {failed}")

    # ── 내부: 다운로드 및 저장 ─────────────────────────────
    def _download_and_save(self, code: str, start: str, end: str):
        # source 찾기
        source = next((s for c, s, _, _ in INDEX_META if c == code), "yfinance")
        df = self._fetch(code, source, start, end)
        if df is not None and not df.empty:
            self._save(code, df)

    def _fetch(self, code: str, source: str, start: str, end: str) -> pd.DataFrame:
        """소스별 데이터 다운로드"""
        if source == "yfinance":
            return self._fetch_yfinance(code, start, end)
        elif source == "fdr":
            return self._fetch_fdr(code, start, end)
        elif source == "fdr_kr":
            return self._fetch_fdr_kr(code, start, end)
        elif source == "fred":
            return self._fetch_fred(code, start, end)
        return None

    def _fetch_yfinance(self, code: str, start: str, end: str) -> pd.DataFrame:
        import yfinance as yf
        ticker = yf.Ticker(code)
        df = ticker.history(start=start, end=end, auto_adjust=True)
        if df.empty:
            return None
        df = df.reset_index()
        df["date"] = pd.to_datetime(df["Date"]).dt.strftime("%Y-%m-%d")
        df = df.rename(columns={"Close": "close"})[["date", "close"]]
        df = df.dropna(subset=["close"])
        return df

    def _fetch_fdr(self, code: str, start: str, end: str) -> pd.DataFrame:
        import FinanceDataReader as fdr
        df = fdr.DataReader(code, start=start, end=end)
        if df.empty:
            return None
        df = df.reset_index()
        # 날짜 컬럼 찾기
        date_col = next((c for c in df.columns if "date" in c.lower() or "Date" in c), df.columns[0])
        # 가격 컬럼 찾기
        close_col = next((c for c in df.columns if c in ["Close", "close", "Adj Close", code.replace("/", "")]), None)
        if close_col is None:
            close_col = df.columns[-1]
        df["date"]  = pd.to_datetime(df[date_col]).dt.strftime("%Y-%m-%d")
        df["close"] = pd.to_numeric(df[close_col], errors="coerce")
        df = df[["date", "close"]].dropna()
        return df

    def _fetch_fdr_kr(self, code: str, start: str, end: str) -> pd.DataFrame:
        """한국 지수 (KOSPI200, KOSDAQ150) - FinanceDataReader KRX 방식"""
        import FinanceDataReader as fdr
        # KS200 → 코스피200, KQ150 → 코스닥150
        ticker_map = {"KS200": "KS200", "KQ150": "KQ150"}
        ticker = ticker_map.get(code, code)
        try:
            df = fdr.DataReader(ticker, start=start, end=end)
            if df.empty:
                return None
            df = df.reset_index()
            date_col  = df.columns[0]
            close_col = "Close" if "Close" in df.columns else df.columns[-1]
            df["date"]  = pd.to_datetime(df[date_col]).dt.strftime("%Y-%m-%d")
            df["close"] = pd.to_numeric(df[close_col], errors="coerce")
            return df[["date", "close"]].dropna()
        except Exception:
            # 대안: KOSPI200 → ^KS200 yfinance
            alt = {"KS200": "^KS200", "KQ150": "^KQ150"}
            return self._fetch_yfinance(alt.get(code, code), start, end)


        """FRED에서 금리 데이터 다운로드 (requests 사용)"""
        import requests
        url = (
            f"https://fred.stlouisfed.org/graph/fredgraph.csv"
            f"?id={code}&vintage_date={end}&cosd={start}&coed={end}"
        )
        resp = requests.get(url, timeout=30)
        if resp.status_code != 200:
            return None
        from io import StringIO
        df = pd.read_csv(StringIO(resp.text))
        df.columns = ["date", "close"]
        df["close"] = pd.to_numeric(df["close"], errors="coerce")
        df = df.dropna(subset=["close"])
        return df

    def _save(self, code: str, df: pd.DataFrame):
        """DB에 저장 (중복 무시)"""
        df = df.copy()
        df["code"] = code
        rows = df[["code", "date", "close"]].values.tolist()
        self.conn.executemany(
            "INSERT OR IGNORE INTO index_daily (code, date, close) VALUES (?, ?, ?)",
            rows
        )
        self.conn.commit()


if __name__ == "__main__":
    loader = IndexLoader()
    loader.download_all()