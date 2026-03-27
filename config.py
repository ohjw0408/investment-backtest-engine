import os

# -------------------------
# 기본 경로
# -------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")

# -------------------------
# DB 경로
# -------------------------
SYMBOL_DB_PATH = os.path.join(DATA_DIR, "meta", "symbol_master.db")
PRICE_DB_PATH = os.path.join(DATA_DIR, "price_daily.db")

# -------------------------
# 기본 설정
# -------------------------
DEFAULT_START_DATE = "2010-01-01"

# -------------------------
# 캐시 정책
# -------------------------
USE_PRICE_CACHE = True