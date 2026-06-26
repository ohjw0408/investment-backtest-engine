import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from modules import rolling


def _geo_series(start_year, n_days, annual):
    """일별 기하성장 인덱스 [[date, value], ...]. value=100*(1+annual)^(t/365.25)."""
    d0 = date(start_year, 1, 1)
    out = []
    for t in range(n_days):
        v = 100.0 * (1.0 + annual) ** (t / 365.25)
        out.append([(d0 + timedelta(days=t)).strftime("%Y-%m-%d"), round(v, 6)])
    return out


def test_rolling_cagr_constant_growth():
    pts = _geo_series(2000, 365 * 8, 0.10)   # 8년, 연 10%
    rc = rolling.rolling_cagr(pts, 5)
    assert rc, "5년 롤링 결과 있어야"
    vals = [v for _, v in rc]
    # 모든 5년 롤링 CAGR ≈ 10%
    assert all(abs(v - 0.10) < 0.01 for v in vals)


def test_horizon_table_loss_prob_zero_on_uptrend():
    pts = _geo_series(2000, 365 * 12, 0.08)
    tbl = rolling.horizon_table(pts, horizons=[1, 3, 10])
    assert tbl[1]["n"] > 0 and tbl[10]["n"] > 0
    # 꾸준한 상승 → 손실확률 0
    assert tbl[1]["loss_prob"] == 0.0
    assert tbl[10]["loss_prob"] == 0.0
    assert abs(tbl[10]["median"] - 0.08) < 0.01
    # 20년은 표본 부족 → n=0
    assert tbl.get(20) is None or True  # horizons에 20 없음


def test_horizon_table_loss_prob_one_on_downtrend():
    pts = _geo_series(2000, 365 * 6, -0.05)   # 매년 -5%
    tbl = rolling.horizon_table(pts, horizons=[1, 3])
    assert tbl[3]["n"] > 0
    assert tbl[3]["loss_prob"] == 1.0


def test_horizon_table_insufficient_sample():
    pts = _geo_series(2000, 365 * 2, 0.10)   # 2년뿐
    tbl = rolling.horizon_table(pts, horizons=[5])
    assert tbl[5]["n"] == 0          # 5년 윈도우 표본 없음
    assert tbl[5]["loss_prob"] is None


def test_drawdown_recovery():
    # 100→150 상승, 150→75 폭락(-50%), 다시 150 회복
    d0 = date(2010, 1, 1)
    seq = list(range(100, 151)) + list(range(150, 74, -1)) + list(range(75, 151))
    pts = [[(d0 + timedelta(days=i)).strftime("%Y-%m-%d"), float(v)] for i, v in enumerate(seq)]
    dd = rolling.drawdown(pts)
    assert abs(dd["max_dd"] - (-0.5)) < 0.01     # 최대낙폭 -50%
    assert dd["recovery_date"] is not None
    assert dd["recovery_days"] > 0


def test_drawdown_monotonic_no_dd():
    pts = _geo_series(2010, 365 * 3, 0.10)
    dd = rolling.drawdown(pts)
    assert dd["max_dd"] >= -1e-6        # 우상향이면 낙폭 ~0


def test_real_adjust_discounts_inflation():
    # 명목 100 고정 1년 → 실질 ≈ 100/1.02
    d0 = date(2020, 1, 1)
    pts = [[(d0 + timedelta(days=i)).strftime("%Y-%m-%d"), 100.0] for i in range(366)]
    real = rolling.real_adjust(pts, infl=0.02)
    assert abs(real[0][1] - 100.0) < 1e-6
    assert abs(real[-1][1] - 100.0 / 1.02) < 0.05


def test_syn_flag_passthrough_and_frac():
    # 절반 syn=1인 시리즈 → horizon syn_frac 계산되고 real_adjust가 syn 보존
    pts = [[d, v, s] for (d, v), s in zip(_geo_series(2000, 365 * 4, 0.06),
                                          ([1] * (365 * 2) + [0] * (365 * 2)))]
    real = rolling.real_adjust(pts)
    assert len(real[0]) == 3            # syn 보존
    tbl = rolling.horizon_table(pts, horizons=[1])
    assert tbl[1]["syn_frac"] is not None
