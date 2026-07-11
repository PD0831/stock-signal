import json
from datetime import datetime, timezone

import pytest
import pandas as pd

from scripts.build_dashboard_snapshots import (
    SCHEMA_VERSION,
    WEIGHTS,
    build_breadth_snapshot,
    build_dashboard_snapshot,
    write_json_atomic,
    run,
)
from scripts.market_snapshot_data import _ntss_series


def test_ntss_series_is_vix3m_minus_vix():
    index = pd.date_range("2026-07-11 13:30", periods=2, freq="15min", tz="UTC")
    histories = {
        "^VIX": pd.DataFrame({"Close": [15.0, 16.0]}, index=index),
        "^VIX3M": pd.DataFrame({"Close": [18.0, 17.5]}, index=index),
    }

    assert _ntss_series(histories).tolist() == [3.0, 1.5]


def test_dashboard_snapshot_merges_universes_and_assigns_weights():
    generated_at = datetime(2026, 7, 11, 9, 30, tzinfo=timezone.utc)
    picks = {
        "nasdaq100": [
            {"symbol": "NVDA", "rank": 1},
            {"symbol": "MSFT", "rank": 2},
            {"symbol": "AAPL", "rank": 3},
        ],
        "sp500": [{"symbol": "JPM"}, {"symbol": "XOM"}],
    }

    snapshot = build_dashboard_snapshot(
        picks,
        generated_at=generated_at,
        market_status={"phase": "B"},
        quality={"fresh": True},
    )

    assert SCHEMA_VERSION == 1
    assert WEIGHTS == (60, 20, 20)
    assert snapshot == {
        "schema_version": 1,
        "generated_at": "2026-07-11T09:30:00+00:00",
        "market_status": {"phase": "B"},
        "quality": {"fresh": True},
        "buy_targets": [
            {
                "symbol": "NVDA",
                "rank": 1,
                "universe": "nasdaq100",
                "target_weight_pct": 60,
            },
            {
                "symbol": "MSFT",
                "rank": 2,
                "universe": "nasdaq100",
                "target_weight_pct": 20,
            },
            {
                "symbol": "AAPL",
                "rank": 3,
                "universe": "nasdaq100",
                "target_weight_pct": 20,
            },
            {"symbol": "JPM", "universe": "sp500", "target_weight_pct": 60},
            {"symbol": "XOM", "universe": "sp500", "target_weight_pct": 20},
        ],
    }


def test_dashboard_snapshot_rejects_more_picks_than_weights():
    picks = {"nasdaq100": ({"symbol": f"S{rank}"} for rank in range(4))}

    with pytest.raises(ValueError, match="nasdaq100.*3"):
        build_dashboard_snapshot(
            picks, generated_at=datetime(2026, 7, 11, tzinfo=timezone.utc)
        )


def test_breadth_snapshot_reports_last_phase_change():
    records = [
        {"t": "2026-07-11T09:30:00+02:00", "phase_code": "A"},
        {"t": "2026-07-11T09:45:00+02:00", "phase_code": "B"},
        {"t": "2026-07-11T10:00:00+02:00", "phase_code": "B"},
        {"t": "2026-07-11T10:15:00+02:00", "phase_code": "E"},
    ]
    generated_at = datetime.fromisoformat("2026-07-11T10:20:00+02:00")

    snapshot = build_breadth_snapshot(
        records, generated_at=generated_at, quality={"valid": 98}
    )

    assert snapshot == {
        "schema_version": 1,
        "generated_at": "2026-07-11T10:20:00+02:00",
        "records": records,
        "quality": {"valid": 98},
        "latest_transition": {
            "at": "2026-07-11T10:15:00+02:00",
            "from": "B",
            "to": "E",
        },
    }


def test_breadth_snapshot_is_independent_of_record_mutations():
    records = [
        {
            "t": "2026-07-11T09:30:00+02:00",
            "phase_code": "A",
            "metrics": {"strong": 42},
        }
    ]

    snapshot = build_breadth_snapshot(records)
    records[0]["metrics"]["strong"] = 99

    assert snapshot["records"][0]["metrics"]["strong"] == 42


def test_breadth_snapshot_defaults_generated_at_and_has_no_transition(monkeypatch):
    fixed_now = datetime(2026, 7, 11, 8, 0, tzinfo=timezone.utc)

    class FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return fixed_now

    monkeypatch.setattr("scripts.build_dashboard_snapshots.datetime", FixedDateTime)
    records = [{"t": "2026-07-11T09:30:00+02:00", "phase_code": "A"}]

    snapshot = build_breadth_snapshot(records)

    assert snapshot["generated_at"] == "2026-07-11T08:00:00+00:00"
    assert snapshot["quality"] is None
    assert snapshot["latest_transition"] is None


def test_generated_at_is_keyword_only_for_both_builders():
    generated_at = datetime(2026, 7, 11, tzinfo=timezone.utc)

    with pytest.raises(TypeError):
        build_dashboard_snapshot({}, generated_at)
    with pytest.raises(TypeError):
        build_breadth_snapshot([], generated_at)


def test_write_json_atomic_creates_parent_and_replaces_file(tmp_path):
    path = tmp_path / "nested" / "snapshot.json"

    write_json_atomic(path, {"schema_version": 1, "value": 2})

    assert json.loads(path.read_text(encoding="utf-8")) == {
        "schema_version": 1,
        "value": 2,
    }
    assert not list(path.parent.glob(f".{path.name}.*.tmp"))


def test_write_json_atomic_leaves_existing_file_on_nan_failure(tmp_path):
    path = tmp_path / "snapshot.json"
    original = '{"schema_version": 1, "value": "old"}\n'
    path.write_text(original, encoding="utf-8")

    with pytest.raises(ValueError, match="Out of range float values"):
        write_json_atomic(path, {"value": float("nan")})

    assert path.read_text(encoding="utf-8") == original
    assert json.loads(path.read_text(encoding="utf-8"))["value"] == "old"


def test_write_json_atomic_cleans_temp_and_preserves_destination_on_replace_failure(
    tmp_path, monkeypatch
):
    path = tmp_path / "snapshot.json"
    original = '{"value": "old"}\n'
    path.write_text(original, encoding="utf-8")

    def fail_replace(self, target):
        raise OSError("replace failed")

    monkeypatch.setattr(type(path), "replace", fail_replace)

    with pytest.raises(OSError, match="replace failed"):
        write_json_atomic(path, {"value": "new"})

    assert path.read_text(encoding="utf-8") == original
    assert not list(tmp_path.glob(f".{path.name}.*.tmp"))


class FakeProvider:
    def __init__(self):
        self.signal_calls = []
        self.breadth_calls = 0

    def compute_signals(self, universe):
        self.signal_calls.append(universe)
        return {
            "universe": universe,
            "valid_count": 99 if universe == "nasdaq100" else 498,
            "failed_count": 2,
            "ma200_selected": [
                {"symbol": "NVDA" if universe == "nasdaq100" else "JPM", "rank": 1}
            ],
        }

    def compute_breadth(self):
        self.breadth_calls += 1
        return {
            "records": [
                {
                    "t": "2026-07-11T09:30:00-04:00",
                    "s": 51.0,
                    "bd": 22.0,
                    "phase_code": "B",
                }
            ],
            "n_stocks": 500,
            "n_valid_hourly": 497,
            "raw_prices": {"AAPL": [100, 101]},
        }


def test_run_computes_each_market_once_and_publishes_compact_snapshots(tmp_path):
    provider = FakeProvider()
    generated_at = datetime(2026, 7, 11, 14, 0, tzinfo=timezone.utc)

    dashboard, breadth = run(tmp_path, provider=provider, generated_at=generated_at)

    assert provider.signal_calls == ["nasdaq100", "sp500"]
    assert provider.breadth_calls == 1
    assert dashboard["market_status"] == {
        "phase_code": "B",
        "as_of": "2026-07-11T09:30:00-04:00",
    }
    assert dashboard["quality"] == {
        "nasdaq100": {"valid_count": 99, "failed_count": 2},
        "sp500": {"valid_count": 498, "failed_count": 2},
    }
    assert breadth["quality"] == {
        "expected_count": 500,
        "valid_count": 497,
        "failed_count": 3,
    }
    assert breadth["records"] == [
        {
            "t": "2026-07-11T09:30:00-04:00",
            "s": 51.0,
            "bd": 22.0,
            "phase_code": "B",
        }
    ]
    for name in ("dashboard_snapshot.json", "breadth_15m.json"):
        payload = json.loads((tmp_path / name).read_text(encoding="utf-8"))
        assert "raw_prices" not in json.dumps(payload)


@pytest.mark.parametrize("invalid_part", ["dashboard", "breadth"])
def test_run_preserves_both_public_files_when_either_payload_is_invalid(
    tmp_path, invalid_part
):
    dashboard_path = tmp_path / "dashboard_snapshot.json"
    breadth_path = tmp_path / "breadth_15m.json"
    dashboard_path.write_text('{"old":"dashboard"}\n', encoding="utf-8")
    breadth_path.write_text('{"old":"breadth"}\n', encoding="utf-8")
    provider = FakeProvider()
    if invalid_part == "dashboard":
        original = provider.compute_signals

        def invalid_signals(universe):
            result = original(universe)
            result["ma200_selected"][0]["distance_pct"] = float("nan")
            return result

        provider.compute_signals = invalid_signals
    else:
        provider.compute_breadth = lambda: {
            "records": [{"t": "now", "s": float("nan")}],
            "n_stocks": 1,
            "n_valid_hourly": 1,
        }

    with pytest.raises(ValueError):
        run(tmp_path, provider=provider)

    assert json.loads(dashboard_path.read_text())["old"] == "dashboard"
    assert json.loads(breadth_path.read_text())["old"] == "breadth"
