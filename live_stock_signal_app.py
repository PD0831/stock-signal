#!/usr/bin/env python3
"""Display-only MVS dashboard backed by precomputed JSON snapshots."""

from __future__ import annotations

import copy
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse

from dashboard_html import BREADTH_HTML, SIGNALS_HTML, _NAV


SNAPSHOT_SCHEMA_VERSION = 1
DATA_DIR = Path(os.environ.get("DATA_DIR", "data"))
_SNAPSHOT_FILES = {"dashboard": "dashboard_snapshot.json", "breadth": "breadth_15m.json"}
_snapshot_cache: dict[Path, tuple[int, int, dict[str, Any]]] = {}


class SnapshotUnavailable(ValueError):
    """A public snapshot is missing, malformed, or inconsistent."""


def _require(payload: dict[str, Any], key: str, expected: type, name: str) -> Any:
    value = payload.get(key)
    if not isinstance(value, expected):
        raise SnapshotUnavailable(f"{name}: required field {key!r} must be {expected.__name__}")
    return value


def _validate_dashboard(payload: dict[str, Any]) -> None:
    _require(payload, "market_status", dict, "dashboard")
    _require(payload, "quality", dict, "dashboard")
    targets = _require(payload, "buy_targets", list, "dashboard")
    fields = {"symbol": str, "universe": str, "rank": int, "target_weight_pct": (int, float)}
    for index, target in enumerate(targets):
        if not isinstance(target, dict):
            raise SnapshotUnavailable(f"dashboard: buy_targets[{index}] must be object")
        for field, expected in fields.items():
            if not isinstance(target.get(field), expected) or isinstance(target.get(field), bool):
                label = expected.__name__ if isinstance(expected, type) else "number"
                raise SnapshotUnavailable(f"dashboard: buy_targets[{index}].{field} must be {label}")


def _validate_breadth(payload: dict[str, Any]) -> None:
    _require(payload, "quality", dict, "breadth")
    records = _require(payload, "records", list, "breadth")
    numeric_fields = {"s", "bd", "mid", "mom", "ntss", "a20", "a50", "a200"}
    for index, record in enumerate(records):
        if not isinstance(record, dict) or not isinstance(record.get("t"), str):
            raise SnapshotUnavailable(f"breadth: record {index} must be object with string t")
        for field in numeric_fields.intersection(record):
            value = record[field]
            if value is not None and (not isinstance(value, (int, float)) or isinstance(value, bool)):
                raise SnapshotUnavailable(f"breadth: record {index}.{field} must be number or null")
    transition = payload.get("latest_transition")
    if transition is not None and not isinstance(transition, dict):
        raise SnapshotUnavailable("breadth: latest_transition must be object or null")


def _decode_snapshot(path: Path, name: str) -> dict[str, Any]:
    try:
        stat = path.stat()
    except OSError as exc:
        raise SnapshotUnavailable(f"{name}: snapshot is unavailable: {exc}") from exc
    cache_key = (stat.st_mtime_ns, stat.st_size)
    cached = _snapshot_cache.get(path)
    if cached is not None and cached[:2] == cache_key:
        return copy.deepcopy(cached[2])
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SnapshotUnavailable(f"{name}: invalid JSON snapshot: {exc}") from exc
    if not isinstance(payload, dict):
        raise SnapshotUnavailable(f"{name}: snapshot root must be an object")
    if payload.get("schema_version") != SNAPSHOT_SCHEMA_VERSION:
        raise SnapshotUnavailable(
            f"{name}: incompatible schema_version {payload.get('schema_version')!r}; expected 1"
        )
    generation_id = _require(payload, "generation_id", str, name)
    if not generation_id:
        raise SnapshotUnavailable(f"{name}: generation_id must not be empty")
    generated_at = _require(payload, "generated_at", str, name)
    try:
        parsed = datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise SnapshotUnavailable(f"{name}: generated_at is not ISO-8601") from exc
    if parsed.tzinfo is None:
        raise SnapshotUnavailable(f"{name}: generated_at must include a timezone")
    (_validate_dashboard if name == "dashboard" else _validate_breadth)(payload)
    _snapshot_cache[path] = (*cache_key, payload)
    return copy.deepcopy(payload)


def _snapshot_pair() -> dict[str, dict[str, Any]]:
    pair = {
        name: _decode_snapshot(DATA_DIR / filename, name)
        for name, filename in _SNAPSHOT_FILES.items()
    }
    if len({payload["generation_id"] for payload in pair.values()}) != 1:
        raise SnapshotUnavailable("snapshot generation mismatch; refresh both artifacts together")
    return pair


def _is_stale(generated_at: str, now: datetime | None = None) -> bool:
    generated = datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
    current = (now or datetime.now(timezone.utc)).astimezone(ZoneInfo("America/New_York"))
    market_open = current.replace(hour=9, minute=30, second=0, microsecond=0)
    market_close = current.replace(hour=16, minute=0, second=0, microsecond=0)
    if current.weekday() < 5 and market_open <= current <= market_close:
        expected = current
    else:
        expected = market_close
        if current.weekday() < 5 and current < market_open:
            expected -= timedelta(days=1)
        while expected.weekday() >= 5:
            expected -= timedelta(days=1)
    return expected.astimezone(timezone.utc) - generated.astimezone(timezone.utc) > timedelta(minutes=30)


def load_snapshot(name: str) -> dict[str, Any]:
    if name not in _SNAPSHOT_FILES:
        raise SnapshotUnavailable(f"unknown snapshot {name!r}")
    payload = _snapshot_pair()[name]
    payload["stale"] = _is_stale(payload["generated_at"])
    return payload


app = FastAPI(title="MVS Dashboard")


@app.get("/", response_class=HTMLResponse)
def signals_page() -> str:
    return SIGNALS_HTML


@app.get("/breadth", response_class=HTMLResponse)
def breadth_page() -> str:
    return BREADTH_HTML


def _snapshot_response(name: str) -> JSONResponse:
    try:
        return JSONResponse(load_snapshot(name))
    except SnapshotUnavailable as exc:
        return JSONResponse({"available": False, "error": str(exc)}, status_code=503)


@app.get("/api/signals")
def signals_api() -> JSONResponse:
    return _snapshot_response("dashboard")


@app.get("/api/breadth")
def breadth_api() -> JSONResponse:
    return _snapshot_response("breadth")
