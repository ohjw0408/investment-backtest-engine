"""
홈 위젯(관심목록) 백엔드 검증 — auth_manager 저장 + _clean_home_widgets + 라우트 + quote.
실행: python tests/test_home_widgets.py
"""
import os, sys, tempfile
from pathlib import Path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_p = _f = 0
def ok(name, cond):
    global _p, _f
    if cond: _p += 1; print("PASS  " + name)
    else:    _f += 1; print("FAIL  " + name)


# ── 1. auth_manager 저장/조회 (격리 temp DB) ──
import modules.auth_manager as am
am.DB_PATH = Path(tempfile.mkdtemp()) / "t_users.db"
am._conn = None
am.init_db()

ok("미설정 시 get_home_widgets None", am.get_home_widgets(1) is None)
W = [{"key": "w_market", "name": "시장 지수",
      "items": [{"code": "^GSPC", "name": "S&P 500"}, {"code": "TLT", "name": "美국채"}]}]
am.save_home_widgets(1, W)
got = am.get_home_widgets(1)
ok("저장 왕복 일치", got == W)
am.save_home_widgets(1, [{"key": "x", "name": "변경", "items": [{"code": "QQQ", "name": "Q"}]}])
ok("재저장 덮어쓰기", am.get_home_widgets(1)[0]["name"] == "변경")
ok("home_widgets는 tax와 독립(다른 user)", am.get_home_widgets(2) is None)

# ── 2. _clean_home_widgets 검증 (app import) ──
import app as appmod
clean = appmod._clean_home_widgets

c, e = clean([{"name": "리스트1", "items": [{"code": "spy", "name": "S&P"}]}])
ok("정상 → cleaned, code 대문자화", e is None and c[0]["items"][0]["code"] == "SPY")
ok("정상 → key 자동부여", e is None and c[0]["key"])
_, e = clean([])
ok("빈 위젯 → 에러", e is not None)
_, e = clean([{"name": "", "items": [{"code": "X"}]}])
ok("빈 이름 → 에러", e is not None)
_, e = clean([{"name": "a", "items": []}])
ok("종목 0개 → 에러", e is not None)
_, e = clean([{"name": "a", "items": [{"name": "코드없음"}]}])
ok("code 없는 종목 → 에러", e is not None)
_, e = clean([{"name": "a", "items": [{"code": "X"}]}] * 11)
ok("위젯 11개 → 에러", e is not None)

# ── 3. 라우트 (test_client, 세션 직접 주입) ──
appmod.app.config["TESTING"] = True
cl = appmod.app.test_client()

r = cl.get("/api/home-config")
j = r.get_json()
ok("GET 비로그인 → 기본 위젯", r.status_code == 200 and j["logged_in"] is False
   and j["widgets"][0]["items"][0]["code"] == "^GSPC")

r = cl.post("/api/home-config", json={"widgets": [{"name": "a", "items": [{"code": "SPY"}]}]})
ok("POST 비로그인 → 401", r.status_code == 401)

with cl.session_transaction() as s:
    s["user_id"] = 999999
am._get_conn().execute(
    "INSERT INTO users (id, google_id, email, name, picture, created_at, last_login) "
    "VALUES (999999, 'test-home-widget', '', 'test', '', '2026-06-29', '2026-06-29')"
)
am._get_conn().commit()
am.set_user_consent(999999)
r = cl.post("/api/home-config", json={"widgets": []})
ok("POST 로그인+잘못된 바디 → 400", r.status_code == 400)

# ── 4. 지수 fallback은 yfinance 성공 시 index_ohlc에 저장 ──
import sqlite3
import pandas as pd
import yfinance as yf

tmp_idx = sqlite3.connect(":memory:")
tmp_idx.execute("CREATE TABLE index_daily (code TEXT, date TEXT, close REAL)")
old_idx_conn = appmod.portfolio_engine.loader.index_conn
old_yf_download = yf.download

def fake_yf_download(code, start=None, progress=False, auto_adjust=False, threads=False, **kwargs):
    return pd.DataFrame(
        {
            "Open": [100.0, 104.0],
            "High": [101.0, 106.0],
            "Low": [99.0, 103.0],
            "Close": [100.0, 105.0],
            "Volume": [10.0, 20.0],
        },
        index=pd.to_datetime(["2026-06-26", "2026-06-29"]),
    )

try:
    appmod.portfolio_engine.loader.index_conn = tmp_idx
    yf.download = fake_yf_download
    closes, currency = appmod._wl_recent_closes("^KS11")
    saved = tmp_idx.execute(
        "SELECT date, close FROM index_ohlc WHERE code='^KS11' ORDER BY date"
    ).fetchall()
    ok("지수 fallback → closes 반환", closes == [100.0, 105.0] and currency == "KRW")
    ok("지수 fallback → index_ohlc upsert", saved == [("2026-06-26", 100.0), ("2026-06-29", 105.0)])

    # ── 4b. NULL close 봉이 있어도 위젯이 죽지 않는다 (BUG-KOSPI-NIGHT-NULL 2026-07-03) ──
    # US장 시간 beat가 마감된 KR지수 당일행을 NaN(=sqlite NULL)으로 upsert하던 오염 시나리오.
    tmp_idx.execute("INSERT INTO index_ohlc (code, date, open, high, low, close, volume) "
                    "VALUES ('^KS11', '2026-06-30', NULL, NULL, NULL, NULL, 0)")
    tmp_idx.commit()
    closes2, _ = appmod._wl_recent_closes("^KS11")
    ok("NULL 봉 스킵 — 직전 유효 종가 반환", closes2 == [100.0, 105.0])

    # 쓰기 가드: refresh용 NaN Close 행은 저장 자체가 안 된다
    import math
    def fake_yf_nan(code, period=None, progress=False, auto_adjust=False, threads=False, **kw):
        return pd.DataFrame(
            {"Open": [104.0, float("nan")], "High": [106.0, float("nan")],
             "Low": [103.0, float("nan")], "Close": [105.0, float("nan")],
             "Volume": [20.0, float("nan")]},
            index=pd.to_datetime(["2026-06-29", "2026-07-01"]))
    import modules.price_loader as plmod
    old_dl = plmod.yf.download
    plmod.yf.download = fake_yf_nan
    try:
        appmod.portfolio_engine.loader.refresh_index_ohlc(codes=["^KS11"])
        nulls = tmp_idx.execute(
            "SELECT COUNT(*) FROM index_ohlc WHERE code='^KS11' AND date='2026-07-01'").fetchone()[0]
        ok("쓰기 가드 — NaN 당일봉 미저장", nulls == 0)
    finally:
        plmod.yf.download = old_dl
finally:
    yf.download = old_yf_download
    appmod.portfolio_engine.loader.index_conn = old_idx_conn
    tmp_idx.close()

# ── 5. _watchlist_quote 통합 (네트워크/DB — 관대) ──
q = appmod._watchlist_quote("^GSPC")
if q is None:
    print("SKIP  _watchlist_quote(^GSPC) None (오프라인/데이터없음)")
else:
    ok("quote 구조 (value/change/up/spark/name)",
       all(k in q for k in ("value", "change", "up", "spark", "name")))
    ok("quote code 대문자", q["code"] == "^GSPC")

print(f"\n{_p} PASS / {_f} FAIL")
sys.exit(1 if _f else 0)
