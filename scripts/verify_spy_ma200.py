"""Verify SPY holdings breadth against Yahoo regular Close data.

Example:
    python scripts/verify_spy_ma200.py --date 2026-06-02 --expect-count 505 --expect-above 270
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd
import yfinance as yf

try:
    from scripts.spy_universe import download_spy_universe
except ModuleNotFoundError:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from spy_universe import download_spy_universe

YF_BATCH_SIZE = 50


def close_columns_from_download(frame: pd.DataFrame, symbols: list[str]) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame()
    if not isinstance(frame.columns, pd.MultiIndex):
        if len(symbols) == 1 and "Close" in frame.columns:
            return frame[["Close"]].rename(columns={"Close": symbols[0]})
        return frame

    level0 = {str(x) for x in frame.columns.get_level_values(0)}
    closes: dict[str, pd.Series] = {}
    for symbol in symbols:
        try:
            if symbol in level0:
                sub = frame[symbol]
                if "Close" in sub.columns:
                    closes[symbol] = sub["Close"]
            else:
                sub = frame.xs(symbol, axis=1, level=1)
                if "Close" in sub.columns:
                    closes[symbol] = sub["Close"]
        except Exception:
            continue
    return pd.DataFrame(closes)


def download_daily_closes(symbols: list[str], period: str) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for i in range(0, len(symbols), YF_BATCH_SIZE):
        batch = symbols[i:i + YF_BATCH_SIZE]
        raw = yf.download(
            batch,
            period=period,
            interval="1d",
            group_by="ticker",
            auto_adjust=False,
            progress=False,
            threads=True,
        )
        closes = close_columns_from_download(raw, batch)
        if not closes.empty:
            frames.append(closes)
    if not frames:
        return pd.DataFrame()
    daily = pd.concat(frames, axis=1)
    daily = daily.loc[:, ~daily.columns.duplicated()].sort_index()
    idx = pd.DatetimeIndex(daily.index)
    if idx.tz is not None:
        idx = idx.tz_convert("America/New_York").tz_localize(None)
    daily.index = pd.DatetimeIndex(idx).normalize()
    return daily


def verify(args: argparse.Namespace) -> dict[str, object]:
    universe = download_spy_universe()
    symbols = universe.symbols
    daily = download_daily_closes(symbols, args.period)
    if daily.empty:
        raise RuntimeError("No Yahoo daily data downloaded")

    target = pd.Timestamp(args.date).normalize() if args.date else daily.index.max()
    available_dates = daily.index[daily.index <= target]
    if available_dates.empty:
        raise RuntimeError(f"No downloaded daily data on or before {target.date()}")
    asof = available_dates.max()
    daily = daily.loc[:asof]

    ma200 = daily.rolling(200, min_periods=1).mean()
    prices = daily.loc[asof]
    refs = ma200.loc[asof]
    valid = prices.notna() & refs.notna()
    above = (prices > refs) & valid

    short_or_missing = []
    for symbol in symbols:
        count = int(daily[symbol].dropna().shape[0]) if symbol in daily.columns else 0
        if count < 1:
            short_or_missing.append({"symbol": symbol, "bars": count})

    result = {
        "date": str(asof.date()),
        "price_basis": "regular_close_not_dividend_adjusted",
        "ma_policy": "SMA200, falling back to available-history average before 200 closes",
        "universe_source": "spdr_spy_holdings_xlsx",
        "spy_holdings_as_of": universe.as_of,
        "spy_raw_holding_rows": universe.raw_holding_rows,
        "spy_excluded_count": universe.excluded_count,
        "spy_excluded_rows": universe.excluded_rows,
        "symbols": len(symbols),
        "has_GOOG": "GOOG" in symbols,
        "has_GOOGL": "GOOGL" in symbols,
        "valid_ma200": int(valid.sum()),
        "above_ma200": int(above.sum()),
        "below_or_equal_ma200": int((valid & ~above).sum()),
        "short_or_missing": short_or_missing,
        "expected_symbols": args.expect_count,
        "expected_above_ma200": args.expect_above,
    }
    result["matches_expected"] = (
        (args.expect_count is None or result["symbols"] == args.expect_count)
        and (args.expect_above is None or result["above_ma200"] == args.expect_above)
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", help="Target date, for example 2026-06-02")
    parser.add_argument("--period", default="2y")
    parser.add_argument("--min-periods", type=int, default=200)
    parser.add_argument("--expect-count", type=int)
    parser.add_argument("--expect-above", type=int)
    args = parser.parse_args()

    result = verify(args)
    print(json.dumps(result, indent=2))
    return 0 if result["matches_expected"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
