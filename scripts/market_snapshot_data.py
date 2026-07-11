"""Standalone yfinance calculations used by the dashboard snapshot command."""

from __future__ import annotations

import gc
from io import StringIO
from typing import Any

import numpy as np
import pandas as pd
import requests
import yfinance as yf

try:
    from scripts.fetch_stock_data import get_sp500
except ModuleNotFoundError:
    from fetch_stock_data import get_sp500

NASDAQ100_URL = "https://en.wikipedia.org/wiki/List_of_NASDAQ-100_companies"
SP500_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
BATCH_SIZE = 50


def _normalise(value: object) -> str | None:
    if value is None or pd.isna(value):
        return None
    symbol = str(value).strip().upper().replace(".", "-")
    return symbol if symbol and symbol != "NAN" else None


def _wikipedia_symbols(universe: str) -> list[str]:
    url = NASDAQ100_URL if universe == "nasdaq100" else SP500_URL
    column = "Ticker" if universe == "nasdaq100" else "Symbol"
    response = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
    response.raise_for_status()
    for table in pd.read_html(StringIO(response.text)):
        if column in table.columns:
            symbols = sorted({s for s in table[column].map(_normalise) if s})
            if len(symbols) >= (80 if universe == "nasdaq100" else 400):
                return symbols
    raise RuntimeError(f"Could not load {universe} symbols")


def _field(frame: pd.DataFrame, symbol: str, field: str) -> pd.Series | None:
    try:
        if not isinstance(frame.columns, pd.MultiIndex):
            return frame[field] if field in frame else None
        level0 = {str(value) for value in frame.columns.get_level_values(0)}
        sub = frame[symbol] if symbol in level0 else frame.xs(symbol, axis=1, level=1)
        return sub[field] if field in sub else None
    except (KeyError, TypeError):
        return None


def _download_fields(symbols: list[str], *, period: str, interval: str, fields: tuple[str, ...]) -> dict[str, pd.DataFrame]:
    result: dict[str, pd.DataFrame] = {}
    for start in range(0, len(symbols), BATCH_SIZE):
        batch = symbols[start : start + BATCH_SIZE]
        raw = yf.download(batch, period=period, interval=interval, group_by="ticker", auto_adjust=False, progress=False, threads=True)
        for symbol in batch:
            columns = {field: _field(raw, symbol, field) for field in fields}
            if all(series is not None for series in columns.values()):
                result[symbol] = pd.DataFrame(columns).dropna(how="all").astype("float32")
        del raw
        gc.collect()
    return result


def _issuer_key(symbol: str) -> str:
    return {"GOOG": "GOOGL", "FOX": "FOXA", "NWS": "NWSA"}.get(symbol, symbol)


def _unique(rows: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    selected, seen = [], set()
    for row in rows:
        key = _issuer_key(row["symbol"])
        if key not in seen:
            selected.append(row)
            seen.add(key)
        if len(selected) == limit:
            break
    return selected


def _phase(strong: float | None, breakdown: float | None) -> str | None:
    if strong is None or breakdown is None:
        return None
    if strong > 55 and breakdown < 20: return "A"
    if strong > 40 and breakdown < 30: return "B"
    if strong > 35 and breakdown < 45: return "C"
    if strong > 25 and breakdown < 35: return "D"
    if strong > 20 and breakdown < 50: return "E"
    if strong < 20 and breakdown < 40: return "F"
    if strong < 30 and breakdown > 50: return "G"
    return "H"


def _ntss_series(histories: dict[str, pd.DataFrame]) -> pd.Series:
    if "^VIX" not in histories or "^VIX3M" not in histories:
        return pd.Series(dtype="float64")
    values = pd.concat(
        [
            histories["^VIX"]["Close"].rename("vix"),
            histories["^VIX3M"]["Close"].rename("vix3m"),
        ],
        axis=1,
    ).sort_index().ffill()
    return (values["vix3m"] - values["vix"]).round(3)


class SnapshotMarketData:
    def symbols(self, universe: str) -> list[str]:
        if universe == "sp500":
            try:
                return get_sp500()[0]
            except Exception:
                pass
        return _wikipedia_symbols(universe)

    def compute_signals(self, universe: str) -> dict[str, Any]:
        symbols = self.symbols(universe)
        history = _download_fields(symbols, period="18mo", interval="1d", fields=("Close", "Volume"))
        rows = []
        failed = set(symbols) - set(history)
        for symbol, frame in history.items():
            clean = frame.dropna(subset=["Close", "Volume"])
            if len(clean) < 63:
                failed.add(symbol)
                continue
            close = float(clean["Close"].iloc[-1])
            adv63 = float((clean["Close"].iloc[-63:] * clean["Volume"].iloc[-63:]).mean())
            ma200 = float(clean["Close"].iloc[-200:].mean()) if len(clean) >= 200 else None
            rows.append({"symbol": symbol, "close": round(close, 2), "adv63": adv63, "ma200": round(ma200, 2) if ma200 else None, "distance_pct": round((close / ma200 - 1) * 100, 2) if ma200 else None, "last_date": str(clean.index[-1].date())})
        rows.sort(key=lambda row: row["adv63"], reverse=True)
        for rank, row in enumerate(rows, 1): row["adv_rank"] = rank
        pool = _unique(rows, 10)
        ranked = sorted((row for row in pool if row["distance_pct"] is not None), key=lambda row: row["distance_pct"], reverse=True)
        picks = [{**row, "rank": rank} for rank, row in enumerate(ranked[:3], 1)]
        return {"universe": universe, "valid_count": len(rows), "failed_count": len(failed), "ma200_selected": picks}

    def compute_breadth(self) -> dict[str, Any]:
        symbols = self.symbols("sp500")
        daily = _download_fields(symbols, period="2y", interval="1d", fields=("Close",))
        intraday = _download_fields(symbols, period="5d", interval="15m", fields=("Close",))
        ntss = _ntss_series(
            _download_fields(["^VIX", "^VIX3M"], period="5d", interval="15m", fields=("Close",))
        )
        series = []
        for symbol in sorted(set(daily) & set(intraday)):
            closes = daily[symbol]["Close"].dropna()
            if closes.empty:
                continue
            refs = {window: float(closes.iloc[-window:].mean()) for window in (20, 50, 200)}
            frame = intraday[symbol]["Close"].rename(symbol).to_frame()
            for window, reference in refs.items(): frame[f"ma{window}"] = reference
            series.append(frame)
        if not series:
            raise RuntimeError("No valid 15-minute breadth data")
        index = sorted(set().union(*(frame.index for frame in series)))
        records = []
        previous = None
        for timestamp in index:
            flags = []
            for frame in series:
                if timestamp not in frame.index or pd.isna(frame.at[timestamp, frame.columns[0]]): continue
                close = float(frame.at[timestamp, frame.columns[0]])
                flags.append(tuple(close > float(frame.at[timestamp, f"ma{window}"]) for window in (20, 50, 200)))
            if not flags: continue
            percentages = [100 * sum(flag[i] for flag in flags) / len(symbols) for i in range(3)]
            strong, breakdown = min(percentages), 100 - max(percentages)
            pullback = min(percentages[1:]) - strong
            recovery = max(percentages) - max(percentages[:2])
            momentum = None
            if previous is not None:
                momentum = round(
                    (strong - previous[0]) + (recovery - previous[3])
                    - (pullback - previous[2]) - (breakdown - previous[1]),
                    3,
                )
            mid = None
            if not ntss.empty:
                nearest = ntss.reindex([timestamp], method="nearest", tolerance=pd.Timedelta("20min"))
                if not nearest.empty and not pd.isna(nearest.iloc[0]): mid = round(float(nearest.iloc[0]), 3)
            record = {"t": pd.Timestamp(timestamp).isoformat(), "s": round(strong, 2), "bd": round(breakdown, 2), "pb": round(pullback, 2), "rc": round(recovery, 2), "a20": round(percentages[0], 2), "a50": round(percentages[1], 2), "a200": round(percentages[2], 2), "mom": momentum, "mid": mid, "phase_code": _phase(strong, breakdown)}
            records.append(record)
            previous = (strong, breakdown, pullback, recovery)
        return {"records": records, "n_stocks": len(symbols), "n_valid_15m": len(series), "n_valid_hourly": len(series)}
