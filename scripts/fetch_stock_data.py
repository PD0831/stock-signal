"""
Downloads NASDAQ100 + S&P500 daily OHLCV data via yfinance.
Run by GitHub Actions daily; output committed to data/ for remote analysis.
"""
import io, json, sys
import pandas as pd
import requests
import yfinance as yf
from pathlib import Path
from datetime import datetime

DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)

PERIOD = "2y"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


def _read_html(url: str, **kwargs) -> list[pd.DataFrame]:
    """Fetch HTML with a browser-like User-Agent, then parse tables."""
    resp = requests.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    return pd.read_html(io.StringIO(resp.text), **kwargs)


def get_nasdaq100() -> list[str]:
    tables = _read_html(
        "https://en.wikipedia.org/wiki/Nasdaq-100",
        attrs={"id": "constituents"},
    )
    return tables[0]["Ticker"].str.replace(".", "-", regex=False).tolist()


def get_sp500() -> list[str]:
    tables = _read_html(
        "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
    )
    return tables[0]["Symbol"].str.replace(".", "-", regex=False).tolist()


def fetch_universe(name: str, symbols: list[str]) -> pd.DataFrame:
    print(f"Downloading {name} ({len(symbols)} symbols)…")
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

    nasdaq_syms = get_nasdaq100()
    print(f"NASDAQ-100: {len(nasdaq_syms)} tickers")
    sp_syms = get_sp500()
    print(f"S&P 500:    {len(sp_syms)} tickers")

    all_syms = sorted(set(nasdaq_syms) | set(sp_syms))
    print(f"Combined unique: {len(all_syms)}")

    df = fetch_universe("combined", all_syms)
    if df.empty:
        print("ERROR: no data downloaded", file=sys.stderr)
        sys.exit(1)

    out_path = DATA_DIR / "stocks_daily.csv"
    df.to_csv(out_path, index=False)
    print(f"Saved {len(df):,} rows → {out_path}  (as of {ts})")

    meta = {
        "updated_at": ts,
        "rows": len(df),
        "symbols": len(df["symbol"].unique()),
        "date_min": str(df["date"].min()),
        "date_max": str(df["date"].max()),
    }
    (DATA_DIR / "stocks_meta.json").write_text(json.dumps(meta, indent=2))
    print("Metadata saved.")


if __name__ == "__main__":
    main()
