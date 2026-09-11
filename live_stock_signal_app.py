#!/usr/bin/env python3
"""Display-only MVS dashboard backed by precomputed JSON snapshots."""

from __future__ import annotations

import copy
import json
import math
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

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
    strategy = payload.get("strategy")
    if strategy is not None:
        if not isinstance(strategy, dict):
            raise SnapshotUnavailable("dashboard: strategy must be object")
        strategy_fields = {
            "strategy_id": str,
            "selection_mode": str,
            "gross_exposure_pct": (int, float),
            "reference_account_usd": (int, float),
        }
        for field, expected in strategy_fields.items():
            if not isinstance(strategy.get(field), expected) or isinstance(strategy.get(field), bool):
                label = expected.__name__ if isinstance(expected, type) else "number"
                raise SnapshotUnavailable(f"dashboard: strategy.{field} must be {label}")
        if strategy["selection_mode"] not in {"regular_long", "dip_long_proxy", "regular_long_hold", "dip_long_hold", "cash"}:
            raise SnapshotUnavailable("dashboard: strategy.selection_mode is invalid")
    fields = {"symbol": str, "universe": str, "rank": int, "target_weight_pct": (int, float)}
    for index, target in enumerate(targets):
        if not isinstance(target, dict):
            raise SnapshotUnavailable(f"dashboard: buy_targets[{index}] must be object")
        for field, expected in fields.items():
            if not isinstance(target.get(field), expected) or isinstance(target.get(field), bool):
                label = expected.__name__ if isinstance(expected, type) else "number"
                raise SnapshotUnavailable(f"dashboard: buy_targets[{index}].{field} must be {label}")
        if not re.fullmatch(r"[A-Z][A-Z0-9.-]{0,9}", target["symbol"]):
            raise SnapshotUnavailable(f"dashboard: buy_targets[{index}].symbol is not a safe ticker")
        if target["universe"] not in {"nasdaq100", "sp500"}:
            raise SnapshotUnavailable(f"dashboard: buy_targets[{index}].universe is invalid")
        if target["rank"] <= 0:
            raise SnapshotUnavailable(f"dashboard: buy_targets[{index}].rank must be positive")
        if strategy is not None:
            for field in ("liquidity_leg_weight_pct", "trend_leg_weight_pct"):
                value = target.get(field)
                if not isinstance(value, (int, float)) or isinstance(value, bool):
                    raise SnapshotUnavailable(
                        f"dashboard: buy_targets[{index}].{field} must be number"
                    )
            sleeve_total = target["liquidity_leg_weight_pct"] + target["trend_leg_weight_pct"]
            if abs(sleeve_total - target["target_weight_pct"]) > 0.01:
                raise SnapshotUnavailable(
                    f"dashboard: buy_targets[{index}].target_weight_pct must equal sleeve weights"
                )
    if strategy is not None:
        target_total = sum(float(target["target_weight_pct"]) for target in targets)
        if abs(target_total - float(strategy["gross_exposure_pct"])) > 0.01:
            raise SnapshotUnavailable(
                "dashboard: strategy.gross_exposure_pct must equal buy target weights"
            )


def _validate_breadth(payload: dict[str, Any]) -> None:
    _require(payload, "quality", dict, "breadth")
    records = _require(payload, "records", list, "breadth")
    numeric_fields = {"s", "bd", "mid", "mom", "ntss", "a20", "a50", "a200"}
    for index, record in enumerate(records):
        if not isinstance(record, dict) or not isinstance(record.get("t"), str):
            raise SnapshotUnavailable(f"breadth: record {index} must be object with string t")
        try:
            timestamp = datetime.fromisoformat(record["t"].replace("Z", "+00:00"))
        except ValueError as exc:
            raise SnapshotUnavailable(f"breadth: record {index}.t must be ISO timestamp") from exc
        if timestamp.tzinfo is None or timestamp.utcoffset() is None:
            raise SnapshotUnavailable(f"breadth: record {index}.t must include timezone")
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
        payload = json.loads(
            path.read_text(encoding="utf-8"),
            parse_constant=lambda value: (_ for _ in ()).throw(
                SnapshotUnavailable(f"{name}: numeric value {value} is not finite")
            ),
        )
    except (OSError, json.JSONDecodeError) as exc:
        raise SnapshotUnavailable(f"{name}: invalid JSON snapshot: {exc}") from exc
    if not isinstance(payload, dict):
        raise SnapshotUnavailable(f"{name}: snapshot root must be an object")
    schema_version = payload.get("schema_version")
    if type(schema_version) is not int or schema_version != SNAPSHOT_SCHEMA_VERSION:
        raise SnapshotUnavailable(
            f"{name}: incompatible schema_version {schema_version!r}; expected integer 1"
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
    if parsed.astimezone(timezone.utc) > datetime.now(timezone.utc) + timedelta(minutes=5):
        raise SnapshotUnavailable(f"{name}: generated_at is implausibly far in the future")
    _validate_provenance(payload, name)
    (_validate_dashboard if name == "dashboard" else _validate_breadth)(payload)
    _validate_quality(payload["quality"], name)
    _require_finite_numbers(payload, name)
    _snapshot_cache[path] = (*cache_key, payload)
    return copy.deepcopy(payload)


def _validate_provenance(payload: dict[str, Any], name: str) -> None:
    provenance = _require(payload, "provenance", dict, name)
    for field in ("builder_name", "market_data_provider", "price_adjustment"):
        value = provenance.get(field)
        if not isinstance(value, str) or not value:
            raise SnapshotUnavailable(f"{name}: provenance.{field} must be nonempty string")
    if type(provenance.get("builder_schema_version")) is not int:
        raise SnapshotUnavailable(
            f"{name}: provenance.builder_schema_version must be integer"
        )
    intervals = provenance.get("intervals")
    if not isinstance(intervals, dict) or not all(
        isinstance(key, str) and isinstance(value, str)
        for key, value in intervals.items()
    ):
        raise SnapshotUnavailable(f"{name}: provenance.intervals must be string map")


def _snapshot_pair() -> dict[str, dict[str, Any]]:
    pair = {
        name: _decode_snapshot(DATA_DIR / filename, name)
        for name, filename in _SNAPSHOT_FILES.items()
    }
    if len({payload["generation_id"] for payload in pair.values()}) != 1:
        raise SnapshotUnavailable("snapshot generation mismatch; refresh both artifacts together")
    if pair["dashboard"]["provenance"] != pair["breadth"]["provenance"]:
        raise SnapshotUnavailable("snapshot provenance mismatch; refresh both artifacts together")
    return pair


def _validate_quality(quality: dict[str, Any], name: str) -> None:
    fresh_until = _require(quality, "fresh_until", str, f"{name}.quality")
    session_status = _require(quality, "session_status", str, f"{name}.quality")
    if session_status not in {"open", "closed"}:
        raise SnapshotUnavailable(f"{name}.quality: session_status must be open or closed")
    try:
        deadline = datetime.fromisoformat(fresh_until.replace("Z", "+00:00"))
    except ValueError as exc:
        raise SnapshotUnavailable(f"{name}.quality: fresh_until is not ISO-8601") from exc
    if deadline.tzinfo is None:
        raise SnapshotUnavailable(f"{name}.quality: fresh_until must include a timezone")


def _require_finite_numbers(value: Any, path: str) -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise SnapshotUnavailable(f"{path}: numeric value must be finite")
    if isinstance(value, dict):
        for key, child in value.items():
            _require_finite_numbers(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _require_finite_numbers(child, f"{path}[{index}]")


def _is_stale(payload: dict[str, Any], now: datetime | None = None) -> bool:
    fresh_until = datetime.fromisoformat(payload["quality"]["fresh_until"].replace("Z", "+00:00"))
    return (now or datetime.now(timezone.utc)).astimezone(timezone.utc) > fresh_until.astimezone(timezone.utc)


def load_snapshot(name: str) -> dict[str, Any]:
    if name not in _SNAPSHOT_FILES:
        raise SnapshotUnavailable(f"unknown snapshot {name!r}")
    payload = _snapshot_pair()[name]
    payload["stale"] = _is_stale(payload)
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
