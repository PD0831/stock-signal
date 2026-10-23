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
    assert result == [{"t": "2026-09-15T13:30:00Z", "s": 43, "spy": None, "qqq": None, "rsp": None}]


def test_rsp_attaches_and_backfills_saved_history():
    from scripts.build_dashboard_snapshots import backfill_benchmark_prices, merge_breadth_history

    stamps = pd.DatetimeIndex(["2026-09-15T09:30:00-04:00", "2026-09-15T09:45:00-04:00"])
    rows = [{"t": "2026-09-15T13:30:00+00:00"}, {"t": "2026-09-15T13:45:00+00:00"}]
    attached = market.attach_benchmark_prices(rows, {"RSP": pd.DataFrame({"Close": [190.5, 0]}, index=stamps)})
    assert [r["rsp"] for r in attached] == [190.5, None]

    saved = [{"t": "2026-09-14T19:45:00Z", "spy": 600.0}, {"t": "2026-09-14T19:30:00Z", "spy": 599.0, "rsp": 189.0}]
    merged = merge_breadth_history(saved, [{"t": "2026-09-14T19:30:00+00:00", "spy": 599.0, "rsp": None}])
    filled = backfill_benchmark_prices(merged, {"rsp": {"2026-09-14T19:45:00+00:00": 189.4, "2026-09-14T19:30:00+00:00": 1.0}})
    assert [r["rsp"] for r in filled] == [189.0, 189.4]
