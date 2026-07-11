"""Build and atomically persist the dashboard's small JSON snapshots."""

from __future__ import annotations

import json
import os
import tempfile
import argparse
import uuid
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Protocol


SCHEMA_VERSION = 1
WEIGHTS = (60, 20, 20)


def snapshot_session_metadata(
    generated_at: datetime, *, calendar: Any = None
) -> dict[str, str]:
    """Describe when this artifact is next expected to be refreshed."""
    if generated_at.tzinfo is None:
        raise ValueError("generated_at must be timezone-aware")
    probe: Any = generated_at.astimezone(timezone.utc)
    if calendar is None:
        import exchange_calendars as xcals
        import pandas as pd

        calendar = xcals.get_calendar("XNYS")
        probe = pd.Timestamp(probe)
    is_open = bool(calendar.is_open_on_minute(probe))
    if is_open:
        candidate = generated_at.astimezone(timezone.utc) + timedelta(minutes=30)
        candidate_probe = type(probe)(candidate) if type(probe) is not datetime else candidate
        if calendar.is_open_on_minute(candidate_probe):
            fresh_until = candidate
        else:
            next_open = calendar.next_open(probe)
            if hasattr(next_open, "to_pydatetime"):
                next_open = next_open.to_pydatetime()
            fresh_until = next_open.astimezone(timezone.utc) + timedelta(minutes=30)
    else:
        next_open = calendar.next_open(probe)
        if hasattr(next_open, "to_pydatetime"):
            next_open = next_open.to_pydatetime()
        fresh_until = next_open.astimezone(timezone.utc) + timedelta(minutes=30)
    return {
        "session_status": "open" if is_open else "closed",
        "fresh_until": fresh_until.isoformat(),
    }


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
    for record in record_list:
        # Real aggregate rows carry numeric breadth fields.  Project the same
        # authoritative phase/action contract used by the homepage so clients
        # never need to duplicate trading semantics.
        if any(key in record for key in ("s", "bd", "mid", "mom")):
            status = _market_status(record)
            record.update({
                "phase_label": status.get("phase"),
                "action": status.get("action"),
                "signal": status.get("signal"),
                "short_type": status.get("short_type"),
            })
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
            if previous.get("phase_label") is not None:
                latest_transition["from_label"] = previous["phase_label"]
            if current.get("phase_label") is not None:
                latest_transition["to_label"] = current["phase_label"]

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


def _market_status(record: Mapping[str, Any] | None) -> dict[str, Any]:
    """Project the latest breadth row into the dashboard's stable UI contract."""
    if record is None:
        return {}
    phase_code = record.get("phase_code", record.get("phase"))
    phases = {
        "A": ("全面牛市", "safe"), "B": ("强势整固", "safe"),
        "C": ("牛市回调", "safe"), "D": ("修复中", "safe"),
        "E": ("震荡整理", "caution"), "F": ("弱势未崩", "caution"),
        "G": ("宽度承压", "panic"), "H": ("恐慌出清", "panic"),
    }
    breakdown = record.get("breakdown", record.get("bd"))
    ntss = record.get("ntss", record.get("mid"))
    if breakdown is not None and breakdown < 35:
        signal, short_type, label = "long", None, "多头窗口"
        action = "多头优先：使用 ADV Top10 → MA200 Top3。"
    elif (ntss is not None and ntss < 0) or phase_code in {"G", "H"}:
        signal, short_type, label = "short", "Risk Off", "空头保险"
        action = "Risk Off 环境：若处于空仓期并满足 Gap Short，执行 QQQ/SPY 70% + 弱股 30%。"
    elif breakdown is not None and breakdown >= 35:
        signal, short_type, label = "short_watch", "Trail Exhaustion", "空头雷达"
        action = "Trail/B 类只作早期裂缝雷达，小仓位或待命，不当作稳定收益来源。"
    else:
        signal, short_type, label = "watch", None, "观察"
        action = "等待 MVS 多头或 Gap Short 触发。"
    if ntss is None:
        ntss_state, ntss_class = "UNKNOWN", "wait"
    elif ntss < 0:
        ntss_state, ntss_class = "PANIC", "panic"
    elif ntss < 2:
        ntss_state, ntss_class = "CAUTION", "caution"
    else:
        ntss_state, ntss_class = "SAFE", "safe"
    phase, phase_class = phases.get(phase_code, (phase_code, "wait"))
    status = {
        "phase_code": phase_code,
        "phase": phase,
        "phase_class": phase_class,
        "signal": signal,
        "label": label,
        "short_type": short_type,
        "ntss_state": ntss_state,
        "ntss_class": ntss_class,
        "action": action,
        "basis": "NTSS = VIX3M - VIX; positive=calm, negative=panic",
        "as_of": record.get("t"),
    }
    aliases = {
        "strong": ("strong", "s"),
        "breakdown": ("breakdown", "bd"),
        "ntss": ("ntss", "mid"),
        "momentum": ("momentum", "mom"),
    }
    for target, names in aliases.items():
        for name in names:
            if record.get(name) is not None:
                status[target] = record[name]
                break
    return status


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
    freshness = snapshot_session_metadata(generated_at)
    signals = {
        universe: provider.compute_signals(universe)
        for universe in ("nasdaq100", "sp500")
    }
    raw_breadth = provider.compute_breadth()
    breadth_records = list(raw_breadth.get("records", []))
    latest = breadth_records[-1] if breadth_records else None
    market_status = _market_status(latest)
    dashboard = build_dashboard_snapshot(
        {name: result.get("ma200_selected", []) for name, result in signals.items()},
        generated_at=generated_at,
        market_status=market_status,
        quality={
            **{name: _quality(result) for name, result in signals.items()},
            **freshness,
        },
    )
    expected = int(raw_breadth.get("n_stocks", 0))
    valid = int(raw_breadth.get("n_valid_hourly", raw_breadth.get("n_valid_15m", 0)))
    breadth_quality = {
        "expected_count": expected,
        "valid_count": valid,
        "failed_count": max(expected - valid, 0),
        **freshness,
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
