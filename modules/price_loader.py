import sqlite3
import pandas as pd
import yfinance as yf
import logging
import warnings
warnings.filterwarnings('ignore', category=FutureWarning)

from datetime import datetime, timedelta
from pathlib import Path

logging.getLogger("yfinance").setLevel(logging.CRITICAL)

BASE_DIR        = Path(__file__).resolve().parent.parent
DATA_DIR        = BASE_DIR / "data"
PRICE_CACHE_DIR = DATA_DIR / "price_cache"
META_DIR        = DATA_DIR / "meta"
DB_PATH         = PRICE_CACHE_DIR / "price_daily.db"
INDEX_DB_PATH   = META_DIR / "index_master.db"


def _load_us_tickers() -> set:
    us_etf_path = META_DIR / "us_etf_list.csv"
    tickers = set()
    if us_etf_path.exists():
        try:
            df = pd.read_csv(us_etf_path)
            tickers = set(df["code"].dropna().tolist())
        except Exception:
            pass
    return tickers


class PriceLoader:

    USD_KRW_START = "1964-05-04"

    def __init__(self):
        PRICE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
        self.index_conn = None
        if INDEX_DB_PATH.exists():
            self.index_conn = sqlite3.connect(str(INDEX_DB_PATH), check_same_thread=False)

        self._us_tickers      = _load_us_tickers()
        self._usdkrw_cache    = None
        self._backfill_engine = None   # 싱글톤
        self._price_cache     = {}     # 가격 데이터 캐시

        self.create_tables()
        self._auto_update_usdkrw()

    # -------------------------------------------------
    # USD/KRW 자동 업데이트
    # -------------------------------------------------

    def _auto_update_usdkrw(self):
        if self.index_conn is None:
            return
        try:
            from datetime import date
            import requests
            today  = date.today().strftime("%Y-%m-%d")
            row    = self.index_conn.execute(
                "SELECT MAX(date) FROM index_daily WHERE code='USD/KRW'"
            ).fetchone()
            db_max = row[0] if row and row[0] else None
            if db_max and db_max >= today:
                return
            start = (
                datetime.strptime(db_max, "%Y-%m-%d") + timedelta(days=1)
            ).strftime("%Y%m%d") if db_max else "19640101"
            end = datetime.today().strftime("%Y%m%d")
            ECOS_KEY = self._load_ecos_key()
            if not ECOS_KEY:
                return
            offset, batch, all_rows = 1, 10000, []
            while True:
                url = (
                    f"https://ecos.bok.or.kr/api/StatisticSearch/{ECOS_KEY}"
                    f"/json/kr/{offset}/{offset+batch-1}"
                    f"/731Y001/D/{start}/{end}/0000001"
                )
                resp = requests.get(url, timeout=15)
                data = resp.json()
                if "StatisticSearch" not in data:
                    break
                rows = data["StatisticSearch"].get("row", [])
                if not rows:
                    break
                all_rows.extend(rows)
                total = int(data["StatisticSearch"].get("list_total_count", 0))
                if offset + batch > total:
                    break
                offset += batch
            if all_rows:
                df = pd.DataFrame(all_rows)
                df["date"]  = pd.to_datetime(df["TIME"], format="%Y%m%d", errors="coerce").dt.strftime("%Y-%m-%d")
                df["close"] = pd.to_numeric(df["DATA_VALUE"], errors="coerce")
                df = df[["date", "close"]].dropna()
                df["code"] = "USD/KRW"
                self.index_conn.executemany(
                    "INSERT OR IGNORE INTO index_daily (code, date, close) VALUES (?, ?, ?)",
                    df[["code", "date", "close"]].values.tolist()
                )
                self.index_conn.commit()
                self._usdkrw_cache = None
                print(f"[PriceLoader] USD/KRW 업데이트: {db_max} → {df['date'].max()}")
        except Exception:
            pass

    def _load_ecos_key(self) -> str:
        import os
        key = os.environ.get("ECOS_API_KEY", "")
        if key:
            return key
        key_path = META_DIR / "ecos_api_key.txt"
        if key_path.exists():
            return key_path.read_text().strip()
        return ""

    # -------------------------------------------------
    # BackfillEngine 싱글톤
    # -------------------------------------------------

    def _get_backfill_engine(self):
        if self._backfill_engine is None:
            from modules.backfill_engine import BackfillEngine
            self._backfill_engine = BackfillEngine(verbose=False)
        return self._backfill_engine

    # -------------------------------------------------
    # 소멸자
    # -------------------------------------------------

    def __del__(self):
        try: self.conn.close()
        except: pass
        try:
            if self.index_conn:
                self.index_conn.close()
        except: pass

    # -------------------------------------------------
    # 테이블 생성
    # -------------------------------------------------

    def create_tables(self):
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS price_daily (
                code TEXT, date TEXT, open REAL, high REAL,
                low REAL, close REAL, volume REAL,
                PRIMARY KEY (code, date)
            )
        """)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS corporate_actions (
                code TEXT, date TEXT, dividend REAL, split REAL,
                PRIMARY KEY (code, date)
            )
        """)
        self.conn.commit()

    # -------------------------------------------------
    # 자산 판별
    # -------------------------------------------------

    def is_kr_etf(self, code: str) -> bool:
        return code.isdigit() and len(code) == 6

    def _kr_yf_ticker(self, code: str) -> str:
        return f"{code}.KS"

    def is_us_asset(self, code: str) -> bool:
        if code in self._us_tickers: return True
        if code.startswith("^"):     return True
        if code.endswith("=F"):      return True
        return False

    # -------------------------------------------------
    # USD/KRW 환율
    # -------------------------------------------------

    def _load_usdkrw(self) -> pd.Series:
        if self._usdkrw_cache is not None:
            return self._usdkrw_cache
        if self.index_conn is None:
            raise RuntimeError("index_master.db가 없습니다.")
        df = pd.read_sql(
            "SELECT date, close FROM index_daily WHERE code='USD/KRW' ORDER BY date",
            self.index_conn,
        )
        if df.empty:
            raise RuntimeError("USD/KRW 환율 데이터가 없습니다.")
        df["date"] = pd.to_datetime(df["date"])
        series     = df.set_index("date")["close"]
        full_idx   = pd.date_range(series.index.min(), series.index.max(), freq="D")
        series     = series.reindex(full_idx).ffill()
        self._usdkrw_cache = series
        return series

    def get_usdkrw(self, date: str) -> float:
        series = self._load_usdkrw()
        dt     = pd.Timestamp(date)
        if dt in series.index:
            return float(series[dt])
        before = series[series.index <= dt]
        if not before.empty:
            return float(before.iloc[-1])
        raise ValueError(f"USD/KRW 환율 데이터가 {date} 이전에 없습니다.")

    # -------------------------------------------------
    # 시작일 유효성 검사
    # -------------------------------------------------

    def validate_start_date(self, tickers: list, start_date: str) -> None:
        has_us = any(self.is_us_asset(t) for t in tickers)
        if not has_us:
            return
        if start_date < self.USD_KRW_START:
            raise ValueError(
                f"미국 자산 포트폴리오 시뮬 시작 가능일: {self.USD_KRW_START} 이후 "
                f"(요청: {start_date})"
            )

    # -------------------------------------------------
    # DB 날짜 범위 조회
    # -------------------------------------------------

    def get_date_range_in_db(self, code):
        cur = self.conn.execute(
            "SELECT MIN(date), MAX(date) FROM price_daily WHERE code = ?", (code,)
        )
        return cur.fetchone()

    # -------------------------------------------------
    # API 다운로드
    # -------------------------------------------------

    def fetch_from_api(self, code, start, end):
        df = yf.download(
            code, start=start, end=end,
            progress=False, auto_adjust=False,
            actions=True, threads=False
        )
        if df.empty:
            return None, None
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df = df.reset_index()
        df["Date"] = df["Date"].dt.strftime("%Y-%m-%d")
        df = df.rename(columns={
            "Date": "date", "Open": "open", "High": "high",
            "Low": "low", "Close": "close", "Volume": "volume",
            "Dividends": "dividend", "Stock Splits": "split"
        })
        if "dividend" not in df.columns: df["dividend"] = 0
        if "split"    not in df.columns: df["split"]    = 1
        df["dividend"] = df["dividend"].fillna(0)
        df["split"]    = df["split"].replace(0, 1).fillna(1)
        df["code"]     = code
        price_df  = df[["code", "date", "open", "high", "low", "close", "volume"]]
        action_df = df[["code", "date", "dividend", "split"]]
        return price_df, action_df

    def _insert_ignore(self, df, table):
        if df is None or df.empty:
            return
        cols         = ", ".join(df.columns)
        placeholders = ", ".join(["?"] * len(df.columns))
        self.conn.executemany(
            f"INSERT OR IGNORE INTO {table} ({cols}) VALUES ({placeholders})",
            df.values.tolist()
        )
        self.conn.commit()

    # -------------------------------------------------
    # 핵심 함수
    # -------------------------------------------------

    def get_price(self, code, start_date, end_date, apply_fx: bool = True):
        """
        가격 데이터 반환
        - 한국 ETF (6자리): .KS 붙여서 다운로드 + 자동 백필링
        - 미국 ETF: 자동 백필링
        - 미국 자산: USD/KRW 환율 적용 (apply_fx=True)
        - 캐시: 동일 코드+기간 두 번째 호출부터 즉시 반환
        """
        start_date = datetime.strptime(start_date, "%Y-%m-%d").date()
        end_date   = datetime.strptime(end_date,   "%Y-%m-%d").date()

        # ── 캐시 체크 ────────────────────────────────────────
        cache_key = f"{code}_{start_date}_{end_date}_{apply_fx}"
        if cache_key in self._price_cache:
            return self._price_cache[cache_key]

        # ── DB 범위 확인 및 API 호출 목록 생성 ───────────────
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

        # ── API 호출 ──────────────────────────────────────────
        yf_code = self._kr_yf_ticker(code) if self.is_kr_etf(code) else code
        for s, e in api_calls:
            price_df, action_df = self.fetch_from_api(
                yf_code, s.strftime("%Y-%m-%d"), e.strftime("%Y-%m-%d")
            )
            if price_df is not None and not price_df.empty:
                price_df = price_df.copy()
                price_df["code"] = code
            if action_df is not None and not action_df.empty:
                action_df = action_df.copy()
                action_df["code"] = code
            self._insert_ignore(price_df, "price_daily")
            self._insert_ignore(action_df, "corporate_actions")

        # ── 백필링 자동 실행 (싱글톤) ────────────────────────
        if self.is_kr_etf(code) or code in self._us_tickers:
            try:
                bf     = self._get_backfill_engine()
                result = bf.backfill(code)
                if result.get("status") == "ok":
                    print(f"[PriceLoader] 백필링 완료: {code} ({result['rows_added']:,}행 추가)")
            except Exception:
                pass

        # ── DB 조회 ───────────────────────────────────────────
        price_df = pd.read_sql(
            "SELECT date, open, high, low, close, volume FROM price_daily "
            "WHERE code = ? AND date BETWEEN ? AND ?",
            self.conn, params=(code, start_date, end_date)
        )
        action_df = pd.read_sql(
            "SELECT date, dividend, split FROM corporate_actions "
            "WHERE code = ? AND date BETWEEN ? AND ?",
            self.conn, params=(code, start_date, end_date)
        )
        action_df = action_df.groupby("date", as_index=False).agg({
            "dividend": "sum", "split": "prod"
        })

        df = price_df.merge(action_df, on="date", how="left")
        df["dividend"] = df["dividend"].fillna(0).infer_objects(copy=False)
        df["split"]    = df["split"].fillna(1).infer_objects(copy=False)

        # NaN 가격 제거
        df = df.dropna(subset=["close"])
        for col in ["open", "high", "low"]:
            df[col] = df[col].fillna(df["close"])

        # ── USD/KRW 환율 적용 (미국 자산만) ──────────────────
        if apply_fx and self.is_us_asset(code) and not df.empty:
            usdkrw = self._load_usdkrw()
            dates  = pd.to_datetime(df["date"])

            def get_rate(d):
                d = d.tz_localize(None) if d.tzinfo is not None else d
                if d in usdkrw.index:
                    return float(usdkrw[d])
                before = usdkrw[usdkrw.index <= d]
                return float(before.iloc[-1]) if not before.empty else 1.0

            rates = dates.map(get_rate).values
            for col in ["open", "high", "low", "close"]:
                if col in df.columns:
                    df[col] = df[col] * rates
            df["dividend"] = df["dividend"] * rates

        # ── 캐시 저장 후 반환 ─────────────────────────────────
        self._price_cache[cache_key] = df
        return df