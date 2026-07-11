"""Validate the two dashboard artifacts before publishing them."""

from __future__ import annotations

import json
import sys
from pathlib import Path

EXPECTED_SCHEMA_VERSION = 1


def _require_type(payload: dict, field: str, expected_type: type, path: Path) -> None:
    if field not in payload or not isinstance(payload[field], expected_type):
        raise ValueError(f"{path}: {field} must be {expected_type.__name__}")


def _validate_core(payload: dict, path: Path) -> None:
    if type(payload.get("schema_version")) is not int or payload["schema_version"] != EXPECTED_SCHEMA_VERSION:
        raise ValueError(f"{path}: unexpected schema_version")
    generation_id = payload.get("generation_id")
    if not isinstance(generation_id, str) or not generation_id:
        raise ValueError(f"{path}: generation_id must be a nonempty string")
    _require_type(payload, "generated_at", str, path)


def validate_snapshot_pair(dashboard_path: Path, breadth_path: Path) -> None:
    payloads = []
    for path in (dashboard_path, breadth_path):
        with path.open(encoding="utf-8") as source:
            payload = json.load(source)
        if not isinstance(payload, dict):
            raise ValueError(f"{path}: artifact must be an object")
        _validate_core(payload, path)
        payloads.append(payload)

    dashboard, breadth = payloads
    _require_type(dashboard, "buy_targets", list, dashboard_path)
    _require_type(dashboard, "market_status", dict, dashboard_path)
    _require_type(dashboard, "quality", dict, dashboard_path)
    _require_type(breadth, "records", list, breadth_path)
    _require_type(breadth, "quality", dict, breadth_path)
    if "latest_transition" not in breadth or not (
        breadth["latest_transition"] is None
        or isinstance(breadth["latest_transition"], dict)
    ):
        raise ValueError(f"{breadth_path}: latest_transition must be null or dict")
    if dashboard["generation_id"] != breadth["generation_id"]:
        raise ValueError("snapshot generation_id values do not match")


def main(argv: list[str] | None = None) -> None:
    args = argv if argv is not None else sys.argv[1:]
    if len(args) != 2:
        raise SystemExit("usage: validate_dashboard_snapshots.py DASHBOARD BREADTH")
    validate_snapshot_pair(Path(args[0]), Path(args[1]))


if __name__ == "__main__":
    main()
