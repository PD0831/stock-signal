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
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# Fallback ticker lists (updated 2025-Q4) used when Wikipedia is unreachable
_NDX100_FALLBACK = [
    "AAPL","ABNB","ADBE","ADI","ADP","ADSK","AEP","AMAT","AMD","AMGN",
    "AMZN","ANSS","APP","ARM","ASML","AVGO","AXON","AZN","BIIB","BKNG",
    "BKR","CCEP","CDNS","CDW","CEG","CHTR","CMCSA","COST","CPRT","CRWD",
    "CSCO","CSGP","CSX","CTAS","CTSH","DASH","DDOG","DXCM","EA","EXC",
    "FANG","FAST","FTNT","GEHC","GFS","GILD","GOOG","GOOGL","HON","IDXX",
    "ILMN","INTC","INTU","ISRG","KDP","KHC","KLAC","LIN","LRCX","LULU",
    "MAR","MCHP","MDLZ","MELI","META","MNST","MRNA","MRVL","MSFT","MU",
    "NFLX","NVDA","NXPI","ODFL","ON","ORLY","PANW","PAYX","PCAR","PDD",
    "PEP","PYPL","QCOM","REGN","ROP","ROST","SBUX","SMCI","SNPS","SPLK",
    "TEAM","TMUS","TSLA","TTD","TTWO","TXN","VRSK","VRTX","WBD","WDAY",
    "XEL","ZS",
]

_SP500_PUBLIC_CSV = (
    "https://raw.githubusercontent.com/datasets/"
    "s-and-p-500-companies/main/data/constituents.csv"
)


def _read_html(url: str, **kwargs) -> list[pd.DataFrame]:
    resp = requests.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    return pd.read_html(io.StringIO(resp.text), **kwargs)


def get_nasdaq100() -> list[str]:
    try:
        tables = _read_html(
            "https://en.wikipedia.org/wiki/Nasdaq-100",
            attrs={"id": "constituents"},
        )
        tickers = tables[0]["Ticker"].str.replace(".", "-", regex=False).tolist()
        print(f"  NASDAQ-100 from Wikipedia: {len(tickers)}")
        return tickers
    except Exception as e:
        print(f"  Wikipedia blocked ({e}), using fallback list ({len(_NDX100_FALLBACK)})")
        return _NDX100_FALLBACK


def get_sp500() -> list[str]:
    # Try public GitHub CSV first (no scraping needed)
    try:
        resp = requests.get(_SP500_PUBLIC_CSV, timeout=30)
        resp.raise_for_status()
        df = pd.read_csv(io.StringIO(resp.text))
        tickers = df["Symbol"].str.replace(".", "-", regex=False).tolist()
        print(f"  S&P 500 from public dataset: {len(tickers)}")
        return tickers
    except Exception as e:
        print(f"  Public dataset failed ({e}), trying Wikipedia…")

    try:
        tables = _read_html("https://en.wikipedia.org/wiki/List_of_S%26P_500_companies")
        tickers = tables[0]["Symbol"].str.replace(".", "-", regex=False).tolist()
        print(f"  S&P 500 from Wikipedia: {len(tickers)}")
        return tickers
    except Exception as e2:
        print(f"  Wikipedia also failed ({e2}), using NASDAQ-100 only")
        return []


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
    sp_syms     = get_sp500()
    all_syms    = sorted(set(nasdaq_syms) | set(sp_syms))
    print(f"Combined unique tickers: {len(all_syms)}")

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
