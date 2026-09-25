"""Historical context for the current breadth reading.

Matches the live Strong / Breakdown / NTSS reading against the daily
TradingView breadth history (``data/breadth_history_daily.csv``, SP500
breadth with QQQ prices) and reports what QQQ did afterwards.  Purely
descriptive: nothing here feeds the trade ledger.

Bucket edges are fixed in advance (NTSS uses the same 0 / 2 cut-offs as the
dashboard badge) so the table cannot be tuned to the current reading.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Mapping

import numpy as np
import pandas as pd

HISTORY_FILE = "breadth_history_daily.csv"
NEIGHBOUR_WIDTH = 5.0          # +/- points for "similar" Strong and Breakdown
EVENT_GAP = 20                 # trading days separating independent episodes
MIN_EVENTS = 5                 # fewer independent episodes -> flagged as thin
HORIZONS = (20, 60)
RISK_OFF_BREAKDOWN = 50.0      # Pine: breakdown > breankdown_limit2
RISK_OFF_MOMENTUM = -5.0       # Pine: net_momentum <= short_trigger
DD_BUCKETS = ((-0.02, "距52周高点 2% 以内"), (-0.06, "距52周高点 2–6%"),
              (-0.15, "距52周高点 6–15%"), (-math.inf, "距52周高点超过 15%"))


def load_history(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path, parse_dates=["date"]).set_index("date").sort_index()
    return frame[~frame.index.duplicated(keep="last")]


def pine_components(a20: float, a50: float, a200: float) -> dict[str, float]:
    """Strong / Pullback / Recovery / Breakdown exactly as the Pine strategy defines them."""
    return {
        "strong": min(a20, a50, a200),
        "pullback": max(0.0, a200 - a50),
        "recovery": max(0.0, a20 - a50),
        "breakdown": 100.0 - max(a20, a50, a200),
    }


def pine_net_momentum(current: Mapping[str, float], previous: Mapping[str, float]) -> float:
    up = lambda key: max(0.0, current[key] - previous[key])
    return (up("strong") + up("recovery")) - (up("pullback") + up("breakdown"))


def _num(value: Any) -> float | None:
    if value is None:
        return None
    value = float(value)
    return round(value, 2) if math.isfinite(value) else None


def _dd_bucket(dd: float) -> tuple[float, float, str]:
    upper = math.inf
    for lower, label in DD_BUCKETS:
        if dd >= lower:
            return lower, upper, label
        upper = lower
    return -math.inf, DD_BUCKETS[-1][0], DD_BUCKETS[-1][1]


def _ntss_bucket(mid: float) -> tuple[float, float, str]:
    if mid < 0:
        return -math.inf, 0.0, "NTSS < 0（PANIC）"
    if mid < 2:
        return 0.0, 2.0, "NTSS 0–2（CAUTION）"
    return 2.0, math.inf, "NTSS ≥ 2（SAFE）"


def _prepare(history: pd.DataFrame) -> pd.DataFrame:
    frame = history.copy()
    close = frame["qqq"]
    frame["dd"] = close / close.rolling(252, min_periods=100).max() - 1
    frame["above_ma200"] = close > close.rolling(200).mean()
    for horizon in HORIZONS:
        frame[f"f{horizon}"] = close.shift(-horizon) / close - 1
    future_min = close[::-1].rolling(60, min_periods=60).min()[::-1].shift(-1)
    frame["mdd60"] = (future_min / close - 1).clip(upper=0)
    up = lambda col: frame[col].diff().clip(lower=0)
    frame["nm"] = (up("strong") + up("recovery")) - (up("pullback") + up("breakdown"))
    frame["zone"] = (frame["breakdown"] > frame["strong"]) & (frame["breakdown"] > RISK_OFF_BREAKDOWN)
    frame["risk_off"] = frame["zone"] & (frame["nm"] <= RISK_OFF_MOMENTUM)
    return frame


def _count_events(mask: pd.Series) -> int:
    positions = np.flatnonzero(mask.to_numpy())
    if not len(positions):
        return 0
    return int(1 + (np.diff(positions) > EVENT_GAP).sum())


def _episodes(frame: pd.DataFrame, mask: pd.Series) -> list[dict[str, Any]]:
    """First day of each independent episode, with what QQQ did afterwards."""
    positions = np.flatnonzero(mask.to_numpy())
    starts = [p for i, p in enumerate(positions) if i == 0 or p - positions[i - 1] > EVENT_GAP]
    return [
        {
            "date": frame.index[p].strftime("%Y-%m-%d"),
            "strong": _num(frame["strong"].iloc[p]),
            "breakdown": _num(frame["breakdown"].iloc[p]),
            "mid": _num(frame["mid"].iloc[p]),
            "f20": _num(frame["f20"].iloc[p] * 100),
            "f60": _num(frame["f60"].iloc[p] * 100),
            "mdd60": _num(frame["mdd60"].iloc[p] * 100),
        }
        for p in starts
    ]


def _row(frame: pd.DataFrame, mask: pd.Series, label: str, condition: str, *, episodic: bool = True) -> dict[str, Any]:
    sample = frame[mask].dropna(subset=["f60", "mdd60"])
    events = _count_events(mask & frame["f60"].notna()) if episodic else None
    row: dict[str, Any] = {
        "label": label,
        "condition": condition,
        "n_days": int(len(sample)),
        "n_events": events,
        "thin": episodic and events < MIN_EVENTS,
    }
    if episodic and _count_events(mask) <= 10:
        row["episodes"] = _episodes(frame, mask)
    if sample.empty:
        return row | {k: None for k in ("f20_mean", "f60_mean", "f60_median", "f60_neg_pct", "mdd60_median", "mdd60_le10_pct")}
    return row | {
        "f20_mean": _num(sample["f20"].mean() * 100),
        "f60_mean": _num(sample["f60"].mean() * 100),
        "f60_median": _num(sample["f60"].median() * 100),
        "f60_neg_pct": _num((sample["f60"] < 0).mean() * 100),
        "mdd60_median": _num(sample["mdd60"].median() * 100),
        "mdd60_le10_pct": _num((sample["mdd60"] <= -0.10).mean() * 100),
    }


def _risk_off_readiness(frame: pd.DataFrame, current: Mapping[str, float], net_momentum: float | None) -> dict[str, Any]:
    zone = current["breakdown"] > current["strong"] and current["breakdown"] > RISK_OFF_BREAKDOWN
    waiting = frame["zone"] & ~frame["risk_off"]
    trigger = frame["risk_off"].to_numpy()
    positions = np.flatnonzero(waiting.to_numpy())
    lags: list[float] = []
    for position in positions:
        ahead = np.flatnonzero(trigger[position + 1 : position + 21])
        lags.append(float(ahead[0] + 1) if len(ahead) else math.inf)
    lags_arr = np.array(lags)
    within = lambda days: _num((lags_arr <= days).mean() * 100) if len(lags_arr) else None
    return {
        "zone": bool(zone),
        "breakdown_gt_50": bool(current["breakdown"] > RISK_OFF_BREAKDOWN),
        "breakdown_gt_strong": bool(current["breakdown"] > current["strong"]),
        "net_momentum": _num(net_momentum),
        "momentum_trigger": RISK_OFF_MOMENTUM,
        "history_waiting_days": int(len(lags_arr)),
        "triggered_within_5d_pct": within(5),
        "triggered_within_10d_pct": within(10),
        "triggered_within_20d_pct": within(20),
    }


def analog_stats(history: pd.DataFrame, current: Mapping[str, Any]) -> dict[str, Any]:
    """Compare ``current`` (strong, breakdown, mid, qqq[, net_momentum]) with the history."""
    frame = _prepare(history)
    strong, breakdown, mid = float(current["strong"]), float(current["breakdown"]), float(current["mid"])
    closes = frame["qqq"].dropna()
    qqq = current.get("qqq")
    if qqq is not None and math.isfinite(float(qqq)) and float(qqq) > 0:
        closes = pd.concat([closes, pd.Series([float(qqq)])], ignore_index=True)
    dd_now = float(closes.iloc[-1] / closes.iloc[-252:].max() - 1)
    above_now = bool(closes.iloc[-1] > closes.iloc[-200:].mean())

    breadth = frame.dropna(subset=["strong", "breakdown"])
    ntss = frame["mid"].dropna()
    pct = lambda series, value: _num((series < value).mean() * 100)

    trend = frame["above_ma200"] == above_now
    similar = trend & ((frame["strong"] - strong).abs() <= NEIGHBOUR_WIDTH) & ((frame["breakdown"] - breakdown).abs() <= NEIGHBOUR_WIDTH)
    dd_lo, dd_hi, dd_label = _dd_bucket(dd_now)
    near = similar & (frame["dd"] >= dd_lo) & (frame["dd"] < dd_hi)
    nt_lo, nt_hi, nt_label = _ntss_bucket(mid)
    near_ntss = near & (frame["mid"] >= nt_lo) & (frame["mid"] < nt_hi)
    trend_label = "QQQ 在 MA200 之上" if above_now else "QQQ 在 MA200 之下"
    band = f"Strong {strong:.0f}±{NEIGHBOUR_WIDTH:.0f}、Breakdown {breakdown:.0f}±{NEIGHBOUR_WIDTH:.0f}"

    rows = [
        _row(frame, frame["qqq"].notna() & frame["strong"].notna(), "基准：全部交易日", "2007 年以来全部日线", episodic=False),
        _row(frame, trend & frame["strong"].notna(), "基准：同一趋势侧", trend_label, episodic=False),
        _row(frame, similar, "宽度相近", f"{trend_label}，{band}"),
        _row(frame, near, "宽度相近 + 位置相同", f"{dd_label}"),
        _row(frame, near_ntss, "宽度相近 + 位置相同 + NTSS 同档", nt_label),
    ]
    return {
        "history_start": breadth.index[0].strftime("%Y-%m-%d"),
        "history_end": frame.index[-1].strftime("%Y-%m-%d"),
        "current": {
            "strong": _num(strong),
            "breakdown": _num(breakdown),
            "mid": _num(mid),
            "qqq_drawdown_pct": _num(dd_now * 100),
            "above_ma200": above_now,
            "strong_percentile": pct(breadth["strong"], strong),
            "breakdown_percentile": pct(breadth["breakdown"], breakdown),
            "mid_percentile": pct(ntss, mid),
        },
        "rows": rows,
        "risk_off": _risk_off_readiness(frame, {"strong": strong, "breakdown": breakdown}, current.get("net_momentum")),
        "method": (
            "日线 SP500 宽度（TradingView S5TW/S5FI/S5TH）与 QQQ 收盘价；之后收益和回撤按 QQQ 计算。"
            f"独立事件按间隔超过 {EVENT_GAP} 个交易日分段；少于 {MIN_EVENTS} 个事件标记为样本不足。"
            "描述性统计，不构成交易信号。"
        ),
    }


def current_from_daily_close(daily_close: Mapping[str, Any] | None, latest: Mapping[str, Any] | None) -> dict[str, Any] | None:
    """Build the current reading in Pine terms from the snapshot's daily-close payload."""
    if not daily_close or not isinstance(daily_close.get("current"), Mapping):
        return None
    cur = daily_close["current"]
    try:
        comps = pine_components(float(cur["a20"]), float(cur["a50"]), float(cur["a200"]))
    except (KeyError, TypeError, ValueError):
        return None
    mid = cur.get("mid")
    if mid is None and latest is not None:
        mid = latest.get("mid")
    if mid is None or not math.isfinite(float(mid)):
        return None
    reading: dict[str, Any] = {**comps, "mid": float(mid), "qqq": (latest or {}).get("qqq"), "net_momentum": None}
    prev = daily_close.get("previous")
    if isinstance(prev, Mapping):
        try:
            prev_comps = pine_components(float(prev["a20"]), float(prev["a50"]), float(prev["a200"]))
            reading["net_momentum"] = pine_net_momentum(comps, prev_comps)
        except (KeyError, TypeError, ValueError):
            pass
    return reading


def build_analogs(data_dir: Path, daily_close: Mapping[str, Any] | None, latest: Mapping[str, Any] | None) -> dict[str, Any] | None:
    path = Path(data_dir) / HISTORY_FILE
    if not path.exists():
        return None
    current = current_from_daily_close(daily_close, latest)
    if current is None:
        return None
    return analog_stats(load_history(path), current)
