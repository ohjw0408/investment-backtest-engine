import sys, sqlite3
import pandas as pd
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parents[1]))

BASE_DIR = Path(__file__).resolve().parents[1]
conn = sqlite3.connect(str(BASE_DIR / "data" / "price_cache" / "price_daily.db"))

df = pd.read_sql(
    "SELECT date, close, volume FROM price_daily WHERE code='360750' ORDER BY date",
    conn
)
df["date"] = pd.to_datetime(df["date"])

# NaN 확인
nan_rows = df[df["close"].isna()]
print(f"NaN 행 수: {len(nan_rows)}")
if not nan_rows.empty:
    print(nan_rows)

# 2025-10-10 주변 갭 확인
mask = (df["date"] >= "2025-10-01") & (df["date"] <= "2025-10-20")
print(f"\n2025-10 주변:\n{df[mask].to_string()}")

# 날짜 갭 전체 확인
diff = df["date"].diff().dt.days
big = diff[diff > 7]
print(f"\n7일 이상 갭:")
for idx, days in big.items():
    print(f"  {df.loc[idx, 'date'].date()} (갭 {days:.0f}일)")