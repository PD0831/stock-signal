"""Validate the two dashboard artifacts before publishing them."""

from __future__ import annotations

import json
import sys
from pathlib import Path

EXPECTED_SCHEMA_VERSION = 1


def validate_snapshot_pair(dashboard_path: Path, breadth_path: Path) -> None:
    payloads = []
    for path in (dashboard_path, breadth_path):
        with path.open(encoding="utf-8") as source:
            payload = json.load(source)
        if payload.get("schema_version") != EXPECTED_SCHEMA_VERSION:
            raise ValueError(f"{path}: unexpected schema_version")
        if not payload.get("generation_id"):
            raise ValueError(f"{path}: missing generation_id")
        payloads.append(payload)
    if payloads[0]["generation_id"] != payloads[1]["generation_id"]:
        raise ValueError("snapshot generation_id values do not match")


def main(argv: list[str] | None = None) -> None:
    args = argv if argv is not None else sys.argv[1:]
    if len(args) != 2:
        raise SystemExit("usage: validate_dashboard_snapshots.py DASHBOARD BREADTH")
    validate_snapshot_pair(Path(args[0]), Path(args[1]))


if __name__ == "__main__":
    main()
