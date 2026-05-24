#!/usr/bin/env python3
"""Live stock-selection web app.

Strategies shown side by side for NASDAQ100 and S&P500:
  稳健核心 — ADV Top5  (rank by 63-day avg dollar volume, pick top 5)
  进攻首选 — Top10→MA200 Top3  (ADV Top10 pool, then rank by close/MA200-1, pick top 3)
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from io import StringIO
from pathlib import Path
from typing import Any

import pandas as pd
import requests
import yfinance as yf
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse

from ibkr_quant.breadth import BreadthComputer


import os

NASDAQ100_URL = "https://en.wikipedia.org/wiki/Nasdaq-100"
SP500_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
CACHE_DIR = Path(os.environ.get("CACHE_DIR", "/tmp"))

app = FastAPI(title="Market Vital Signs (MVS)")
_memory_cache: dict[str, tuple[datetime, Any]] = {}


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
        "nasdaq100_current_wikipedia.csv" if universe == "nasdaq100" else "sp500_current_wikipedia.csv"
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
        yf_symbols,
        period="18mo",
        interval="1d",
        group_by="ticker",
        auto_adjust=True,
        progress=False,
        threads=True,
    )
    return cache_set(key, flatten_yfinance_frame(frame, yf_symbols))


def issuer_key(symbol: str) -> str:
    same = {"GOOG": "GOOGL", "GOOGL": "GOOGL", "FOX": "FOXA", "FOXA": "FOXA", "NWS": "NWSA", "NWSA": "NWSA"}
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
        clean["Close"] = pd.to_numeric(clean["Close"], errors="coerce")
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

        rows.append({
            "symbol": symbol,
            "last_date": last_date,
            "close": round(last_close, 2),
            "adv63": adv63,
            "ma200": round(ma200, 2) if ma200 is not None else None,
            "distance_pct": distance_pct,
        })

    rows.sort(key=lambda r: r["adv63"], reverse=True)
    for idx, r in enumerate(rows, 1):
        r["adv_rank"] = idx

    # ADV pool: top adv_pool_size unique issuers by ADV
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

    # ADV Top5 selection (stable)
    adv_selected = [
        {
            "symbol": r["symbol"],
            "close": r["close"],
            "adv63": r["adv63"],
            "adv_rank": r["adv_rank"],
            "ma200": r["ma200"],
            "distance_pct": r["distance_pct"],
            "rank": idx,
            "is_top3": idx <= 3,
        }
        for idx, r in enumerate(pool[:5], 1)
    ]

    # MA200 Top3 selection (offensive): sort pool by distance_pct desc
    ma_pool = [r for r in pool if r["distance_pct"] is not None]
    ma_sorted = sorted(ma_pool, key=lambda r: r["distance_pct"], reverse=True)
    ma200_selected = [
        {
            "symbol": r["symbol"],
            "close": r["close"],
            "adv63": r["adv63"],
            "adv_rank": r["adv_rank"],
            "ma200": r["ma200"],
            "distance_pct": r["distance_pct"],
            "rank": idx,
        }
        for idx, r in enumerate(ma_sorted[:3], 1)
    ]

    as_of = max((r["last_date"] for r in rows), default=None)
    return {
        "as_of": as_of,
        "universe": universe,
        "universe_count": len(symbols),
        "valid_count": len(rows),
        "failed_count": len(failed_symbols),
        "adv_selected": adv_selected,
        "ma200_selected": ma200_selected,
    }


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return HTML


@app.get("/api/signals")
def api_signals() -> JSONResponse:
    try:
        return JSONResponse({
            "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "nasdaq100": compute_signals("nasdaq100"),
            "sp500": compute_signals("sp500"),
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
    cached = cache_get("breadth:daily", ttl_minutes=60)
    if cached is not None:
        return JSONResponse(cached)

    try:
        snapshot = BreadthComputer(CACHE_DIR / "ema_state.json").update(date.today())
        payload = {
            "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "date": snapshot.date.isoformat(),
            "s5th": snapshot.s5th,
            "s5fi": snapshot.s5fi,
            "s5tw": snapshot.s5tw,
            "previous_s5th": snapshot.previous_s5th,
            "previous_s5fi": snapshot.previous_s5fi,
            "previous_s5tw": snapshot.previous_s5tw,
            "delta_s5th": snapshot.s5th - snapshot.previous_s5th,
            "delta_s5fi": snapshot.s5fi - snapshot.previous_s5fi,
            "delta_s5tw": snapshot.s5tw - snapshot.previous_s5tw,
        }
        return JSONResponse(cache_set("breadth:daily", payload))
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


@app.get("/breadth", response_class=HTMLResponse)
def breadth_page() -> str:
    return BREADTH_HTML


HTML = r"""
<!doctype html>
<html lang="zh">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Market Vital Signs (MVS) 选股信号</title>
  <style>
    :root {
      --bg: #f4f5f7;
      --panel: #ffffff;
      --text: #1b1f24;
      --muted: #6b7280;
      --line: #e2e6ed;
      --stable:      #0f766e;
      --stable-bg:   #f0fdf4;
      --stable-line: #86efac;
      --stable-dark: #166534;
      --offens:      #b45309;
      --offens-bg:   #fffbeb;
      --offens-line: #fcd34d;
      --offens-dark: #92400e;
      --sym:   #1d4ed8;
      --pos:   #067647;
      --neg:   #b42318;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: var(--bg);
      color: var(--text);
      font-size: 14px;
    }
    header {
      background: var(--panel);
      border-bottom: 1px solid var(--line);
      padding: 16px 24px;
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 16px;
    }
    .hd-left h1 { margin: 0 0 3px; font-size: 18px; }
    .hd-left p  { margin: 0; font-size: 13px; color: var(--muted); }
    .hd-right   { display: flex; align-items: center; gap: 10px; flex-shrink: 0; }
    #clock { font-size: 12px; color: var(--muted); }
    button {
      height: 34px;
      padding: 0 14px;
      border: none;
      border-radius: 6px;
      font-size: 13px;
      font-weight: 600;
      cursor: pointer;
      background: var(--stable);
      color: white;
    }
    button:disabled { opacity: .55; cursor: wait; }
    .nav {
      background: var(--panel);
      border-bottom: 1px solid var(--line);
      padding: 0 24px;
      display: flex;
      gap: 4px;
    }
    .nav a {
      color: var(--muted);
      text-decoration: none;
      padding: 10px 12px;
      font-size: 13px;
      font-weight: 700;
      border-bottom: 2px solid transparent;
    }
    .nav a:hover { color: var(--text); }
    .nav a.active { color: var(--stable-dark); border-bottom-color: var(--stable); }
    main { max-width: 1300px; margin: 0 auto; padding: 18px; display: grid; gap: 20px; }

    /* Universe block */
    .universe { display: grid; gap: 10px; }
    .universe-label {
      font-size: 15px;
      font-weight: 700;
      padding: 0 2px;
      display: flex;
      justify-content: space-between;
      align-items: baseline;
    }
    .universe-meta { font-size: 12px; color: var(--muted); font-weight: 400; }
    .cards { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }

    /* Card */
    .card { background: var(--panel); border: 1px solid var(--line); border-radius: 10px; overflow: hidden; }
    .card-hd {
      padding: 11px 15px;
      border-bottom: 1px solid var(--line);
      display: flex;
      justify-content: space-between;
      align-items: baseline;
      gap: 10px;
    }
    .card-hd.stable { background: var(--stable-bg); border-bottom-color: var(--stable-line); }
    .card-hd.offens { background: var(--offens-bg); border-bottom-color: var(--offens-line); }
    .card-title { font-weight: 700; font-size: 13px; }
    .card-title.stable { color: var(--stable-dark); }
    .card-title.offens { color: var(--offens-dark); }
    .card-sub  { font-size: 11px; color: var(--muted); }
    .card-note {
      padding: 7px 14px;
      font-size: 11px;
      color: var(--muted);
      border-top: 1px solid var(--line);
      background: #fafbfc;
    }

    /* Spinner / message rows */
    .msg-row { padding: 14px 15px; color: var(--muted); font-size: 13px; }
    .msg-row.err { color: var(--neg); }

    /* Table */
    table { width: 100%; border-collapse: collapse; font-size: 13px; }
    th, td {
      padding: 8px 11px;
      border-bottom: 1px solid var(--line);
      text-align: right;
      white-space: nowrap;
    }
    th:first-child, td:first-child { text-align: left; }
    th {
      color: var(--muted);
      font-size: 11px;
      font-weight: 700;
      background: #fbfcfe;
      text-transform: uppercase;
      letter-spacing: .03em;
    }
    tr:last-child td { border-bottom: none; }

    /* Symbol */
    .sym { font-weight: 800; color: var(--sym); letter-spacing: -.01em; }

    /* Rank badge */
    .badge {
      display: inline-flex; align-items: center; justify-content: center;
      min-width: 26px; height: 20px; padding: 0 6px;
      border-radius: 999px; font-size: 11px; font-weight: 800;
    }
    .badge.stable { background: var(--stable-dark); color: #fff; }
    .badge.offens { background: var(--offens-dark); color: #fff; }
    .badge.dim    { background: #e5e7eb; color: #6b7280; }

    /* Pct colouring */
    .pos { color: var(--pos); font-weight: 600; }
    .neg { color: var(--neg); font-weight: 600; }
    .na  { color: var(--muted); }

    @media (max-width: 800px) {
      .cards  { grid-template-columns: 1fr; }
      header  { flex-direction: column; align-items: flex-start; }
      main    { padding: 12px; }
    }
  </style>
</head>
<body>
<header>
  <div class="hd-left">
    <h1>Market Vital Signs <span style="font-size:13px;font-weight:400;opacity:.6;">MVS</span></h1>
    <p>宽度健康时选股 · 两种策略对比 · 数据来自 Yahoo Finance</p>
  </div>
  <div class="hd-right">
    <span id="clock">-</span>
    <button id="runBtn">刷新</button>
  </div>
</header>
<nav class="nav">
  <a class="active" href="/">选股信号</a>
  <a href="/breadth">市场宽度</a>
</nav>

<main>
  <!-- NASDAQ100 -->
  <div class="universe">
    <div class="universe-label">
      <span>NASDAQ100 / QQQ</span>
      <span class="universe-meta" id="nasdaqMeta"></span>
    </div>
    <div class="cards">
      <!-- ADV stable -->
      <div class="card">
        <div class="card-hd stable">
          <span class="card-title stable">稳健核心 · ADV Top5</span>
          <span class="card-sub">CAGR 44–49% · MaxDD ~22%</span>
        </div>
        <div class="msg-row" id="nasdaqAdvMsg">正在加载…</div>
        <table id="nasdaqAdvTbl" style="display:none">
          <thead><tr>
            <th>股票</th><th>排名</th><th>收盘价</th><th>距MA200</th><th>63日均成交额</th>
          </tr></thead>
          <tbody id="nasdaqAdvBody"></tbody>
        </table>
        <div class="card-note">绿色 Top3 = ADV Top3（更集中）；浅色 4–5 = 可选扩展。</div>
      </div>
      <!-- MA200 offensive -->
      <div class="card">
        <div class="card-hd offens">
          <span class="card-title offens">进攻首选 · ADV Top10 → MA200 Top3</span>
          <span class="card-sub">CAGR 52% · MaxDD ~32%</span>
        </div>
        <div class="msg-row" id="nasdaqMaMsg">正在加载…</div>
        <table id="nasdaqMaTbl" style="display:none">
          <thead><tr>
            <th>股票</th><th>动量排名</th><th>收盘价</th><th>MA200</th><th>距MA200 ↑</th><th>63日均成交额</th>
          </tr></thead>
          <tbody id="nasdaqMaBody"></tbody>
        </table>
        <div class="card-note">ADV Top10 中按 close/MA200−1 最高的3只；动量最强但回撤更大。</div>
      </div>
    </div>
  </div>

  <!-- S&P500 -->
  <div class="universe">
    <div class="universe-label">
      <span>S&amp;P500 / SPY</span>
      <span class="universe-meta" id="sp500Meta"></span>
    </div>
    <div class="cards">
      <div class="card">
        <div class="card-hd stable">
          <span class="card-title stable">稳健核心 · ADV Top5</span>
          <span class="card-sub">流动性加权，等权买入</span>
        </div>
        <div class="msg-row" id="sp500AdvMsg">正在加载…</div>
        <table id="sp500AdvTbl" style="display:none">
          <thead><tr>
            <th>股票</th><th>排名</th><th>收盘价</th><th>距MA200</th><th>63日均成交额</th>
          </tr></thead>
          <tbody id="sp500AdvBody"></tbody>
        </table>
        <div class="card-note">绿色 Top3 = ADV Top3；同公司双重股权已去重。</div>
      </div>
      <div class="card">
        <div class="card-hd offens">
          <span class="card-title offens">进攻首选 · ADV Top10 → MA200 Top3</span>
          <span class="card-sub">动量最强3只</span>
        </div>
        <div class="msg-row" id="sp500MaMsg">正在加载…</div>
        <table id="sp500MaTbl" style="display:none">
          <thead><tr>
            <th>股票</th><th>动量排名</th><th>收盘价</th><th>MA200</th><th>距MA200 ↑</th><th>63日均成交额</th>
          </tr></thead>
          <tbody id="sp500MaBody"></tbody>
        </table>
        <div class="card-note">ADV Top10 池内按 MA200 距离排序，取前3。</div>
      </div>
    </div>
  </div>
</main>

<script>
  const P2 = new Intl.NumberFormat("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const P1 = new Intl.NumberFormat("en-US", { minimumFractionDigits: 1, maximumFractionDigits: 1 });
  const P0 = new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 });

  function money(v) {
    if (v >= 1e9) return "$" + P2.format(v / 1e9) + "B";
    if (v >= 1e6) return "$" + P2.format(v / 1e6) + "M";
    return "$" + P0.format(v);
  }

  function distCell(pct) {
    if (pct == null) return `<span class="na">N/A</span>`;
    const cls = pct >= 0 ? "pos" : "neg";
    const sign = pct >= 0 ? "+" : "";
    return `<span class="${cls}">${sign}${P1.format(pct)}%</span>`;
  }

  function advRow(r) {
    const badgeCls = r.rank <= 3 ? "stable" : "dim";
    return `<tr>
      <td><span class="sym">${r.symbol}</span></td>
      <td><span class="badge ${badgeCls}">${r.rank}</span></td>
      <td>$${P2.format(r.close)}</td>
      <td>${distCell(r.distance_pct)}</td>
      <td>${money(r.adv63)}</td>
    </tr>`;
  }

  function maRow(r) {
    const ma = r.ma200 != null ? "$" + P2.format(r.ma200) : `<span class="na">N/A</span>`;
    return `<tr>
      <td><span class="sym">${r.symbol}</span></td>
      <td><span class="badge offens">${r.rank}</span></td>
      <td>$${P2.format(r.close)}</td>
      <td>${ma}</td>
      <td>${distCell(r.distance_pct)}</td>
      <td>${money(r.adv63)}</td>
    </tr>`;
  }

  function show(tblId, msgId, rows, renderFn) {
    const tbl = document.getElementById(tblId);
    const msg = document.getElementById(msgId);
    document.getElementById(tblId.replace("Tbl", "Body")).innerHTML = rows.map(renderFn).join("");
    msg.style.display = "none";
    tbl.style.display = "";
  }

  function renderUniverse(data, prefix) {
    show(prefix + "AdvTbl", prefix + "AdvMsg", data.adv_selected, advRow);
    show(prefix + "MaTbl",  prefix + "MaMsg",  data.ma200_selected, maRow);
    document.getElementById(prefix + "Meta").textContent =
      `截至 ${data.as_of} · ${data.valid_count}/${data.universe_count} 有效`;
  }

  function setLoading() {
    ["nasdaq", "sp500"].forEach(p => {
      ["AdvMsg", "MaMsg"].forEach(s => {
        const el = document.getElementById(p + s);
        el.textContent = "正在抓取并计算…";
        el.className = "msg-row";
        el.style.display = "";
      });
      ["AdvTbl", "MaTbl"].forEach(s => {
        document.getElementById(p + s).style.display = "none";
      });
      document.getElementById(p + "Meta").textContent = "";
    });
  }

  function setError(msg) {
    ["nasdaq", "sp500"].forEach(p => {
      ["AdvMsg", "MaMsg"].forEach(s => {
        const el = document.getElementById(p + s);
        el.textContent = "错误: " + msg;
        el.className = "msg-row err";
      });
    });
  }

  async function runSignal() {
    const btn = document.getElementById("runBtn");
    btn.disabled = true;
    setLoading();
    try {
      const res = await fetch("/api/signals");
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "请求失败");
      document.getElementById("clock").textContent = data.generated_at.replace("T", " ");
      renderUniverse(data.nasdaq100, "nasdaq");
      renderUniverse(data.sp500, "sp500");
    } catch (err) {
      setError(err.message);
    } finally {
      btn.disabled = false;
    }
  }

  document.getElementById("runBtn").addEventListener("click", runSignal);
  runSignal();
</script>
</body>
</html>
"""

BREADTH_HTML = r"""
<!doctype html>
<html lang="zh">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Market Vital Signs (MVS) 市场宽度</title>
  <style>
    :root {
      --bg: #f4f5f7;
      --panel: #ffffff;
      --text: #1b1f24;
      --muted: #6b7280;
      --line: #e2e6ed;
      --stable: #0f766e;
      --stable-bg: #f0fdf4;
      --stable-dark: #166534;
      --warn: #b45309;
      --warn-bg: #fffbeb;
      --neg: #b42318;
      --neg-bg: #fef2f2;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: var(--bg);
      color: var(--text);
      font-size: 14px;
    }
    header {
      background: var(--panel);
      border-bottom: 1px solid var(--line);
      padding: 16px 24px;
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 16px;
    }
    .hd-left h1 { margin: 0 0 3px; font-size: 18px; }
    .hd-left p { margin: 0; font-size: 13px; color: var(--muted); }
    .nav {
      background: var(--panel);
      border-bottom: 1px solid var(--line);
      padding: 0 24px;
      display: flex;
      gap: 4px;
    }
    .nav a {
      color: var(--muted);
      text-decoration: none;
      padding: 10px 12px;
      font-size: 13px;
      font-weight: 700;
      border-bottom: 2px solid transparent;
    }
    .nav a:hover { color: var(--text); }
    .nav a.active { color: var(--stable-dark); border-bottom-color: var(--stable); }
    main { max-width: 1100px; margin: 0 auto; padding: 18px; display: grid; gap: 16px; }
    .grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 14px; }
    .card {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 10px;
      padding: 16px;
    }
    .label {
      color: var(--muted);
      font-size: 12px;
      font-weight: 800;
      text-transform: uppercase;
      letter-spacing: .03em;
    }
    .value {
      font-size: 34px;
      font-weight: 800;
      line-height: 1.1;
      margin-top: 8px;
      font-variant-numeric: tabular-nums;
    }
    .delta { margin-top: 6px; font-size: 13px; font-weight: 700; }
    .pos { color: var(--stable-dark); }
    .neg { color: var(--neg); }
    .meta {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 10px;
      padding: 14px 16px;
      color: var(--muted);
      display: flex;
      justify-content: space-between;
      gap: 12px;
      flex-wrap: wrap;
    }
    button {
      height: 34px;
      padding: 0 14px;
      border: none;
      border-radius: 6px;
      font-size: 13px;
      font-weight: 600;
      cursor: pointer;
      background: var(--stable);
      color: white;
    }
    .msg { color: var(--muted); }
    .err { color: var(--neg); }
    @media (max-width: 800px) {
      .grid { grid-template-columns: 1fr; }
      header { flex-direction: column; align-items: flex-start; }
      main { padding: 12px; }
    }
  </style>
</head>
<body>
<header>
  <div class="hd-left">
    <h1>Market Vital Signs <span style="font-size:13px;font-weight:400;opacity:.6;">MVS</span></h1>
    <p>S&amp;P 500 市场宽度 · EMA20 / EMA50 / EMA200</p>
  </div>
  <button id="runBtn">刷新</button>
</header>
<nav class="nav">
  <a href="/">选股信号</a>
  <a class="active" href="/breadth">市场宽度</a>
</nav>
<main>
  <div class="meta">
    <span id="status">正在加载市场宽度…</span>
    <span id="time">—</span>
  </div>
  <div class="grid">
    <div class="card">
      <div class="label">S5TH · Above EMA200</div>
      <div class="value" id="s5th">—</div>
      <div class="delta" id="dS5th">—</div>
    </div>
    <div class="card">
      <div class="label">S5FI · Above EMA50</div>
      <div class="value" id="s5fi">—</div>
      <div class="delta" id="dS5fi">—</div>
    </div>
    <div class="card">
      <div class="label">S5TW · Above EMA20</div>
      <div class="value" id="s5tw">—</div>
      <div class="delta" id="dS5tw">—</div>
    </div>
  </div>
</main>
<script>
  const P1 = new Intl.NumberFormat("en-US", { minimumFractionDigits: 1, maximumFractionDigits: 1 });
  function pct(v) { return P1.format(v) + "%"; }
  function delta(v) {
    const cls = v >= 0 ? "pos" : "neg";
    const sign = v >= 0 ? "+" : "";
    return `<span class="${cls}">${sign}${P1.format(v)} pts vs prev</span>`;
  }
  async function loadBreadth() {
    const btn = document.getElementById("runBtn");
    btn.disabled = true;
    document.getElementById("status").textContent = "正在计算市场宽度…";
    document.getElementById("status").className = "msg";
    try {
      const res = await fetch("/api/breadth");
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "请求失败");
      document.getElementById("s5th").textContent = pct(data.s5th);
      document.getElementById("s5fi").textContent = pct(data.s5fi);
      document.getElementById("s5tw").textContent = pct(data.s5tw);
      document.getElementById("dS5th").innerHTML = delta(data.delta_s5th);
      document.getElementById("dS5fi").innerHTML = delta(data.delta_s5fi);
      document.getElementById("dS5tw").innerHTML = delta(data.delta_s5tw);
      document.getElementById("status").textContent = "数据日期 " + data.date;
      document.getElementById("time").textContent = data.generated_at.replace("T", " ");
    } catch (err) {
      document.getElementById("status").textContent = "错误: " + err.message;
      document.getElementById("status").className = "err";
    } finally {
      btn.disabled = false;
    }
  }
  document.getElementById("runBtn").addEventListener("click", loadBreadth);
  loadBreadth();
</script>
</body>
</html>
"""
