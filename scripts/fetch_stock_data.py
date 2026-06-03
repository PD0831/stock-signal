"""
Download S&P 500 daily OHLCV data via yfinance.
Run by GitHub Actions daily; output committed to data/ for market breadth analysis.

Breadth is calculated by constituent security ticker, not by issuer. Dual-share
classes such as GOOG/GOOGL are intentionally kept as separate symbols.
"""
import io
import json
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
import requests
import yfinance as yf

DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)

PERIOD = "2y"
UNIVERSE = "sp500"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

_SP500_PUBLIC_CSV = (
    "https://raw.githubusercontent.com/datasets/"
    "s-and-p-500-companies/main/data/constituents.csv"
)


def _read_html(url: str, **kwargs) -> list[pd.DataFrame]:
    resp = requests.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    return pd.read_html(io.StringIO(resp.text), **kwargs)


def normalize_symbol(value: object) -> str | None:
    if value is None or pd.isna(value):
        return None
    symbol = str(value).strip().upper().replace(".", "-")
    return symbol or None


def _symbols_from_column(frame: pd.DataFrame, column: str) -> list[str]:
    symbols = [s for s in frame[column].map(normalize_symbol).tolist() if s]
    return sorted(dict.fromkeys(symbols))


def get_sp500() -> list[str]:
    # Try public GitHub CSV first (no scraping needed).
    try:
        resp = requests.get(_SP500_PUBLIC_CSV, timeout=30)
        resp.raise_for_status()
        df = pd.read_csv(io.StringIO(resp.text))
        tickers = _symbols_from_column(df, "Symbol")
        print(f"  S&P 500 from public dataset: {len(tickers)}")
        return tickers
    except Exception as e:
        print(f"  Public dataset failed ({e}), trying Wikipedia...")

    try:
        tables = _read_html("https://en.wikipedia.org/wiki/List_of_S%26P_500_companies")
        tickers = _symbols_from_column(tables[0], "Symbol")
        print(f"  S&P 500 from Wikipedia: {len(tickers)}")
        return tickers
    except Exception as e2:
        print(f"  Wikipedia also failed ({e2})")
        return []


def fetch_universe(name: str, symbols: list[str]) -> pd.DataFrame:
    print(f"Downloading {name} ({len(symbols)} symbols)...")
    raw = yf.download(
        symbols,
        period=PERIOD,
        interval="1d",
        auto_adjust=True,
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

    sp_syms = get_sp500()
    if not sp_syms:
        print("ERROR: no S&P 500 symbols loaded", file=sys.stderr)
        sys.exit(1)

    if {"GOOG", "GOOGL"}.issubset(sp_syms):
        print("  Alphabet share classes retained separately: GOOG, GOOGL")
    else:
        print("  WARNING: expected GOOG and GOOGL to be present as separate tickers", file=sys.stderr)

    df = fetch_universe("S&P 500 breadth universe", sp_syms)
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
        "expected_symbols": len(sp_syms),
        "symbols": len(downloaded_symbols),
        "missing_symbols": sorted(set(sp_syms) - set(downloaded_symbols)),
        "rows": len(df),
        "date_min": str(df["date"].min()),
        "date_max": str(df["date"].max()),
    }
    (DATA_DIR / "stocks_meta.json").write_text(json.dumps(meta, indent=2))
    print("Metadata saved.")


if __name__ == "__main__":
    main()
