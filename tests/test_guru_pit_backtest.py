"""투자대가 시점별(point-in-time) 백테스트 — 결정론 단위 테스트.

핵심 불변식:
  - 공시일이 지나야 그 분기 비중으로 바뀐다(미래정보 없음)
  - target_weights는 제자리 갱신 → SimulationConfig가 공유하는 객체가 함께 움직인다
  - 스케줄은 NAV 곡선과 같은 세그먼트를 쓴다(비교탭과 백테가 같은 역사)
"""
from datetime import datetime

import pytest

from modules.rebalance.scheduled import ScheduledRebalance


SCHEDULE = [
    ("2020-02-14", {"AAA": 0.6, "BBB": 0.4}),
    ("2020-05-15", {"AAA": 1.0}),
    ("2020-08-14", {"CCC": 0.5, "AAA": 0.5}),
]


def _d(s):
    return datetime.strptime(s, "%Y-%m-%d")


def test_weights_switch_only_after_filed():
    shared = {}
    st = ScheduledRebalance(SCHEDULE, shared)

    # 첫 공시 전 = 아직 아무 비중도 없다(현금 보유)
    assert st.should_rebalance(_d("2020-01-02"), None, None) is False
    assert shared == {}

    # 공시일 당일 진입
    assert st.should_rebalance(_d("2020-02-14"), None, None) is True
    assert shared == {"AAA": 0.6, "BBB": 0.4}

    # 다음 공시 전엔 그대로
    assert st.should_rebalance(_d("2020-04-01"), None, None) is False
    assert shared == {"AAA": 0.6, "BBB": 0.4}

    # 다음 공시일에 교체
    assert st.should_rebalance(_d("2020-05-15"), None, None) is True
    assert shared == {"AAA": 1.0}


def test_late_start_jumps_to_latest_segment():
    """시작일이 여러 공시 뒤면 첫 매수에서 곧바로 최신 비중으로 들어간다."""
    shared = {}
    st = ScheduledRebalance(SCHEDULE, shared)
    assert st.should_rebalance(_d("2020-09-01"), None, None) is True
    assert shared == {"CCC": 0.5, "AAA": 0.5}
    # 남은 세그먼트가 없으므로 이후엔 리밸런싱하지 않는다
    assert st.should_rebalance(_d("2020-12-31"), None, None) is False


def test_target_weights_object_is_shared_not_replaced():
    """config.target_weights가 같은 객체를 참조해야 적립·배당 스윕도 시점별을 따른다."""
    shared = {}
    st = ScheduledRebalance(SCHEDULE, shared)
    st.should_rebalance(_d("2020-02-14"), None, None)
    st.should_rebalance(_d("2020-05-15"), None, None)
    assert st.target_weights is shared


def test_generate_orders_uses_current_segment():
    class _PF:
        cash = 0.0

        def total_value(self, price_dict):
            return 1_000_000.0

        def current_weights(self, price_dict, include_cash=False):
            return {}

    shared = {}
    st = ScheduledRebalance(SCHEDULE, shared)
    st.should_rebalance(_d("2020-02-14"), None, None)
    orders = st.generate_orders(_PF(), {"AAA": 10.0, "BBB": 20.0})
    assert orders == {"AAA": 600_000.0, "BBB": 400_000.0}


# ── 스케줄 생성 (실 DB 사용, 없으면 skip) ─────────────────────────────────
def _nav():
    nav = pytest.importorskip("modules.gurus.nav")
    if not nav.weight_schedule("warren-buffett"):
        pytest.skip("guru_holdings.db 미존재/미빌드")
    return nav


def test_weight_schedule_matches_nav_segments():
    nav = _nav()
    sched = nav.weight_schedule("warren-buffett")
    segs = nav._segments("0001067983")
    assert len(sched) == len(segs)
    assert [d for d, _ in sched] == [d for d, _ in segs]
    for _, w in sched:
        assert abs(sum(w.values()) - 1.0) < 1e-9
        assert len(w) <= nav.TOP_N


def test_weight_schedule_is_point_in_time():
    """과거 세그먼트는 그 시절 보유여야 한다 — 오늘 종목이 소급되면 안 된다."""
    nav = _nav()
    sched = dict(nav.weight_schedule("warren-buffett"))
    old = [w for d, w in sched.items() if d < "2016-01-01"]
    assert old, "2016년 이전 세그먼트가 있어야 함"
    # 버핏은 2016년 이후에 애플을 샀다 — 그 전 구간에 AAPL이 있으면 후견편향
    assert all("AAPL" not in w for w in old)


def test_coverage_filter_renormalizes():
    nav = _nav()
    full = nav.weight_schedule("warren-buffett")
    keep = sorted({c for _, w in full for c in w})[:3]
    cov = {c: ("1900-01-01", "2100-01-01") for c in keep}
    filtered = nav.weight_schedule("warren-buffett", coverage=cov)
    assert filtered
    for _, w in filtered:
        assert set(w) <= set(keep)
        assert abs(sum(w.values()) - 1.0) < 1e-9
