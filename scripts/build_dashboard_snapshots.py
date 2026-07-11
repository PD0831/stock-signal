"""Build and atomically persist the dashboard's small JSON snapshots."""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping


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
        for pick, weight in zip(universe_picks, WEIGHTS):
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
    record_list = list(records)
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
    serialized = json.dumps(payload, allow_nan=False, ensure_ascii=False, indent=2) + "\n"
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
