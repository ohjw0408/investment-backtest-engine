"""알림 교통정리(2026-07-02) 검증 — 시장 게이팅·히스테리시스 재발화·당일 가드·마감 요약.
실행: python tests/test_alert_market_hysteresis.py  (FakeLoader, 네트워크/실DB 0)
"""
import os, sys, tempfile
from pathlib import Path
from datetime import datetime, timedelta
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


class FakeLoader:
    supports_live_quotes = False
    def __init__(self, series):
        self.series = series
    def get_price(self, code, start, end, apply_fx=True, allow_synthetic=False):
        s = self.series.get(str(code).upper())
        return pd.DataFrame() if s is None else pd.DataFrame({"close": list(s)})
    def is_kr_etf(self, code):
        return str(code).isdigit()


# ── 1. 시장 분류 ──────────────────────────────────────
ok("069500=KR", alert_runner.rule_market("069500") == "KR")
ok("^KS11=KR", alert_runner.rule_market("^KS11") == "KR")
ok("KRX_GOLD=KR", alert_runner.rule_market("KRX_GOLD") == "KR")
ok("AAPL=US", alert_runner.rule_market("AAPL") == "US")
ok("^GSPC=US", alert_runner.rule_market("^GSPC") == "US")
ok("BTC-USD=ANY", alert_runner.rule_market("BTC-USD") == "ANY")
ok("GC=F=ANY", alert_runner.rule_market("GC=F") == "ANY")

# ── 2. 시장 게이팅: KR 룰은 US-only 슬롯에서 미평가 ──
UID = 21
loader = FakeLoader({"069500": [100, 100, 105], "AAPL": [100, 100, 105]})  # 둘 다 +5%
alert_store.create_rule(UID, scope="symbol", rule_type="daily_pct",
                        code="069500", direction="both", threshold=1)
alert_store.create_rule(UID, scope="symbol", rule_type="daily_pct",
                        code="AAPL", direction="both", threshold=1)

fired_us = alert_runner.run_alert_evaluation(loader, markets={"US"})
evs = alert_store.get_events(UID)
ok("US 슬롯: AAPL만 발화(코스피 22:30 재발 방지)",
   fired_us == 1 and all(e.get("code") != "069500" for e in evs))

fired_kr = alert_runner.run_alert_evaluation(loader, markets={"KR"})
evs = alert_store.get_events(UID)
ok("KR 슬롯: 069500 발화", fired_kr == 1 and any(e.get("code") == "069500" for e in evs))

# ── 3. 히스테리시스 ──────────────────────────────────
UID2 = 22
t0 = datetime(2026, 7, 2, 10, 0, 0)
rid = alert_store.create_rule(UID2, scope="symbol", rule_type="daily_pct",
                              code="TSLA", direction="both", threshold=5)

up = FakeLoader({"TSLA": [100, 100, 106]})       # +6% = up 존
neutral = FakeLoader({"TSLA": [100, 100, 100.5]})  # +0.5% = neutral
down = FakeLoader({"TSLA": [100, 100, 93]})      # -7% = down 존

ok("① up 진입 발화", alert_runner.run_alert_evaluation(up, now=t0, markets={"US"}) == 1)
ok("② 같은 존 유지 재발화 0",
   alert_runner.run_alert_evaluation(up, now=t0 + timedelta(minutes=15), markets={"US"}) == 0)
# up → down 직행: 방향 전환은 45분 가드 무시하고 즉시
ok("③ 방향 전환(↑→↓) 즉시 발화",
   alert_runner.run_alert_evaluation(down, now=t0 + timedelta(minutes=30), markets={"US"}) == 1)
# down → neutral 복귀(발화 없음, 상태만 재무장)
ok("④ neutral 복귀 발화 0",
   alert_runner.run_alert_evaluation(neutral, now=t0 + timedelta(minutes=45), markets={"US"}) == 0)
# neutral → down 재진입: 같은 방향 재발화 — 마지막 down 발화에서 45분 미경과 → 억제
ok("⑤ 같은 방향 재진입 45분 내 억제",
   alert_runner.run_alert_evaluation(down, now=t0 + timedelta(minutes=60), markets={"US"}) == 0)
# 상태는 down으로 저장됨 → neutral 다시 복귀 후 45분 경과 뒤 재진입 → 발화
alert_runner.run_alert_evaluation(neutral, now=t0 + timedelta(minutes=75), markets={"US"})
ok("⑥ 45분 경과 후 재크로싱 발화",
   alert_runner.run_alert_evaluation(down, now=t0 + timedelta(minutes=80), markets={"US"}) == 1)

# ── 4. 당일 가드: 라이브가 '어제 봉'이라 판명되면 daily_pct 스킵 ──
UID3 = 23
alert_store.create_rule(UID3, scope="symbol", rule_type="daily_pct",
                        code="NVDA", direction="both", threshold=1)

class StaleLiveLoader(FakeLoader):
    supports_live_quotes = True   # 라이브 경로 사용

from modules.alerts import live_quote as lq
_orig = lq.get_live_price
lq.get_live_price = lambda loader, code: {"cur": 110.0, "prev": 100.0, "cur_is_today": False}
try:
    stale = StaleLiveLoader({"NVDA": [100, 100, 110]})
    fired_stale = alert_runner.run_alert_evaluation(stale, markets={"US"})
    ok("어제 봉(+10%)로는 미발화(22:30 오발화 차단)", fired_stale == 0)
    lq.get_live_price = lambda loader, code: {"cur": 110.0, "prev": 100.0, "cur_is_today": True}
    fired_fresh = alert_runner.run_alert_evaluation(stale, markets={"US"})
    ok("오늘 봉(+10%)은 발화", fired_fresh == 1)
finally:
    lq.get_live_price = _orig

# ── 4.5 ANY 자산 상시 평가 (자산군 커버 2026-07-02) ──
UID5 = 25
any_loader = FakeLoader({"BTC-USD": [100, 100, 107]})  # +7%
alert_store.create_rule(UID5, scope="symbol", rule_type="daily_pct",
                        code="BTC-USD", direction="both", threshold=5)
# 주말/장외 = markets 빈 집합이어도 ANY(크립토)는 평가·발화
fired_any = alert_runner.run_alert_evaluation(any_loader, markets=set())
ok("주말(장 전부 닫힘)에도 크립토 발화", fired_any == 1)
# 빈 markets에서 portfolio/rebalance 룰은 게이팅(평가 안 함)
UID6 = 26
am.upsert_group(UID6, "주식", target_pct=60)
am.upsert_group(UID6, "채권", target_pct=40)
gs = am.get_groups(UID6)
am.upsert_holding(UID6, "AAA", quantity=72, avg_price=1, group_id=gs[0]["id"])
am.upsert_holding(UID6, "BBB", quantity=28, avg_price=1, group_id=gs[1]["id"])
for h in am.get_holdings(UID6):
    am.set_manual_price(UID6, h["id"], 1)
alert_store.create_rule(UID6, scope="portfolio", rule_type="rebalance_band", threshold=5)
fired_reb_closed = alert_runner.run_alert_evaluation(any_loader, markets=set())
ok("장 닫힘: 리밸런싱 룰 미평가", not alert_store.get_events(UID6))
fired_reb_open = alert_runner.run_alert_evaluation(any_loader, markets={"KR"})
ok("장 열림: 리밸런싱 발화", any("리밸런싱" in e["title"] for e in alert_store.get_events(UID6)))

# ── 5. 마감 요약 ─────────────────────────────────────
UID4 = 24
loader4 = FakeLoader({"069500": [100, 100, 98.5], "AAPL": [100, 100, 99.9]})  # KR -1.5% / US -0.1%
r_kr = alert_store.create_rule(UID4, scope="symbol", rule_type="daily_pct",
                               code="069500", direction="both", threshold=1)
alert_store.create_rule(UID4, scope="symbol", rule_type="daily_pct",
                        code="AAPL", direction="both", threshold=1)

fired_cs = alert_runner.run_close_summary(loader4, "KR")
evs4 = alert_store.get_events(UID4)
# run_close_summary는 전 사용자 대상 — UID4 수신함만 검사 (KR -1.5%만, AAPL -0.1% 미포함)
ok("KR 마감 요약: UID4 수신함 1건", len(evs4) == 1 and fired_cs >= 1)
ok("타이틀에 '마감'", "마감" in evs4[0]["title"])
ok("AAPL 마감 요약 없음", all(e.get("code") != "AAPL" for e in evs4))
rule_after = [r for r in alert_store.get_rules(UID4) if r["id"] == r_kr][0]
ok("마감 요약은 쿨다운 미변경(last_triggered_at 없음)",
   not rule_after.get("last_triggered_at"))

print(f"\n{_p} PASS / {_f} FAIL")
sys.exit(1 if _f else 0)
