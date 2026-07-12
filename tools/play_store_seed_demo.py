"""Seed a local Play Store demo user and print a Flask session cookie.

This touches only the local development users.db entry for google_id
``play-store-demo``. It is used by the Play Store graphics capture script.
"""

import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from flask.sessions import SecureCookieSessionInterface  # noqa: E402

from app import app  # noqa: E402
from modules import auth_manager as am  # noqa: E402


DEMO_GOOGLE_ID = "play-store-demo"


def reset_demo_user(user_id):
    conn = am._get_conn()
    for sql in (
        "DELETE FROM holdings WHERE user_id=?",
        "DELETE FROM asset_groups WHERE user_id=?",
        "DELETE FROM saved_portfolios WHERE user_id=?",
        "DELETE FROM user_settings WHERE user_id=?",
        "DELETE FROM device_tokens WHERE user_id=?",
        "DELETE FROM alert_rules WHERE user_id=?",
        "DELETE FROM alert_events WHERE user_id=?",
    ):
        try:
            conn.execute(sql, (user_id,))
        except Exception:
            pass
    conn.commit()


def insert_groups(user_id):
    conn = am._get_conn()
    rows = [
        ("성장 자산", "#2563EB", 60),
        ("배당 자산", "#059669", 25),
        ("채권", "#7C3AED", 10),
        ("금", "#D97706", 5),
    ]
    ids = {}
    now = am.datetime.now().isoformat()
    for name, color, target in rows:
        cur = conn.execute(
            "INSERT INTO asset_groups (user_id, name, color, target_pct, created_at) "
            "VALUES (?,?,?,?,?)",
            (user_id, name, color, target, now),
        )
        ids[name] = cur.lastrowid
    conn.commit()
    return ids


def insert_holdings(user_id, group_ids):
    # current values add to exactly 40,000,000 KRW.
    rows = [
        ("SPY", "SPDR S&P 500 ETF", 10_000_000, 910_000, 850_000, "성장 자산"),
        ("QQQ", "Invesco QQQ", 6_000_000, 780_000, 725_000, "성장 자산"),
        ("005930", "삼성전자", 4_000_000, 83_500, 78_800, "성장 자산"),
        ("000660", "SK하이닉스", 4_000_000, 285_000, 252_000, "성장 자산"),
        ("SCHD", "Schwab US Dividend Equity ETF", 6_000_000, 37_500, 35_600, "배당 자산"),
        ("JEPQ", "JPMorgan Nasdaq Equity Premium Income ETF", 4_000_000, 79_000, 76_200, "배당 자산"),
        ("TLT", "iShares 20+ Year Treasury Bond ETF", 4_000_000, 124_000, 127_000, "채권"),
        ("KRX_GOLD", "KRX 금현물", 2_000_000, 184_000, 168_000, "금"),
    ]
    now = am.datetime.now().isoformat()
    conn = am._get_conn()
    for code, _name, value, price, avg, group_name in rows:
        qty = value / price
        conn.execute(
            "INSERT INTO holdings "
            "(user_id, code, quantity, avg_price, manual_price, buy_date, account_type, group_id, created_at, updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                user_id,
                code,
                qty,
                avg,
                price,
                "2024-01-15",
                "일반",
                group_ids[group_name],
                now,
                now,
            ),
        )
    conn.commit()


def insert_portfolio(user_id):
    tickers = [
        {"code": "SPY", "name": "SPDR S&P 500 ETF", "badge": "US ETF", "weight": 25, "quantity": 0},
        {"code": "QQQ", "name": "Invesco QQQ", "badge": "US ETF", "weight": 15, "quantity": 0},
        {"code": "SCHD", "name": "Schwab US Dividend Equity ETF", "badge": "US ETF", "weight": 15, "quantity": 0},
        {"code": "JEPQ", "name": "JPMorgan Nasdaq Equity Premium Income ETF", "badge": "US ETF", "weight": 10, "quantity": 0},
        {"code": "005930", "name": "삼성전자", "badge": "KOSPI", "weight": 10, "quantity": 0},
        {"code": "000660", "name": "SK하이닉스", "badge": "KOSPI", "weight": 10, "quantity": 0},
        {"code": "TLT", "name": "iShares 20+ Year Treasury Bond ETF", "badge": "US ETF", "weight": 10, "quantity": 0},
        {"code": "KRX_GOLD", "name": "KRX 금현물", "badge": "원자재", "weight": 5, "quantity": 0},
    ]
    am.upsert_portfolio(user_id, "자산배분 데모 포트폴리오", tickers)


def main():
    user = am.get_or_create_user(
        DEMO_GOOGLE_ID,
        "demo@moneymilestone.co.kr",
        "Money Milestone Demo",
        "",
    )
    reset_demo_user(user["id"])
    groups = insert_groups(user["id"])
    insert_holdings(user["id"], groups)
    insert_portfolio(user["id"])
    am.save_settings(
        user["id"],
        {
            "hide_amounts": False,
            "age": 40,
            "pension_age": 65,
            "earned_income": 60_000_000,
            "isa_type": "general",
            "rebal_band": 5,
        },
    )
    am.set_user_consent(user["id"], push_notifications=False)

    serializer = SecureCookieSessionInterface().get_signing_serializer(app)
    print(serializer.dumps({"user_id": user["id"]}))


if __name__ == "__main__":
    main()
