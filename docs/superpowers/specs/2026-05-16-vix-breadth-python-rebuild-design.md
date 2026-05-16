# VIX & Breadth 2D Strategy — Python Rebuild Design

**Date:** 2026-05-16  
**Status:** Approved  
**Scope:** Extend `ibkr_quant` to compute SP500 breadth from scratch (yfinance) and replace the QQQ Top10 stock selection with a dual sub-portfolio based on NAS100 constituents.

---

## Problem

The current `ibkr_quant` system depends on manually downloaded TradingView CSV files for VIX, VIX3M, S5TH, S5FI, and S5TW. Stock selection uses a hardcoded QQQ Top10 proxy list. Both must become fully automated and data-source independent.

---

## Solution: Four Targeted Changes to `ibkr_quant`

No new package. No new server. Four files changed, one file added.

```
ibkr_quant/
  breadth.py       ← NEW
  universe.py      ← UPDATE
  portfolio.py     ← UPDATE
  local_signal.py  ← UPDATE
  config.py        ← UPDATE

var/
  ema_state.json   ← runtime artifact (auto-created on first run)
```

---

## Daily Data Flow

```
POST /run/local-signal
  1. breadth.py        — load ema_state.json
                       — yfinance: fetch ^VIX, ^VIX3M (period=5d)
                       — yfinance: fetch ~500 SP500 stocks (period=5d)
                       — update EMA200/50/5 per stock
                       — compute S5TH, S5FI, S5TW (% above each EMA)
                       — save updated ema_state.json
  2. signals.py        — (unchanged) compute VIX state + breadth areas → signal decision
  3. portfolio.py      — yfinance: fetch 63d close+volume for ~100 NAS100 stocks
                       — ADV Top5 → 70% weight (Sub-portfolio A)
                       — ADV Top10 → MA200 Top3 → 30% weight (Sub-portfolio B)
                       — merge: overlapping stocks sum their weights
                       — apply max_symbol_weight cap (25%)
  4. execution.py      — (unchanged) submit IBKR orders
```

The `/webhook/tradingview` endpoint remains fully functional as a signal cross-check.

---

## Module Specifications

### `breadth.py` — New module

**Responsibility:** Compute S5TH, S5FI, S5TW from SP500 constituent prices. Maintain incremental EMA state so only today's close is needed on normal runs.

**State file format** (`var/ema_state.json`):
```json
{
  "_counts": {
    "2026-05-15": {"s5th": 68.4, "s5fi": 72.1, "s5tw": 61.3},
    "2026-05-14": {"s5th": 66.1, "s5fi": 70.8, "s5tw": 59.7}
  },
  "AAPL": {"ema200": 182.3, "ema50": 185.1, "ema5": 187.2, "last_date": "2026-05-15"},
  "MSFT": {"ema200": 412.1, "ema50": 418.7, "ema5": 421.0, "last_date": "2026-05-15"}
}
```

The `_counts` key stores the last two days of computed S5TH/S5FI/S5TW values so `BreadthSnapshot` can return both today's and yesterday's counts without recomputing from EMA states.

**EMA formula:** `EMA_today = close × k + EMA_prev × (1 − k)` where `k = 2 / (period + 1)`

**Bootstrap (first run / state missing):**
- Fetch 220 days of history for all SP500 members via `yfinance.download()`
- Compute EMA200/50/5 from the full history
- Save state
- Duration: ~30 seconds, runs once

**Normal daily update:**
1. Load `ema_state.json`
2. `yfinance.download(sp500_tickers, period="5d", interval="1d")` — covers weekends and holidays
3. For each stock, apply EMA update for each new trading day since `last_date`
4. Count: S5TH = % stocks with close > EMA200; S5FI = % above EMA50; S5TW = % above EMA5
5. Also store yesterday's counts alongside today's (needed for `net_momentum` delta in `signals.py`)
6. Save updated state

**SP500 member list:** `pd.read_html("https://en.wikipedia.org/wiki/List_of_S%26P_500_companies")[0]` at startup, cached in memory for the session.

**Edge cases:**
- Stock not yet in state (new SP500 addition): bootstrap that stock individually on next run
- Stock missing today's close (halt, delisted): skip in count; denominator shrinks by 1

**Public interface:**
```python
class BreadthComputer:
    def __init__(self, state_path: Path) -> None: ...
    def update(self, as_of: date) -> BreadthSnapshot: ...

@dataclass
class BreadthSnapshot:
    date: date
    s5th: float        # % SP500 stocks above EMA200
    s5fi: float        # % SP500 stocks above EMA50
    s5tw: float        # % SP500 stocks above EMA5
    previous_s5th: float
    previous_s5fi: float
    previous_s5tw: float
```

---

### `universe.py` — Update

**Add:** `NAS100_FULL_BY_YEAR: dict[int, tuple[str, ...]]` — all ~100 NAS100 members per year, same structure as the existing `QQQ_TOP10_BY_YEAR_PROXY`.

**Add:** `nas100_members_on(as_of: date) -> tuple[str, ...]` — returns the member list for the correct year.

**Keep unchanged:** `qqq_top10_on()`, `qqq_market_cap_top5_on()` — used by existing tests and the TV webhook path.

---

### `portfolio.py` — Update

**Replace** `build_target_positions()` with the dual sub-portfolio logic. All other functions (`rank_by_ma200_distance`, `reference_prices`) stay.

**Algorithm:**
```
1. symbols = nas100_members_on(as_of)
2. Fetch 63-day close + volume for all symbols via yfinance (one batch call)
3. Compute ADV per stock: mean(close × volume) over last 63 trading days

Sub-portfolio A — Stable Core (70%):
  adv_top5 = top 5 by ADV
  weight per stock = 0.70 / 5 = 0.14

Sub-portfolio B — Aggressive (30%):
  adv_top10 = top 10 by ADV
  ma200_top3 = top 3 of adv_top10 by (close / MA200 − 1), descending
  weight per stock = 0.30 / 3 = 0.10

4. Merge: if a stock appears in both, sum the weights
   (e.g. NVDA in A + B → 0.14 + 0.10 = 0.24)
5. Apply max_symbol_weight cap (default 0.25) — cap any stock at 0.25, distribute excess proportionally across remaining uncapped positions
6. Return list[TargetPosition] with symbol, weight, source label
```

**Source labels:** `"adv_top5"`, `"ma200_top3"`, `"adv_top5+ma200_top3"` (for overlap cases).

---

### `local_signal.py` — Update

**Replace** CSV file reading with yfinance + BreadthComputer calls.

```python
def compute_local_decision(config: AppConfig, params: SignalParams | None = None) -> SignalDecision:
    # VIX / VIX3M
    vix_data = yfinance.download(["^VIX", "^VIX3M"], period="5d", interval="1d", auto_adjust=False)
    vix = float(vix_data["Close"]["^VIX"].dropna().iloc[-1])
    vix3m = float(vix_data["Close"]["^VIX3M"].dropna().iloc[-1])

    # Breadth
    computer = BreadthComputer(config.ema_state_path)
    breadth = computer.update(date.today())

    # Build snapshot and compute signal (unchanged)
    snapshot = SignalSnapshot(
        timestamp=..., signal=...,
        vix=vix, vix3m=vix3m,
        s5th=breadth.s5th, s5fi=breadth.s5fi, s5tw=breadth.s5tw,
        previous_s5th=breadth.previous_s5th, ...
    )
    ...
```

The old CSV glob logic is removed from this function. The glob fields remain in `AppConfig` so the TV webhook still compiles without changes.

---

### `config.py` — Update

Add one field:
```python
ema_state_path: Path = Path(os.getenv("EMA_STATE_PATH", "var/ema_state.json"))
```

No other changes.

---

## Stock Selection: NAS100 Constituent Data

The `NAS100_FULL_BY_YEAR` dict in `universe.py` follows the same pattern as `QQQ_TOP10_BY_YEAR_PROXY` but includes all ~100 members per year. It is a static Python dict (not a runtime API call) to guarantee reproducibility and avoid network dependency during signal computation.

The yearly list is sourced from Wikipedia's Nasdaq-100 historical composition and the existing research in `compare_qqq_adv_topn.py` (which already uses a `HistoricalUniverse` from `spy_momentum_v1`). For live trading, the current year's list is sufficient.

---

## What Does Not Change

| Component | Status |
|---|---|
| `signals.py` — VIX/breadth signal math | Unchanged |
| `execution.py` — IBKR order submission | Unchanged |
| `risk.py` — pre-trade checks | Unchanged |
| `storage.py` — SQLite audit log | Unchanged |
| `app.py` — FastAPI routes | Unchanged |
| `/webhook/tradingview` endpoint | Unchanged |
| `models.py` | Unchanged |

---

## Constraints and Decisions

- **No paid data provider.** All data via yfinance (`^VIX`, `^VIX3M`, SP500 stocks, NAS100 stocks).
- **Incremental EMA.** Only today's close is fetched on normal runs. Bootstrap happens once.
- **No individual stock stop-loss.** Exit is driven entirely by the VIX/Breadth signal.
- **No trading in February or August.** Preserved from Pine Script `allow_entry` logic.
- **Capital split is fixed:** 70% Sub-portfolio A (ADV Top5), 30% Sub-portfolio B (MA200 Top3 from ADV Top10).
- **Overlap stocks sum their weights** and are capped at `max_symbol_weight` (25%).

---

## Out of Scope

- Backtesting (existing Python backtest scripts remain separate)
- Short selling (the live system is long-only, consistent with existing `ibkr_quant` README)
- Mean-reversion (`MEAN SIGNAL`) execution — remains configurable via `ENABLE_MEAN` env var
