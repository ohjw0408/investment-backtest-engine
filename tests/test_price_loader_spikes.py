import sys
from pathlib import Path

import pandas as pd

sys.path.append(str(Path(__file__).resolve().parents[1]))

from modules.price_loader import _drop_isolated_price_spikes


def test_drop_isolated_one_day_high_spike():
    df = pd.DataFrame(
        [
            {"date": "2026-06-16", "open": 750.0, "high": 760.0, "low": 740.0, "close": 750.0, "volume": 1},
            {"date": "2026-06-17", "open": 332000.0, "high": 348000.0, "low": 331500.0, "close": 346500.0, "volume": 1},
            {"date": "2026-06-18", "open": 746.0, "high": 748.0, "low": 743.0, "close": 746.0, "volume": 1},
        ]
    )

    out = _drop_isolated_price_spikes(df)

    assert out["date"].tolist() == ["2026-06-16", "2026-06-18"]


def test_keep_persistent_price_level_change():
    df = pd.DataFrame(
        [
            {"date": "2026-06-16", "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0, "volume": 1},
            {"date": "2026-06-17", "open": 2600.0, "high": 2620.0, "low": 2590.0, "close": 2600.0, "volume": 1},
            {"date": "2026-06-18", "open": 2700.0, "high": 2720.0, "low": 2690.0, "close": 2700.0, "volume": 1},
        ]
    )

    out = _drop_isolated_price_spikes(df)

    assert out["date"].tolist() == ["2026-06-16", "2026-06-17", "2026-06-18"]
