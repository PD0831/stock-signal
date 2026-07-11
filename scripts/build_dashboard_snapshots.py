"""Build and atomically persist the dashboard's small JSON snapshots."""

from __future__ import annotations

import json
import os
import tempfile
import argparse
import uuid
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Protocol


SCHEMA_VERSION = 1
WEIGHTS = (60, 20, 20)


def _timestamp(value: datetime) -> str:
    return value.isoformat()


def build_dashboard_snapshot(
    picks: Mapping[str, Iterable[Mapping[str, Any]]],
    *,
    generated_at: datetime,
    market_status: Any = None,
    quality: Any = None,
) -> dict[str, Any]:
    """Return the compact dashboard payload for picks from each universe."""
    buy_targets = []
    for universe, universe_picks in picks.items():
        universe_pick_list = list(universe_picks)
        if len(universe_pick_list) > len(WEIGHTS):
            raise ValueError(
                f"{universe} has {len(universe_pick_list)} picks; "
                f"at most {len(WEIGHTS)} are supported"
            )
        for pick, weight in zip(universe_pick_list, WEIGHTS):
            buy_targets.append(
                {
                    **pick,
                    "universe": universe,
                    "target_weight_pct": weight,
                }
            )

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": _timestamp(generated_at),
        "market_status": market_status,
        "quality": quality,
        "buy_targets": buy_targets,
    }


def _phase(record: Mapping[str, Any]) -> Any:
    return record.get("phase_code", record.get("phase"))


def build_breadth_snapshot(
    records: Iterable[Mapping[str, Any]],
    *,
    generated_at: datetime | None = None,
    quality: Any = None,
) -> dict[str, Any]:
    """Return breadth records plus the most recent adjacent phase change."""
    record_list = deepcopy(list(records))
    latest_transition = None
    for previous, current in zip(record_list, record_list[1:]):
        previous_phase = _phase(previous)
        current_phase = _phase(current)
        if previous_phase != current_phase:
            latest_transition = {
                "at": current["t"],
                "from": previous_phase,
                "to": current_phase,
            }

    if generated_at is None:
        generated_at = datetime.now(timezone.utc)

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": _timestamp(generated_at),
        "records": record_list,
        "quality": quality,
        "latest_transition": latest_transition,
    }


def write_json_atomic(path: str | os.PathLike[str], payload: Any) -> None:
    """Serialize strictly, then replace *path* with a complete sibling file."""
    serialized = json.dumps(
        payload, allow_nan=False, ensure_ascii=False, separators=(",", ":")
    ) + "\n"
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)

    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=destination.parent,
            prefix=f".{destination.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary.write(serialized)
            temporary.flush()
            os.fsync(temporary.fileno())
            temporary_path = Path(temporary.name)
        temporary_path.replace(destination)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()


class MarketDataProvider(Protocol):
    def compute_signals(self, universe: str) -> Mapping[str, Any]: ...

    def compute_breadth(self) -> Mapping[str, Any]: ...


def _json_bytes(payload: Any) -> bytes:
    return (json.dumps(payload, allow_nan=False, ensure_ascii=False, separators=(",", ":")) + "\n").encode()


def _publish_pair(output_dir: Path, payloads: Mapping[str, Any]) -> None:
    """Publish a validated pair, restoring both destinations on replace failure."""
    serialized = {name: _json_bytes(payload) for name, payload in payloads.items()}
    output_dir.mkdir(parents=True, exist_ok=True)
    previous = {
        name: (output_dir / name).read_bytes() if (output_dir / name).exists() else None
        for name in payloads
    }
    staged: dict[str, Path] = {}
    try:
        for name, body in serialized.items():
            with tempfile.NamedTemporaryFile(
                dir=output_dir, prefix=f".{name}.", suffix=".tmp", delete=False
            ) as handle:
                handle.write(body)
                handle.flush()
                os.fsync(handle.fileno())
                staged[name] = Path(handle.name)
        replaced: list[str] = []
        try:
            for name, temporary in staged.items():
                temporary.replace(output_dir / name)
                replaced.append(name)
        except Exception:
            for name in replaced:
                destination = output_dir / name
                old = previous[name]
                if old is None:
                    destination.unlink(missing_ok=True)
                else:
                    with tempfile.NamedTemporaryFile(
                        dir=output_dir, prefix=f".{name}.rollback.", delete=False
                    ) as handle:
                        handle.write(old)
                        rollback = Path(handle.name)
                    rollback.replace(destination)
            raise
    finally:
        for temporary in staged.values():
            temporary.unlink(missing_ok=True)


def _quality(signals: Mapping[str, Any]) -> dict[str, Any]:
    quality = {
        "valid_count": int(signals.get("valid_count", 0)),
        "failed_count": int(signals.get("failed_count", 0)),
    }
    for key in ("universe_source", "universe_warning", "universe_error"):
        if signals.get(key) is not None:
            quality[key] = signals[key]
    return quality


def run(
    output_dir: str | os.PathLike[str],
    *,
    provider: MarketDataProvider | None = None,
    generated_at: datetime | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Compute and atomically publish the two compact dashboard artifacts."""
    if provider is None:
        provider = YFinanceMarketDataProvider()
    generated_at = generated_at or datetime.now(timezone.utc)
    signals = {
        universe: provider.compute_signals(universe)
        for universe in ("nasdaq100", "sp500")
    }
    raw_breadth = provider.compute_breadth()
    breadth_records = list(raw_breadth.get("records", []))
    latest = breadth_records[-1] if breadth_records else None
    market_status = (
        {"phase_code": latest.get("phase_code"), "as_of": latest.get("t")}
        if latest is not None
        else None
    )
    dashboard = build_dashboard_snapshot(
        {name: result.get("ma200_selected", []) for name, result in signals.items()},
        generated_at=generated_at,
        market_status=market_status,
        quality={name: _quality(result) for name, result in signals.items()},
    )
    expected = int(raw_breadth.get("n_stocks", 0))
    valid = int(raw_breadth.get("n_valid_hourly", raw_breadth.get("n_valid_15m", 0)))
    breadth_quality = {
        "expected_count": expected,
        "valid_count": valid,
        "failed_count": max(expected - valid, 0),
    }
    for key in ("universe_source", "universe_warning", "universe_error"):
        if raw_breadth.get(key) is not None:
            breadth_quality[key] = raw_breadth[key]
    breadth = build_breadth_snapshot(
        breadth_records,
        generated_at=generated_at,
        quality=breadth_quality,
    )
    if raw_breadth.get("daily_close") is not None:
        breadth["daily_close"] = raw_breadth["daily_close"]
    generation_id = f"{generated_at.isoformat()}-{uuid.uuid4().hex[:12]}"
    dashboard["generation_id"] = generation_id
    breadth["generation_id"] = generation_id
    _publish_pair(
        Path(output_dir),
        {"dashboard_snapshot.json": dashboard, "breadth_15m.json": breadth},
    )
    return dashboard, breadth


class YFinanceMarketDataProvider:
    """Lazy adapter around standalone market calculations.

    Heavy dependencies are imported only for the snapshot command, keeping this
    module importable in lightweight validation and display environments.
    """

    def __init__(self) -> None:
        try:
            from scripts.market_snapshot_data import SnapshotMarketData
        except ModuleNotFoundError:
            from market_snapshot_data import SnapshotMarketData

        self._implementation = SnapshotMarketData()

    def compute_signals(self, universe: str) -> Mapping[str, Any]:
        return self._implementation.compute_signals(universe)

    def compute_breadth(self) -> Mapping[str, Any]:
        return self._implementation.compute_breadth()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("data"))
    args = parser.parse_args(argv)
    run(args.output_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
