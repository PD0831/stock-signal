"""Build and atomically persist the dashboard's small JSON snapshots."""

from __future__ import annotations

import json
import os
import tempfile
import argparse
import uuid
import calendar
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Protocol


SCHEMA_VERSION = 1
WEIGHTS = (60, 20, 20)
MVS_GROSS_EXPOSURE = 1.125
MVS_SLEEVE_WEIGHT = 0.5
MVS_TREND_WEIGHTS = (0.60, 0.20, 0.20)
PROVENANCE = {
    "builder_name": "scripts.build_dashboard_snapshots",
    "builder_schema_version": SCHEMA_VERSION,
    "market_data_provider": "yfinance/Yahoo Finance",
    "price_adjustment": "unadjusted",
    "intervals": {"signals": "1d/2y", "breadth": "15m/5d + 1d/2y"},
}


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


def build_mvs_portfolio(
    nasdaq_signals: Mapping[str, Any], market_status: Mapping[str, Any]
) -> dict[str, Any]:
    """Build one account-level NASDAQ-100 portfolio from the two MVS sleeves.

    Phase C is the dashboard's operational proxy for the backtest's explicit
    Dip Long event.  The proxy remains labelled as development evidence so it
    cannot be confused with the audited TradingView signal history.
    """
    is_long = market_status.get("signal") == "long"
    phase_code = market_status.get("phase_code")
    if not is_long:
        selection_mode = "cash"
        mode_basis = "mvs_risk_state"
    elif phase_code == "C":
        selection_mode = "dip_long_proxy"
        mode_basis = "phase_c_proxy"
    else:
        selection_mode = "regular_long"
        mode_basis = "mvs_long_state"

    configured_gross = round(MVS_GROSS_EXPOSURE * 100.0, 3)
    strategy = {
        "strategy_id": "mvs_dipadv10_pool15_v1",
        "evidence_status": "development",
        "universe": "nasdaq100",
        "selection_mode": selection_mode,
        "mode_basis": mode_basis,
        "configured_gross_exposure_pct": configured_gross,
        "gross_exposure_pct": 0.0,
        "reference_account_usd": 100000,
        "execution": (
            "Regular Long: next open; Phase C dip proxy: same close; "
            "monthly review: next open; Risk Off: next open"
        ),
    }
    if not is_long:
        return {"strategy": strategy, "buy_targets": []}

    adv_ranked = list(nasdaq_signals.get("adv_ranked", []))
    trend_selected = list(nasdaq_signals.get("ema200_selected", []))
    target_by_symbol: dict[str, dict[str, Any]] = {}

    def add_target(pick: Mapping[str, Any], field: str, weight_pct: float) -> None:
        symbol = str(pick.get("symbol", ""))
        if not symbol:
            return
        target = target_by_symbol.setdefault(
            symbol,
            {
                **pick,
                "symbol": symbol,
                "universe": "nasdaq100",
                "liquidity_leg_weight_pct": 0.0,
                "trend_leg_weight_pct": 0.0,
                "target_weight_pct": 0.0,
            },
        )
        for key, value in pick.items():
            if value is not None and key != "rank":
                target[key] = value
        target[field] += weight_pct
        target["target_weight_pct"] += weight_pct

    liquidity_weight = MVS_GROSS_EXPOSURE * MVS_SLEEVE_WEIGHT / 3.0 * 100.0
    for pick in adv_ranked[:3]:
        add_target(pick, "liquidity_leg_weight_pct", liquidity_weight)

    if selection_mode == "dip_long_proxy":
        dip_weight = MVS_GROSS_EXPOSURE * MVS_SLEEVE_WEIGHT / 10.0 * 100.0
        for pick in adv_ranked[:10]:
            add_target(pick, "trend_leg_weight_pct", dip_weight)
    else:
        for pick, sleeve_weight in zip(trend_selected[:3], MVS_TREND_WEIGHTS):
            weight = MVS_GROSS_EXPOSURE * MVS_SLEEVE_WEIGHT * sleeve_weight * 100.0
            add_target(pick, "trend_leg_weight_pct", weight)

    targets = sorted(
        target_by_symbol.values(),
        key=lambda target: (-target["target_weight_pct"], target["symbol"]),
    )
    for rank, target in enumerate(targets, 1):
        target["rank"] = rank
        for field in (
            "liquidity_leg_weight_pct",
            "trend_leg_weight_pct",
            "target_weight_pct",
        ):
            target[field] = round(float(target[field]), 3)
        target["target_notional_per_100k_usd"] = round(
            target["target_weight_pct"] * 1000.0, 2
        )
    strategy["gross_exposure_pct"] = round(
        sum(target["target_weight_pct"] for target in targets), 3
    )
    return {"strategy": strategy, "buy_targets": targets}


def build_dashboard_snapshot(
    picks: Mapping[str, Iterable[Mapping[str, Any]]],
    *,
    generated_at: datetime,
    market_status: Any = None,
    quality: Any = None,
    strategy: Mapping[str, Any] | None = None,
    buy_targets: Iterable[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Return the compact dashboard payload for picks from each universe."""
    targets = list(buy_targets) if buy_targets is not None else []
    if buy_targets is None:
        for universe, universe_picks in picks.items():
            universe_pick_list = list(universe_picks)
            if len(universe_pick_list) > len(WEIGHTS):
                raise ValueError(
                    f"{universe} has {len(universe_pick_list)} picks; "
                    f"at most {len(WEIGHTS)} are supported"
                )
            for pick, weight in zip(universe_pick_list, WEIGHTS):
                targets.append(
                    {
                        **pick,
                        "universe": universe,
                        "target_weight_pct": weight,
                    }
                )

    payload = {
        "schema_version": SCHEMA_VERSION,
        "provenance": deepcopy(PROVENANCE),
        "generated_at": _timestamp(generated_at),
        "market_status": market_status,
        "quality": quality,
        "buy_targets": targets,
    }
    if strategy is not None:
        payload["strategy"] = dict(strategy)
    return payload


def _phase(record: Mapping[str, Any]) -> Any:
    return record.get("phase_code", record.get("phase"))


def _aware_record_time(record: Mapping[str, Any]) -> datetime:
    raw = record.get("t")
    if not isinstance(raw, str):
        raise ValueError("breadth record timestamp must be timezone-aware ISO-8601")
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("breadth record timestamp must be timezone-aware ISO-8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("breadth record timestamp must be timezone-aware ISO-8601")
    return parsed


def _subtract_calendar_months(value: datetime, months: int) -> datetime:
    month_index = value.year * 12 + value.month - 1 - months
    year, month_zero = divmod(month_index, 12)
    month = month_zero + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return value.replace(year=year, month=month, day=day)


def merge_breadth_history(
    existing_records: list[dict[str, Any]],
    new_records: list[dict[str, Any]],
    *,
    months: int = 3,
) -> list[dict[str, Any]]:
    """Merge aggregate records, preferring new duplicates and retaining months."""
    if months <= 0:
        raise ValueError("months must be positive")
    merged: dict[datetime, dict[str, Any]] = {}
    for source in (existing_records, new_records):
        for original in source:
            copied = deepcopy(original)
            merged[_aware_record_time(copied)] = copied
    if not merged:
        return []
    latest = max(merged)
    cutoff = _subtract_calendar_months(latest, months).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    return [merged[key] for key in sorted(merged) if key >= cutoff]


def _existing_breadth_records(output_dir: Path) -> list[dict[str, Any]]:
    path = output_dir / "breadth_15m.json"
    if not path.exists():
        return []
    try:
        payload = json.loads(
            path.read_text(encoding="utf-8"),
            parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)),
        )
        if type(payload.get("schema_version")) is not int or payload["schema_version"] != SCHEMA_VERSION:
            return []
        if payload.get("provenance") != PROVENANCE or not isinstance(payload.get("records"), list):
            return []
        records = deepcopy(payload["records"])
        for record in records:
            if not isinstance(record, dict):
                return []
            _aware_record_time(record)
        return records
    except (OSError, ValueError, TypeError, AttributeError, json.JSONDecodeError):
        return []


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
        "provenance": deepcopy(PROVENANCE),
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
        if phase_code == "C":
            action = "Phase C 牛市回调：使用 ADV Top3 流动性腿 + ADV Top10 等权 Dip 代理腿。"
        else:
            action = "多头窗口：使用 ADV Top3 流动性腿 + ADV Top15 → EMA200 Top3 趋势腿。"
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
    output_path = Path(output_dir)
    breadth_records = merge_breadth_history(
        _existing_breadth_records(output_path),
        list(raw_breadth.get("records", [])),
    )
    latest = breadth_records[-1] if breadth_records else None
    market_status = _market_status(latest)
    portfolio = build_mvs_portfolio(signals["nasdaq100"], market_status)
    dashboard = build_dashboard_snapshot(
        {},
        generated_at=generated_at,
        market_status=market_status,
        quality={
            **{name: _quality(result) for name, result in signals.items()},
            **freshness,
        },
        strategy=portfolio["strategy"],
        buy_targets=portfolio["buy_targets"],
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
        output_path,
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
