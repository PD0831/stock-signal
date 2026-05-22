#!/usr/bin/env python3
"""Live stock-selection + hourly breadth monitor web app.

Routes:
  GET /             — stock selection signals (NASDAQ100 + S&P500)
  GET /breadth      — hourly S&P500 breadth chart (Plotly)
  GET /api/signals  — JSON: stock selection data
  GET /api/breadth  — JSON: hourly breadth records (202 while computing)
"""

from __future__ import annotations

import gc
import threading
import time
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from io import StringIO
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import requests
import yfinance as yf
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
import os

# ── Config ────────────────────────────────────────────────────────────────────
NASDAQ100_URL = "https://en.wikipedia.org/wiki/Nasdaq-100"
SP500_URL     = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
CACHE_DIR     = Path(os.environ.get("CACHE_DIR", "/tmp"))

BREADTH_PERIOD     = "3mo"
BREADTH_SMOOTH     = 3
BREADTH_MIN_STOCKS = 100

# ── In-memory cache ───────────────────────────────────────────────────────────
_memory_cache: dict[str, tuple[datetime, Any]] = {}
_breadth_computing  = False
_breadth_error: str = ""
_breadth_started_at: datetime | None = None


def cache_get(key: str, ttl_minutes: int) -> Any | None:
    item = _memory_cache.get(key)
    if item is None:
        return None
    ts, value = item
    if datetime.now(timezone.utc) - ts > timedelta(minutes=ttl_minutes):
        return None
    return value


def cache_set(key: str, value: Any) -> Any:
    _memory_cache[key] = (datetime.now(timezone.utc), value)
    return value


def cache_evict_stale(max_age_minutes: int = 420) -> None:
    """Delete cache entries older than max_age_minutes to prevent unbounded growth."""
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=max_age_minutes)
    stale = [k for k, (ts, _) in list(_memory_cache.items()) if ts < cutoff]
    for k in stale:
        del _memory_cache[k]


# ── Startup: launch breadth background thread ─────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    t = threading.Thread(target=_bg_refresh_breadth, daemon=True)
    t.start()
    yield


app = FastAPI(title="Live Stock Signal", lifespan=lifespan)


# ── Stock signal helpers ──────────────────────────────────────────────────────
def normalize_symbol(raw: object) -> str | None:
    if raw is None or pd.isna(raw):
        return None
    value = str(raw).strip().upper()
    if not value or value == "NAN":
        return None
    return value.replace(".", "-")


def fetch_html(url: str) -> str:
    response = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
    response.raise_for_status()
    return response.text


def fallback_current_symbols(universe: str) -> list[str]:
    path = CACHE_DIR / (
        "nasdaq100_current_wikipedia.csv" if universe == "nasdaq100"
        else "sp500_current_wikipedia.csv"
    )
    if not path.exists():
        return []
    frame = pd.read_csv(path)
    return sorted({s for s in frame["symbol"].map(normalize_symbol).dropna().tolist()})


def fetch_current_symbols(universe: str) -> list[str]:
    cached = cache_get(f"symbols:{universe}", ttl_minutes=360)
    if cached is not None:
        return cached
    try:
        url = NASDAQ100_URL if universe == "nasdaq100" else SP500_URL
        tables = pd.read_html(StringIO(fetch_html(url)))
        symbols: list[str] = []
        if universe == "nasdaq100":
            for table in tables:
                if "Ticker" in table.columns:
                    symbols = table["Ticker"].map(normalize_symbol).dropna().tolist()
                    if len(symbols) >= 80:
                        break
        else:
            for table in tables:
                if "Symbol" in table.columns:
                    symbols = table["Symbol"].map(normalize_symbol).dropna().tolist()
                    if len(symbols) >= 400:
                        break
        symbols = sorted(set(symbols))
        if symbols:
            return cache_set(f"symbols:{universe}", symbols)
    except Exception:
        pass
    return cache_set(f"symbols:{universe}", fallback_current_symbols(universe))


def flatten_yfinance_frame(frame: pd.DataFrame, symbols: list[str]) -> dict[str, pd.DataFrame]:
    data: dict[str, pd.DataFrame] = {}
    if frame.empty:
        return data
    if isinstance(frame.columns, pd.MultiIndex):
        level0 = {str(x) for x in frame.columns.get_level_values(0)}
        for symbol in symbols:
            try:
                sub = frame[symbol].copy() if symbol in level0 else frame.xs(symbol, axis=1, level=1).copy()
            except Exception:
                continue
            if "Close" in sub.columns and "Volume" in sub.columns:
                data[symbol] = sub[["Close", "Volume"]].dropna(how="all")
    else:
        if len(symbols) == 1 and "Close" in frame.columns and "Volume" in frame.columns:
            data[symbols[0]] = frame[["Close", "Volume"]].dropna(how="all")
    return data


def fetch_history(symbols: list[str]) -> dict[str, pd.DataFrame]:
    key = "history:" + ",".join(symbols)
    cached = cache_get(key, ttl_minutes=45)
    if cached is not None:
        return cached
    yf_symbols = [s.replace(".", "-") for s in symbols]
    frame = yf.download(
        yf_symbols, period="13mo", interval="1d",
        group_by="ticker", auto_adjust=True, progress=False, threads=True,
    )
    return cache_set(key, flatten_yfinance_frame(frame, yf_symbols))


def issuer_key(symbol: str) -> str:
    same = {"GOOG": "GOOGL", "GOOGL": "GOOGL", "FOX": "FOXA", "FOXA": "FOXA",
            "NWS": "NWSA", "NWSA": "NWSA"}
    return same.get(symbol, symbol)


def compute_signals(universe: str, adv_pool_size: int = 10) -> dict[str, Any]:
    symbols = fetch_current_symbols(universe)
    if not symbols:
        raise RuntimeError("Could not load current universe symbols.")
    history = fetch_history(symbols)
    rows: list[dict[str, Any]] = []
    failed_symbols: set[str] = set(symbols) - set(history)
    for symbol, frame in history.items():
        clean = frame.copy()
        clean["Close"]  = pd.to_numeric(clean["Close"],  errors="coerce")
        clean["Volume"] = pd.to_numeric(clean["Volume"], errors="coerce")
        clean = clean.dropna(subset=["Close", "Volume"])
        if len(clean) < 63:
            failed_symbols.add(symbol)
            continue
        last_close = float(clean["Close"].iloc[-1])
        adv63 = float((clean["Close"].iloc[-63:] * clean["Volume"].iloc[-63:]).mean())
        last_date = clean.index[-1]
        if hasattr(last_date, "date"):
            last_date = last_date.date().isoformat()
        ma200: float | None = None
        distance_pct: float | None = None
        if len(clean) >= 200:
            ma200 = float(clean["Close"].iloc[-200:].mean())
            distance_pct = round((last_close / ma200 - 1) * 100, 2)
        rows.append({"symbol": symbol, "last_date": last_date, "close": round(last_close, 2),
                     "adv63": adv63, "ma200": round(ma200, 2) if ma200 else None,
                     "distance_pct": distance_pct})
    rows.sort(key=lambda r: r["adv63"], reverse=True)
    for idx, r in enumerate(rows, 1):
        r["adv_rank"] = idx
    pool: list[dict[str, Any]] = []
    seen: set[str] = set()
    for r in rows:
        ik = issuer_key(r["symbol"])
        if ik in seen:
            continue
        pool.append(r)
        seen.add(ik)
        if len(pool) >= adv_pool_size:
            break
    adv_selected = [
        {"symbol": r["symbol"], "close": r["close"], "adv63": r["adv63"],
         "adv_rank": r["adv_rank"], "ma200": r["ma200"], "distance_pct": r["distance_pct"],
         "rank": idx, "is_top3": idx <= 3}
        for idx, r in enumerate(pool[:5], 1)
    ]
    ma_pool   = [r for r in pool if r["distance_pct"] is not None]
    ma_sorted = sorted(ma_pool, key=lambda r: r["distance_pct"], reverse=True)
    ma200_selected = [
        {"symbol": r["symbol"], "close": r["close"], "adv63": r["adv63"],
         "adv_rank": r["adv_rank"], "ma200": r["ma200"], "distance_pct": r["distance_pct"],
         "rank": idx}
        for idx, r in enumerate(ma_sorted[:3], 1)
    ]
    as_of = max((r["last_date"] for r in rows), default=None)
    return {"as_of": as_of, "universe": universe, "universe_count": len(symbols),
            "valid_count": len(rows), "failed_count": len(failed_symbols),
            "adv_selected": adv_selected, "ma200_selected": ma200_selected}


# ── Breadth: incremental hourly data fetch ────────────────────────────────────
def _fetch_hourly(yf_symbols: list[str]) -> pd.DataFrame:
    """Return hourly close DataFrame for yf_symbols.

    First call (cache cold): downloads the full BREADTH_PERIOD window.
    Subsequent calls: downloads only the last 2 days and splices into the
    cached data, so a 3-month re-download is never needed on hourly refresh.
    """
    cached: pd.DataFrame | None = cache_get("hourly_raw", ttl_minutes=180)
    if cached is not None:
        print("[breadth] incremental hourly update (2d)…")
        recent_raw = yf.download(yf_symbols, period="2d", interval="1h",
                                 auto_adjust=True, progress=False, threads=True)
        if recent_raw.empty:
            return cached
        recent = recent_raw["Close"] if isinstance(recent_raw.columns, pd.MultiIndex) else recent_raw
        del recent_raw
        if recent.index.tz is None:
            recent.index = recent.index.tz_localize("UTC")
        # Keep cached bars that predate the fresh window, trimmed to ~3 months
        cutoff  = recent.index.min()
        oldest  = recent.index.max() - pd.Timedelta(days=93)
        base    = cached[(cached.index >= oldest) & (cached.index < cutoff)]
        merged  = pd.concat([base, recent])
        merged  = merged.loc[:, merged.isna().mean() < 0.5]
        del recent, base
        gc.collect()
        cache_set("hourly_raw", merged)
        return merged

    # Cold start — full download
    print(f"[breadth] full hourly download ({BREADTH_PERIOD})…")
    raw = yf.download(yf_symbols, period=BREADTH_PERIOD, interval="1h",
                      auto_adjust=True, progress=False, threads=True)
    hourly_df = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw
    del raw
    hourly_df = hourly_df.loc[:, hourly_df.isna().mean() < 0.5]
    if hourly_df.index.tz is None:
        hourly_df.index = hourly_df.index.tz_localize("UTC")
    gc.collect()
    cache_set("hourly_raw", hourly_df)
    return hourly_df


# ── Breadth: calculation ──────────────────────────────────────────────────────
def _ema(s: pd.Series, span: int) -> pd.Series:
    return s.ewm(span=span, adjust=False, min_periods=1).mean()


def _daily_to_hourly_ref(daily_ma: pd.DataFrame, hourly_idx: pd.DatetimeIndex) -> pd.DataFrame:
    di = daily_ma.index
    if hasattr(di, "tz") and di.tz is not None:
        di = di.tz_localize(None)
    daily_ma_norm = daily_ma.copy()
    daily_ma_norm.index = pd.DatetimeIndex(di).normalize()
    bar_dates = pd.DatetimeIndex(
        [pd.Timestamp(ts.tz_localize(None) if ts.tzinfo else ts).normalize()
         for ts in hourly_idx]
    )
    ref = daily_ma_norm.reindex(bar_dates, method="ffill")
    ref.index = hourly_idx
    return ref.ffill()


def _pct_above(hourly_prices: pd.DataFrame, ref: pd.DataFrame, min_n: int) -> pd.Series:
    valid   = hourly_prices.notna() & ref.notna()
    above   = (hourly_prices > ref) & valid
    n_valid = valid.sum(axis=1)
    pct = above.sum(axis=1).astype(float) / n_valid.clip(lower=1) * 100
    pct[n_valid < min_n] = np.nan
    return pct


def _calculate_breadth(daily: pd.DataFrame, hourly: pd.DataFrame) -> pd.DataFrame:
    common   = daily.columns.intersection(hourly.columns)
    ma20_ts  = daily[common].rolling(20,  min_periods=15).mean()
    ma50_ts  = daily[common].rolling(50,  min_periods=40).mean()
    ma200_ts = daily[common].rolling(200, min_periods=150).mean()
    ma20_ref  = _daily_to_hourly_ref(ma20_ts,  hourly.index)
    ma50_ref  = _daily_to_hourly_ref(ma50_ts,  hourly.index)
    ma200_ref = _daily_to_hourly_ref(ma200_ts, hourly.index)
    h = hourly[common]
    above_20  = _ema(_pct_above(h, ma20_ref[common],  BREADTH_MIN_STOCKS), BREADTH_SMOOTH)
    above_50  = _ema(_pct_above(h, ma50_ref[common],  BREADTH_MIN_STOCKS), BREADTH_SMOOTH)
    above_200 = _ema(_pct_above(h, ma200_ref[common], BREADTH_MIN_STOCKS), BREADTH_SMOOTH)
    m  = pd.concat([above_20, above_50, above_200], axis=1)
    m2 = pd.concat([above_20, above_50], axis=1)
    return pd.DataFrame({
        "above_20":  above_20.round(2),
        "above_50":  above_50.round(2),
        "above_200": above_200.round(2),
        "strong":    m.min(axis=1).round(2),
        "breakdown": (100 - m.max(axis=1)).round(2),
        "pullback":  (m2.min(axis=1) - m.min(axis=1)).round(2),
        "recovery":  (m.max(axis=1) - m2.max(axis=1)).round(2),
    }, index=hourly.index)


def _calc_momentum(df: pd.DataFrame) -> pd.Series:
    return (((df["strong"].diff() + df["recovery"].diff())
             - (df["pullback"].diff() + df["breakdown"].diff()))
            .round(3))


def _calc_ntss(vix_df: pd.DataFrame, idx: pd.DatetimeIndex) -> pd.Series:
    if "vix" not in vix_df.columns or "vix3m" not in vix_df.columns:
        return pd.Series(np.nan, index=idx)
    ntss = (vix_df["vix3m"].ffill() - vix_df["vix"].ffill()).round(3)
    if ntss.index.tz is None:
        ntss.index = ntss.index.tz_localize("UTC")
    else:
        ntss.index = ntss.index.tz_convert("UTC")
    return ntss.reindex(idx, method="nearest", tolerance=pd.Timedelta("90min"))


def compute_breadth_data() -> dict:
    print("[breadth] starting computation…")
    symbols    = fetch_current_symbols("sp500")
    yf_symbols = [s.replace(".", "-") for s in symbols]

    # Daily — reuse existing cache if signals were fetched recently
    history  = fetch_history(symbols)
    daily_df = pd.DataFrame({s: df["Close"] for s, df in history.items()
                             if "Close" in df.columns})

    # Hourly — incremental after first load
    hourly_df = _fetch_hourly(yf_symbols)

    n_stocks = daily_df.shape[1]
    breadth = _calculate_breadth(daily_df, hourly_df)
    del daily_df, hourly_df
    gc.collect()

    # VIX
    vix_frames: dict[str, pd.Series] = {}
    for ticker, key in [("^VIX", "vix"), ("^VIX3M", "vix3m")]:
        try:
            hist = yf.Ticker(ticker).history(period=BREADTH_PERIOD, interval="1h")
            if not hist.empty:
                vix_frames[key] = hist["Close"].rename(key)
        except Exception:
            pass
    vix_df = pd.concat(vix_frames.values(), axis=1) if vix_frames else pd.DataFrame()
    ntss   = _calc_ntss(vix_df, breadth.index)

    breadth["ntss"]     = ntss.values
    breadth["momentum"] = _calc_momentum(breadth).values

    try:
        idx_et = breadth.index.tz_convert("America/New_York")
    except Exception:
        idx_et = breadth.index

    def v(x: Any) -> float | None:
        return None if pd.isna(x) else round(float(x), 2)

    records = [
        {"t":    idx_et[i].strftime("%Y-%m-%d %H:%M"),
         "s":    v(row["strong"]),    "bd":   v(row["breakdown"]),
         "pb":   v(row["pullback"]),  "rc":   v(row["recovery"]),
         "mid":  v(row["ntss"]),      "mom":  v(row["momentum"]),
         "a20":  v(row.get("above_20")),
         "a50":  v(row.get("above_50")),
         "a200": v(row.get("above_200"))}
        for i, (_, row) in enumerate(breadth.iterrows())
    ]
    del breadth
    gc.collect()
    print(f"[breadth] done — {len(records)} bars")
    return {"generated_at": datetime.now().isoformat(timespec="seconds"),
            "timeframe": "1H", "n_stocks": n_stocks, "records": records}


def _bg_refresh_breadth() -> None:
    global _breadth_computing, _breadth_error, _breadth_started_at
    while True:
        _breadth_computing  = True
        _breadth_error      = ""
        _breadth_started_at = datetime.now(timezone.utc)
        try:
            data = compute_breadth_data()
            cache_set("breadth", data)
            cache_evict_stale()
            _breadth_error = ""
            time.sleep(3600)
        except Exception as e:
            _breadth_error = str(e)
            print(f"[breadth] error: {e}")
            time.sleep(300)   # retry in 5 min on failure instead of 60 min
        finally:
            _breadth_computing = False


# ── Routes ────────────────────────────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return SIGNALS_HTML


@app.get("/api/signals")
def api_signals() -> JSONResponse:
    try:
        return JSONResponse({
            "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "nasdaq100": compute_signals("nasdaq100"),
            "sp500":     compute_signals("sp500"),
        })
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


@app.get("/api/signal/{universe}")
def api_signal(universe: str) -> JSONResponse:
    if universe not in ("nasdaq100", "sp500"):
        return JSONResponse({"error": "universe must be nasdaq100 or sp500"}, status_code=400)
    try:
        payload = compute_signals(universe)
        payload["generated_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
        return JSONResponse(payload)
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


@app.get("/api/breadth")
def api_breadth() -> JSONResponse:
    data = cache_get("breadth", ttl_minutes=120)
    if data is None:
        elapsed = ""
        if _breadth_started_at:
            secs = int((datetime.now(timezone.utc) - _breadth_started_at).total_seconds())
            elapsed = f" ({secs//60}m {secs%60}s elapsed)"
        if _breadth_error:
            # last attempt failed — retry is scheduled, expose the error
            return JSONResponse({"status": "error", "error": _breadth_error,
                                 "message": "Last attempt failed — retrying in 5 min."},
                                status_code=202)
        if _breadth_computing:
            return JSONResponse({"status": "computing",
                                 "message": f"Downloading 500+ stocks of hourly data{elapsed}. "
                                            f"Takes 3–8 min on first load — hang tight."},
                                status_code=202)
        # thread hasn't started yet (startup race) — kick it off
        t = threading.Thread(target=_bg_refresh_breadth, daemon=True)
        t.start()
        return JSONResponse({"status": "starting",
                             "message": "Starting breadth computation…"},
                            status_code=202)
    return JSONResponse(data)


@app.get("/breadth", response_class=HTMLResponse)
def breadth_page() -> str:
    return BREADTH_HTML


# ── HTML: shared nav ──────────────────────────────────────────────────────────
_NAV = r"""
<style>
  .nav-bar { background:#161b22; border-bottom:1px solid #30363d; padding:0 24px; display:flex; gap:0; }
  .nav-link { display:block; padding:9px 16px; font-size:13px; font-weight:600;
              text-decoration:none; color:#8b949e;
              border-bottom:2px solid transparent; transition:color .15s; }
  .nav-link:hover { color:#c9d1d9; }
  .nav-link.active { color:#58a6ff; border-bottom-color:#58a6ff; }
</style>
<nav class="nav-bar">
  <a id="nav-signals" class="nav-link" href="/">选股信号</a>
  <a id="nav-breadth" class="nav-link" href="/breadth">市场宽度</a>
</nav>
<script>
  (function(){
    var id = location.pathname.startsWith("/breadth") ? "nav-breadth" : "nav-signals";
    document.getElementById(id).classList.add("active");
  })();
</script>
"""

# ── HTML: signals page ────────────────────────────────────────────────────────
SIGNALS_HTML = r"""<!doctype html>
<html lang="zh">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>VIX × Breadth 选股信号</title>
  <style>
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      background: #0d1117;
      color: #e6edf3;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      font-size: 13px;
      min-height: 100vh;
    }
    header {
      background: #161b22;
      border-bottom: 1px solid #30363d;
      padding: 14px 24px;
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 16px;
    }
    .hd-title { font-size: 16px; font-weight: 700; letter-spacing: -.01em; }
    .hd-sub   { font-size: 11px; color: #8b949e; margin-top: 3px; }
    .hd-right { display: flex; align-items: center; gap: 10px; }
    #clock { font-size: 12px; color: #8b949e; font-variant-numeric: tabular-nums; }
    #runBtn {
      height: 30px; padding: 0 12px;
      background: #21262d; border: 1px solid #30363d;
      color: #c9d1d9; border-radius: 6px;
      font-size: 12px; font-weight: 600; cursor: pointer;
    }
    #runBtn:hover { background: #30363d; border-color: #484f58; }
    #runBtn:disabled { opacity: .5; cursor: wait; }

    main { max-width: 1280px; margin: 0 auto; padding: 20px 16px; display: grid; gap: 32px; }

    .sec-hd {
      display: flex; align-items: baseline;
      justify-content: space-between;
      padding-bottom: 10px;
      border-bottom: 1px solid #21262d;
      margin-bottom: 14px;
    }
    .sec-title { font-size: 15px; font-weight: 700; }
    .sec-meta  { font-size: 11px; color: #8b949e; }

    .cards { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }

    .card {
      background: #161b22;
      border: 1px solid #30363d;
      border-radius: 10px;
      overflow: hidden;
    }
    .card-hd {
      padding: 11px 15px 11px 13px;
      border-bottom: 1px solid #30363d;
      display: flex; justify-content: space-between; align-items: center;
    }
    .card-hd.stable { border-left: 3px solid #3fb950; }
    .card-hd.offens { border-left: 3px solid #d29922; }
    .card-title { font-size: 13px; font-weight: 700; }
    .card-title.stable { color: #3fb950; }
    .card-title.offens { color: #d29922; }
    .card-perf { font-size: 11px; color: #484f58; }
    .card-note {
      padding: 7px 15px;
      font-size: 11px; color: #484f58;
      background: #0d1117;
      border-top: 1px solid #21262d;
    }

    .msg-row { padding: 16px 15px; color: #8b949e; font-size: 13px; }
    .msg-row.err { color: #f85149; }

    table { width: 100%; border-collapse: collapse; }
    th, td {
      padding: 9px 15px;
      text-align: right;
      white-space: nowrap;
      border-bottom: 1px solid #21262d;
    }
    th:first-child, td:first-child { text-align: left; }
    th {
      font-size: 10px; font-weight: 700;
      color: #484f58; text-transform: uppercase; letter-spacing: .05em;
      background: #0d1117;
    }
    tbody tr { transition: background .1s; }
    tbody tr:hover { background: rgba(139,148,158,.05); }
    tbody tr:last-child td { border-bottom: none; }

    .sym { font-size: 14px; font-weight: 800; color: #58a6ff; letter-spacing: -.02em; }
    .rk {
      display: inline-flex; align-items: center; justify-content: center;
      width: 22px; height: 22px; border-radius: 50%;
      font-size: 11px; font-weight: 800;
    }
    .rk.s-hi  { background: #3fb950; color: #0d1117; }
    .rk.s-lo  { background: #21262d; color: #8b949e; }
    .rk.o-hi  { background: #d29922; color: #0d1117; }
    .pos { color: #3fb950; font-weight: 600; font-variant-numeric: tabular-nums; }
    .neg { color: #f85149; font-weight: 600; font-variant-numeric: tabular-nums; }
    .na  { color: #484f58; }
    .num { color: #c9d1d9; font-variant-numeric: tabular-nums; }

    @media (max-width: 760px) {
      .cards  { grid-template-columns: 1fr; }
      header  { flex-direction: column; align-items: flex-start; }
      main    { padding: 12px; gap: 20px; }
    }
  </style>
</head>
<body>
<header>
  <div>
    <div class="hd-title">VIX × Breadth 选股信号</div>
    <div class="hd-sub">信号激活时参考 · 数据来自 Yahoo Finance</div>
  </div>
  <div class="hd-right">
    <span id="clock">—</span>
    <button id="runBtn">⟳ 刷新</button>
  </div>
</header>
""" + _NAV + r"""
<main>
  <div>
    <div class="sec-hd">
      <span class="sec-title">NASDAQ 100 / QQQ</span>
      <span class="sec-meta" id="nasdaqMeta">—</span>
    </div>
    <div class="cards">
      <div class="card">
        <div class="card-hd stable">
          <span class="card-title stable">稳健核心 · ADV Top5</span>
          <span class="card-perf">CAGR 44–49% · MaxDD ~22%</span>
        </div>
        <div class="msg-row" id="nasdaqAdvMsg">正在加载…</div>
        <table id="nasdaqAdvTbl" style="display:none">
          <thead><tr><th>股票</th><th>#</th><th>收盘价</th><th>距 MA200</th><th>63日均量</th></tr></thead>
          <tbody id="nasdaqAdvBody"></tbody>
        </table>
        <div class="card-note">深绿 Top3 建议买入 · 浅色 4–5 为可选扩展</div>
      </div>
      <div class="card">
        <div class="card-hd offens">
          <span class="card-title offens">进攻首选 · ADV Top10 → MA200 Top3</span>
          <span class="card-perf">CAGR 52% · MaxDD ~32%</span>
        </div>
        <div class="msg-row" id="nasdaqMaMsg">正在加载…</div>
        <table id="nasdaqMaTbl" style="display:none">
          <thead><tr><th>股票</th><th>#</th><th>收盘价</th><th>MA200</th><th>超出幅度 ↑</th><th>63日均量</th></tr></thead>
          <tbody id="nasdaqMaBody"></tbody>
        </table>
        <div class="card-note">ADV Top10 中选距 MA200 最远的 3 只 · 动量最强但回撤更大</div>
      </div>
    </div>
  </div>
  <div>
    <div class="sec-hd">
      <span class="sec-title">S&amp;P 500 / SPY</span>
      <span class="sec-meta" id="sp500Meta">—</span>
    </div>
    <div class="cards">
      <div class="card">
        <div class="card-hd stable">
          <span class="card-title stable">稳健核心 · ADV Top5</span>
          <span class="card-perf">流动性加权 · 等权买入</span>
        </div>
        <div class="msg-row" id="sp500AdvMsg">正在加载…</div>
        <table id="sp500AdvTbl" style="display:none">
          <thead><tr><th>股票</th><th>#</th><th>收盘价</th><th>距 MA200</th><th>63日均量</th></tr></thead>
          <tbody id="sp500AdvBody"></tbody>
        </table>
        <div class="card-note">深绿 Top3 · 同公司双重股权已去重</div>
      </div>
      <div class="card">
        <div class="card-hd offens">
          <span class="card-title offens">进攻首选 · ADV Top10 → MA200 Top3</span>
          <span class="card-perf">动量最强 3 只</span>
        </div>
        <div class="msg-row" id="sp500MaMsg">正在加载…</div>
        <table id="sp500MaTbl" style="display:none">
          <thead><tr><th>股票</th><th>#</th><th>收盘价</th><th>MA200</th><th>超出幅度 ↑</th><th>63日均量</th></tr></thead>
          <tbody id="sp500MaBody"></tbody>
        </table>
        <div class="card-note">ADV Top10 池内按 MA200 距离排序，取前 3</div>
      </div>
    </div>
  </div>
</main>
<script>
  const P2 = new Intl.NumberFormat("en-US", { minimumFractionDigits:2, maximumFractionDigits:2 });
  const P1 = new Intl.NumberFormat("en-US", { minimumFractionDigits:1, maximumFractionDigits:1 });
  const P0 = new Intl.NumberFormat("en-US", { maximumFractionDigits:0 });
  function money(v) {
    if (v >= 1e9) return "$" + P2.format(v/1e9) + "B";
    if (v >= 1e6) return "$" + P2.format(v/1e6) + "M";
    return "$" + P0.format(v);
  }
  function distCell(pct) {
    if (pct == null) return '<span class="na">N/A</span>';
    const cls = pct >= 0 ? "pos" : "neg";
    const sgn = pct >= 0 ? "+" : "";
    return '<span class="' + cls + '">' + sgn + P1.format(pct) + "%</span>";
  }
  function advRow(r) {
    const rc = r.rank <= 3 ? "s-hi" : "s-lo";
    return "<tr>"
      + "<td><span class='sym'>" + r.symbol + "</span></td>"
      + "<td><span class='rk " + rc + "'>" + r.rank + "</span></td>"
      + "<td class='num'>$" + P2.format(r.close) + "</td>"
      + "<td>" + distCell(r.distance_pct) + "</td>"
      + "<td class='num'>" + money(r.adv63) + "</td>"
      + "</tr>";
  }
  function maRow(r) {
    const ma = r.ma200 != null
      ? "<span class='num'>$" + P2.format(r.ma200) + "</span>"
      : '<span class="na">N/A</span>';
    return "<tr>"
      + "<td><span class='sym'>" + r.symbol + "</span></td>"
      + "<td><span class='rk o-hi'>" + r.rank + "</span></td>"
      + "<td class='num'>$" + P2.format(r.close) + "</td>"
      + "<td>" + ma + "</td>"
      + "<td>" + distCell(r.distance_pct) + "</td>"
      + "<td class='num'>" + money(r.adv63) + "</td>"
      + "</tr>";
  }
  function show(tblId, msgId, rows, renderFn) {
    document.getElementById(tblId.replace("Tbl","Body")).innerHTML = rows.map(renderFn).join("");
    document.getElementById(msgId).style.display = "none";
    document.getElementById(tblId).style.display = "";
  }
  function renderUniverse(data, prefix) {
    show(prefix+"AdvTbl", prefix+"AdvMsg", data.adv_selected,  advRow);
    show(prefix+"MaTbl",  prefix+"MaMsg",  data.ma200_selected, maRow);
    document.getElementById(prefix+"Meta").textContent =
      "截至 " + data.as_of + " · " + data.valid_count + "/" + data.universe_count + " 有效";
  }
  function setLoading() {
    ["nasdaq","sp500"].forEach(p => {
      ["AdvMsg","MaMsg"].forEach(s => {
        const el = document.getElementById(p+s);
        el.textContent = "正在抓取并计算…"; el.className = "msg-row"; el.style.display = "";
      });
      ["AdvTbl","MaTbl"].forEach(s => { document.getElementById(p+s).style.display = "none"; });
      document.getElementById(p+"Meta").textContent = "—";
    });
  }
  function setError(msg) {
    ["nasdaq","sp500"].forEach(p =>
      ["AdvMsg","MaMsg"].forEach(s => {
        const el = document.getElementById(p+s);
        el.textContent = "错误: " + msg; el.className = "msg-row err";
      })
    );
  }
  async function runSignal() {
    const btn = document.getElementById("runBtn");
    btn.disabled = true; setLoading();
    try {
      const res  = await fetch("/api/signals");
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "请求失败");
      document.getElementById("clock").textContent = data.generated_at.replace("T"," ");
      renderUniverse(data.nasdaq100, "nasdaq");
      renderUniverse(data.sp500,     "sp500");
    } catch(err) { setError(err.message); }
    finally { btn.disabled = false; }
  }
  document.getElementById("runBtn").addEventListener("click", runSignal);
  runSignal();
</script>
</body>
</html>
"""

# ── HTML: breadth page ────────────────────────────────────────────────────────
BREADTH_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Breadth Monitor — VIX & Area Cross 2D</title>
  <script src="https://cdn.plot.ly/plotly-2.27.0.min.js"></script>
  <style>
    *, *::before, *::after { box-sizing:border-box; margin:0; padding:0; }
    body { background:#0d1117; color:#e6edf3;
           font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
           font-size:13px; min-height:100vh; }
    header { background:#161b22; border-bottom:1px solid #30363d;
             padding:10px 20px; display:flex; align-items:center; gap:12px; flex-wrap:wrap; }
    header h1 { font-size:15px; font-weight:600; color:#58a6ff; }
    .header-meta { font-size:11px; color:#8b949e; margin-left:auto; }
    #refreshBtn { background:#21262d; border:1px solid #30363d; color:#c9d1d9;
                  border-radius:6px; padding:4px 12px; font-size:12px; cursor:pointer; }
    #refreshBtn:hover { background:#30363d; }
    .status-bar { display:flex; gap:10px; padding:10px 16px; background:#161b22;
                  border-bottom:1px solid #30363d; flex-wrap:wrap; align-items:center; }
    .card { background:#21262d; border:1px solid #30363d; border-radius:8px;
            padding:7px 14px; min-width:105px; text-align:center; }
    .card .lbl { font-size:10px; color:#8b949e; margin-bottom:2px;
                 text-transform:uppercase; letter-spacing:.4px; }
    .card .val { font-size:20px; font-weight:700; font-variant-numeric:tabular-nums; }
    .card .dlt { font-size:10px; margin-top:2px; }
    .green{color:#3fb950} .red{color:#f85149} .yellow{color:#d29922}
    .blue{color:#58a6ff}  .gray{color:#8b949e}
    .badge { border-radius:20px; padding:3px 12px; font-size:12px; font-weight:600;
             letter-spacing:.4px; white-space:nowrap; }
    .safe    { background:#1a3a1a; color:#3fb950; border:1px solid #3fb950; }
    .caution { background:#2d2200; color:#d29922; border:1px solid #d29922; }
    .panic   { background:#3a1a1a; color:#f85149; border:1px solid #f85149; }
    .allow   { background:#1a3a1a; color:#3fb950; border:1px solid #3fb950; }
    .wait    { background:#21262d; color:#8b949e; border:1px solid #30363d; }
    .controls { display:flex; gap:8px; padding:8px 16px; border-bottom:1px solid #21262d;
                align-items:center; flex-wrap:wrap; }
    .lbl-sm { color:#8b949e; font-size:11px; }
    .btn-grp { display:flex; gap:3px; }
    .btn { background:#21262d; border:1px solid #30363d; color:#c9d1d9;
           border-radius:5px; padding:4px 10px; font-size:11px; cursor:pointer; }
    .btn:hover { background:#30363d; }
    .btn.active { background:#1f6feb; border-color:#388bfd; color:#fff; }
    #chartWrap { padding:4px 8px 12px; }
    #loadMsg { display:flex; flex-direction:column; align-items:center;
               justify-content:center; min-height:60vh; gap:16px;
               color:#8b949e; text-align:center; }
    #loadMsg h2 { color:#58a6ff; }
    .spinner { width:40px; height:40px; border:3px solid #30363d;
               border-top-color:#58a6ff; border-radius:50%;
               animation:spin 0.8s linear infinite; }
    @keyframes spin { to { transform:rotate(360deg); } }
  </style>
</head>
<body>
<header>
  <h1>VIX &amp; Area Cross 2D — Breadth Monitor</h1>
  <span style="font-size:11px;color:#8b949e">S&amp;P 500 · Hourly · yfinance</span>
  <div class="header-meta">
    Generated: <span id="genTime">—</span> &nbsp;|&nbsp; <span id="nStocks">—</span> stocks
    &nbsp;&nbsp;
    <button id="refreshBtn" onclick="location.reload()">⟳ Refresh</button>
    <span id="autoReload" style="font-size:11px;color:#484f58;margin-left:8px"></span>
  </div>
</header>
""" + _NAV + r"""
<div class="status-bar" id="statusBar" style="display:none">
  <div class="card">
    <div class="lbl">Strong</div>
    <div class="val green" id="vS">—</div>
    <div class="dlt gray"  id="dS">—</div>
  </div>
  <div class="card">
    <div class="lbl">Breakdown</div>
    <div class="val" id="vBD">—</div>
    <div class="dlt gray" id="dBD">—</div>
  </div>
  <div class="card">
    <div class="lbl">3M–30D (Mid)</div>
    <div class="val blue" id="vMid">—</div>
    <div class="dlt gray" id="dMid">—</div>
  </div>
  <div class="card">
    <div class="lbl">Net Momentum</div>
    <div class="val" id="vMom">—</div>
    <div class="dlt gray" id="dMom">—</div>
  </div>
  <div style="margin-left:auto;display:flex;gap:10px;align-items:center;flex-wrap:wrap">
    <span class="lbl-sm">Phase</span>
    <span class="badge" id="phaseTag">—</span>
    <span class="lbl-sm" style="margin-left:4px">NTSS</span>
    <span class="badge" id="stateTag">—</span>
    <span class="badge" id="stageTag" style="display:none">—</span>
    <span class="lbl-sm" style="margin-left:4px">BL=35</span>
    <span class="badge" id="trigTag">—</span>
    <span style="font-size:10px;color:#484f58;margin-left:8px" id="lastBar">—</span>
  </div>
</div>

<div class="controls" id="ctrlBar" style="display:none">
  <span class="lbl-sm">Show last:</span>
  <div class="btn-grp" id="rangeGrp">
    <button class="btn" onclick="setRange(5)">5D</button>
    <button class="btn active" onclick="setRange(10)">10D</button>
    <button class="btn" onclick="setRange(20)">20D</button>
    <button class="btn" onclick="setRange(30)">30D</button>
    <button class="btn" onclick="setRange(0)">All</button>
  </div>
</div>

<div id="loadMsg">
  <div class="spinner"></div>
  <h2>Loading breadth data…</h2>
  <p id="loadDetail">Fetching from server…</p>
</div>

<div id="chartWrap" style="display:none">
  <div id="chartDiv"></div>
</div>

<script>
let DATA         = null;
let currentRange = 10;

const C = {
  strong:"#3fb950", breakdown:"#f85149",
  midPos:"#58a6ff", midNeg:"#f85149",
  momPos:"#3fb950", momNeg:"#f85149",
  ref:"rgba(139,148,158,0.35)", text:"#8b949e",
};

// ── Fetch with retry on 202 ───────────────────────────────────────────────────
async function loadData() {
  for (let attempt = 0; attempt < 60; attempt++) {
    try {
      const res = await fetch("/api/breadth");
      if (res.status === 202) {
        const j = await res.json();
        const detail = document.getElementById("loadDetail");
        if (j.status === "error") {
          detail.textContent = "Error: " + (j.error || j.message);
          detail.style.color = "#f85149";
        } else {
          detail.textContent = (j.message || "Computing…");
          detail.style.color = "";
        }
        await new Promise(r => setTimeout(r, 15000));
        continue;
      }
      if (!res.ok) throw new Error("HTTP " + res.status);
      DATA = await res.json();
      onDataReady();
      return;
    } catch(e) {
      document.getElementById("loadDetail").textContent = "Network error: " + e.message + " — retrying…";
      await new Promise(r => setTimeout(r, 15000));
    }
  }
  document.getElementById("loadDetail").textContent = "Timed out. Please refresh the page.";
}

function onDataReady() {
  document.getElementById("loadMsg").style.display   = "none";
  document.getElementById("chartWrap").style.display = "block";
  document.getElementById("statusBar").style.display = "flex";
  document.getElementById("ctrlBar").style.display   = "flex";
  document.getElementById("genTime").textContent = DATA.generated_at.replace("T"," ");
  document.getElementById("nStocks").textContent = DATA.n_stocks;
  updateStatus();
  render(currentRange);
  startAutoReload();
}

// ── Status cards ──────────────────────────────────────────────────────────────
function updateStatus() {
  const recs = DATA.records;
  const n    = recs.length - 1;
  if (n < 1) return;
  const cur  = recs[n];
  const prev = recs[n-1];
  const fmt  = (v, d) => v != null ? v.toFixed(d==null?1:d) : "—";
  const sgn  = v => v > 0 ? "+" : "";

  function card(valId, dltId, cv, pv, sfx, posGood) {
    const el = document.getElementById(valId);
    const dl = document.getElementById(dltId);
    const d  = (cv != null && pv != null) ? cv - pv : null;
    el.textContent = fmt(cv) + (sfx||"");
    if      (valId==="vS")   el.className = "val " + (cv >= 35 ? "green" : "red");
    else if (valId==="vBD")  el.className = "val " + (cv >= 50 ? "red" : cv >= 35 ? "yellow" : "green");
    else if (valId==="vMid") el.className = "val " + (cv==null?"gray": cv<0?"red": cv<2?"yellow":"blue");
    else if (valId==="vMom") el.className = "val " + (cv==null?"gray": cv>=0?"green":"red");
    dl.textContent = d!=null ? sgn(d)+fmt(d,2)+(sfx||"")+" vs prev" : "—";
    dl.className   = d!=null ? "dlt "+(posGood?(d>=0?"green":"red"):(d<=0?"green":"red")) : "dlt gray";
  }
  card("vS",  "dS",  cur.s,  prev.s,  "%", true);
  card("vBD", "dBD", cur.bd, prev.bd, "%", false);
  card("vMid","dMid",cur.mid,prev.mid,"",  true);
  card("vMom","dMom",cur.mom,prev.mom,"",  true);

  const st = document.getElementById("stateTag");
  if (cur.mid!=null) {
    if      (cur.mid<0) { st.textContent="PANIC";   st.className="badge panic"; }
    else if (cur.mid<2) { st.textContent="CAUTION"; st.className="badge caution"; }
    else                { st.textContent="SAFE";    st.className="badge safe"; }
  }
  const tr = document.getElementById("trigTag");
  const ok = cur.bd!=null && cur.bd<35;
  tr.textContent = ok ? "BL=35 ✓ ALLOW" : "BL=35 ✗ WAIT";
  tr.className   = "badge " + (ok ? "allow" : "wait");

  // ── Market phase (Strong × BD) ───────────────────────────────────────────
  const ph = document.getElementById("phaseTag");
  if (ph && cur.s!=null && cur.bd!=null) {
    const s = cur.s, bd = cur.bd, mid = cur.mid;
    let phase, cls;
    if      (s>55 && bd<20)  { phase="A 全面牛市"; cls="safe"; }
    else if (s>40 && bd<30)  { phase="B 强势整固"; cls="safe"; }
    else if (s>35 && bd<45)  { phase="C 牛市回调"; cls="safe"; }
    else if (s>25 && bd<35)  { phase="D 修复中";   cls="safe"; }
    else if (s>20 && bd<50)  { phase="E 震荡整理"; cls="caution"; }
    else if (s<20 && bd<40)  { phase="F 弱势未崩"; cls="caution"; }
    else if (s<30 && bd>50)  { phase="G 宽度承压"; cls="panic"; }
    else                     { phase="H 恐慌出清"; cls="panic"; }
    ph.textContent = phase;
    ph.className   = "badge " + cls;
  }

  // ── NTSS recovery stage (only shown when in panic/bear phase) ────────────
  const sg = document.getElementById("stageTag");
  if (sg && cur.mid!=null) {
    const m = cur.mid, s = cur.s, bd = cur.bd;
    const inPanic = s < 20 && bd > 55;
    if (inPanic) {
      let stage, scls;
      if      (m < -3) { stage="① 极端恐慌";  scls="panic"; }
      else if (m < -1) { stage="② 恐慌中";    scls="panic"; }
      else if (m <  0) { stage="③ 临近0轴";   scls="caution"; }
      else if (m <  1) { stage="④ 刚穿零";    scls="caution"; }
      else if (m <  2) { stage="⑤ 弱确认";    scls="caution"; }
      else             { stage="⑥ 强确认 ★";  scls="safe"; }
      sg.textContent = stage;
      sg.className   = "badge " + scls;
      sg.style.display = "";
    } else {
      sg.style.display = "none";
    }
  }

  document.getElementById("lastBar").textContent = "Last: " + cur.t + " ET";
}

// ── Data slice ────────────────────────────────────────────────────────────────
function sliceRecords(days) {
  const all = DATA.records;
  if (days === 0) return all;
  const dates = [...new Set(all.map(r => r.t.split(" ")[0]))].sort();
  const from  = days >= dates.length ? dates[0] : dates[dates.length - days];
  return all.filter(r => r.t.split(" ")[0] >= from);
}

// ── Buy period shapes ─────────────────────────────────────────────────────────
function buyPeriodShapes(recs) {
  const shapes = [];
  for (const pair of [[50,"rgba(63,185,80,0.07)"],[35,"rgba(63,185,80,0.18)"]]) {
    const limit = pair[0], color = pair[1];
    let start = null;
    for (let i = 0; i < recs.length; i++) {
      const active = recs[i].bd != null && recs[i].bd < limit;
      if (active && start === null) { start = recs[i].t; }
      else if (!active && start !== null) {
        shapes.push({type:"rect",xref:"x",yref:"paper",
          x0:start,x1:recs[i-1].t,y0:0,y1:1,
          fillcolor:color,line:{width:0},layer:"below"});
        start = null;
      }
    }
    if (start !== null)
      shapes.push({type:"rect",xref:"x",yref:"paper",
        x0:start,x1:recs[recs.length-1].t,y0:0,y1:1,
        fillcolor:color,line:{width:0},layer:"below"});
  }
  return shapes;
}

// ── Traces ────────────────────────────────────────────────────────────────────
function makeTraces(recs) {
  const T    = recs.map(r => r.t);
  const S    = recs.map(r => r.s);
  const BD   = recs.map(r => r.bd);
  const MID  = recs.map(r => r.mid);
  const MOM  = recs.map(r => r.mom);
  const A20  = recs.map(r => r.a20);
  const A50  = recs.map(r => r.a50);
  const A200 = recs.map(r => r.a200);
  const midColors = MID.map(v => v!=null && v<0 ? C.midNeg : C.midPos);
  const momColors = MOM.map(v => v!=null && v<0 ? C.momNeg : C.momPos);
  return [
    {x:T,y:S,  name:"Strong",      xaxis:"x",yaxis:"y",  type:"scatter",mode:"lines",
     line:{color:C.strong,width:2},fill:"tozeroy",fillcolor:"rgba(63,185,80,0.10)",
     hovertemplate:"<b>Strong</b>: %{y:.1f}%<extra></extra>"},
    {x:T,y:BD, name:"Breakdown",   xaxis:"x",yaxis:"y",  type:"scatter",mode:"lines",
     line:{color:C.breakdown,width:2,dash:"dot"},fill:"tozeroy",fillcolor:"rgba(248,81,73,0.08)",
     hovertemplate:"<b>Breakdown</b>: %{y:.1f}%<extra></extra>"},
    {x:T,y:A20,name:">20d MA",     xaxis:"x",yaxis:"y2", type:"scatter",mode:"lines",
     line:{color:"#f0a500",width:1.5},hovertemplate:"<b>>20d</b>: %{y:.1f}%<extra></extra>"},
    {x:T,y:A50,name:">50d MA",     xaxis:"x",yaxis:"y2", type:"scatter",mode:"lines",
     line:{color:"#58a6ff",width:1.5},hovertemplate:"<b>>50d</b>: %{y:.1f}%<extra></extra>"},
    {x:T,y:A200,name:">200d MA",   xaxis:"x",yaxis:"y2", type:"scatter",mode:"lines",
     line:{color:"#3fb950",width:1.5},hovertemplate:"<b>>200d</b>: %{y:.1f}%<extra></extra>"},
    {x:T,y:MID,name:"3M-30D(Mid)", xaxis:"x",yaxis:"y3", type:"bar",marker:{color:midColors},
     hovertemplate:"<b>3M-30D</b>: %{y:.2f}<extra></extra>"},
    {x:T,y:MOM,name:"Momentum",    xaxis:"x",yaxis:"y4", type:"bar",marker:{color:momColors},
     hovertemplate:"<b>Mom</b>: %{y:.2f}<extra></extra>"},
  ];
}

// ── Layout ────────────────────────────────────────────────────────────────────
function makeLayout(recs) {
  const grid = "#21262d";
  const rl   = (yr, y0) => ({type:"line",xref:"paper",yref:yr,x0:0,x1:1,y0,y1:y0,
                               line:{color:C.ref,width:1,dash:"dot"}});
  const shapes = [
    ...buyPeriodShapes(recs),
    rl("y",35),rl("y",50),rl("y2",35),rl("y2",50),
    rl("y3",2),rl("y3",1),
    {type:"line",xref:"paper",yref:"y3",x0:0,x1:1,y0:-1,y1:-1,line:{color:"rgba(248,81,73,0.35)",width:1,dash:"dot"}},
    {type:"line",xref:"paper",yref:"y3",x0:0,x1:1,y0:-3,y1:-3,line:{color:"rgba(248,81,73,0.6)",width:1,dash:"dot"}},
    {type:"line",xref:"paper",yref:"y3",x0:0,x1:1,y0:0,y1:0,line:{color:"rgba(139,148,158,0.6)",width:1.5}},
    rl("y4",5),rl("y4",-5),
    {type:"line",xref:"paper",yref:"y4",x0:0,x1:1,y0:0,y1:0,line:{color:"rgba(139,148,158,0.6)",width:1.5}},
  ];
  const lbl  = (yr, txt) => ({xref:"paper",yref:yr,x:0.01,y:1,text:"<b>"+txt+"</b>",
                               showarrow:false,font:{color:"#c9d1d9",size:10},
                               xanchor:"left",yanchor:"top"});
  const rlbl = (yr, y, txt) => ({xref:"paper",yref:yr,x:1.002,y,text:txt,
                                  showarrow:false,font:{color:C.ref,size:9},xanchor:"left"});
  return {
    paper_bgcolor:"#0d1117", plot_bgcolor:"#0d1117",
    font:{color:C.text,size:11},
    margin:{l:52,r:36,t:12,b:36},
    height:Math.max(window.innerHeight-230,480),
    showlegend:true,
    legend:{orientation:"h",x:0,y:-0.04,font:{size:10},bgcolor:"rgba(0,0,0,0)"},
    hovermode:"x unified",
    xaxis:{domain:[0,1],type:"date",gridcolor:grid,linecolor:grid,tickfont:{size:10},showgrid:true,
           rangebreaks:[{bounds:["sat","mon"]},{bounds:[17,9],pattern:"hour"}]},
    yaxis: {domain:[0.77,1.00],range:[0,105],gridcolor:grid,ticksuffix:"%",zeroline:false},
    yaxis2:{domain:[0.52,0.75],range:[0,105],gridcolor:grid,ticksuffix:"%",zeroline:false},
    yaxis3:{domain:[0.27,0.50],gridcolor:grid,zeroline:false},
    yaxis4:{domain:[0.00,0.24],gridcolor:grid,zeroline:false},
    shapes,
    annotations:[
      lbl("y",  "Strong / Breakdown %"),
      lbl("y2", "% above 20d / 50d / 200d daily MA"),
      lbl("y3", "3M–30D Mid  [VIX3M−VIX]"),
      lbl("y4", "Net Momentum"),
      rlbl("y",35,"35"),rlbl("y",50,"50"),
      rlbl("y2",35,"35"),rlbl("y2",50,"50"),
      rlbl("y3",2," 2"),rlbl("y3",1," 1"),rlbl("y3",0," 0"),
      rlbl("y3",-1,"-1"),rlbl("y3",-3,"-3"),
      rlbl("y4",5,"+5"),rlbl("y4",-5,"-5"),
    ],
  };
}

// ── Render ────────────────────────────────────────────────────────────────────
function render(days) {
  currentRange = days;
  const recs = sliceRecords(days);
  Plotly.react("chartDiv", makeTraces(recs), makeLayout(recs), {
    responsive:true, displayModeBar:true, displaylogo:false,
    modeBarButtonsToRemove:["select2d","lasso2d","autoScale2d"],
  });
}

function setRange(days) {
  document.querySelectorAll("#rangeGrp .btn").forEach((b,i) => {
    b.classList.toggle("active", [5,10,20,30,0][i] === days);
  });
  if (DATA) render(days);
}

window.addEventListener("resize", () => {
  if (DATA) Plotly.relayout("chartDiv", {height:Math.max(window.innerHeight-230,480)});
});

// ── Auto-reload countdown ─────────────────────────────────────────────────────
function startAutoReload() {
  let rem = 60 * 60 * 1000;
  const el = document.getElementById("autoReload");
  const tick = setInterval(() => {
    rem -= 1000;
    if (rem <= 0) { clearInterval(tick); location.reload(); return; }
    const m = Math.floor(rem/60000);
    const s = Math.floor((rem%60000)/1000);
    if (el) el.textContent = "auto-reload in " + m + ":" + String(s).padStart(2,"0");
  }, 1000);
}

loadData();
</script>
</body>
</html>
"""
