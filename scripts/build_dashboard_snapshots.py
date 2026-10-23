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
from zoneinfo import ZoneInfo


SCHEMA_VERSION = 1
WEIGHTS = (60, 20, 20)
MVS_GROSS_EXPOSURE = 1.15
MVS_SLEEVE_WEIGHT = 0.5
MVS_TREND_WEIGHTS = (0.60, 0.20, 0.20)
PROVENANCE = {
    "builder_name": "scripts.build_dashboard_snapshots",
    "builder_schema_version": SCHEMA_VERSION,
    "market_data_provider": "yfinance/Yahoo Finance",
    "price_adjustment": "unadjusted",
    "intervals": {"signals": "1d/2y", "breadth": "15m/5d + 1d/2y"},
}
MARKET_TZ = ZoneInfo("America/New_York")
# Pine strategy: risk_off = breakdown > strong and breakdown > breankdown_limit2
# and net_momentum <= short_trigger (pure breadth, no VIX/NTSS condition).
RISK_OFF_BREAKDOWN = 50.0
RISK_OFF_MOMENTUM = -5.0


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
    nasdaq_signals: Mapping[str, Any],
    market_status: Mapping[str, Any],
    *,
    position_state: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build one account-level NASDAQ-100 portfolio from the two MVS sleeves.

    The trade ledger decides whether the account is invested and which entry
    selector applies.  Market breadth labels remain observational and cannot
    silently open or close a position.
    """
    if position_state is None:
        is_invested = market_status.get("signal") == "long"
        entry_signal = "Dip Long" if market_status.get("phase_code") == "C" else "Long"
        ledger = {"position_state": "long" if is_invested else "flat"}
    else:
        ledger = dict(position_state)
        is_invested = ledger.get("position_state") == "long"
        entry_signal = str(ledger.get("entry_signal", "Long"))
    if not is_invested:
        selection_mode = "cash"
        mode_basis = "trade_ledger"
    elif entry_signal == "Dip Long":
        selection_mode = "dip_long_hold"
        mode_basis = "open_dip_entry"
    else:
        selection_mode = "regular_long_hold"
        mode_basis = "open_long_entry"

    configured_gross = round(MVS_GROSS_EXPOSURE * 100.0, 3)
    strategy = {
        "strategy_id": "mvs_dipadv10_pool15_lev115_v2",
        "evidence_status": "development",
        "universe": "nasdaq100",
        "selection_mode": selection_mode,
        "mode_basis": mode_basis,
        "position_state": "long" if is_invested else "flat",
        "configured_gross_exposure_pct": configured_gross,
        "gross_exposure_pct": 0.0,
        "reference_account_usd": 100000,
        "action_label": "继续持有" if is_invested else "保持空仓",
        "action": (
            "交易账本仍为 Long；继续持有最近一次月度复核组合。"
            "观察类宽度标签不触发清仓。"
            if is_invested
            else "交易账本为空仓；等待下一个有效 Long 或 Dip Long 入场事件。"
        ),
        "execution": (
            "Regular Long: next open; Dip Long: same close; "
            "monthly review: next open; Risk Off: next open"
        ),
    }
    for field in (
        "entry_signal",
        "signal_date",
        "execution_date",
        "selection_as_of",
        "source_as_of",
        "source_status",
        "source",
    ):
        if ledger.get(field) is not None:
            strategy[field] = ledger[field]
    if not is_invested:
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

    if selection_mode == "dip_long_hold":
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
            target[field] = round(float(target[field]), 4)
    rounded_total = sum(target["target_weight_pct"] for target in targets)
    rounding_residual = round(configured_gross - rounded_total, 4)
    if targets and rounding_residual:
        adjustment_target = next(
            (
                target
                for target in targets
                if target["liquidity_leg_weight_pct"]
                and not target["trend_leg_weight_pct"]
            ),
            next(
                (
                    target
                    for target in targets
                    if bool(target["liquidity_leg_weight_pct"])
                    != bool(target["trend_leg_weight_pct"])
                ),
                targets[-1],
            ),
        )
        adjustment_field = (
            "liquidity_leg_weight_pct"
            if adjustment_target["liquidity_leg_weight_pct"]
            else "trend_leg_weight_pct"
        )
        adjustment_target[adjustment_field] = round(
            adjustment_target[adjustment_field] + rounding_residual, 4
        )
        adjustment_target["target_weight_pct"] = round(
            adjustment_target["target_weight_pct"] + rounding_residual, 4
        )
    for target in targets:
        target["target_notional_per_100k_usd"] = round(
            target["target_weight_pct"] * 1000.0, 2
        )
    strategy["gross_exposure_pct"] = round(
        sum(target["target_weight_pct"] for target in targets), 2
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


BENCHMARK_KEYS = ("spy", "qqq", "rsp")


def backfill_benchmark_prices(
    records: list[dict[str, Any]],
    backfill: Mapping[str, Mapping[str, float]] | None,
) -> list[dict[str, Any]]:
    """Fill missing benchmark prices at exact instants from a longer provider window."""
    if not backfill:
        return records
    lookups = {
        key: {_aware_record_time({"t": stamp}): price for stamp, price in prices.items()}
        for key, prices in backfill.items()
        if key in BENCHMARK_KEYS and prices
    }
    for record in records:
        for key, prices in lookups.items():
            if record.get(key) is None:
                price = prices.get(_aware_record_time(record))
                if price is not None:
                    record[key] = price
    return records


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
            timestamp = _aware_record_time(copied)
            previous = merged.get(timestamp, {})
            for key in BENCHMARK_KEYS:
                if copied.get(key) is None and previous.get(key) is not None:
                    copied[key] = previous[key]
            merged[timestamp] = copied
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
    previous_closes = _previous_session_closes(record_list)
    for record in record_list:
        # Real aggregate rows carry numeric breadth fields.  Project the same
        # authoritative phase/action contract used by the homepage so clients
        # never need to duplicate trading semantics.
        if any(key in record for key in ("s", "bd", "mid", "mom")):
            previous_close = previous_closes.get(id(record))
            status = _market_status(record, previous_close)
            record.update({
                "nm": status.get("net_momentum_pine"),
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
    def compute_signals(self, universe: str, as_of: str | None = None) -> Mapping[str, Any]: ...

    def compute_breadth(self) -> Mapping[str, Any]: ...


def _json_bytes(payload: Any) -> bytes:
    return (json.dumps(payload, allow_nan=False, ensure_ascii=False, separators=(",", ":")) + "\n").encode()


def _load_position_state(output_dir: Path) -> dict[str, Any]:
    path = output_dir / "mvs_position_state.json"
    if not path.exists():
        return {"position_state": "flat", "state_source": "missing_ledger"}
    with path.open(encoding="utf-8") as source:
        state = json.load(source)
    if not isinstance(state, dict) or state.get("position_state") not in {"long", "flat"}:
        raise ValueError(f"{path}: position_state must be long or flat")
    return state


def _selection_cutoff(generated_at: datetime, position_state: Mapping[str, Any]) -> str:
    generated_day = generated_at.astimezone(timezone.utc).date()
    first_of_month = generated_day.replace(day=1)
    previous_month_end = first_of_month - timedelta(days=1)
    signal_date = datetime.fromisoformat(str(position_state["signal_date"])).date()
    return max(signal_date, previous_month_end).isoformat()


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


def _pine_components(record: Mapping[str, Any] | None) -> dict[str, float] | None:
    """Strong / Pullback / Recovery / Breakdown exactly as the Pine strategy defines them."""
    if record is None:
        return None
    try:
        a20, a50, a200 = (float(record[key]) for key in ("a20", "a50", "a200"))
    except (KeyError, TypeError, ValueError):
        return None
    return {
        "strong": min(a20, a50, a200),
        "pullback": max(0.0, a200 - a50),
        "recovery": max(0.0, a20 - a50),
        "breakdown": 100.0 - max(a20, a50, a200),
    }


def _pine_net_momentum(
    record: Mapping[str, Any], previous_close: Mapping[str, Any] | None
) -> float | None:
    """Pine net momentum versus the previous session close (positive increments only)."""
    current, previous = _pine_components(record), _pine_components(previous_close)
    if current is None or previous is None:
        return None
    up = lambda key: max(0.0, current[key] - previous[key])
    return (up("strong") + up("recovery")) - (up("pullback") + up("breakdown"))


def _market_date(record: Mapping[str, Any]) -> Any:
    return _aware_record_time(record).astimezone(MARKET_TZ).date()


def _previous_session_closes(records: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
    """Map each record to the last record of the preceding ET session."""
    result: dict[int, dict[str, Any]] = {}
    last_of_previous: dict[str, Any] | None = None
    last_seen: dict[str, Any] | None = None
    current_date = None
    for record in records:
        try:
            date = _market_date(record)
        except ValueError:
            continue
        if current_date is not None and date != current_date:
            last_of_previous = last_seen
        current_date = date
        if last_of_previous is not None:
            result[id(record)] = last_of_previous
        last_seen = record
    return result


def _market_status(
    record: Mapping[str, Any] | None,
    previous_close: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Project the latest breadth row into the dashboard's stable UI contract.

    ``previous_close`` is the prior session's closing breadth row; Pine Risk Off
    needs it for net momentum and is never assumed without it.
    """
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
    pine = _pine_components(record)
    pine_strong = pine["strong"] if pine else record.get("strong", record.get("s"))
    pine_breakdown = pine["breakdown"] if pine else breakdown
    net_momentum = _pine_net_momentum(record, previous_close)
    risk_off_zone = (
        pine_strong is not None and pine_breakdown is not None
        and pine_breakdown > pine_strong and pine_breakdown > RISK_OFF_BREAKDOWN
    )
    if breakdown is not None and breakdown < 35:
        signal, short_type, label = "long", None, "多头窗口"
        if phase_code == "C":
            action = "Phase C 牛市回调：使用 ADV Top3 流动性腿 + ADV Top10 等权 Dip 代理腿。"
        else:
            action = "多头窗口：使用 ADV Top3 流动性腿 + ADV Top15 → EMA200 Top3 趋势腿。"
    elif risk_off_zone and net_momentum is not None and net_momentum <= RISK_OFF_MOMENTUM:
        signal, short_type, label = "short", "Risk Off", "空头保险"
        action = "Risk Off 环境：若处于空仓期并满足 Gap Short，A 类只做 ADV Top30 MA200 最弱股 30%，不叠加 QQQ/SPY 70%。"
    elif risk_off_zone:
        signal, short_type, label = "short_watch", "Risk Off Pending", "Risk Off 待触发"
        nm = "—" if net_momentum is None else f"{net_momentum:.2f}"
        action = (
            f"Risk Off 待触发：Breakdown > 50 且 > Strong，净动量 {nm} 需 ≤ {RISK_OFF_MOMENTUM:.0f}"
            "（Pine 口径，对前一日收盘，以收盘为准）。"
        )
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
        "net_momentum_pine": None if net_momentum is None else round(net_momentum, 2),
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


def _breadth_analogs(
    data_dir: Path, daily_close: Mapping[str, Any] | None, latest: Mapping[str, Any] | None
) -> dict[str, Any] | None:
    """Historical context table; optional, so a failure never blocks a refresh."""
    try:
        try:
            from scripts.breadth_analogs import build_analogs
        except ModuleNotFoundError:
            from breadth_analogs import build_analogs
        return build_analogs(data_dir, daily_close, latest)
    except Exception as exc:  # noqa: BLE001 - descriptive add-on only
        print(f"breadth analogs unavailable: {exc!r}")
        return None


def run(
    output_dir: str | os.PathLike[str],
    *,
    provider: MarketDataProvider | None = None,
    generated_at: datetime | None = None,
    position_state: Mapping[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Compute and atomically publish the two compact dashboard artifacts."""
    if provider is None:
        provider = YFinanceMarketDataProvider()
    generated_at = generated_at or datetime.now(timezone.utc)
    freshness = snapshot_session_metadata(generated_at)
    output_path = Path(output_dir)
    ledger = dict(position_state) if position_state is not None else _load_position_state(output_path)
    signals = {
        universe: provider.compute_signals(universe)
        for universe in ("nasdaq100", "sp500")
    }
    portfolio_signals = signals["nasdaq100"]
    if ledger.get("position_state") == "long":
        cutoff = _selection_cutoff(generated_at, ledger)
        portfolio_signals = provider.compute_signals("nasdaq100", as_of=cutoff)
        ledger["selection_as_of"] = portfolio_signals.get("selection_as_of", cutoff)
    raw_breadth = provider.compute_breadth()
    breadth_records = backfill_benchmark_prices(
        merge_breadth_history(
            _existing_breadth_records(output_path),
            list(raw_breadth.get("records", [])),
        ),
        raw_breadth.get("benchmark_backfill"),
    )
    latest = breadth_records[-1] if breadth_records else None
    daily_close = raw_breadth.get("daily_close") or {}
    latest_previous_close = daily_close.get("previous") if isinstance(daily_close, Mapping) else None
    if latest_previous_close is None and latest is not None:
        latest_previous_close = _previous_session_closes(breadth_records).get(id(latest))
    market_status = _market_status(latest, latest_previous_close)
    portfolio = build_mvs_portfolio(
        portfolio_signals, market_status, position_state=ledger
    )
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
    if breadth["records"] and market_status:
        # Keep the latest row consistent with the homepage, which measures net
        # momentum against the authoritative previous daily close.
        breadth["records"][-1].update({
            "nm": market_status.get("net_momentum_pine"),
            "action": market_status.get("action"),
            "signal": market_status.get("signal"),
            "short_type": market_status.get("short_type"),
        })
    breadth["analogs"] = _breadth_analogs(output_path, breadth.get("daily_close"), latest)
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

    def compute_signals(self, universe: str, as_of: str | None = None) -> Mapping[str, Any]:
        return self._implementation.compute_signals(universe, as_of=as_of)

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
