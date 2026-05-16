# Implementation Plan — VIX & Breadth Python Rebuild

**Spec:** `2026-05-16-vix-breadth-python-rebuild-design.md`  
**Date:** 2026-05-16

---

## Overview

Five sequential steps. Each step is independently testable before the next begins.

---

## Step 1 — `config.py`: Add `ema_state_path`

**File:** `ibkr_quant/config.py`  
**Change:** Add one field to `AppConfig`.

```python
ema_state_path: Path = Path(os.getenv("EMA_STATE_PATH", "var/ema_state.json"))
```

**Test:** `python -c "from ibkr_quant.config import load_config; print(load_config().ema_state_path)"` prints `var/ema_state.json`.

---

## Step 2 — `breadth.py`: SP500 Incremental Breadth Computer

**File:** `ibkr_quant/breadth.py` (new)

### 2a — `BreadthSnapshot` dataclass

```python
@dataclass
class BreadthSnapshot:
    date: date
    s5th: float
    s5fi: float
    s5tw: float
    previous_s5th: float
    previous_s5fi: float
    previous_s5tw: float
```

### 2b — SP500 member list helper

```python
def fetch_sp500_tickers() -> list[str]:
    table = pd.read_html("https://en.wikipedia.org/wiki/List_of_S%26P_500_companies")[0]
    return table["Symbol"].str.replace(".", "-", regex=False).tolist()
```

Note: Wikipedia uses `.` (e.g. `BRK.B`); yfinance expects `-` (`BRK-B`).

### 2c — EMA state helpers

```python
def _load_state(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text())

def _save_state(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2))
```

### 2d — Bootstrap (first run)

```python
def _bootstrap(tickers: list[str], state: dict) -> dict:
    df = yf.download(tickers, period="220d", interval="1d", auto_adjust=True, progress=False)["Close"]
    for ticker in df.columns:
        series = df[ticker].dropna()
        if len(series) < 200:
            continue
        closes = series.values.astype(float)
        ema200 = _compute_ema(closes, 200)
        ema50  = _compute_ema(closes, 50)
        ema5   = _compute_ema(closes, 5)
        state[ticker] = {
            "ema200": ema200,
            "ema50": ema50,
            "ema5": ema5,
            "last_date": series.index[-1].date().isoformat(),
        }
    return state

def _compute_ema(closes: np.ndarray, period: int) -> float:
    k = 2.0 / (period + 1)
    ema = closes[0]
    for c in closes[1:]:
        ema = c * k + ema * (1 - k)
    return ema
```

### 2e — Daily incremental update

```python
def _update_state(tickers: list[str], state: dict) -> dict:
    df = yf.download(tickers, period="5d", interval="1d", auto_adjust=True, progress=False)["Close"]
    for ticker in df.columns:
        series = df[ticker].dropna()
        if ticker not in state:
            continue  # will be bootstrapped on next full run
        entry = state[ticker]
        last = date.fromisoformat(entry["last_date"])
        k200 = 2.0 / 201
        k50  = 2.0 / 51
        k5   = 2.0 / 6
        for ts, close in series.items():
            day = ts.date() if hasattr(ts, "date") else ts
            if day <= last:
                continue
            if pd.isna(close):
                continue
            entry["ema200"] = close * k200 + entry["ema200"] * (1 - k200)
            entry["ema50"]  = close * k50  + entry["ema50"]  * (1 - k50)
            entry["ema5"]   = close * k5   + entry["ema5"]   * (1 - k5)
            entry["last_date"] = day.isoformat()
    return state
```

### 2f — Count breadth and store in `_counts`

```python
def _count_breadth(state: dict) -> tuple[float, float, float]:
    above200 = above50 = above5 = total = 0
    for key, entry in state.items():
        if key == "_counts":
            continue
        total += 1
        close_proxy = entry["ema5"]  # best available close proxy (last updated close ≈ ema5 after k=2/6)
        # Actually we compare last close vs EMA — use ema5 as close approximation is wrong.
        # Store last_close separately — see revised 2e below.
        if entry.get("last_close", entry["ema5"]) > entry["ema200"]:
            above200 += 1
        if entry.get("last_close", entry["ema5"]) > entry["ema50"]:
            above50 += 1
        if entry.get("last_close", entry["ema5"]) > entry["ema5"]:
            above5 += 1
    if total == 0:
        return 0.0, 0.0, 0.0
    return above200 / total * 100, above50 / total * 100, above5 / total * 100
```

**Correction to 2e:** also store `last_close` in each entry so the count compares actual close vs EMA (not EMA vs EMA):

```python
entry["last_close"] = float(close)
```

### 2g — `BreadthComputer` class (public interface)

```python
class BreadthComputer:
    def __init__(self, state_path: Path) -> None:
        self._path = state_path

    def update(self, as_of: date) -> BreadthSnapshot:
        tickers = fetch_sp500_tickers()
        state = _load_state(self._path)

        needs_bootstrap = not any(k != "_counts" for k in state)
        if needs_bootstrap:
            state = _bootstrap(tickers, state)
        else:
            state = _update_state(tickers, state)

        today_s5th, today_s5fi, today_s5tw = _count_breadth(state)

        counts = state.setdefault("_counts", {})
        today_key = as_of.isoformat()
        counts[today_key] = {"s5th": today_s5th, "s5fi": today_s5fi, "s5tw": today_s5tw}

        # Keep only last 2 days in _counts
        sorted_keys = sorted(counts.keys(), reverse=True)
        state["_counts"] = {k: counts[k] for k in sorted_keys[:2]}

        _save_state(self._path, state)

        # Previous day counts
        prev_key = sorted_keys[1] if len(sorted_keys) >= 2 else today_key
        prev = state["_counts"].get(prev_key, state["_counts"][today_key])

        return BreadthSnapshot(
            date=as_of,
            s5th=today_s5th, s5fi=today_s5fi, s5tw=today_s5tw,
            previous_s5th=prev["s5th"],
            previous_s5fi=prev["s5fi"],
            previous_s5tw=prev["s5tw"],
        )
```

**Test:**
```bash
python -c "
from pathlib import Path
from datetime import date
from ibkr_quant.breadth import BreadthComputer
b = BreadthComputer(Path('var/ema_state.json'))
snap = b.update(date.today())
print(snap)
"
```
Expected: prints a `BreadthSnapshot` with plausible values (S5TH ~40–80, S5FI ~40–80, S5TW ~30–80).

---

## Step 3 — `local_signal.py`: Replace CSV reads with yfinance + BreadthComputer

**File:** `ibkr_quant/local_signal.py`

Replace the entire body of `compute_local_decision()`. Keep the function signature identical.

```python
def compute_local_decision(config: AppConfig, params: SignalParams | None = None) -> SignalDecision:
    import yfinance as yf

    # VIX / VIX3M
    vix_raw = yf.download(["^VIX", "^VIX3M"], period="5d", interval="1d",
                           auto_adjust=False, progress=False)["Close"]
    vix_val  = float(vix_raw["^VIX"].dropna().iloc[-1])
    vix3m_val = float(vix_raw["^VIX3M"].dropna().iloc[-1])

    # Breadth
    from .breadth import BreadthComputer
    computer = BreadthComputer(config.ema_state_path)
    breadth = computer.update(date.today())

    # Determine signal type by probing all three
    ts = datetime.combine(breadth.date, time(21, 5), tzinfo=timezone.utc)
    base = dict(
        timestamp=ts,
        nas100_close=None,
        vix=vix_val,
        vix3m=vix3m_val,
        s5th=breadth.s5th,
        s5fi=breadth.s5fi,
        s5tw=breadth.s5tw,
        previous_s5th=breadth.previous_s5th,
        previous_s5fi=breadth.previous_s5fi,
        previous_s5tw=breadth.previous_s5tw,
    )

    probes = {
        SignalType.SHORT: calculate_decision(SignalSnapshot(signal=SignalType.SHORT, **base), params),
        SignalType.LONG:  calculate_decision(SignalSnapshot(signal=SignalType.LONG,  **base), params),
        SignalType.MEAN:  calculate_decision(SignalSnapshot(signal=SignalType.MEAN,  **base), params),
    }
    if probes[SignalType.SHORT].short_signal:
        return probes[SignalType.SHORT]
    if probes[SignalType.LONG].long_signal:
        return probes[SignalType.LONG]
    if config.enable_mean and probes[SignalType.MEAN].mean_signal:
        return probes[SignalType.MEAN]

    neutral = probes[SignalType.LONG]
    neutral.accepted = False
    neutral.confirmed_signal = None
    neutral.reason = "local recomputation produced no actionable signal"
    return neutral
```

Remove all imports related to the old CSV-loading helpers (`latest_matching_file`, `_load_close_series`, etc.) — they are no longer called from this file. Keep the helper functions in the file if any other module imports them; otherwise delete.

**Test:**
```bash
curl -s -X POST http://127.0.0.1:8080/run/local-signal | python -m json.tool
```
Expected: returns a JSON `ExecutionReport` with `submitted` and `message` fields. Signal values should be plausible.

---

## Step 4 — `universe.py`: Add NAS100 full member list

**File:** `ibkr_quant/universe.py`

Add `NAS100_FULL_BY_YEAR` dict with all ~100 NAS100 members per year (2006–2026), and a lookup function.

For 2025–2026 use the current confirmed NAS100 composition. For earlier years, use the historical data already researched in `compare_qqq_adv_topn.py` (which uses `spy_momentum_v1.universe.HistoricalUniverse`).

```python
NAS100_FULL_BY_YEAR: dict[int, tuple[str, ...]] = {
    # Current year (2026) — confirmed NAS100 members
    2026: (
        "AAPL", "MSFT", "NVDA", "AMZN", "META", "GOOGL", "GOOG", "TSLA",
        "AVGO", "COST", "NFLX", "ASML", "AZN", "TMUS", "AMD", "PEP",
        "CSCO", "ADBE", "INTU", "QCOM", "TXN", "AMGN", "ISRG", "CMCSA",
        "AMAT", "HON", "BKNG", "VRTX", "PANW", "MU", "ADP", "LRCX",
        "MELI", "GILD", "SBUX", "INTC", "MDLZ", "REGN", "ADI", "KLAC",
        "CEG", "SNPS", "CDNS", "MRVL", "CRWD", "ABNB", "MAR", "FTNT",
        "ORLY", "CTAS", "CSX", "PYPL", "NXPI", "MCHP", "WDAY", "MNST",
        "PAYX", "PCAR", "CPRT", "DXCM", "FAST", "EA", "IDXX", "KDP",
        "AEP", "ROST", "ODFL", "BIIB", "GFS", "LULU", "DLTR", "SGEN",
        "XEL", "TEAM", "FANG", "ANSS", "VRSK", "WBA", "EBAY", "ILMN",
        "ZS", "DDOG", "GEHC", "ON", "TTD", "ALGN", "DASH", "ROP",
        "WBD", "TTWO", "SIRI", "OKTA", "ZM", "LCID", "RIVN",
    ),
    # Add prior years following the same pattern...
    # For live trading only 2025–2026 is strictly needed.
    2025: (
        "MSFT", "AAPL", "NVDA", "AMZN", "GOOGL", "META", "AVGO", "TSLA",
        "COST", "NFLX", "ASML", "TMUS", "AZN", "AMD", "PEP", "QCOM",
        "CSCO", "ADBE", "INTU", "TXN", "AMGN", "ISRG", "CMCSA", "AMAT",
        "HON", "BKNG", "VRTX", "PANW", "MU", "ADP", "LRCX", "MELI",
        "GILD", "SBUX", "INTC", "MDLZ", "REGN", "ADI", "KLAC", "CEG",
        "SNPS", "CDNS", "MRVL", "CRWD", "ABNB", "MAR", "FTNT", "ORLY",
        "CTAS", "CSX", "PYPL", "NXPI", "MCHP", "WDAY", "MNST", "PAYX",
        "PCAR", "CPRT", "DXCM", "FAST", "EA", "IDXX", "KDP", "AEP",
        "ROST", "ODFL", "BIIB", "GFS", "LULU", "DLTR", "XEL", "TEAM",
        "FANG", "ANSS", "VRSK", "WBA", "EBAY", "ILMN", "ZS", "DDOG",
        "GEHC", "ON", "TTD", "ALGN", "DASH", "ROP", "WBD", "TTWO",
        "SIRI", "OKTA", "ZM", "GOOG",
    ),
}


def nas100_members_on(as_of: date) -> tuple[str, ...]:
    years = sorted(NAS100_FULL_BY_YEAR)
    year = max((y for y in years if y <= as_of.year), default=years[-1])
    return NAS100_FULL_BY_YEAR[year]
```

**Note:** The full historical list (2006–2024) can be populated later from the `HistoricalUniverse` data already used by the backtesting scripts. For live trading, 2025–2026 is sufficient from day one.

**Test:**
```python
from datetime import date
from ibkr_quant.universe import nas100_members_on
members = nas100_members_on(date.today())
assert len(members) > 80
print(f"{len(members)} NAS100 members loaded")
```

---

## Step 5 — `portfolio.py`: Dual Sub-Portfolio Selection

**File:** `ibkr_quant/portfolio.py`

Replace `build_target_positions()`. Keep `rank_by_ma200_distance()` and `reference_prices()` unchanged.

```python
def build_target_positions(histories: dict[str, pd.Series], as_of: date) -> list[TargetPosition]:
    import yfinance as yf
    from .universe import nas100_members_on

    members = list(nas100_members_on(as_of))

    # Fetch 63 days of close + volume for all NAS100 members
    raw = yf.download(members, period="90d", interval="1d",
                      auto_adjust=True, progress=False)
    closes  = raw["Close"]
    volumes = raw["Volume"]

    # ADV: 63-day average dollar volume
    adv: dict[str, float] = {}
    for sym in members:
        if sym not in closes.columns:
            continue
        c = closes[sym].dropna().iloc[-63:]
        v = volumes[sym].dropna().iloc[-63:]
        idx = c.index.intersection(v.index)
        if len(idx) < 20:
            continue
        adv[sym] = float((c.loc[idx] * v.loc[idx]).mean())

    ranked_adv = sorted(adv, key=adv.get, reverse=True)

    # Sub-portfolio A: ADV Top 5 → 70%
    portfolio_a = ranked_adv[:5]
    weight_a = 0.70 / len(portfolio_a)

    # Sub-portfolio B: ADV Top 10 → MA200 Top 3 → 30%
    adv_top10 = ranked_adv[:10]
    portfolio_b = rank_by_ma200_distance(histories, as_of, tuple(adv_top10), top_n=3)
    weight_b = 0.30 / len(portfolio_b) if portfolio_b else 0.0

    # Merge weights
    weights: dict[str, float] = {}
    sources: dict[str, list[str]] = {}
    for sym in portfolio_a:
        weights[sym] = weights.get(sym, 0.0) + weight_a
        sources.setdefault(sym, []).append("adv_top5")
    for sym in portfolio_b:
        weights[sym] = weights.get(sym, 0.0) + weight_b
        sources.setdefault(sym, []).append("ma200_top3")

    # Apply max_symbol_weight cap: redistribute excess proportionally
    cap = 0.25
    for _ in range(10):  # iterate until stable
        excess = {s: w - cap for s, w in weights.items() if w > cap}
        if not excess:
            break
        total_excess = sum(excess.values())
        uncapped = [s for s, w in weights.items() if w <= cap]
        if not uncapped:
            break
        per_uncapped = total_excess / len(uncapped)
        for sym in excess:
            weights[sym] = cap
        for sym in uncapped:
            weights[sym] = min(cap, weights[sym] + per_uncapped)

    return [
        TargetPosition(
            symbol=sym,
            weight=round(w, 6),
            source="+".join(sources[sym]),
        )
        for sym, w in sorted(weights.items())
    ]
```

**Note:** `histories` is passed in from `app.py` for the MA200 calculation (uses pre-loaded local history). The ADV fetch is a separate yfinance call for volume data not in `histories`.

**Test:**
```python
from datetime import date
from ibkr_quant.portfolio import build_target_positions
from ibkr_quant.data import load_close_histories
from ibkr_quant.universe import nas100_members_on

members = list(nas100_members_on(date.today()))
histories = load_close_histories(members, None)  # or pass data_root
positions = build_target_positions(histories, date.today())
total_weight = sum(p.weight for p in positions)
print(f"{len(positions)} positions, total weight = {total_weight:.4f}")
for p in positions:
    print(f"  {p.symbol:6s}  {p.weight:.4f}  [{p.source}]")
```
Expected: 5–8 positions, total weight ≈ 1.0, each ≤ 0.25.

---

## Integration Test

After all five steps, run the full local signal pipeline end-to-end:

```bash
# 1. Start the server
uvicorn ibkr_quant.app:app --host 127.0.0.1 --port 8080

# 2. Trigger local signal run
curl -s -X POST http://127.0.0.1:8080/run/local-signal | python -m json.tool
```

Verify:
- `submitted`: true/false (depends on signal + IBKR connection)
- `message`: describes signal outcome, not an error
- No exceptions in server log
- `var/ema_state.json` exists and contains SP500 stock entries + `_counts`

---

## Implementation Order

| Step | File | What | Risk |
|------|------|------|------|
| 1 | `config.py` | Add `ema_state_path` | Trivial |
| 2 | `breadth.py` | New module, bootstrap + incremental EMA | Core logic |
| 3 | `local_signal.py` | Replace CSV reads | Medium |
| 4 | `universe.py` | Add NAS100 list | Low |
| 5 | `portfolio.py` | Replace selection logic | Medium |

Steps 1, 4 are safe to do first (no behavior change until step 2/3/5 are wired up).  
Step 2 is the highest-risk piece — test it in isolation before proceeding to step 3.

---

## Dependencies

No new packages needed. All already in `requirements.txt`:
- `yfinance>=0.2` ✓
- `pandas>=2.0` ✓
- `fastapi`, `uvicorn` ✓

`lxml` or `html5lib` is needed for `pd.read_html()` (Wikipedia SP500 list) — both already in `requirements.txt` ✓
