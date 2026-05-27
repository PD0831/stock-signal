"""
Downloads NASDAQ100 + S&P500 daily OHLCV data via yfinance.
Run by GitHub Actions daily; output committed to data/ for remote analysis.
"""
import io, sys
import pandas as pd
import yfinance as yf
from pathlib import Path
from datetime import datetime, timedelta

DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)

PERIOD = "2y"   # 2 years of daily bars


def get_nasdaq100() -> list[str]:
    url = "https://en.wikipedia.org/wiki/Nasdaq-100"
    df = pd.read_html(url, attrs={"id": "constituents"})[0]
    return df["Ticker"].str.replace(".", "-", regex=False).tolist()


def get_sp500() -> list[str]:
    url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
    df = pd.read_html(url)[0]
    return df["Symbol"].str.replace(".", "-", regex=False).tolist()


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
    # Reshape to long format: date, symbol, open, high, low, close, volume
    frames = []
    for sym in symbols:
        try:
            df = raw.xs(sym, axis=1, level=1)[["Open","High","Low","Close","Volume"]].copy()
            df = df.dropna(subset=["Close","Volume"])
            df.index.name = "date"
            df = df.reset_index()
            df.insert(0, "symbol", sym)
            df.columns = ["symbol","date","open","high","low","close","volume"]
            df["dollar_volume"] = df["close"] * df["volume"]
            frames.append(df)
        except Exception as e:
            print(f"  skip {sym}: {e}", file=sys.stderr)
    if not frames:
        return pd.DataFrame()
    out = pd.concat(frames, ignore_index=True)
    out["date"] = pd.to_datetime(out["date"]).dt.date
    out = out.sort_values(["symbol","date"]).reset_index(drop=True)
    return out


def main():
    ts = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

    nasdaq_syms = get_nasdaq100()
    sp_syms     = get_sp500()
    # Combined unique set
    all_syms    = sorted(set(nasdaq_syms) | set(sp_syms))

    df = fetch_universe("NASDAQ100+SP500", all_syms)
    if df.empty:
        print("ERROR: no data downloaded", file=sys.stderr)
        sys.exit(1)

    out_path = DATA_DIR / "stocks_daily.csv"
    df.to_csv(out_path, index=False)
    print(f"Saved {len(df):,} rows → {out_path}  (as of {ts})")

    # Also save a small metadata file
    meta = {
        "updated_at": ts,
        "rows": len(df),
        "symbols": len(df["symbol"].unique()),
        "date_min": str(df["date"].min()),
        "date_max": str(df["date"].max()),
    }
    import json
    (DATA_DIR / "stocks_meta.json").write_text(json.dumps(meta, indent=2))
    print("Metadata saved.")


if __name__ == "__main__":
    main()
