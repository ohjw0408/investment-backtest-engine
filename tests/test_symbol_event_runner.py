"""
symbol_event_runner 결정론 검증 — 실적/배당락 룰 발화, 계좌별 예상 배당금 집계.
market_calendar 조회는 스텁으로 대체(네트워크 0). 실행: python tests/test_symbol_event_runner.py
"""
import datetime
import os, sys, tempfile
from pathlib import Path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_p = _f = 0
def ok(name, cond):
    global _p, _f
    if cond: _p += 1; print("PASS  " + name)
    else:    _f += 1; print("FAIL  " + name)

import modules.auth_manager as am
am.DB_PATH = Path(tempfile.mkdtemp()) / "t_users.db"
am._conn = None
am.init_db()
am.init_holdings_db()

from modules.alerts import alert_store, symbol_event_runner as SER
alert_store.init_alerts_db()

UID = 11
TODAY = datetime.date(2026, 8, 20)
TOMORROW = TODAY + datetime.timedelta(days=1)


class FakeLoader:
    def is_kr_etf(self, code):
        return str(code).isdigit()


# 보유: 일반계좌 SCHD 10주 + ISA 133690 100주 + 일반 133690 50주
HOLDINGS = [
    {"code": "SCHD", "quantity": 10, "account_type": "일반"},
    {"code": "133690", "quantity": 100, "account_type": "ISA"},
    {"code": "133690", "quantity": 50, "account_type": "일반"},
    {"code": "KRX_GOLD", "quantity": 3, "account_type": "일반"},
    {"code": "QQQM", "quantity": 5, "account_type": "일반"},
]

# 배당락: 오늘 SCHD(주당 1,000원 세전) + 133690(주당 200원), 내일 QQQM
DIVS = [
    {"date": TODAY.isoformat(), "type": "dividend", "symbol": "SCHD",
     "dps_krw": 1000.0, "projected": False},
    {"date": TODAY.isoformat(), "type": "dividend", "symbol": "133690",
     "dps_krw": 200.0, "projected": False},
    {"date": TOMORROW.isoformat(), "type": "dividend", "symbol": "QQQM",
     "dps_krw": 500.0, "projected": True},
]
EARNS = {"SCHD": [], "133690": [], "KRX_GOLD": [],
         "AAPL": [{"date": TODAY.isoformat(), "type": "earnings", "symbol": "AAPL"}]}

SER._holding_rows = lambda uid: list(HOLDINGS)
SER._display_name = lambda c: {"SCHD": "슈드", "133690": "KODEX 200"}.get(c, c)
SER._dividends_for = lambda loader, codes, cache: [
    d for d in DIVS if d["symbol"] in set(codes)]
SER._earnings_for = lambda codes, cache: [e for c in codes for e in EARNS.get(c, [])]

loader = FakeLoader()


def last_event():
    return alert_store.get_events(UID, limit=1)[0]


# ── 1. 배당락 + 계좌별 금액 (보유 전체, 당일) ──────────
r_div = alert_store.create_rule(UID, scope="holdings", rule_type="dividend",
                                window="d0", direction="amount")
fired = SER.run_symbol_event_alerts(loader, today=TODAY, rules=alert_store.get_rules(UID))
ok("배당 룰 1건 발화", fired == 1)
ev = last_event()
# SCHD  10주 × 1,000 × (1-0.15 미국세)      = 8,500
# 133690 ISA 100주 × 200 × 1.0(비과세)      = 20,000
# 133690 일반 50주 × 200 × (1-0.154)        = 8,460
ok("합계 = 36,960원", "36,960원" in ev["title"])
ok("계좌별 ISA 20,000원", "ISA 20,000원" in ev["body"])
ok("계좌별 일반 16,960원", "일반 16,960원" in ev["body"])
ok("종목명 노출(코드 아님)", "슈드" in ev["body"] and "KODEX 200" in ev["body"])
ok("지급일 아님을 명시", "실제 입금일" in ev["body"])
ok("target_url = /myassets", ev["meta"]["target_url"] == "/myassets")

# ── 2. 같은 날 재실행 = 중복 발화 없음 ──────────────────
again = SER.run_symbol_event_alerts(loader, today=TODAY, rules=alert_store.get_rules(UID))
ok("당일 중복 발화 없음", again == 0)

# ── 3. 하루 전 알림(window=d1) = 내일 배당락을 오늘 발화 ─
alert_store.delete_rule(UID, r_div)
r_pre = alert_store.create_rule(UID, scope="holdings", rule_type="dividend", window="d1")
fired = SER.run_symbol_event_alerts(loader, today=TODAY, rules=alert_store.get_rules(UID))
ok("d1 룰 발화(내일 QQQM)", fired == 1)
ev = last_event()
ok("'내일' 문구", ev["title"].startswith("💰 내일 배당락"))
ok("금액 미동봉(direction 없음)", "예상 배당" not in ev["title"])
ok("예상일 안내", "예상일" in ev["body"])

# ── 4. 특정 종목 실적 발표 ─────────────────────────────
alert_store.delete_rule(UID, r_pre)
alert_store.create_rule(UID, scope="symbol", rule_type="earnings",
                        code="AAPL", window="d0")
fired = SER.run_symbol_event_alerts(loader, today=TODAY, rules=alert_store.get_rules(UID))
ok("실적 룰 발화", fired == 1)
ev = last_event()
ok("실적 제목", ev["title"] == "📊 오늘 실적 발표 — AAPL")
ok("target_url = /symbol/AAPL", ev["meta"]["target_url"] == "/symbol/AAPL")

# ── 5. 해당 날짜 일정 없으면 무발화 ─────────────────────
fired = SER.run_symbol_event_alerts(loader, today=TODAY + datetime.timedelta(days=5),
                                    rules=alert_store.get_rules(UID))
ok("일정 없는 날 무발화", fired == 0)

print(f"\n{_p} passed, {_f} failed")
sys.exit(1 if _f else 0)
