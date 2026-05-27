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
            tickers = set(df["code"].dropna().astype(str).str.upper().tolist())
        except Exception:
            pass
    return tickers


def _load_kr_tickers() -> set:
    tickers = set()
    for path in (META_DIR / "kr_etf_list.csv",):
        if path.exists():
            try:
                df = pd.read_csv(path, dtype={"code": str})
                tickers.update(df["code"].dropna().astype(str).str.upper().tolist())
            except Exception:
                pass

    sym_db = META_DIR / "symbol_master.db"
    if sym_db.exists():
        try:
            with sqlite3.connect(str(sym_db)) as conn:
                rows = conn.execute(
                    "SELECT code FROM symbols WHERE country='KR'"
                ).fetchall()
            tickers.update(str(row[0]).upper() for row in rows if row and row[0])
        except Exception:
            pass
    return tickers


def _looks_like_krx_code(code: str) -> bool:
    code = str(code).split(".")[0].upper()
    return bool(code) and len(code) == 6 and code[0].isdigit() and code.isalnum()


class PriceLoader:

    USD_KRW_START = "1964-05-04"

    def __init__(self):
        PRICE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
        self.index_conn = None
        if INDEX_DB_PATH.exists():
            self.index_conn = sqlite3.connect(str(INDEX_DB_PATH), check_same_thread=False)

        self._us_tickers      = _load_us_tickers()
        self._kr_tickers      = _load_kr_tickers()
        self._usdkrw_cache    = None
        self._backfill_engine = None   # 싱글톤
        self._price_cache     = {}     # 가격 데이터 캐시
        self._backfilled_codes: set = set()  # backfill 성공한 ticker (재시도 불필요)
        self._backfill_skip_codes: set = set()  # 재시도해도 의미없는 ticker (no_meta 등)

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
        code = str(code).split(".")[0].upper()
        return code in self._kr_tickers or _looks_like_krx_code(code)

    def _kr_yf_ticker(self, code: str) -> str:
        return f"{str(code).split('.')[0].upper()}.KS"

    def is_us_asset(self, code: str) -> bool:
        code = str(code).upper()
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
        code = str(code).split(".")[0].upper()
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

        # ── 백필링 자동 실행 (ticker당 1회) ─────────────────
        # _backfilled_codes: 성공 완료 → 재시도 불필요
        # _backfill_skip_codes: 영구 실패 (no_meta, no_index_map, no_pre_data) → 재시도 무의미
        _PERMANENT_SKIP = {"no_meta", "no_index_map", "no_pre_data", "empty_after_scale"}
        if (
            (self.is_kr_etf(code) or code in self._us_tickers)
            and code not in self._backfilled_codes
            and code not in self._backfill_skip_codes
        ):
            try:
                bf     = self._get_backfill_engine()
                result = bf.backfill(code)
                status = result.get("status", "")
                if status == "ok":
                    print(f"[PriceLoader] 백필링 완료: {code} ({result['rows_added']:,}행 추가)")
                    self._backfilled_codes.add(code)
                elif status in _PERMANENT_SKIP:
                    self._backfill_skip_codes.add(code)
                # 그 외(no_index_data, scale_failed, no_etf_data): 재시도 허용 → 아무것도 추가 안 함
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
    # -------------------------------------------------
    # 종목 상세 데이터 (symbol detail page용)
    # -------------------------------------------------

    def get_symbol_data(self, code: str) -> dict:
        """
        종목 상세 페이지용 데이터 반환
        - KR 주식/ETF (6자리): yfinance .KS
        - US ETF/주식/지수/선물: yfinance
        - KRX 금현물: index_master.db
        - 기타 (BTC-USD 등): yfinance 직접
        """
        import sqlite3 as _sq
        from datetime import datetime as _dt, timedelta as _td

        code     = str(code).split(".")[0].upper()
        today    = _dt.today().strftime("%Y-%m-%d")
        start_dl = "2000-01-01"

        # ── KRX 금현물 특별 처리 ────────────────────────
        if code == "KRX_GOLD":
            if self.index_conn is None:
                raise ValueError("KRX_GOLD 데이터 없음")
            rows = self.index_conn.execute(
                "SELECT date, close FROM index_daily WHERE code='KRX_GOLD' ORDER BY date"
            ).fetchall()
            if not rows:
                raise ValueError("KRX_GOLD 데이터 없음")
            prices    = [{"date": r[0], "close": round(float(r[1]), 2)} for r in rows]
            cur_price = prices[-1]["close"]
            prev_price = prices[-2]["close"] if len(prices) > 1 else None
            cutoff_1y  = (_dt.now() - _td(days=365)).strftime("%Y-%m-%d")
            prices_1y  = [p["close"] for p in prices if p["date"] >= cutoff_1y]
            return {
                "code": "KRX_GOLD", "name": "금 (KRX 현물)",
                "country": "KR", "currency": "KRW",
                "current_price": cur_price, "prev_price": prev_price,
                "last_date": prices[-1]["date"],
                "high_52w": max(prices_1y) if prices_1y else None,
                "low_52w":  min(prices_1y) if prices_1y else None,
                "div_yield": None, "issuer": "KRX", "category": "금현물",
                "expense_ratio": None, "aum": None,
                "dividends": [], "prices": prices, "is_index": True,
            }

        # ── 가격 로드 ─────────────────────────────────
        is_kr = self.is_kr_etf(code)
        _INDEX_FUTURES = frozenset({'GC=F', 'SI=F', 'CL=F', 'NG=F', 'KRW=X'})
        is_index = code.startswith('^') or code in _INDEX_FUTURES
        if is_index:
            country  = 'KR' if code == '^KS11' else 'US'
            currency = 'KRW' if code in ('^KS11', 'KRW=X') else 'USD'
        else:
            currency = "KRW" if is_kr else "USD"
            country  = "KR"  if is_kr else "US"

        # ── 지수: index_daily 우선 조회, stale이면 yfinance로 최근분 보충 ──
        _INDEX_DB_ALIAS = {'KRW=X': 'USD/KRW', '^KS11': 'KS200'}
        _INDEX_NAMES    = {
            'KRW=X': '달러/원 환율',    '^GSPC': 'S&P 500',
            '^IXIC': 'NASDAQ Composite', '^KS11': '코스피 (KOSPI)',
            'GC=F':  '금 선물 (COMEX)', '^NDX':  'NASDAQ-100',
            '^DJI':  '다우존스',         '^N225': '닛케이 225',
        }
        if is_index and self.index_conn is not None:
            db_code  = _INDEX_DB_ALIAS.get(code, code)
            idx_rows = self.index_conn.execute(
                "SELECT date, close FROM index_daily WHERE code=? ORDER BY date",
                (db_code,)
            ).fetchall()
            if idx_rows:
                prices    = [{"date": r[0], "close": round(float(r[1]), 4)} for r in idx_rows]
                last_date = prices[-1]["date"]
                five_ago  = (_dt.today() - _td(days=5)).strftime("%Y-%m-%d")
                if last_date < five_ago:
                    try:
                        gap_start = (_dt.strptime(last_date, "%Y-%m-%d") + _td(days=1)).strftime("%Y-%m-%d")
                        yf_raw = yf.download(code, start=gap_start, end=today,
                                             progress=False, auto_adjust=False, threads=False)
                        if not yf_raw.empty:
                            if isinstance(yf_raw.columns, pd.MultiIndex):
                                yf_raw.columns = yf_raw.columns.get_level_values(0)
                            yf_raw = yf_raw.reset_index()
                            for _, r in yf_raw.iterrows():
                                d = r["Date"].strftime("%Y-%m-%d") if hasattr(r["Date"], "strftime") else str(r["Date"])[:10]
                                prices.append({"date": d, "close": round(float(r["Close"]), 4)})
                    except Exception:
                        pass
                cur_price  = prices[-1]["close"]
                prev_price = prices[-2]["close"] if len(prices) > 1 else None
                last_date  = prices[-1]["date"]
                cutoff_1y  = (_dt.today() - _td(days=365)).strftime("%Y-%m-%d")
                prices_1y  = [p["close"] for p in prices if p["date"] >= cutoff_1y]
                return {
                    "code": code, "name": _INDEX_NAMES.get(code, code),
                    "country": country, "currency": currency,
                    "current_price": cur_price, "prev_price": prev_price,
                    "last_date": last_date,
                    "high_52w": max(prices_1y) if prices_1y else None,
                    "low_52w":  min(prices_1y) if prices_1y else None,
                    "div_yield": None, "issuer": None, "category": "INDEX",
                    "expense_ratio": None, "aum": None,
                    "dividends": [], "prices": prices, "is_index": True,
                }
            # index_daily에 없으면 아래 yfinance 경로로 fall-through

        df = self.get_price(code, start_dl, today, apply_fx=False)

        # get_price 실패 시 yfinance 직접 (BTC-USD 등)
        if df is None or df.empty:
            yf_code = self._kr_yf_ticker(code) if is_kr else code
            raw = yf.download(
                yf_code, period="5y", progress=False,
                auto_adjust=False, actions=True, threads=False
            )
            if raw.empty:
                raise ValueError(f"{code} 데이터를 찾을 수 없습니다.")
            if isinstance(raw.columns, pd.MultiIndex):
                raw.columns = raw.columns.get_level_values(0)
            raw = raw.reset_index()
            raw["Date"] = raw["Date"].dt.strftime("%Y-%m-%d")
            raw = raw.rename(columns={"Date": "date", "Close": "close", "Dividends": "dividend"})
            df = raw[["date", "close"]].copy()
            df["dividend"] = raw.get("dividend", 0)

        prices    = [{"date": row["date"], "close": round(float(row["close"]), 4)}
                     for _, row in df.iterrows()]
        cur_price = prices[-1]["close"]
        prev_price = prices[-2]["close"] if len(prices) > 1 else None
        last_date  = prices[-1]["date"]

        # 52주 고저
        cutoff_1y = (_dt.now() - _td(days=365)).strftime("%Y-%m-%d")
        prices_1y = [p["close"] for p in prices if p["date"] >= cutoff_1y]
        high_52w  = max(prices_1y) if prices_1y else None
        low_52w   = min(prices_1y) if prices_1y else None

        # 배당 내역 (지수/선물은 배당 없음)
        if is_index:
            dividends = []
            div_yield = None
        else:
            divs_raw = self.conn.execute(
                "SELECT date, dividend FROM corporate_actions "
                "WHERE code=? AND dividend > 0 ORDER BY date DESC LIMIT 12",
                (code,)
            ).fetchall()
            dividends   = [{"date": r[0], "dividend": round(float(r[1]), 6)} for r in divs_raw]
            recent_divs = [d["dividend"] for d in dividends if d["date"] >= cutoff_1y]
            div_yield   = (sum(recent_divs) / cur_price * 100) if cur_price and recent_divs else None

        # 메타 정보 (symbol_master.db)
        sym_db = META_DIR / "symbol_master.db"
        name = issuer = category = ""
        if sym_db.exists():
            sc  = _sq.connect(str(sym_db))
            row = sc.execute("SELECT * FROM symbols WHERE code=?", (code,)).fetchone()
            sc.close()
            if row:
                cols = [d[0] for d in sc.description] if False else \
                       ["id","code","name","market","country","is_etf",
                        "underlying_symbol","category","index_name","issuer","leverage","hedge"]
                d    = dict(zip(cols, row))
                name     = d.get("name", "")
                issuer   = d.get("issuer", "") or ""
                category = d.get("category", "") or ""

        # KR ETF → kr_etf_list.csv 보완
        if is_kr and not issuer:
            try:
                kr_csv = META_DIR / "kr_etf_list.csv"
                if kr_csv.exists():
                    kr_df = pd.read_csv(str(kr_csv))
                    r = kr_df[kr_df["code"].astype(str) == code]
                    if not r.empty:
                        issuer   = str(r.iloc[0].get("issuer", ""))
                        category = category or str(r.iloc[0].get("index", ""))
            except Exception:
                pass

        # US ETF → us_etf_list.csv 보완
        if not is_kr and not category:
            try:
                us_csv = META_DIR / "us_etf_list.csv"
                if us_csv.exists():
                    us_df = pd.read_csv(str(us_csv))
                    r = us_df[us_df["code"] == code]
                    if not r.empty:
                        category = str(r.iloc[0].get("category", ""))
            except Exception:
                pass

        # yfinance 메타 (AUM, 보수율, 이름 보완)
        aum = expense_ratio = None
        try:
            yf_code = self._kr_yf_ticker(code) if is_kr else code
            info    = yf.Ticker(yf_code).info
            if not name: name = info.get("longName", code)
            if not issuer:
                issuer = info.get("fundFamily", "") or info.get("company", "")
            if not category:
                category = info.get("category", "") or info.get("sector", "")
            aum           = info.get("totalAssets")
            expense_ratio = info.get("expenseRatio") or info.get("annualReportExpenseRatio")
        except Exception:
            pass

        if not name:
            name = code
        if is_index and not category:
            category = 'INDEX'

        return {
            "code": code, "name": name,
            "country": country, "currency": currency,
            "current_price": cur_price, "prev_price": prev_price,
            "last_date": last_date, "high_52w": high_52w, "low_52w": low_52w,
            "div_yield": div_yield, "issuer": issuer, "category": category,
            "expense_ratio": expense_ratio, "aum": aum,
            "dividends": dividends, "prices": prices,
            "is_index": is_index,
        }
