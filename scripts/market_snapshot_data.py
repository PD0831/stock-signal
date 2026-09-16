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
BREADTH_MIN_STOCKS = 100
BREADTH_SMOOTH = 3


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


def attach_benchmark_prices(records: list[dict[str, Any]], histories: dict[str, pd.DataFrame]) -> list[dict[str, Any]]:
    """Join raw 15-minute closes at exact instants; missing bars stay missing."""
    prices = {}
    for symbol in ("SPY", "QQQ"):
        frame = histories.get(symbol)
        values = {}
        if frame is not None and "Close" in frame:
            for stamp, close in frame["Close"].items():
                stamp = pd.Timestamp(stamp)
                if stamp.tzinfo is not None and pd.notna(close) and np.isfinite(close) and close > 0:
                    values[stamp.tz_convert("UTC")] = round(float(close), 3)
        prices[symbol.lower()] = values
    return [{**row, **{key: values.get(pd.Timestamp(row["t"]).tz_convert("UTC"))
                      for key, values in prices.items()}} for row in records]


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


def _ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False, min_periods=1).mean()


def _daily_to_intraday_ref(daily_ma: pd.DataFrame, index: pd.DatetimeIndex) -> pd.DataFrame:
    daily_index = daily_ma.index
    if getattr(daily_index, "tz", None) is not None:
        daily_index = daily_index.tz_localize(None)
    normalised = daily_ma.copy()
    normalised.index = pd.DatetimeIndex(daily_index).normalize()
    bar_dates = pd.DatetimeIndex(
        [pd.Timestamp(ts.tz_localize(None) if ts.tzinfo else ts).normalize() for ts in index]
    )
    reference = normalised.reindex(bar_dates, method="ffill")
    reference.index = index
    return reference.ffill()


def _count_above(prices: pd.DataFrame, reference: pd.DataFrame, min_n: int) -> pd.Series:
    valid = prices.notna() & reference.notna()
    counts = ((prices > reference) & valid).sum(axis=1).astype(float)
    counts[valid.sum(axis=1) < min_n] = np.nan
    return counts


def _valid_count(prices: pd.DataFrame, reference: pd.DataFrame) -> pd.Series:
    return (prices.notna() & reference.notna()).sum(axis=1).astype(float)


def _pct_above(prices: pd.DataFrame, reference: pd.DataFrame, min_n: int, denominator: int | None) -> pd.Series:
    valid = prices.notna() & reference.notna()
    divisor = denominator if denominator and denominator > 0 else valid.sum(axis=1).clip(lower=1)
    result = ((prices > reference) & valid).sum(axis=1).astype(float) / divisor * 100
    result[valid.sum(axis=1) < min_n] = np.nan
    return result


def _calculate_breadth(daily: pd.DataFrame, intraday: pd.DataFrame, denominator: int | None = None) -> pd.DataFrame:
    common = daily.columns.intersection(intraday.columns)
    references = {
        window: _daily_to_intraday_ref(daily[common].rolling(window, min_periods=1).mean(), intraday.index)
        for window in (20, 50, 200)
    }
    prices = intraday[common]
    percentages = {
        window: _ema(_pct_above(prices, references[window], BREADTH_MIN_STOCKS, denominator), BREADTH_SMOOTH)
        for window in (20, 50, 200)
    }
    all_ma = pd.concat(list(percentages.values()), axis=1)
    short_ma = pd.concat([percentages[20], percentages[50]], axis=1)
    return pd.DataFrame({
        "above_20": percentages[20].round(2),
        "above_50": percentages[50].round(2),
        "above_200": percentages[200].round(2),
        "above_20_n": _count_above(prices, references[20], BREADTH_MIN_STOCKS),
        "above_50_n": _count_above(prices, references[50], BREADTH_MIN_STOCKS),
        "above_200_n": _count_above(prices, references[200], BREADTH_MIN_STOCKS),
        "valid_20_n": _valid_count(prices, references[20]),
        "valid_50_n": _valid_count(prices, references[50]),
        "valid_200_n": _valid_count(prices, references[200]),
        "strong": all_ma.min(axis=1).round(2),
        "breakdown": (100 - all_ma.max(axis=1)).round(2),
        "pullback": (short_ma.min(axis=1) - all_ma.min(axis=1)).round(2),
        "recovery": (all_ma.max(axis=1) - short_ma.max(axis=1)).round(2),
    }, index=intraday.index)


def _calc_momentum(frame: pd.DataFrame) -> pd.Series:
    return ((frame["strong"].diff() + frame["recovery"].diff()) - (frame["pullback"].diff() + frame["breakdown"].diff())).round(3)


def _calc_ntss(vix: pd.DataFrame, index: pd.DatetimeIndex) -> pd.Series:
    if "vix" not in vix or "vix3m" not in vix:
        return pd.Series(np.nan, index=index)
    ntss = (vix["vix3m"].ffill() - vix["vix"].ffill()).round(3)
    ntss.index = ntss.index.tz_localize("UTC") if ntss.index.tz is None else ntss.index.tz_convert("UTC")
    return ntss.reindex(index, method="nearest", tolerance=pd.Timedelta("90min"))


def _record(timestamp: object, row: pd.Series, label: str | None = None) -> dict[str, Any]:
    value = lambda key: None if key not in row or pd.isna(row[key]) else round(float(row[key]), 3)
    count = lambda key: None if key not in row or pd.isna(row[key]) else int(round(float(row[key])))
    return {"t": label or pd.Timestamp(timestamp).isoformat(), "s": value("strong"), "bd": value("breakdown"), "pb": value("pullback"), "rc": value("recovery"), "a20": value("above_20"), "a50": value("above_50"), "a200": value("above_200"), "a20_n": count("above_20_n"), "a50_n": count("above_50_n"), "a200_n": count("above_200_n"), "valid_20_n": count("valid_20_n"), "valid_50_n": count("valid_50_n"), "valid_200_n": count("valid_200_n"), "mom": value("momentum"), "mid": value("ntss"), "phase_code": _phase(value("strong"), value("breakdown"))}


def _calculate_daily_breadth(daily: pd.DataFrame, denominator: int) -> pd.DataFrame:
    refs = {window: daily.rolling(window, min_periods=1).mean() for window in (20, 50, 200)}
    pct = {window: _pct_above(daily, refs[window], BREADTH_MIN_STOCKS, denominator) for window in refs}
    all_ma, short_ma = pd.concat(list(pct.values()), axis=1), pd.concat([pct[20], pct[50]], axis=1)
    result = pd.DataFrame({"above_20": pct[20].round(2), "above_50": pct[50].round(2), "above_200": pct[200].round(2), "above_20_n": _count_above(daily, refs[20], BREADTH_MIN_STOCKS), "above_50_n": _count_above(daily, refs[50], BREADTH_MIN_STOCKS), "above_200_n": _count_above(daily, refs[200], BREADTH_MIN_STOCKS), "valid_20_n": _valid_count(daily, refs[20]), "valid_50_n": _valid_count(daily, refs[50]), "valid_200_n": _valid_count(daily, refs[200]), "strong": all_ma.min(axis=1).round(2), "breakdown": (100-all_ma.max(axis=1)).round(2), "pullback": (short_ma.min(axis=1)-all_ma.min(axis=1)).round(2), "recovery": (all_ma.max(axis=1)-short_ma.max(axis=1)).round(2)}, index=daily.index)
    result["momentum"] = _calc_momentum(result)
    return result


def daily_close_payload(
    daily: pd.DataFrame, denominator: int, ntss: pd.Series | None = None
) -> dict[str, Any] | None:
    calculated = _calculate_daily_breadth(daily, denominator)
    if ntss is not None and not ntss.empty:
        calculated.index = pd.DatetimeIndex(calculated.index).tz_localize(None).normalize()
        aligned_ntss = ntss.dropna().sort_index()
        aligned_ntss.index = pd.DatetimeIndex(aligned_ntss.index).tz_localize(None).normalize()
        calculated = calculated.loc[calculated.index <= aligned_ntss.index[-1]]
        calculated["ntss"] = aligned_ntss.reindex(calculated.index, method="ffill").values
    valid = calculated.dropna(subset=["strong", "breakdown"])
    if valid.empty: return None
    current_time = valid.index[-1]
    payload = {"current": _record(current_time, valid.iloc[-1], f"{current_time:%Y-%m-%d} EOD")}
    if len(valid) > 1:
        previous_time = valid.index[-2]
        payload["previous"] = _record(previous_time, valid.iloc[-2], f"{previous_time:%Y-%m-%d} EOD")
    return payload


class SnapshotMarketData:
    def __init__(self) -> None:
        self._symbols: dict[str, list[str]] = {}
        self._universe_meta: dict[str, dict[str, Any]] = {}
        self._daily: dict[str, dict[str, pd.DataFrame]] = {}

    def symbols(self, universe: str) -> list[str]:
        if universe in self._symbols:
            return self._symbols[universe]
        if universe == "sp500":
            try:
                symbols, diagnostics = get_sp500()
                self._symbols[universe] = symbols
                self._universe_meta[universe] = diagnostics
                return symbols
            except Exception as exc:
                symbols = _wikipedia_symbols(universe)
                self._symbols[universe] = symbols
                self._universe_meta[universe] = {"universe_source": "fallback_sp500_wikipedia", "universe_warning": "Primary SPY holdings source failed; using Wikipedia.", "universe_error": str(exc)}
                return symbols
        symbols = _wikipedia_symbols(universe)
        self._symbols[universe] = symbols
        self._universe_meta[universe] = {"universe_source": "wikipedia_nasdaq100"}
        return symbols

    def compute_signals(self, universe: str, as_of: str | None = None) -> dict[str, Any]:
        symbols = self.symbols(universe)
        history = self._daily.get(universe)
        if history is None:
            history = _download_fields(symbols, period="2y", interval="1d", fields=("Close", "Volume"))
            self._daily[universe] = history
        cutoff = pd.Timestamp(as_of).date() if as_of is not None else None
        rows = []
        failed = set(symbols) - set(history)
        for symbol, frame in history.items():
            full = frame.dropna(subset=["Close", "Volume"])
            clean = full
            if cutoff is not None:
                clean = full.loc[[pd.Timestamp(value).date() <= cutoff for value in full.index]]
            if len(clean) < 63:
                failed.add(symbol)
                continue
            selection_close = float(clean["Close"].iloc[-1])
            latest_close = float(full["Close"].iloc[-1])
            adv63 = float((clean["Close"].iloc[-63:] * clean["Volume"].iloc[-63:]).mean())
            ema200 = (
                float(
                    clean["Close"]
                    .ewm(span=200, adjust=False, min_periods=200)
                    .mean()
                    .iloc[-1]
                )
                if len(clean) >= 200
                else None
            )
            rows.append({"symbol": symbol, "close": round(latest_close, 2), "selection_close": round(selection_close, 2), "adv63": adv63, "ema200": round(ema200, 2) if ema200 else None, "distance_pct": round((selection_close / ema200 - 1) * 100, 2) if ema200 else None, "selection_date": str(pd.Timestamp(clean.index[-1]).date()), "last_date": str(pd.Timestamp(full.index[-1]).date())})
        rows.sort(key=lambda row: row["adv63"], reverse=True)
        for rank, row in enumerate(rows, 1): row["adv_rank"] = rank
        pool = _unique(rows, 15)
        ranked = sorted((row for row in pool if row["distance_pct"] is not None), key=lambda row: row["distance_pct"], reverse=True)
        picks = [{**row, "rank": rank} for rank, row in enumerate(ranked[:3], 1)]
        adv_ranked = [{**row, "rank": rank} for rank, row in enumerate(pool, 1)]
        selection_as_of = max((row["selection_date"] for row in rows), default=None)
        return {"universe": universe, "valid_count": len(rows), "failed_count": len(failed), "selection_as_of": selection_as_of, "adv_ranked": adv_ranked, "ema200_selected": picks, **self._universe_meta.get(universe, {})}

    def compute_breadth(self) -> dict[str, Any]:
        symbols = self.symbols("sp500")
        daily = self._daily.get("sp500") or _download_fields(symbols, period="2y", interval="1d", fields=("Close", "Volume"))
        intraday = _download_fields(symbols, period="5d", interval="15m", fields=("Close",))
        common = sorted(set(daily) & set(intraday))
        if not common:
            raise RuntimeError("No valid 15-minute breadth data")
        daily_wide_all = pd.concat([frame["Close"].rename(symbol) for symbol, frame in daily.items() if "Close" in frame], axis=1)
        daily_wide = daily_wide_all[common]
        intraday_wide = pd.concat([intraday[symbol]["Close"].rename(symbol) for symbol in common], axis=1)
        breadth = _calculate_breadth(daily_wide, intraday_wide, denominator=len(symbols))
        breadth["momentum"] = _calc_momentum(breadth)
        vix_history = _download_fields(["^VIX", "^VIX3M"], period="5d", interval="15m", fields=("Close",))
        daily_vix_history = _download_fields(["^VIX", "^VIX3M"], period="2y", interval="1d", fields=("Close",))
        daily_ntss = _ntss_series(daily_vix_history)
        vix = pd.DataFrame()
        if "^VIX" in vix_history and "^VIX3M" in vix_history:
            vix = pd.concat([vix_history["^VIX"]["Close"].rename("vix"), vix_history["^VIX3M"]["Close"].rename("vix3m")], axis=1)
        breadth["ntss"] = _calc_ntss(vix, breadth.index)
        records = []
        for timestamp, row in breadth.iterrows(): records.append(_record(timestamp, row))
        # Benchmark outages must not prevent publishing the breadth snapshot.
        try:
            benchmarks = _download_fields(["SPY", "QQQ"], period="5d", interval="15m", fields=("Close",))
        except Exception:
            benchmarks = {}
        records = attach_benchmark_prices(records, benchmarks)
        return {"records": records, "daily_close": daily_close_payload(daily_wide_all, len(symbols), ntss=daily_ntss), "n_stocks": len(symbols), "n_valid_15m": len(common), "n_valid_hourly": len(common), **self._universe_meta.get("sp500", {})}
