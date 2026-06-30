import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from modules.price_loader import PriceLoader


class _FakeFunds:
    top_holdings = pd.DataFrame(
        [
            {"Name": "NVIDIA Corp", "Holding Percent": 0.0789},
            {"Name": "Apple Inc", "Holding Percent": 0.0704},
        ],
        index=["NVDA", "AAPL"],
    )


class _FakeTicker:
    funds_data = _FakeFunds()


def test_yfinance_etf_holdings_are_normalized_to_percent():
    loader = PriceLoader.__new__(PriceLoader)

    holdings = loader._fetch_yfinance_etf_holdings("SPY", ticker_obj=_FakeTicker(), limit=2)

    assert holdings == [
        {
            "rank": 1,
            "code": "NVDA",
            "name": "NVIDIA Corp",
            "weight_pct": 7.89,
            "source": "Yahoo Finance",
        },
        {
            "rank": 2,
            "code": "AAPL",
            "name": "Apple Inc",
            "weight_pct": 7.04,
            "source": "Yahoo Finance",
        },
    ]
