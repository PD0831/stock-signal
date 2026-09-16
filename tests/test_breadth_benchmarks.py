import pandas as pd
import pytest
from scripts import market_snapshot_data as market


def test_prices_align_to_exact_instants_without_filling_gaps():
    rows = [{"t": "2026-09-15T13:30:00+00:00"}, {"t": "2026-09-15T13:45:00+00:00"}, {"t": "2026-09-15T14:00:00+00:00"}]
    history = {
        "SPY": pd.DataFrame({"Close": [600, 603]}, index=pd.DatetimeIndex(["2026-09-15T09:30:00-04:00", "2026-09-15T10:00:00-04:00"])),
        "QQQ": pd.DataFrame({"Close": [500, float("inf"), -1]}, index=pd.to_datetime([r["t"] for r in rows])),
    }
    result = market.attach_benchmark_prices(rows, history)
    assert [r["spy"] for r in result] == [600, None, 603]
    assert [r["qqq"] for r in result] == [500, None, None]
    assert "spy" not in rows[0]


def test_missing_benchmark_preserves_breadth():
    result = market.attach_benchmark_prices([{"t": "2026-09-15T13:30:00Z", "s": 43}], {})
    assert result == [{"t": "2026-09-15T13:30:00Z", "s": 43, "spy": None, "qqq": None}]
