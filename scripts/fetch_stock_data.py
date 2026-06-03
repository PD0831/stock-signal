"""
Download SPY holdings daily OHLCV data via yfinance.
Run by GitHub Actions daily; output committed to data/ for market breadth analysis.

Breadth is calculated by constituent security ticker, not by issuer. Dual-share
classes such as GOOG/GOOGL are intentionally kept as separate symbols.
"""
import json
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
import yfinance as yf

try:
    from scripts.spy_universe import download_spy_universe
except ModuleNotFoundError:
    from spy_universe import download_spy_universe

DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)

PERIOD = "2y"
UNIVERSE = "spy_holdings"


def get_sp500() -> tuple[list[str], dict[str, object]]:
    universe = download_spy_universe()
    tickers = universe.symbols
    diagnostics = {
        "universe_source": "spdr_spy_holdings_xlsx",
        "spy_holdings_as_of": universe.as_of,
        "spy_raw_holding_rows": universe.raw_holding_rows,
        "spy_excluded_rows": universe.excluded_rows,
        "spy_excluded_count": universe.excluded_count,
    }
    print(
        "  SPY holdings universe: "
        f"{len(tickers)} equity tickers "
        f"({universe.raw_holding_rows} raw rows, {universe.excluded_count} excluded)"
    )
    return tickers, diagnostics


def fetch_universe(name: str, symbols: list[str]) -> pd.DataFrame:
    print(f"Downloading {name} ({len(symbols)} symbols)...")
    raw = yf.download(
        symbols,
        period=PERIOD,
        interval="1d",
        auto_adjust=False,
        progress=False,
        threads=True,
    )
    frames = []
    for sym in symbols:
        try:
            df = raw.xs(sym, axis=1, level=1)[["Open", "High", "Low", "Close", "Volume"]].copy()
            df = df.dropna(subset=["Close", "Volume"])
            df.index.name = "date"
            df = df.reset_index()
            df.insert(0, "symbol", sym)
            df.columns = ["symbol", "date", "open", "high", "low", "close", "volume"]
            df["dollar_volume"] = df["close"] * df["volume"]
            frames.append(df)
        except Exception as e:
            print(f"  skip {sym}: {e}", file=sys.stderr)
    if not frames:
        return pd.DataFrame()
    out = pd.concat(frames, ignore_index=True)
    out["date"] = pd.to_datetime(out["date"]).dt.date
    return out.sort_values(["symbol", "date"]).reset_index(drop=True)


def main():
    ts = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

    sp_syms, diagnostics = get_sp500()
    if not sp_syms:
        print("ERROR: no SPY holdings symbols loaded", file=sys.stderr)
        sys.exit(1)

    if {"GOOG", "GOOGL"}.issubset(sp_syms):
        print("  Alphabet share classes retained separately: GOOG, GOOGL")
    else:
        print("  WARNING: expected GOOG and GOOGL to be present as separate tickers", file=sys.stderr)

    df = fetch_universe("SPY holdings breadth universe", sp_syms)
    if df.empty:
        print("ERROR: no data downloaded", file=sys.stderr)
        sys.exit(1)

    out_path = DATA_DIR / "stocks_daily.csv"
    df.to_csv(out_path, index=False)
    print(f"Saved {len(df):,} rows -> {out_path}  (as of {ts})")

    downloaded_symbols = sorted(df["symbol"].unique())
    meta = {
        "updated_at": ts,
        "universe": UNIVERSE,
        "counting_method": "constituent_security_ticker",
        "share_class_policy": "GOOG and GOOGL counted separately",
        "price_basis": "regular_close_not_dividend_adjusted",
        "expected_symbols": len(sp_syms),
        "symbols": len(downloaded_symbols),
        "missing_symbols": sorted(set(sp_syms) - set(downloaded_symbols)),
        "rows": len(df),
        "date_min": str(df["date"].min()),
        "date_max": str(df["date"].max()),
        **diagnostics,
    }
    (DATA_DIR / "stocks_meta.json").write_text(json.dumps(meta, indent=2))
    print("Metadata saved.")


if __name__ == "__main__":
    main()
