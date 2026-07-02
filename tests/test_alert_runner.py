"""
alert_runner 결정론 검증 — FakeLoader 주입(네트워크/실DB 0), 발화→수신함 적재 확인.
실행: python tests/test_alert_runner.py
"""
import os, sys, tempfile
from pathlib import Path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd

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

from modules.alerts import alert_store, alert_runner
alert_store.init_alerts_db()

UID = 7


class FakeLoader:
    """code -> 종가 리스트(오래된→최신)."""
    supports_live_quotes = False  # 라이브(yf/index_ohlc) 경로 차단 — 결정론
    def __init__(self, series):
        self.series = series
    def get_price(self, code, start, end, apply_fx=True, allow_synthetic=False):
        s = self.series.get(str(code).upper())
        if s is None:
            return pd.DataFrame()
        return pd.DataFrame({"close": s})
    def is_kr_etf(self, code):
        return str(code).isdigit()


# TSLA: 어제 100 → 오늘 112 (+12%), 동시에 전고점 110 돌파 = 신고가
# QQQ : 완만, 트리거 없음
loader = FakeLoader({
    "TSLA": [90, 95, 100, 105, 110, 100, 112],
    "QQQ":  [380, 381, 382, 383, 384, 385, 386],
})

r_pct = alert_store.create_rule(UID, scope="symbol", rule_type="daily_pct",
                                code="TSLA", direction="up", threshold=5)
r_high = alert_store.create_rule(UID, scope="symbol", rule_type="new_high",
                                 code="TSLA", window="all")
r_qqq = alert_store.create_rule(UID, scope="symbol", rule_type="daily_pct",
                                code="QQQ", direction="up", threshold=5)

fired = alert_runner.run_alert_evaluation(loader)
ok("발화 2건(TSLA pct+신고가)", fired == 2)
ok("수신함 2건", alert_store.unread_count(UID) == 2)
titles = " ".join(e["title"] for e in alert_store.get_events(UID))
ok("daily_pct 이벤트", "12.00%" in titles or "12.0" in titles)
ok("신고가 이벤트", "신고가" in titles)

# 쿨다운: 즉시 재실행하면 추가 발화 0
fired2 = alert_runner.run_alert_evaluation(loader)
ok("쿨다운으로 재발화 0", fired2 == 0)

# QQQ 룰은 한 번도 발화 안 함
ok("QQQ 미발화", all(e.get("code") != "QQQ" for e in alert_store.get_events(UID)))

# ── 리밸런싱 ──
UID2 = 8
am.upsert_group(UID2, "주식", target_pct=60)
am.upsert_group(UID2, "채권", target_pct=40)
groups = am.get_groups(UID2)
gid_stock, gid_bond = groups[0]["id"], groups[1]["id"]
# 주식 72% / 채권 28% (밴드 5%p 초과)
am.upsert_holding(UID2, "AAA", quantity=72, avg_price=1, group_id=gid_stock)
am.upsert_holding(UID2, "BBB", quantity=28, avg_price=1, group_id=gid_bond)
am.set_manual_price(UID2, am.get_holdings(UID2)[0]["id"], 1)  # 가격 1 고정
for h in am.get_holdings(UID2):
    am.set_manual_price(UID2, h["id"], 1)

r_reb = alert_store.create_rule(UID2, scope="portfolio", rule_type="rebalance_band",
                                threshold=5)
fired3 = alert_runner.run_alert_evaluation(loader)
ev_reb = alert_store.get_events(UID2)
ok("리밸런싱 발화", fired3 == 1 and ev_reb and "리밸런싱" in ev_reb[0]["title"])

# ── 저장 포트폴리오 수익 알림 (일일 리밸 지수) ──
UID3 = 11
am.init_portfolios_db()
ploader = FakeLoader({
    "AAA": [100, 100, 101],   # 마지막날 +1%
    "BBB": [100, 100, 103],   # 마지막날 +3%
})
# 일일 리밸 지수: d0=100, d1=100, d2=100*(1+0.5*0.01+0.5*0.03)=102
idx = alert_runner.compute_portfolio_index(
    ploader, [{"code": "AAA", "weight": 50}, {"code": "BBB", "weight": 50}])
ok("포폴 지수 길이 3", len(idx) == 3)
ok("일일 리밸 마지막 ~102", abs(idx[-1] - 102.0) < 1e-6)

am.upsert_portfolio(UID3, "5050", [{"code": "AAA", "name": "A", "weight": 50},
                                   {"code": "BBB", "name": "B", "weight": 50}])
pid = am.get_portfolios(UID3)[0]["id"]
alert_store.create_rule(UID3, scope="portfolio", portfolio_id=pid,
                        rule_type="daily_pct", direction="up", threshold=1)
firedp = alert_runner.run_alert_evaluation(ploader)
evp = alert_store.get_events(UID3)
ok("포폴 수익 알림 발화(+2% ≥1%)", firedp == 1 and evp and "5050" in evp[0]["title"])

print(f"\n{_p} PASS / {_f} FAIL")
sys.exit(1 if _f else 0)
