"""tr_index 공용 빌더 골든 — TR 배당재투자 + NULL홀 가드(fill_method=None) 잠금.
인메모리 sqlite로 결정론 검증(라이브 DB 비의존). P2 분석탭 롤링 소스."""
import sqlite3
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.tr_index import ticker_tr_series, build_portfolio_tr_index


def _mk_conn():
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE price_daily(code TEXT, date TEXT, close REAL, volume REAL)")
    conn.execute("CREATE TABLE corporate_actions(code TEXT, date TEXT, dividend REAL)")
    return conn


def test_dividend_reinvest():
    """배당락에 배당 재투자 → TR이 (close+div)/prev 비율로 점프."""
    conn = _mk_conn()
    rows = [("A", f"2020-01-{d:02d}", 100.0, 1000) for d in range(1, 6)]
    conn.executemany("INSERT INTO price_daily VALUES (?,?,?,?)", rows)
    conn.execute("INSERT INTO corporate_actions VALUES ('A','2020-01-03',10.0)")
    m, syn = ticker_tr_series(conn, "A")
    # day1=100 기준. day3 배당10 재투자 → tr3 = tr2*(100+10)/100 = 110
    assert abs(m["2020-01-02"] - 100.0) < 1e-6
    assert abs(m["2020-01-03"] - 110.0) < 1e-6
    assert abs(m["2020-01-05"] - 110.0) < 1e-6   # 이후 close 동일 → 유지
    assert all(v == 0 for v in syn.values())       # volume>0 → 합성 아님


def test_synthetic_flag():
    """volume=0(합성 백필) → syn=1."""
    conn = _mk_conn()
    conn.execute("INSERT INTO price_daily VALUES ('A','2020-01-01',100.0,0)")
    conn.execute("INSERT INTO price_daily VALUES ('A','2020-01-02',101.0,500)")
    m, syn = ticker_tr_series(conn, "A")
    assert syn["2020-01-01"] == 1
    assert syn["2020-01-02"] == 0


def test_null_hole_no_fake_jump():
    """종목 데이터 구멍이 forward-fill되어 가짜 점프 만들지 않는다(fill_method=None).
    A 연속·B 중간 결손 → B 재개일 포폴 지수가 비현실적 점프 없어야."""
    conn = _mk_conn()
    # A: 매일 +0% (close 100 고정)
    a = [("A", f"2020-01-{d:02d}", 100.0, 1000) for d in range(1, 11)]
    # B: 시작 100 → 결손(4~7일 없음) → 8일 200으로 재등장. pad면 4~7일 100 유지 후
    #    8일 +100% 가짜수익. fill_method=None이면 8일 B수익 NaN → 그날 제외(점프 없음).
    b = [("B", "2020-01-01", 100.0, 1000), ("B", "2020-01-02", 100.0, 1000),
         ("B", "2020-01-03", 100.0, 1000),
         ("B", "2020-01-08", 200.0, 1000), ("B", "2020-01-09", 200.0, 1000),
         ("B", "2020-01-10", 200.0, 1000)]
    conn.executemany("INSERT INTO price_daily VALUES (?,?,?,?)", a + b)
    pts = build_portfolio_tr_index([{"code": "A", "weight": 50}, {"code": "B", "weight": 50}], conn=conn)
    vals = [v for _d, v, _s in pts]
    # 일일수익 최대 절대값 — 가짜 +100%(50% 비중→+50%) 점프 없어야. 둘 다 거의 0%.
    rets = [vals[i] / vals[i - 1] - 1 for i in range(1, len(vals))]
    assert max(abs(r) for r in rets) < 0.02, f"가짜 점프 감지: {max(rets)}"


def test_empty():
    assert build_portfolio_tr_index([]) == []
    assert build_portfolio_tr_index([{"code": "", "weight": 0}]) == []
