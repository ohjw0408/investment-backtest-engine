import pandas as pd
import numpy as np

from modules.dividend_simulator import DividendSimulator


class FakeLoader:
    USD_KRW_START = "2022-01-01"

    def __init__(self):
        today = pd.Timestamp.today().normalize()
        dates = pd.date_range("2022-01-01", today, freq="D")

        active = pd.DataFrame({
            "date": dates.strftime("%Y-%m-%d"),
            "close": 10000.0,
            "dividend": 0.0,
        })
        month_end_idx = active.groupby(pd.to_datetime(active["date"]).dt.to_period("M")).tail(1).index
        active.loc[month_end_idx, "dividend"] = 30.0

        late_dates = pd.date_range(today - pd.DateOffset(months=2), today, freq="D")
        late_zero_weight = pd.DataFrame({
            "date": late_dates.strftime("%Y-%m-%d"),
            "close": 10000.0,
            "dividend": 0.0,
        })

        self.data = {
            "ACTIVE": active,
            "0083S0": late_zero_weight,
            "NO_DIV": late_zero_weight,
        }

    def get_price(self, code, start_date, end_date):
        return self.data[str(code)].copy()


def test_zero_weight_ticker_does_not_change_dividend_target_result():
    loader = FakeLoader()

    base = DividendSimulator(loader, ["ACTIVE"], {"ACTIVE": 1.0})
    with_zero = DividendSimulator(loader, ["0083S0", "ACTIVE"], {"0083S0": 0.0, "ACTIVE": 1.0})
    base.MIN_CASES = 0
    with_zero.MIN_CASES = 0

    base_result = base.get_probability(
        seed=100_000_000,
        monthly=0,
        years=1,
        target_monthly_div=100_000,
    )
    zero_result = with_zero.get_probability(
        seed=100_000_000,
        monthly=0,
        years=1,
        target_monthly_div=100_000,
    )

    assert zero_result == base_result
    assert zero_result["cases_count"] > 0


def test_synthetic_dividend_is_diluted_by_no_dividend_weight():
    loader = FakeLoader()
    seed = 100_000_000

    base = DividendSimulator(loader, ["ACTIVE"], {"ACTIVE": 1.0})
    one_pct = DividendSimulator(loader, ["NO_DIV", "ACTIVE"], {"NO_DIV": 0.01, "ACTIVE": 0.99})
    half = DividendSimulator(loader, ["NO_DIV", "ACTIVE"], {"NO_DIV": 0.50, "ACTIVE": 0.50})

    base_div = base._simulate_synthetic(
        seed, monthly=0, years=1, div_stats=base._calc_div_stats(), rng=np.random.default_rng(1)
    )
    one_pct_div = one_pct._simulate_synthetic(
        seed, monthly=0, years=1, div_stats=one_pct._calc_div_stats(), rng=np.random.default_rng(1)
    )
    half_div = half._simulate_synthetic(
        seed, monthly=0, years=1, div_stats=half._calc_div_stats(), rng=np.random.default_rng(1)
    )

    assert one_pct_div < base_div
    assert one_pct_div > half_div
    assert 0.97 <= one_pct_div / base_div <= 1.0
    assert 0.45 <= half_div / base_div <= 0.55


class MonthlyAnchorProbe(DividendSimulator):
    def __init__(self):
        pass

    def _run_rolling(self, seed, monthly, years):
        return seed, monthly, years

    def _calc_prob(self, payload, target_monthly):
        seed, monthly, _years = payload
        threshold = 11_250_000 if seed == 100_000_000 else 9_000_000
        return 1.0 if monthly >= threshold else 0.0


def test_monthly_anchor_decreases_when_seed_increases():
    sim = MonthlyAnchorProbe()

    lower_seed_monthly = sim._find_anchor_monthly(
        seed=100_000_000,
        years=5,
        target_monthly_div=3_000_000,
        probability=0.90,
    )
    higher_seed_monthly = sim._find_anchor_monthly(
        seed=200_000_000,
        years=5,
        target_monthly_div=3_000_000,
        probability=0.90,
    )

    assert higher_seed_monthly <= lower_seed_monthly


class BracketNarrowingProbe(DividendSimulator):
    def __init__(self):
        pass

    def _run_rolling(self, seed, monthly, years):
        return seed, monthly, years

    def _calc_prob(self, payload, target_monthly):
        seed, monthly, years = payload
        if years == 70:
            return 1.0
        if monthly >= 12_500_000:
            return 1.0
        if seed >= 250_000_000:
            return 1.0
        return 0.0


def test_monthly_anchor_narrows_wide_expansion_bracket():
    sim = BracketNarrowingProbe()

    monthly = sim._find_anchor_monthly(
        seed=0,
        years=5,
        target_monthly_div=3_000_000,
        probability=0.90,
    )

    assert monthly <= 12_600_000


def test_seed_anchor_narrows_wide_expansion_bracket():
    sim = BracketNarrowingProbe()

    seed = sim._find_anchor_seed(
        monthly=0,
        years=5,
        target_monthly_div=3_000_000,
        probability=0.90,
    )

    assert seed <= 260_000_000


def test_year_anchor_extends_to_seventy_years():
    sim = BracketNarrowingProbe()

    years = sim._find_anchor_years(
        seed=0,
        monthly=0,
        target_monthly_div=3_000_000,
        probability=0.90,
    )

    assert years == 70.0
