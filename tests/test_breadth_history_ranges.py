from datetime import datetime, timezone

import pytest

from scripts.build_dashboard_snapshots import merge_breadth_history


def record(timestamp: str, value: float) -> dict:
    return {"t": timestamp, "s": value, "bd": 100 - value, "mid": value / 10}


def test_new_records_replace_duplicates_and_results_are_sorted():
    existing = [
        record("2026-06-01T10:00:00-04:00", 10),
        record("2026-06-01T10:15:00-04:00", 20),
    ]
    new = [
        record("2026-06-01T10:30:00-04:00", 30),
        record("2026-06-01T10:15:00-04:00", 99),
    ]

    merged = merge_breadth_history(existing, new)

    assert [item["t"] for item in merged] == [
        "2026-06-01T10:00:00-04:00",
        "2026-06-01T10:15:00-04:00",
        "2026-06-01T10:30:00-04:00",
    ]
    assert merged[1]["s"] == 99


def test_history_uses_three_calendar_month_cutoff():
    merged = merge_breadth_history([
        record("2026-03-29T09:30:00-04:00", 1),
        record("2026-03-30T09:30:00-04:00", 2),
        record("2026-06-30T16:00:00-04:00", 3),
    ], [])

    assert [item["s"] for item in merged] == [2, 3]


@pytest.mark.parametrize("timestamp", ["2026-06-01T10:00:00", "not-a-date"])
def test_history_rejects_invalid_or_naive_timestamps(timestamp):
    with pytest.raises(ValueError, match="timezone-aware"):
        merge_breadth_history([], [record(timestamp, 1)])


def test_history_is_deep_copied():
    source = record("2026-06-01T10:00:00-04:00", 1)
    merged = merge_breadth_history([], [source])
    source["s"] = 999
    assert merged[0]["s"] == 1
