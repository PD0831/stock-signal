"""Validate the two dashboard artifacts before publishing them."""

from __future__ import annotations

import json
import math
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

EXPECTED_SCHEMA_VERSION = 1
TICKER_PATTERN = re.compile(r"[A-Z][A-Z0-9.-]{0,9}")


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
    try:
        generated_at = datetime.fromisoformat(payload["generated_at"].replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{path}: generated_at must be ISO-8601") from exc
    if generated_at.tzinfo is None:
        raise ValueError(f"{path}: generated_at must include a timezone")
    if generated_at.astimezone(timezone.utc) > datetime.now(timezone.utc) + timedelta(minutes=5):
        raise ValueError(f"{path}: generated_at is implausibly far in the future")
    provenance = payload.get("provenance")
    if not isinstance(provenance, dict):
        raise ValueError(f"{path}: provenance must be dict")
    for field in ("builder_name", "market_data_provider", "price_adjustment"):
        if not isinstance(provenance.get(field), str) or not provenance[field]:
            raise ValueError(f"{path}: provenance.{field} must be a nonempty string")
    if type(provenance.get("builder_schema_version")) is not int:
        raise ValueError(f"{path}: provenance.builder_schema_version must be integer")
    intervals = provenance.get("intervals")
    if not isinstance(intervals, dict) or not all(
        isinstance(key, str) and isinstance(value, str)
        for key, value in intervals.items()
    ):
        raise ValueError(f"{path}: provenance.intervals must be a string map")


def _reject_non_finite(value: object, location: str) -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError(f"{location}: numeric value must be finite")
    if isinstance(value, dict):
        for key, child in value.items():
            _reject_non_finite(child, f"{location}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _reject_non_finite(child, f"{location}[{index}]")


def _validate_quality(quality: dict, path: Path) -> None:
    _require_type(quality, "fresh_until", str, path)
    if quality.get("session_status") not in {"open", "closed"}:
        raise ValueError(f"{path}: session_status must be open or closed")
    try:
        fresh_until = datetime.fromisoformat(quality["fresh_until"].replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{path}: fresh_until must be ISO-8601") from exc
    if fresh_until.tzinfo is None:
        raise ValueError(f"{path}: fresh_until must include a timezone")


def validate_snapshot_pair(dashboard_path: Path, breadth_path: Path) -> None:
    payloads = []
    for path in (dashboard_path, breadth_path):
        with path.open(encoding="utf-8") as source:
            payload = json.load(
                source,
                parse_constant=lambda value: (_ for _ in ()).throw(
                    ValueError(f"{path}: numeric value {value} is not finite")
                ),
            )
        if not isinstance(payload, dict):
            raise ValueError(f"{path}: artifact must be an object")
        _validate_core(payload, path)
        _reject_non_finite(payload, str(path))
        payloads.append(payload)

    dashboard, breadth = payloads
    _require_type(dashboard, "buy_targets", list, dashboard_path)
    _require_type(dashboard, "market_status", dict, dashboard_path)
    _require_type(dashboard, "quality", dict, dashboard_path)
    _validate_quality(dashboard["quality"], dashboard_path)
    strategy = dashboard.get("strategy")
    if strategy is not None:
        if not isinstance(strategy, dict):
            raise ValueError(f"{dashboard_path}: strategy must be an object")
        for field in ("strategy_id", "selection_mode"):
            if not isinstance(strategy.get(field), str) or not strategy[field]:
                raise ValueError(f"{dashboard_path}: strategy.{field} must be a nonempty string")
        for field in ("gross_exposure_pct", "reference_account_usd"):
            value = strategy.get(field)
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                raise ValueError(f"{dashboard_path}: strategy.{field} must be a number")
        if strategy["selection_mode"] not in {"regular_long", "dip_long_proxy", "regular_long_hold", "dip_long_hold", "cash"}:
            raise ValueError(f"{dashboard_path}: strategy.selection_mode is invalid")
    for index, target in enumerate(dashboard["buy_targets"]):
        if not isinstance(target, dict):
            raise ValueError(f"{dashboard_path}: buy_targets[{index}] must be an object")
        symbol = target.get("symbol")
        if not isinstance(symbol, str) or TICKER_PATTERN.fullmatch(symbol) is None:
            raise ValueError(f"{dashboard_path}: buy_targets[{index}].symbol is invalid")
        if target.get("universe") not in {"nasdaq100", "sp500"}:
            raise ValueError(f"{dashboard_path}: buy_targets[{index}].universe is invalid")
        rank = target.get("rank")
        if type(rank) is not int or rank <= 0:
            raise ValueError(f"{dashboard_path}: buy_targets[{index}].rank must be a positive integer")
        weight = target.get("target_weight_pct")
        if not isinstance(weight, (int, float)) or isinstance(weight, bool):
            raise ValueError(
                f"{dashboard_path}: buy_targets[{index}].target_weight_pct must be a number"
            )
        if strategy is not None:
            for field in ("liquidity_leg_weight_pct", "trend_leg_weight_pct"):
                value = target.get(field)
                if not isinstance(value, (int, float)) or isinstance(value, bool):
                    raise ValueError(
                        f"{dashboard_path}: buy_targets[{index}].{field} must be a number"
                    )
            sleeve_total = target["liquidity_leg_weight_pct"] + target["trend_leg_weight_pct"]
            if abs(sleeve_total - target["target_weight_pct"]) > 0.01:
                raise ValueError(
                    f"{dashboard_path}: buy_targets[{index}].target_weight_pct must equal sleeve weights"
                )
    if strategy is not None:
        target_total = sum(float(target["target_weight_pct"]) for target in dashboard["buy_targets"])
        if abs(target_total - float(strategy["gross_exposure_pct"])) > 0.01:
            raise ValueError(
                f"{dashboard_path}: strategy.gross_exposure_pct must equal buy target weights"
            )
    _require_type(breadth, "records", list, breadth_path)
    _require_type(breadth, "quality", dict, breadth_path)
    _validate_quality(breadth["quality"], breadth_path)
    if "latest_transition" not in breadth or not (
        breadth["latest_transition"] is None
        or isinstance(breadth["latest_transition"], dict)
    ):
        raise ValueError(f"{breadth_path}: latest_transition must be null or dict")
    if dashboard["generation_id"] != breadth["generation_id"]:
        raise ValueError("snapshot generation_id values do not match")
    if dashboard["provenance"] != breadth["provenance"]:
        raise ValueError("snapshot provenance values do not match")


def main(argv: list[str] | None = None) -> None:
    args = argv if argv is not None else sys.argv[1:]
    if len(args) != 2:
        raise SystemExit("usage: validate_dashboard_snapshots.py DASHBOARD BREADTH")
    validate_snapshot_pair(Path(args[0]), Path(args[1]))


if __name__ == "__main__":
    main()
