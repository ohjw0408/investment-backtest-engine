"""
backfill_engine.py
────────────────────────────────────────────────────────────────────────────────
한국 상장 ETF의 상장일 이전 데이터를 기초지수로 백필링

흐름:
  1. kr_etf_list.csv에서 ETF 메타데이터 로드
  2. index_master.db에서 기초지수 데이터 로드
  3. ETF 상장일 기준 스케일 맞추기
  4. 레버리지 적용 (일간 수익률 × leverage)
  5. 환율 적용 (market=US, hedge=unhedged → × USD/KRW)
  6. price_daily.db에 저장

사용법:
  engine = BackfillEngine()
  engine.backfill("360750")        # 단일 ETF
  engine.backfill_all()            # 전체 ETF
────────────────────────────────────────────────────────────────────────────────
"""

import sqlite3
import logging
from pathlib import Path

import pandas as pd
import numpy as np

from modules.seed_util import stable_seed

logging.getLogger("yfinance").setLevel(logging.CRITICAL)

# 배당 없는 지수 — 배당 주입 제외
# (원자재·FX·금리수치는 무배당 또는 별도 모델. DJUSDIV_PROXY는 Phase 6.0에서 price-return
#  체인으로 재구축되어 배당을 분리 주입하므로 더 이상 제외하지 않음.)
# 채권 금리(DGS*)는 Stage B(Phase 7)에서 가격 모델 + 쿠폰 분배금으로 처리 예정.
_NO_DIVIDEND_INDICES: set[str] = {
    "DGS30", "DGS10", "DGS3MO",
    "GC=F", "SI=F", "CL=F", "HG=F",
    "USD/KRW", "USD/JPY",
    "KRX_GOLD",   # 금현물 — 배당 없음
}

# 금현물·국제금(unhedged) ETF: 상장전 프록시를 KRX_GOLD(KRW/g 네이티브, FX 포함)로.
# GC=F(USD)는 환율 미반영이라 unhedged 원화 ETF엔 형태가 틀림 → 환헤지 선물 ETF만 GC=F 유지.
_GOLD_KRX_SPOT: set[str] = {"411060", "0072R0", "0064K0", "0066W0"}

# 프록시 지수 → 배당수익률 테이블(index_div_yield) 별칭.
# DJUSDIV_PROXY 가격 체인의 배당은 DJUSDIV100 실측 yield(2011~2026)로 주입.
_YIELD_TABLE_ALIAS: dict[str, str] = {
    "DJUSDIV_PROXY": "DJUSDIV100",
}

BASE_DIR      = Path(__file__).resolve().parent.parent
DATA_DIR      = BASE_DIR / "data"
META_DIR      = DATA_DIR / "meta"
PRICE_DIR     = DATA_DIR / "price_cache"

INDEX_DB_PATH = META_DIR / "index_master.db"
PRICE_DB_PATH = PRICE_DIR / "price_daily.db"
KR_ETF_PATH   = META_DIR / "kr_etf_list.csv"

# ── US ETF category → index_master.db 코드 매핑 ──────────
US_CATEGORY_MAP = {
    "US Equity - Large Cap Blend":      "^GSPC",
    "US Equity - Large Cap Growth":     "^NDX",
    "US Equity - Large Cap Value":      "^GSPC",
    "US Equity - Total Market":         "^GSPC",
    "US Equity - Mid Cap Blend":        "^GSPC",
    "US Equity - Small Cap Blend":      "^RUT",
    "US Equity - Small Cap Growth":     "^RUT",
    "US Equity - Small Cap Value":      "^RUT",
    "US Equity - Dividend":             "DJUSDIV_PROXY",  # SCHD<-SDY<-DVY<-^GSPC chain
    "US Equity - Dividend Growth":      "DJUSDIV_PROXY",  # SCHD<-SDY<-DVY<-^GSPC chain
    "US Equity - Factor":               "^GSPC",
    "US Bond - Long Treasury":          "DGS30",
    "US Bond - Intermediate Treasury":  "DGS10",
    "US Bond - Short Treasury":         "DGS3MO",
    "US Bond - Aggregate":              "DGS10",
    "US Bond - Corporate IG":           "DGS10",
    "US Bond - High Yield":             "DGS10",
    "US Bond - TIPS":                   "DGS10",
    "US Bond - MBS":                    "DGS10",
    "US Bond - Municipal":              "DGS10",
    "Commodity - Gold":                 "GC=F",
    "Commodity - Silver":               "SI=F",
    "Commodity - Energy":               "CL=F",
    "Commodity - Precious Metals":      "GC=F",
    "Commodity - Broad":                "CL=F",
    "Commodity - Agriculture":          None,
    "International Equity - Developed": "ACWI",
    "International Equity - Emerging":  "EEM",
    "International Equity - Country":   "ACWI",
    "Global Equity":                    "ACWI",
    "International Bond":               "DGS10",
    "Emerging Markets Bond":            "DGS10",
    "US Sector - Technology":           "^NDX",
    "US Sector - Healthcare":           "^GSPC",
    "US Sector - Financials":           "^GSPC",
    "US Sector - Energy":               "CL=F",
    "US Sector - Consumer Discretionary": "^GSPC",
    "US Sector - Consumer Staples":     "^GSPC",
    "US Sector - Industrials":          "^GSPC",
    "US Sector - Materials":            "^GSPC",
    "US Sector - Real Estate":          "^GSPC",
    "US Sector - Utilities":            "^GSPC",
    "US Sector - Communication":        "^GSPC",
    "Asset Allocation":                 "^GSPC",
    "Thematic":                         "^GSPC",
    "Covered Call":                     "^GSPC",
    "Leveraged":                        None,
    "Inverse":                          None,
    "Crypto":                           None,
}

# ── 지수 → index_master.db 코드 매핑 ──────────────────────
INDEX_MAP = {
    "SP500":               "^GSPC",
    "NASDAQ100":           "^NDX",
    "KOSPI200":            "KS200",
    "KOSPI":               "KS200",
    "KRX300":              "KS200",
    "KOSDAQ150":           "KQ150",   # KODEX229200<-^KQ11 chain
    "DJ_US_DIVIDEND":      "DJUSDIV_PROXY",  # SCHD<-SDY<-DVY<-^GSPC chain
    "PHLX_SEMICONDUCTOR":  "^SOX",
    "US_TREASURY_30Y":     "DGS30",
    "US_TREASURY_10Y":     "DGS10",
    "US_TREASURY":         "DGS10",
    "GOLD":                "GC=F",
    "SILVER":              "SI=F",
    "COPPER":              "HG=F",
    "OIL":                 "CL=F",
    "JAPAN_NIKKEI225":     "^N225",
    "JAPAN_TOPIX":         "TPX.F",
    "CHINA_HSCEI":         "^HSCE",
    "CHINA_CSI300":        "000300.SS",
    "INDIA_NIFTY50":       "^NSEI",
    "MSCI_WORLD":          "ACWI",
    "MSCI_EM":             "EEM",
    "DOW":                 "^DJI",
    "RUSSELL2000":         "^RUT",
    "EUROPE":              "^STOXX50E",
}


def inject_quarterly_dividends(
    price_conn: sqlite3.Connection,
    code: str,
    price_series: pd.Series,
    annual_yield_src: tuple,
    seed: int = 0,
    table_name: str = "corporate_actions",
) -> int:
    """
    분기말(3,6,9,12월 마지막 거래일)에 배당 레코드를 corporate_actions에 삽입.

    annual_yield_src 형식:
      ("table",   yield_table: dict[int, float], resolve_fn)  → Tier 1+2
      ("musigma", mu: float, sigma: float)                    → Tier 3
    """
    QUARTER_END_MONTHS = {3, 6, 9, 12}
    rng     = np.random.default_rng(seed=seed)
    records = []

    for year in sorted(price_series.index.year.unique()):
        mode = annual_yield_src[0]

        if mode == "table":
            _, yield_table, resolve_fn = annual_yield_src
            annual_yield = resolve_fn(yield_table, year)
        else:  # "musigma"
            _, mu, sigma = annual_yield_src
            annual_yield = max(0.0, float(rng.normal(mu, sigma)))

        if annual_yield <= 0:
            continue

        for month in QUARTER_END_MONTHS:
            mask  = (price_series.index.year == year) & (price_series.index.month == month)
            dates = price_series.index[mask]
            if dates.empty:
                continue
            ex_date = dates[-1]
            div     = float(price_series[ex_date]) * (annual_yield / 4.0)
            records.append((code, ex_date.strftime("%Y-%m-%d"), round(div, 6), 1.0))

    if not records:
        return 0, []

    price_conn.executemany(
        f"INSERT OR IGNORE INTO {table_name} (code, date, dividend, split) VALUES (?,?,?,?)",
        records,
    )
    price_conn.commit()
    return len(records), [r[1] for r in records]


def inject_monthly_coupons(
    price_conn: sqlite3.Connection,
    code: str,
    price_series: pd.Series,
    yield_series: pd.Series,
    freq: int = 12,
    book_factor: float = 1.0,
    table_name: str = "corporate_actions",
) -> tuple:
    """채권 쿠폰(이자)을 월말에 분배금으로 corporate_actions에 주입 (Stage B).

    쿠폰 = price[ex_date] × (해당시점 yield(%) / 100) / freq × book_factor.
    book_factor: 모델 쿠폰(현재 시장금리)을 실측 분배(book yield, 보수 차감)에 맞추는 보정(<1).
    yield_series = 금리(%) 시계열 (DGS* 등). 백필 가격구간(price_series)에만 주입한다.
    """
    if price_series.empty:
        return 0, []
    y = yield_series.dropna().sort_index().astype(float)
    if y.empty:
        return 0, []

    records = []
    # 월별 마지막 거래일
    month_last = pd.Series(price_series.index, index=price_series.index).groupby(
        [price_series.index.year, price_series.index.month]
    ).last()
    for ex_date in month_last:
        yv = y[y.index <= ex_date]
        if yv.empty:
            continue
        rate = float(yv.iloc[-1]) / 100.0
        if rate <= 0:
            continue
        coupon = float(price_series[ex_date]) * rate / float(freq) * float(book_factor)
        if coupon <= 0:
            continue
        records.append((code, ex_date.strftime("%Y-%m-%d"), round(coupon, 6), 1.0))

    if not records:
        return 0, []
    price_conn.executemany(
        f"INSERT OR IGNORE INTO {table_name} (code, date, dividend, split) VALUES (?,?,?,?)",
        records,
    )
    price_conn.commit()
    return len(records), [r[1] for r in records]


class BackfillEngine:

    def __init__(self, verbose: bool = True):
        self.verbose    = verbose
        self.index_conn = sqlite3.connect(str(INDEX_DB_PATH), check_same_thread=False)
        self.price_conn = sqlite3.connect(str(PRICE_DB_PATH), check_same_thread=False)
        self._index_cache: dict = {}
        self._usdkrw_cache      = None
        self._etf_meta          = self._load_etf_meta()
        self._ensure_corporate_actions_table()
        from modules.provenance import ensure_provenance_tables
        ensure_provenance_tables(self.price_conn)

    def __del__(self):
        try: self.index_conn.close()
        except: pass
        try: self.price_conn.close()
        except: pass

    # ── 메타데이터 로드 ────────────────────────────────────

    def _load_etf_meta(self) -> pd.DataFrame:
        """KR + US ETF 메타데이터 통합 로드"""
        frames = []

        # 한국 ETF
        if KR_ETF_PATH.exists():
            kr = pd.read_csv(KR_ETF_PATH, dtype=str)
            kr["leverage"] = pd.to_numeric(kr["leverage"], errors="coerce").fillna(1.0)
            kr["etf_type"] = "KR"
            frames.append(kr)

        # 미국 ETF
        us_etf_path = META_DIR / "us_etf_list.csv"
        if us_etf_path.exists():
            us = pd.read_csv(us_etf_path, dtype=str)
            us["index"]    = us["category"].map(US_CATEGORY_MAP)
            us["market"]   = "US"
            us["leverage"] = 1.0
            us["hedge"]    = "unhedged"
            us["etf_type"] = "US"
            frames.append(us)

        if not frames:
            raise FileNotFoundError("ETF 메타데이터 파일이 없습니다.")

        df = pd.concat(frames, ignore_index=True)
        return df.set_index("code")

    # ── corporate_actions 테이블 보장 ─────────────────────

    def _ensure_corporate_actions_table(self):
        self.price_conn.execute("""
            CREATE TABLE IF NOT EXISTS corporate_actions (
                code     TEXT,
                date     TEXT,
                dividend REAL,
                split    REAL,
                PRIMARY KEY (code, date)
            )
        """)
        self.price_conn.commit()

    # ── 배당수익률 DB 조회 (Tier 1+2) ────────────────────

    def _load_div_yield_table(self, index_code: str) -> dict[int, float] | None:
        """index_master.db의 index_div_yield에서 연도별 수익률 조회.

        프록시 지수에 자체 yield 테이블이 없으면 _YIELD_TABLE_ALIAS로 대체 조회.
        (예: DJUSDIV_PROXY → DJUSDIV100 실측 yield)
        """
        lookup = _YIELD_TABLE_ALIAS.get(index_code, index_code)
        rows = self.index_conn.execute(
            "SELECT year, annual_yield FROM index_div_yield "
            "WHERE index_code=? ORDER BY year",
            (lookup,),
        ).fetchall()
        return {int(yr): float(val) for yr, val in rows} if rows else None

    def _resolve_yield(self, yield_table: dict[int, float], year: int) -> float:
        """
        테이블 내 연도가 있으면 반환.
        없으면(프록시 이전 구간) 테이블 전체 mu/sigma로 가상 생성.
        seed=year로 재현성 보장.
        """
        if year in yield_table:
            return yield_table[year]

        values = list(yield_table.values())
        mu     = float(np.mean(values))
        sigma  = max(float(np.std(values)), mu * 0.10)
        rng    = np.random.default_rng(seed=year)
        return max(0.0, float(rng.normal(mu, sigma)))

    # ── ETF 실측 배당 mu/sigma (Tier 3) ──────────────────

    def _load_etf_actual_div_yield(self, code: str) -> tuple[float, float] | None:
        """ETF 자신의 corporate_actions 실측 데이터에서 연간 배당수익률 mu/sigma 계산."""
        rows = self.price_conn.execute("""
            SELECT strftime('%Y', ca.date) yr,
                   SUM(ca.dividend)        total_div,
                   AVG(pd.close)           avg_price
            FROM corporate_actions ca
            JOIN price_daily pd ON ca.code = pd.code AND ca.date = pd.date
            WHERE ca.code = ? AND ca.dividend > 0
            GROUP BY yr
        """, (code,)).fetchall()

        if not rows:
            return None

        yields = [float(r[1]) / float(r[2]) for r in rows if r[2] and float(r[2]) > 0]
        if not yields:
            return None

        mu    = float(np.mean(yields))
        sigma = max(
            float(np.std(yields)) if len(yields) >= 2 else mu * 0.20,
            mu * 0.10,
        )
        return mu, sigma

    # ── 지수 데이터 로드 (캐시) ───────────────────────────

    def _load_index(self, index_code: str) -> pd.Series | None:
        if index_code in self._index_cache:
            return self._index_cache[index_code]

        # KRX_GOLD: KRW/g 연속 시계열(2014~ KRX금 + 2014이전 GC=F×환율) — price_loader와 공유
        if index_code == "KRX_GOLD":
            from modules.price_loader import build_krx_gold_krw_series
            series = build_krx_gold_krw_series(self.index_conn, self._load_usdkrw())
            self._index_cache[index_code] = series
            return series

        df = pd.read_sql(
            "SELECT date, close FROM index_daily WHERE code=? ORDER BY date",
            self.index_conn,
            params=(index_code,),
        )
        if df.empty:
            return None

        df["date"] = pd.to_datetime(df["date"])
        series = df.set_index("date")["close"].astype(float)
        self._index_cache[index_code] = series
        return series

    # ── 환율 데이터 로드 (캐시) ───────────────────────────

    def _load_usdkrw(self) -> pd.Series:
        if self._usdkrw_cache is not None:
            return self._usdkrw_cache

        df = pd.read_sql(
            "SELECT date, close FROM index_daily WHERE code='USD/KRW' ORDER BY date",
            self.index_conn,
        )
        df["date"] = pd.to_datetime(df["date"])
        series = df.set_index("date")["close"].astype(float)
        full_idx = pd.date_range(series.index.min(), series.index.max(), freq="D")
        series   = series.reindex(full_idx).ffill()
        self._usdkrw_cache = series
        return series

    # ── ETF 기존 데이터 범위 조회 ─────────────────────────

    def _get_etf_range(self, code: str):
        # 실제 상장일: volume>0인 첫 날 (백필 데이터는 volume=0으로 저장)
        listing = self.price_conn.execute(
            "SELECT MIN(date) FROM price_daily WHERE code=? AND volume > 0", (code,)
        ).fetchone()[0]
        if listing is None:
            # 백필 이전 (첫 다운로드 직후): volume 무관 MIN
            listing = self.price_conn.execute(
                "SELECT MIN(date) FROM price_daily WHERE code=?", (code,)
            ).fetchone()[0]
        max_date = self.price_conn.execute(
            "SELECT MAX(date) FROM price_daily WHERE code=?", (code,)
        ).fetchone()[0]
        return listing, max_date

    # ── 저장 ──────────────────────────────────────────────

    def _save(self, code: str, df: pd.DataFrame):
        df = df.copy()
        df["code"] = code
        rows = df[["code", "date", "open", "high", "low", "close", "volume"]].values.tolist()
        self.price_conn.executemany(
            "INSERT OR IGNORE INTO price_daily (code, date, open, high, low, close, volume) VALUES (?,?,?,?,?,?,?)",
            rows
        )
        self.price_conn.commit()

    # ── 레버리지 적용 ─────────────────────────────────────

    def _apply_leverage(self, series: pd.Series, leverage: float) -> pd.Series:
        """일간 수익률에 레버리지 적용 후 첫 번째 값 기준 복원"""
        if leverage == 1.0:
            return series
        daily_ret = series.pct_change().fillna(0)
        lev_ret   = daily_ret * leverage
        result    = (1 + lev_ret).cumprod() * series.iloc[0]
        return result

    # ── 스케일 맞추기 ─────────────────────────────────────

    def _scale_to_etf(
        self,
        index_series: pd.Series,
        etf_series:   pd.Series,
        etf_start:    pd.Timestamp,
    ) -> pd.Series | None:
        """
        ETF 상장일 기준으로 지수 데이터 스케일 조정
        ETF 첫 거래일 가격 / 지수 첫 거래일 값 = scale factor
        """
        # 지수에서 ETF 상장일 이후 첫 번째 날짜 찾기
        idx_after = index_series.index[index_series.index >= etf_start]
        if len(idx_after) == 0:
            return None
        scale_date = idx_after[0]

        # ETF에서 같은 날짜 또는 이후 첫 번째 날짜 찾기
        etf_after = etf_series.index[etf_series.index >= scale_date]
        if len(etf_after) == 0:
            return None
        etf_scale_date = etf_after[0]

        # 지수도 같은 날짜로 맞추기
        idx_match = index_series.index[index_series.index >= etf_scale_date]
        if len(idx_match) == 0:
            return None
        final_scale_date = idx_match[0]

        index_val = index_series[final_scale_date]
        etf_val   = etf_series[etf_scale_date]

        if index_val == 0:
            return None

        scale  = etf_val / index_val
        scaled = index_series * scale
        return scaled

    # ── 단일 ETF 백필링 ───────────────────────────────────

    def backfill(self, code: str) -> dict:
        """단일 ETF 백필링"""
        if code not in self._etf_meta.index:
            return {"code": code, "status": "no_meta"}

        meta = self._etf_meta.loc[code]
        if isinstance(meta, pd.DataFrame):
            meta = meta.iloc[0]
        index_nm  = str(meta["index"])
        market    = str(meta["market"])
        leverage  = float(meta["leverage"])
        hedge     = str(meta["hedge"])
        name      = str(meta.get("name", code))

        # 채권 ETF (Stage B): 명시 config(rate 금리시계열 + duration)로 직접 매핑.
        # us_etf_list category가 "US Fixed Income"으로 뭉뚱그려져 듀레이션 구분 불가하므로
        # ETF 코드로 직접 키잉한다 (etf_proxy_map 씨앗).
        from modules.bond_model import (
            bond_config, build_bond_price_series, COUPON_FREQ_PER_YEAR,
            COUPON_BOOK_FACTOR, STRIP_DURATION_MULT, unsupported_currency,
        )
        etf_type = str(meta.get("etf_type", "KR"))
        us_category = str(meta.get("category", "")) if etf_type == "US" else None
        # US 채권은 코드 dict > 영문명 키워드 분류기(category=US Fixed Income일 때만). KR은 index 카테고리.
        bcfg    = bond_config(code, index_nm, name=name, etf_type=etf_type, us_category=us_category)
        is_bond = bcfg is not None
        # 통화 가드: 비USD/KRW 통화 노출 채권(엔화·유로 등)은 우리 FX엔진이 USD로 둔갑시켜
        # 백필하면 환율 틀림 → 거부(안전스킵). 라벨이 'US Treasury'로 맞아도 차단.
        if is_bond and unsupported_currency(name):
            return {"code": code, "status": "currency_unsupported_skip"}
        # 스트립(무이표)은 듀레이션 ≈ 만기로 길다 → 이름 감지해 가산.
        # 레버리지/인버스는 meta.leverage로 아래 _apply_leverage가 기존 로직으로 처리.
        if is_bond and ("스트립" in name or "strip" in name.lower()):
            bcfg = {**bcfg, "duration": bcfg["duration"] * STRIP_DURATION_MULT}

        # 지수 코드 매핑
        # US ETF는 index 컬럼이 이미 index_master.db 코드 (^GSPC, DGS30 등)
        # KR ETF는 index 컬럼이 SP500, NASDAQ100 등 → INDEX_MAP으로 변환
        if is_bond:
            index_code = bcfg["rate"]
        elif etf_type == "US":
            index_code = index_nm if index_nm and index_nm != "None" else None
        else:
            index_code = INDEX_MAP.get(index_nm)

        # 금현물·국제금 ETF는 GC=F 대신 KRX_GOLD(KRW/g 네이티브) 프록시 사용
        if code in _GOLD_KRX_SPOT:
            index_code = "KRX_GOLD"

        if not index_code or index_code == "None":
            return {"code": code, "status": f"no_index_map ({index_nm})"}

        # ETF 기존 데이터 확인
        etf_min, etf_max = self._get_etf_range(code)
        if etf_min is None:
            return {"code": code, "status": "no_etf_data"}

        etf_start = pd.Timestamp(etf_min)

        # 이미 백필된 경우 스킵 (volume=0인 상장 이전 데이터 존재)
        already = self.price_conn.execute(
            "SELECT COUNT(*) FROM price_daily WHERE code=? AND volume=0 AND date < ?",
            (code, etf_min)
        ).fetchone()[0]
        if already > 0:
            if self.verbose:
                print(f"[BackfillEngine] {code} 이미 백필됨 ({already:,}행) → 스킵")
            return {"code": code, "status": "ok", "rows_added": 0,
                    "date_from": None, "date_to": None, "div_rows_written": 0}

        # 지수 데이터 로드
        index_series = self._load_index(index_code)
        if index_series is None:
            return {"code": code, "status": f"no_index_data ({index_code})"}

        # 인덱스 충분성 체크: 100행 미만이면 프록시로 사용 거부
        # (예: DJUSDIV100 1행처럼 사실상 빈 데이터 방지)
        _MIN_INDEX_ROWS = 100
        if len(index_series) < _MIN_INDEX_ROWS:
            return {
                "code": code,
                "status": f"index_insufficient ({index_code}: {len(index_series)} rows < {_MIN_INDEX_ROWS})",
            }

        # 채권: yield(%) 시계열 → price-return 지수로 변환 (캐리=이자는 쿠폰으로 분리).
        bond_yield = None
        if is_bond:
            bond_yield   = index_series.copy()
            # 환헤지 ETF(hedge="hedge"): 선물환 비용 = 미-한 단기금리차(DGS3MO − CD91)만큼
            # 수익 차감(covered interest parity). 그날그날 역사적 금리 사용 → 시대 무관.
            hedge_cost_pct = None
            if hedge == "hedge":
                us_short = self._load_index("DGS3MO")
                kr_short = self._load_index("CD91")
                if us_short is not None and kr_short is not None:
                    su = us_short.reindex(bond_yield.index).ffill()
                    sk = kr_short.reindex(bond_yield.index).ffill()
                    hedge_cost_pct = su - sk
            index_series = build_bond_price_series(
                index_series, bcfg["duration"], bcfg.get("model", "duration"),
                hedge_cost_pct=hedge_cost_pct)

        # ETF 상장일 이전 지수 데이터 확인
        pre_series = index_series[index_series.index < etf_start]
        if pre_series.empty:
            return {"code": code, "status": "no_pre_data"}

        # ETF 실제 가격 데이터
        etf_df = pd.read_sql(
            "SELECT date, close FROM price_daily WHERE code=? ORDER BY date",
            self.price_conn,
            params=(code,),
        )
        etf_df["date"] = pd.to_datetime(etf_df["date"])
        etf_series = etf_df.set_index("date")["close"].astype(float)

        # 레버리지 적용 (전체 구간에 적용)
        if leverage != 1.0:
            index_series = self._apply_leverage(index_series, leverage)

        # 환율 적용 여부 결정
        # - 한국 ETF (market=US, hedge=unhedged): ETF 가격이 원화이므로 환율 적용
        # - 미국 ETF: ETF 가격이 달러이므로 환율 적용 안 함 (get_price에서 처리)
        etf_type   = str(meta.get("etf_type", "KR"))
        fx_applied = etf_type == "KR" and market == "US" and hedge == "unhedged"

        if fx_applied:
            usdkrw = self._load_usdkrw()
            # FX 시계열 시작(USD/KRW=1964-05-04) 이전 구간은 환산 불가 — 과거 rate=1.0
            # 폴백이 ×255.77 절벽을 만들었다(379780, 2026-07-14 무결성 스캔).
            # 환산 불가 구간은 백필하지 않고 FX 시작일부터 절단한다.
            index_series = index_series[index_series.index >= usdkrw.index.min()]
            if index_series.empty:
                return {"code": code, "status": "no_fx_overlap"}
            def get_rate(d):
                if d in usdkrw.index:
                    return float(usdkrw[d])
                before = usdkrw[usdkrw.index <= d]
                return float(before.iloc[-1]) if not before.empty else 1.0
            rates        = index_series.index.map(get_rate)
            index_series = index_series * rates.values

        # 스케일 맞추기 (전체 index_series 기준, ETF 상장일 가격으로 맞춤)
        scaled = self._scale_to_etf(index_series, etf_series, etf_start)
        if scaled is None:
            return {"code": code, "status": "scale_failed"}

        # ETF 상장 이전 구간만
        scaled = scaled[scaled.index < etf_start]
        if scaled.empty:
            return {"code": code, "status": "empty_after_scale"}

        # DataFrame 구성
        df = pd.DataFrame({
            "date":   scaled.index.strftime("%Y-%m-%d"),
            "open":   scaled.values,
            "high":   scaled.values,
            "low":    scaled.values,
            "close":  scaled.values,
            "volume": 0.0,
        })

        self._save(code, df)

        # ── 배당/쿠폰 주입 ─────────────────────────────────
        div_rows = 0
        div_dates: list[str] = []
        if is_bond:
            # 채권: 쿠폰(이자)을 월 분배금으로 명시 주입 (해당시점 yield × price / 12).
            div_rows, div_dates = inject_monthly_coupons(
                price_conn=self.price_conn,
                code=code,
                price_series=scaled,
                yield_series=bond_yield,
                freq=COUPON_FREQ_PER_YEAR,
                book_factor=COUPON_BOOK_FACTOR,
            )
        elif leverage == 1.0 and index_code not in _NO_DIVIDEND_INDICES:
            yield_table = self._load_div_yield_table(index_code)

            if yield_table:
                # Tier 1+2: DB에 연도별 배당수익률 존재
                div_rows, div_dates = inject_quarterly_dividends(
                    price_conn=self.price_conn,
                    code=code,
                    price_series=scaled,
                    annual_yield_src=("table", yield_table, self._resolve_yield),
                    seed=stable_seed(code),
                )
            else:
                # Tier 3: ETF 자신의 실측 corporate_actions에서 mu/sigma 계산
                actual = self._load_etf_actual_div_yield(code)
                if actual:
                    div_rows, div_dates = inject_quarterly_dividends(
                        price_conn=self.price_conn,
                        code=code,
                        price_series=scaled,
                        annual_yield_src=("musigma", actual[0], actual[1]),
                        seed=stable_seed(code),
                    )
                # actual이 None이면 배당 없음 (비배당 ETF) → div_rows = 0

        # ── Provenance 기록 ───────────────────────────────
        from modules.provenance import (
            new_run_id, write_backfill_run, write_price_source,
            write_action_source, MODEL_VERSION_BACKFILL,
        )
        run_id     = new_run_id()
        confidence = "C" if (leverage != 1.0 or is_bond) else "B"
        write_price_source(
            conn=self.price_conn,
            run_id=run_id,
            code=code,
            dates=df["date"].tolist(),
            source_type="backfill",
            source_code=index_code,
            model_version=MODEL_VERSION_BACKFILL,
            confidence=confidence,
        )
        if div_dates:
            write_action_source(
                conn=self.price_conn,
                run_id=run_id,
                code=code,
                dates=div_dates,
                source_type="backfill",
                source_code=index_code,
                model_version=MODEL_VERSION_BACKFILL,
                confidence=confidence,
            )
        write_backfill_run(
            conn=self.price_conn,
            run_id=run_id,
            code=code,
            status="ok",
            method="index_proxy",
            model_version=MODEL_VERSION_BACKFILL,
            proxy_code=index_code,
            confidence=confidence,
            date_from=df["date"].min(),
            date_to=df["date"].max(),
            rows_written=len(df),
            div_rows_written=div_rows,
            fx_applied=fx_applied,
            leverage=leverage,
        )

        result = {
            "code":       code,
            "status":     "ok",
            "run_id":     run_id,
            "rows_added": len(df),
            "div_rows":   div_rows,
            "date_from":  df["date"].min(),
            "date_to":    df["date"].max(),
            "index_code": index_code,
            "leverage":   leverage,
            "fx_applied": fx_applied,
        }

        if self.verbose:
            fx_str  = " ×환율" if fx_applied else ""
            lev_str = f" ×{leverage}" if leverage != 1.0 else ""
            div_str = f" 배당{div_rows}건" if div_rows > 0 else ""
            print(f"  ✅ {code:8s} {name[:22]:22s} "
                  f"← {index_code:12s}{lev_str}{fx_str}{div_str} "
                  f"| {result['date_from']} ~ {result['date_to']} ({len(df):,}행)")

        return result

    # ── 전체 ETF 백필링 ───────────────────────────────────

    def backfill_all(self, market_filter: str = None) -> pd.DataFrame:
        """전체 ETF 백필링"""
        meta = self._etf_meta.copy()
        if market_filter:
            meta = meta[meta["market"] == market_filter]

        print(f"\n{'='*65}")
        print(f"전체 백필링 시작: {len(meta)}개 ETF")
        if market_filter:
            print(f"  필터: market={market_filter}")
        print(f"{'='*65}")

        results = []
        ok = skip = fail = 0

        for code in meta.index:
            result = self.backfill(code)
            results.append(result)
            status = result["status"]
            if status == "ok":
                ok += 1
            elif status in ("no_pre_data", "no_etf_data"):
                skip += 1
            else:
                fail += 1
                if self.verbose and status not in ("no_index_map",):
                    print(f"  ⚠️  {code:8s} → {status}")

        print(f"\n{'='*65}")
        print(f"완료: {ok}개 성공 / {skip}개 스킵 / {fail}개 실패")
        return pd.DataFrame(results)


if __name__ == "__main__":
    engine = BackfillEngine(verbose=True)

    # 핵심 ETF 테스트
    print("\n── 핵심 ETF 백필링 테스트 ──────────────────────────")
    test_codes = [
        "360750",  # TIGER 미국S&P500 (환노출)
        "379800",  # KODEX 미국S&P500 (환노출)
        "133690",  # TIGER 미국나스닥100 (환노출)
        "069500",  # KODEX 200 (KR)
        "102110",  # TIGER 200 (KR)
        "453850",  # ACE 미국30년국채액티브(H)
        "411060",  # ACE KRX금현물
    ]

    for code in test_codes:
        engine.backfill(code)

    # 결과 확인
    print("\n── 백필링 후 전체 데이터 범위 ──────────────────────")
    for code in test_codes:
        row = engine.price_conn.execute(
            "SELECT MIN(date), MAX(date), COUNT(*) FROM price_daily WHERE code=?", (code,)
        ).fetchone()
        name = engine._etf_meta.loc[code, "name"] if code in engine._etf_meta.index else code
        print(f"  {code} {name[:20]:20s}: {row[0]} ~ {row[1]}  ({row[2]:,}행)")