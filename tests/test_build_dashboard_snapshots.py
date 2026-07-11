import json
from pathlib import Path
from datetime import datetime, timezone

import pytest
import pandas as pd
import yaml

from scripts.build_dashboard_snapshots import (
    SCHEMA_VERSION,
    WEIGHTS,
    build_breadth_snapshot,
    build_dashboard_snapshot,
    write_json_atomic,
    run,
    snapshot_session_metadata,
    _market_status,
)


def test_session_metadata_keeps_holiday_snapshot_fresh_until_next_open():
    class Calendar:
        def is_open_on_minute(self, at):
            return False
        def next_open(self, at):
            return datetime.fromisoformat("2026-07-06T13:30:00+00:00")

    metadata = snapshot_session_metadata(
        datetime.fromisoformat("2026-07-03T15:00:00+00:00"), calendar=Calendar()
    )

    assert metadata == {
        "session_status": "closed",
        "fresh_until": "2026-07-06T14:00:00+00:00",
    }


def test_session_metadata_early_close_rolls_to_next_session():
    class Calendar:
        def is_open_on_minute(self, at):
            return at < datetime.fromisoformat("2026-11-27T18:00:00+00:00")
        def next_open(self, at):
            return datetime.fromisoformat("2026-11-30T14:30:00+00:00")

    metadata = snapshot_session_metadata(
        datetime.fromisoformat("2026-11-27T17:45:00+00:00"), calendar=Calendar()
    )

    assert metadata["fresh_until"] == "2026-11-30T15:00:00+00:00"


def test_session_metadata_preopen_stays_fresh_through_first_update():
    class Calendar:
        def is_open_on_minute(self, at):
            return False
        def next_open(self, at):
            return datetime.fromisoformat("2026-07-06T13:30:00+00:00")

    metadata = snapshot_session_metadata(
        datetime.fromisoformat("2026-07-06T13:15:00+00:00"), calendar=Calendar()
    )

    assert metadata["fresh_until"] == "2026-07-06T14:00:00+00:00"
from scripts.market_snapshot_data import _calculate_breadth, _calc_ntss, _ntss_series
from scripts.market_snapshot_data import SnapshotMarketData, daily_close_payload


def _workflow():
    workflow_path = Path(__file__).parents[1] / ".github/workflows/refresh_dashboard.yml"
    assert workflow_path.exists(), "snapshot refresh workflow must be checked in"
    parsed = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))
    parsed["on"] = parsed.pop(True, parsed.get("on"))
    return parsed


def test_refresh_workflow_separates_read_only_build_from_write_publish():
    workflow = _workflow()
    build = workflow["jobs"]["build"]
    publish = workflow["jobs"]["publish"]

    assert workflow["on"]["workflow_dispatch"] is None
    assert workflow["on"]["schedule"] == [{"cron": "*/15 13-21 * * 1-5"}]
    assert workflow["concurrency"] == {
        "group": "mvs-dashboard-refresh",
        "cancel-in-progress": True,
    }
    assert build["permissions"] == {"contents": "read"}
    assert publish["permissions"] == {"contents": "write"}
    assert publish["needs"] == "build"
    assert build["outputs"]["should_run"] == "${{ steps.market-hours.outputs.should_run }}"
    assert publish["if"] == "needs.build.outputs.should_run == 'true'"

    build_checkout = next(step for step in build["steps"] if "actions/checkout" in step.get("uses", ""))
    setup_python = next(step for step in build["steps"] if "actions/setup-python" in step.get("uses", ""))
    assert build_checkout["with"]["persist-credentials"] is False
    assert setup_python["with"]["python-version"] == "3.12"
    assert all("@v" not in step.get("uses", "") for job in (build, publish) for step in job["steps"])


def test_refresh_workflow_locks_dependencies_and_publishes_only_snapshots():
    workflow = _workflow()
    build_steps = workflow["jobs"]["build"]["steps"]
    publish_steps = workflow["jobs"]["publish"]["steps"]
    build_commands = "\n".join(step.get("run", "") for step in build_steps)
    publish_commands = "\n".join(step.get("run", "") for step in publish_steps)
    upload = next(step for step in build_steps if "actions/upload-artifact" in step.get("uses", ""))

    assert "python scripts/nyse_market_hours.py" in build_commands
    assert "pip install --require-hashes -r requirements-actions.lock" in build_commands
    assert "python scripts/build_dashboard_snapshots.py --output-dir data" in build_commands
    assert upload["with"]["path"].splitlines() == [
        "data/dashboard_snapshot.json",
        "data/breadth_15m.json",
    ]
    assert "git add -- data/dashboard_snapshot.json data/breadth_15m.json" in publish_commands
    assert "git diff --cached --quiet" in publish_commands
    assert "git add -A" not in publish_commands
    assert "git add ." not in publish_commands
    validate_index = next(
        index for index, step in enumerate(publish_steps)
        if "validate_dashboard_snapshots.py" in step.get("run", "")
    )
    commit_index = next(
        index for index, step in enumerate(publish_steps)
        if "git add -- data/dashboard_snapshot.json" in step.get("run", "")
    )
    assert validate_index < commit_index

    lock = (Path(__file__).parents[1] / "requirements-actions.lock").read_text()
    assert "--hash=sha256:" in lock
    assert "exchange-calendars==" in lock


def test_nyse_gate_observes_holiday_and_early_close():
    from scripts.nyse_market_hours import is_nyse_open

    class FakeNYSECalendar:
        def is_open_on_minute(self, timestamp):
            holiday = timestamp.date().isoformat() == "2026-07-03"
            early_close = timestamp.date().isoformat() == "2026-11-27"
            return not holiday and (not early_close or timestamp.hour < 18)

    calendar = FakeNYSECalendar()
    assert not is_nyse_open(
        datetime.fromisoformat("2026-07-03T15:00:00+00:00"), calendar=calendar
    )
    assert is_nyse_open(
        datetime.fromisoformat("2026-11-27T17:45:00+00:00"), calendar=calendar
    )
    assert not is_nyse_open(
        datetime.fromisoformat("2026-11-27T18:45:00+00:00"), calendar=calendar
    )


def test_nyse_gate_uses_actual_xnys_sessions():
    from scripts.nyse_market_hours import is_nyse_open

    assert is_nyse_open(datetime.fromisoformat("2026-07-06T14:00:00+00:00"))
    assert is_nyse_open(datetime.fromisoformat("2026-01-05T15:00:00+00:00"))
    assert not is_nyse_open(datetime.fromisoformat("2026-07-03T15:00:00+00:00"))
    assert is_nyse_open(datetime.fromisoformat("2026-11-27T17:45:00+00:00"))
    assert not is_nyse_open(datetime.fromisoformat("2026-11-27T18:15:00+00:00"))


def test_snapshot_pair_validation_requires_schema_and_matching_generation(tmp_path):
    from scripts.validate_dashboard_snapshots import validate_snapshot_pair

    dashboard = tmp_path / "dashboard_snapshot.json"
    breadth = tmp_path / "breadth_15m.json"
    generated_at = datetime.now(timezone.utc).isoformat()
    quality = {"fresh_until": generated_at, "session_status": "closed"}
    dashboard.write_text(json.dumps({
        "schema_version": 1, "generation_id": "same", "generated_at": generated_at,
        "buy_targets": [], "market_status": {}, "quality": quality,
    }))
    breadth.write_text(json.dumps({
        "schema_version": 1, "generation_id": "same", "generated_at": generated_at,
        "records": [], "quality": quality, "latest_transition": None,
    }))
    validate_snapshot_pair(dashboard, breadth)

    breadth.write_text(json.dumps({
        "schema_version": 1, "generation_id": "different", "generated_at": generated_at,
        "records": [], "quality": quality, "latest_transition": None,
    }))
    with pytest.raises(ValueError, match="generation_id"):
        validate_snapshot_pair(dashboard, breadth)

    breadth.write_text(json.dumps({
        "schema_version": 2, "generation_id": "same", "generated_at": generated_at,
        "records": [], "quality": quality, "latest_transition": None,
    }))
    with pytest.raises(ValueError, match="schema_version"):
        validate_snapshot_pair(dashboard, breadth)


@pytest.mark.parametrize(
    ("artifact", "field", "bad_value"),
    [
        ("dashboard", "schema_version", "1"),
        ("dashboard", "generation_id", ""),
        ("dashboard", "generated_at", None),
        ("dashboard", "buy_targets", {}),
        ("dashboard", "market_status", []),
        ("dashboard", "quality", []),
        ("breadth", "records", {}),
        ("breadth", "quality", []),
        ("breadth", "latest_transition", []),
    ],
)
def test_snapshot_pair_validation_rejects_missing_or_wrong_types(
    tmp_path, artifact, field, bad_value
):
    from scripts.validate_dashboard_snapshots import validate_snapshot_pair

    generated_at = datetime.now(timezone.utc).isoformat()
    quality = {"fresh_until": generated_at, "session_status": "closed"}
    payloads = {
        "dashboard": {
            "schema_version": 1, "generation_id": "same", "generated_at": generated_at,
            "buy_targets": [], "market_status": {}, "quality": quality,
        },
        "breadth": {
            "schema_version": 1, "generation_id": "same", "generated_at": generated_at,
            "records": [], "quality": quality, "latest_transition": None,
        },
    }
    payloads[artifact][field] = bad_value
    paths = {name: tmp_path / f"{name}.json" for name in payloads}
    for name, payload in payloads.items():
        paths[name].write_text(json.dumps(payload))

    with pytest.raises(ValueError, match=field):
        validate_snapshot_pair(paths["dashboard"], paths["breadth"])


def test_snapshot_pair_validation_rejects_truncated_json(tmp_path):
    from scripts.validate_dashboard_snapshots import validate_snapshot_pair

    dashboard = tmp_path / "dashboard.json"
    breadth = tmp_path / "breadth.json"
    dashboard.write_text('{"schema_version": 1')
    breadth.write_text("{}")

    with pytest.raises(json.JSONDecodeError):
        validate_snapshot_pair(dashboard, breadth)


@pytest.mark.parametrize(
    "bad_target",
    [
        {"symbol": "<script>", "universe": "sp500"},
        {"symbol": "AAPL", "universe": "javascript:alert(1)"},
    ],
)
def test_publication_validator_rejects_unsafe_buy_targets(tmp_path, bad_target):
    from scripts.validate_dashboard_snapshots import validate_snapshot_pair

    generated_at = datetime.now(timezone.utc).isoformat()
    quality = {"fresh_until": generated_at, "session_status": "closed"}
    dashboard = tmp_path / "dashboard.json"
    breadth = tmp_path / "breadth.json"
    dashboard.write_text(json.dumps({
        "schema_version": 1, "generation_id": "same", "generated_at": generated_at,
        "buy_targets": [bad_target], "market_status": {}, "quality": quality,
    }))
    breadth.write_text(json.dumps({
        "schema_version": 1, "generation_id": "same", "generated_at": generated_at,
        "records": [], "quality": quality, "latest_transition": None,
    }))

    with pytest.raises(ValueError, match="invalid"):
        validate_snapshot_pair(dashboard, breadth)


def test_publication_validator_rejects_non_finite_json(tmp_path):
    from scripts.validate_dashboard_snapshots import validate_snapshot_pair

    generated_at = datetime.now(timezone.utc).isoformat()
    quality = {"fresh_until": generated_at, "session_status": "closed"}
    dashboard = tmp_path / "dashboard.json"
    breadth = tmp_path / "breadth.json"
    dashboard.write_text(json.dumps({
        "schema_version": 1, "generation_id": "same", "generated_at": generated_at,
        "buy_targets": [], "market_status": {}, "quality": quality,
    }))
    breadth.write_text(json.dumps({
        "schema_version": 1, "generation_id": "same", "generated_at": generated_at,
        "records": [{"t": generated_at, "s": float("inf")}],
        "quality": quality, "latest_transition": None,
    }))

    with pytest.raises(ValueError, match="finite"):
        validate_snapshot_pair(dashboard, breadth)


@pytest.mark.parametrize(
    ("mutation", "expected"),
    [
        (lambda target: target.pop("rank"), "rank"),
        (lambda target: target.pop("target_weight_pct"), "target_weight_pct"),
        (lambda target: target.update(rank=True), "rank"),
        (lambda target: target.update(target_weight_pct=False), "target_weight_pct"),
        (lambda target: target.update(rank=0), "rank"),
    ],
)
def test_publication_validator_rejects_invalid_required_target_fields(
    tmp_path, mutation, expected
):
    from scripts.validate_dashboard_snapshots import validate_snapshot_pair

    generated_at = datetime.now(timezone.utc).isoformat()
    quality = {"fresh_until": generated_at, "session_status": "closed"}
    target = {
        "symbol": "AAPL", "universe": "sp500", "rank": 1,
        "target_weight_pct": 60,
    }
    mutation(target)
    dashboard = tmp_path / "dashboard.json"
    breadth = tmp_path / "breadth.json"
    dashboard.write_text(json.dumps({
        "schema_version": 1, "generation_id": "same", "generated_at": generated_at,
        "buy_targets": [target], "market_status": {}, "quality": quality,
    }))
    breadth.write_text(json.dumps({
        "schema_version": 1, "generation_id": "same", "generated_at": generated_at,
        "records": [], "quality": quality, "latest_transition": None,
    }))

    with pytest.raises(ValueError, match=expected):
        validate_snapshot_pair(dashboard, breadth)


@pytest.mark.parametrize(
    ("artifact", "field"),
    [("dashboard", "buy_targets"), ("breadth", "latest_transition")],
)
def test_snapshot_pair_validation_rejects_missing_required_fields(
    tmp_path, artifact, field
):
    from scripts.validate_dashboard_snapshots import validate_snapshot_pair

    generated_at = datetime.now(timezone.utc).isoformat()
    quality = {"fresh_until": generated_at, "session_status": "closed"}
    payloads = {
        "dashboard": {
            "schema_version": 1, "generation_id": "same", "generated_at": generated_at,
            "buy_targets": [], "market_status": {}, "quality": quality,
        },
        "breadth": {
            "schema_version": 1, "generation_id": "same", "generated_at": generated_at,
            "records": [], "quality": quality, "latest_transition": None,
        },
    }
    del payloads[artifact][field]
    paths = {name: tmp_path / f"{name}.json" for name in payloads}
    for name, payload in payloads.items():
        paths[name].write_text(json.dumps(payload))

    with pytest.raises(ValueError, match=field):
        validate_snapshot_pair(paths["dashboard"], paths["breadth"])


def test_ntss_series_is_vix3m_minus_vix():
    index = pd.date_range("2026-07-11 13:30", periods=2, freq="15min", tz="UTC")
    histories = {
        "^VIX": pd.DataFrame({"Close": [15.0, 16.0]}, index=index),
        "^VIX3M": pd.DataFrame({"Close": [18.0, 17.5]}, index=index),
    }

    assert _ntss_series(histories).tolist() == [3.0, 1.5]


def test_build_breadth_matches_canonical_available_history_ema_and_date_refs():
    symbols = [f"S{i:03}" for i in range(100)]
    days = pd.date_range("2026-01-01", periods=3, freq="D")
    daily = pd.DataFrame(
        [[100.0] * 100, [200.0] * 100, [300.0] * 100], index=days, columns=symbols
    )
    bars = pd.DatetimeIndex(
        ["2026-01-02 15:00:00+00:00", "2026-01-03 15:00:00+00:00"]
    )
    intraday = pd.DataFrame(
        [[140.0] * 100, [250.0] * 100], index=bars, columns=symbols
    )

    actual = _calculate_breadth(daily, intraday, denominator=100)
    expected = pd.DataFrame(
        {
            "above_20": [0.0, 50.0],
            "above_50": [0.0, 50.0],
            "above_200": [0.0, 50.0],
            "above_20_n": [0.0, 100.0],
            "above_50_n": [0.0, 100.0],
            "above_200_n": [0.0, 100.0],
            "valid_20_n": [100.0, 100.0],
            "valid_50_n": [100.0, 100.0],
            "valid_200_n": [100.0, 100.0],
            "strong": [0.0, 50.0],
            "breakdown": [100.0, 50.0],
            "pullback": [0.0, 0.0],
            "recovery": [0.0, 0.0],
        },
        index=bars,
    )

    pd.testing.assert_frame_equal(actual, expected)


def test_build_breadth_masks_rows_below_minimum_stock_count():
    daily = pd.DataFrame([[100.0] * 99], columns=[f"S{i}" for i in range(99)])
    intraday = pd.DataFrame(
        [[101.0] * 99],
        index=pd.DatetimeIndex(["2026-01-01 15:00:00+00:00"]),
        columns=daily.columns,
    )

    result = _calculate_breadth(daily, intraday, denominator=100)

    assert result[["above_20", "above_50", "above_200"]].isna().all().all()
    assert result[["above_20_n", "above_50_n", "above_200_n"]].isna().all().all()


def test_build_ntss_matches_canonical_90_minute_tolerance():
    source_index = pd.DatetimeIndex(["2026-01-01 12:00:00+00:00"])
    vix = pd.DataFrame({"vix": [15.0], "vix3m": [18.0]}, index=source_index)
    target = pd.DatetimeIndex(
        ["2026-01-01 13:29:00+00:00", "2026-01-01 13:31:00+00:00"]
    )

    result = _calc_ntss(vix, target)

    assert result.iloc[0] == 3.0
    assert pd.isna(result.iloc[1])
    assert result.index.equals(target)


def test_provider_reuses_sp500_daily_download_for_signals_and_breadth(monkeypatch):
    symbols = [f"S{i:03}" for i in range(100)]
    days = pd.date_range("2025-01-01", periods=201, freq="D")
    bars = pd.DatetimeIndex(["2026-01-01 15:00:00+00:00"])
    daily_calls = 0

    def fake_download(requested, *, period, interval, fields):
        nonlocal daily_calls
        if interval == "1d":
            if requested != ["^VIX", "^VIX3M"]:
                daily_calls += 1
            return {s: pd.DataFrame({"Close": range(1, 202), "Volume": [1000] * 201}, index=days) for s in requested}
        if requested == ["^VIX", "^VIX3M"]:
            return {}
        return {s: pd.DataFrame({"Close": [250.0]}, index=bars) for s in requested}

    provider = SnapshotMarketData()
    monkeypatch.setattr(provider, "symbols", lambda universe: symbols)
    monkeypatch.setattr("scripts.market_snapshot_data._download_fields", fake_download)

    provider.compute_signals("sp500")
    result = provider.compute_breadth()

    assert daily_calls == 1
    assert {"a20_n", "a50_n", "a200_n", "valid_20_n", "valid_50_n", "valid_200_n"} <= result["records"][0].keys()
    assert set(result["daily_close"]) == {"current", "previous"}


def test_provider_reports_sp500_fallback_source_and_error(monkeypatch):
    monkeypatch.setattr("scripts.market_snapshot_data.get_sp500", lambda: (_ for _ in ()).throw(RuntimeError("SPDR unavailable")))
    monkeypatch.setattr("scripts.market_snapshot_data._wikipedia_symbols", lambda universe: ["AAPL"])
    provider = SnapshotMarketData()

    assert provider.symbols("sp500") == ["AAPL"]
    assert provider._universe_meta["sp500"] == {
        "universe_source": "fallback_sp500_wikipedia",
        "universe_warning": "Primary SPY holdings source failed; using Wikipedia.",
        "universe_error": "SPDR unavailable",
    }


def test_daily_close_uses_daily_only_ticker_and_aligns_daily_ntss():
    symbols = [f"S{i:03}" for i in range(101)]
    days = pd.date_range("2026-01-01", periods=2, freq="D")
    daily = pd.DataFrame([[100.0] * 101, [110.0] * 101], index=days, columns=symbols)
    daily.iloc[-1, -1] = 90.0
    ntss = pd.Series([2.5], index=pd.DatetimeIndex(["2026-01-02"]))

    payload = daily_close_payload(daily, denominator=101, ntss=ntss)

    assert payload["current"]["valid_20_n"] == 101
    assert payload["current"]["a20_n"] == 100
    assert payload["current"]["mid"] == 2.5


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
                    "mid": 1.25,
                    "mom": 4.5,
                    "phase_code": "B",
                }
            ],
            "n_stocks": 500,
            "n_valid_hourly": 497,
            "raw_prices": {"AAPL": [100, 101]},
        }


@pytest.mark.parametrize(
    ("phase", "expected_phase", "strong", "breakdown", "ntss", "signal", "label", "action"),
    [
        ("A", "全面牛市", 60.0, 10.0, 2.0, "long", "多头窗口", "多头优先：使用 ADV Top10 → MA200 Top3。"),
        ("B", "强势整固", 45.0, 20.0, -1.0, "long", "多头窗口", "多头优先：使用 ADV Top10 → MA200 Top3。"),
        # Numeric long precedence wins even if an inconsistent phase says G.
        ("G", "宽度承压", 15.0, 30.0, -1.0, "long", "多头窗口", "多头优先：使用 ADV Top10 → MA200 Top3。"),
        ("G", "宽度承压", 15.0, 55.0, 1.0, "short", "空头保险", "Risk Off 环境：若处于空仓期并满足 Gap Short，执行 QQQ/SPY 70% + 弱股 30%。"),
        ("H", "恐慌出清", 10.0, 60.0, 1.0, "short", "空头保险", "Risk Off 环境：若处于空仓期并满足 Gap Short，执行 QQQ/SPY 70% + 弱股 30%。"),
        # Negative NTSS takes precedence over the breakdown watch threshold.
        ("E", "震荡整理", 25.0, 40.0, -0.1, "short", "空头保险", "Risk Off 环境：若处于空仓期并满足 Gap Short，执行 QQQ/SPY 70% + 弱股 30%。"),
        ("E", "震荡整理", 25.0, 40.0, 1.0, "short_watch", "空头雷达", "Trail/B 类只作早期裂缝雷达，小仓位或待命，不当作稳定收益来源。"),
        ("D", "修复中", 30.0, None, 1.0, "watch", "观察", "等待 MVS 多头或 Gap Short 触发。"),
    ],
)
def test_market_status_uses_established_phase_and_numeric_signal_precedence(
    phase, expected_phase, strong, breakdown, ntss, signal, label, action
):
    status = _market_status({
        "t": "2026-07-11T10:00:00Z", "phase_code": phase,
        "s": strong, "bd": breakdown, "mid": ntss, "mom": 2.0,
    })

    assert status["phase"] == expected_phase
    assert status["signal"] == signal
    assert status["label"] == label
    assert status["action"] == action
    assert status["short_type"] == {
        "short": "Risk Off", "short_watch": "Trail Exhaustion",
    }.get(signal)


@pytest.mark.parametrize("code,name", [
    ("A", "全面牛市"), ("B", "强势整固"), ("C", "牛市回调"), ("D", "修复中"),
    ("E", "震荡整理"), ("F", "弱势未崩"), ("G", "宽度承压"), ("H", "恐慌出清"),
])
def test_market_status_preserves_all_established_phase_labels(code, name):
    assert _market_status({"phase_code": code, "bd": None, "mid": 1})["phase"] == name


def test_run_computes_each_market_once_and_publishes_compact_snapshots(tmp_path):
    provider = FakeProvider()
    generated_at = datetime(2026, 7, 11, 14, 0, tzinfo=timezone.utc)

    dashboard, breadth = run(tmp_path, provider=provider, generated_at=generated_at)

    assert provider.signal_calls == ["nasdaq100", "sp500"]
    assert provider.breadth_calls == 1
    assert dashboard["market_status"] == {
        "phase_code": "B",
        "as_of": "2026-07-11T09:30:00-04:00",
        "strong": 51.0,
        "breakdown": 22.0,
        "ntss": 1.25,
        "momentum": 4.5,
        "phase": "强势整固",
        "signal": "long",
        "label": "多头窗口",
        "phase_class": "safe", "short_type": None,
        "ntss_state": "CAUTION", "ntss_class": "caution",
        "action": "多头优先：使用 ADV Top10 → MA200 Top3。",
        "basis": "NTSS = VIX3M - VIX; positive=calm, negative=panic",
    }
    assert dashboard["quality"] == {
        "nasdaq100": {"valid_count": 99, "failed_count": 2},
        "sp500": {"valid_count": 498, "failed_count": 2},
        "session_status": "closed",
        "fresh_until": "2026-07-13T14:00:00+00:00",
    }
    assert breadth["quality"] == {
        "expected_count": 500,
        "valid_count": 497,
        "failed_count": 3,
        "session_status": "closed",
        "fresh_until": "2026-07-13T14:00:00+00:00",
    }
    assert breadth["records"] == [
        {
            "t": "2026-07-11T09:30:00-04:00",
            "s": 51.0,
            "bd": 22.0,
            "mid": 1.25,
            "mom": 4.5,
            "phase_code": "B",
        }
    ]
    for name in ("dashboard_snapshot.json", "breadth_15m.json"):
        payload = json.loads((tmp_path / name).read_text(encoding="utf-8"))
        assert "raw_prices" not in json.dumps(payload)
    assert dashboard["generation_id"] == breadth["generation_id"]


def test_publish_pair_rolls_back_first_file_when_second_replace_fails(tmp_path, monkeypatch):
    from scripts.build_dashboard_snapshots import _publish_pair

    first = tmp_path / "dashboard_snapshot.json"
    second = tmp_path / "breadth_15m.json"
    first.write_text('{"old":1}', encoding="utf-8")
    second.write_text('{"old":2}', encoding="utf-8")
    original_replace = type(first).replace
    calls = 0

    def fail_second(self, target):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("second replace failed")
        return original_replace(self, target)

    monkeypatch.setattr(type(first), "replace", fail_second)
    with pytest.raises(OSError, match="second replace"):
        _publish_pair(tmp_path, {first.name: {"new": 1}, second.name: {"new": 2}})

    assert json.loads(first.read_text()) == {"old": 1}
    assert json.loads(second.read_text()) == {"old": 2}


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
