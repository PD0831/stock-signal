from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf


@dataclass
class BreadthSnapshot:
    date: date
    s5th: float
    s5fi: float
    s5tw: float
    previous_s5th: float
    previous_s5fi: float
    previous_s5tw: float


def fetch_sp500_tickers() -> list[str]:
    import io
    import requests
    resp = requests.get(
        "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies",
        headers={"User-Agent": "Mozilla/5.0 (compatible; breadth-computer/1.0)"},
        timeout=15,
    )
    resp.raise_for_status()
    table = pd.read_html(io.StringIO(resp.text))[0]
    return table["Symbol"].str.replace(".", "-", regex=False).tolist()


def _load_state(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text())


def _save_state(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2))


def _compute_ema_from_series(closes: np.ndarray, period: int) -> float:
    k = 2.0 / (period + 1)
    ema = float(closes[0])
    for c in closes[1:]:
        ema = float(c) * k + ema * (1 - k)
    return ema


def _bootstrap(tickers: list[str], state: dict) -> dict:
    print(f"Bootstrapping EMA state for {len(tickers)} SP500 stocks (runs once, ~30s)...")
    df = yf.download(tickers, period="220d", interval="1d", auto_adjust=True, progress=False)["Close"]
    for ticker in df.columns:
        series = df[ticker].dropna()
        if len(series) < 200:
            continue
        closes = series.values.astype(float)
        state[ticker] = {
            "ema200": _compute_ema_from_series(closes, 200),
            "ema50": _compute_ema_from_series(closes, 50),
            "ema20": _compute_ema_from_series(closes, 20),
            "last_close": float(closes[-1]),
            "last_date": series.index[-1].date().isoformat(),
        }
    return state


def _needs_migration(state: dict) -> bool:
    for key, entry in state.items():
        if key == "_counts":
            continue
        if isinstance(entry, dict) and "ema5" in entry:
            return True
    return False


def _migrate_state(tickers: list[str], state: dict) -> dict:
    """Replace ema5 with ema20 by re-bootstrapping EMA20 from 60-day history."""
    print("Migrating EMA state: ema5 → ema20 (one-time, ~10s)…")
    df = yf.download(tickers, period="90d", interval="1d", auto_adjust=True, progress=False)["Close"]
    for ticker in df.columns:
        entry = state.get(ticker)
        if not isinstance(entry, dict) or "ema5" not in entry:
            continue
        series = df[ticker].dropna()
        if len(series) < 25:
            continue
        entry["ema20"] = _compute_ema_from_series(series.values.astype(float), 20)
        del entry["ema5"]
    return state


def _update_state(tickers: list[str], state: dict) -> dict:
    if _needs_migration(state):
        state = _migrate_state(tickers, state)

    df = yf.download(tickers, period="5d", interval="1d", auto_adjust=True, progress=False)["Close"]
    k200 = 2.0 / 201
    k50 = 2.0 / 51
    k20 = 2.0 / 21
    for ticker in df.columns:
        if ticker not in state:
            continue
        series = df[ticker].dropna()
        entry = state[ticker]
        if "ema20" not in entry:
            continue
        last = date.fromisoformat(entry["last_date"])
        for ts, close in series.items():
            day = ts.date() if hasattr(ts, "date") else ts
            if day <= last or pd.isna(close):
                continue
            c = float(close)
            entry["ema200"] = c * k200 + entry["ema200"] * (1 - k200)
            entry["ema50"] = c * k50 + entry["ema50"] * (1 - k50)
            entry["ema20"] = c * k20 + entry["ema20"] * (1 - k20)
            entry["last_close"] = c
            entry["last_date"] = day.isoformat()
    return state


def _count_breadth(state: dict) -> tuple[float, float, float]:
    above200 = above50 = above20 = total = 0
    for key, entry in state.items():
        if key == "_counts":
            continue
        if not isinstance(entry, dict) or "last_close" not in entry:
            continue
        total += 1
        c = entry["last_close"]
        if c > entry["ema200"]:
            above200 += 1
        if c > entry["ema50"]:
            above50 += 1
        if c > entry["ema20"]:
            above20 += 1
    if total == 0:
        return 0.0, 0.0, 0.0
    return above200 / total * 100, above50 / total * 100, above20 / total * 100


class BreadthComputer:
    def __init__(self, state_path: Path) -> None:
        self._path = state_path

    def update(self, as_of: date) -> BreadthSnapshot:
        tickers = fetch_sp500_tickers()
        state = _load_state(self._path)

        has_stock_entries = any(k != "_counts" for k in state)
        if not has_stock_entries:
            state = _bootstrap(tickers, state)
        else:
            state = _update_state(tickers, state)

        today_s5th, today_s5fi, today_s5tw = _count_breadth(state)

        counts = state.setdefault("_counts", {})
        today_key = as_of.isoformat()
        counts[today_key] = {"s5th": today_s5th, "s5fi": today_s5fi, "s5tw": today_s5tw}

        sorted_keys = sorted(counts.keys(), reverse=True)
        state["_counts"] = {k: counts[k] for k in sorted_keys[:2]}

        _save_state(self._path, state)

        prev_key = sorted_keys[1] if len(sorted_keys) >= 2 else today_key
        prev = state["_counts"].get(prev_key, state["_counts"][today_key])

        return BreadthSnapshot(
            date=as_of,
            s5th=today_s5th,
            s5fi=today_s5fi,
            s5tw=today_s5tw,
            previous_s5th=prev["s5th"],
            previous_s5fi=prev["s5fi"],
            previous_s5tw=prev["s5tw"],
        )
