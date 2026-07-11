# MVS Low-Memory Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace Render-side full-universe computation with GitHub Actions-generated snapshots, redesign the homepage around an execution table, and provide a lightweight 15-minute breadth radar.

**Architecture:** `scripts/build_dashboard_snapshots.py` owns downloads and calculations and writes two versioned JSON artifacts. `live_stock_signal_app.py` becomes a display-only FastAPI service that validates and serves those artifacts without live market downloads. GitHub Actions refreshes snapshots during US market hours; stale valid artifacts remain readable after refresh failure.

**Tech Stack:** Python 3.11, FastAPI, pandas, yfinance, GitHub Actions, vanilla HTML/CSS/JavaScript, pytest

---

### Task 1: Repair existing breadth regressions

**Files:**
- Modify: `live_stock_signal_app.py`
- Test: `test_live_stock_signal_app.py`

- [ ] **Step 1: Preserve RED evidence**

Run the two failing `BreadthReferenceTests` individually. Expected failures are `above_200_n == NaN` and `daily_close_payload()` rejecting `denominator`.

- [ ] **Step 2: Align the installed breadth implementation**

Make `_install_breadth_patch()` use available-history moving averages and preserve the canonical signature:

```python
def daily_close_payload(
    daily_df: pd.DataFrame,
    min_n: int = BREADTH_MIN_STOCKS,
    denominator: int | None = None,
) -> dict[str, Any] | None:
    daily_breadth = _calculate_breadth_from_daily(
        daily_df, min_n=min_n, denominator=denominator
    )
```

- [ ] **Step 3: Verify and commit**

Run `PYTHONPATH="$PWD" python -m pytest -q -c /dev/null --rootdir="$PWD" test_live_stock_signal_app.py`. Expected: 17 passed. Commit as `fix: align breadth reference calculations`.

### Task 2: Define deterministic snapshot builders

**Files:**
- Create: `scripts/build_dashboard_snapshots.py`
- Create: `tests/test_build_dashboard_snapshots.py`

- [ ] **Step 1: Write failing builder tests**

Use fixed DataFrames and timestamps. Assert `build_dashboard_snapshot()` emits schema version, generated time, merged universes, ranks and 60/20/20 target weights. Assert `build_breadth_snapshot()` finds the latest phase transition and retains only aggregate records.

- [ ] **Step 2: Verify RED**

Run `PYTHONPATH="$PWD" python -m pytest -q -c /dev/null --rootdir="$PWD" tests/test_build_dashboard_snapshots.py`. Expected: import failure because the module does not exist.

- [ ] **Step 3: Implement pure builders**

Create the following public API:

```python
SCHEMA_VERSION = 1
WEIGHTS = (60, 20, 20)

def build_dashboard_snapshot(picks, *, generated_at, market_status=None, quality=None): ...
def build_breadth_snapshot(records, *, generated_at=None, quality=None): ...
def write_json_atomic(path: Path, payload: dict[str, Any]) -> None: ...
```

`write_json_atomic()` must serialize with `allow_nan=False` before replacing the existing file, so a failed build cannot destroy the last good snapshot.

- [ ] **Step 4: Verify and commit**

Run the focused tests. Expected: all pass. Commit as `feat: define dashboard snapshot builders`.

### Task 3: Move market computation into the snapshot command

**Files:**
- Modify: `scripts/build_dashboard_snapshots.py`
- Modify: `scripts/fetch_stock_data.py`
- Modify: `tests/test_build_dashboard_snapshots.py`

- [ ] **Step 1: Add failing orchestration tests**

With injected fake download functions, verify `run(output_dir)` computes both universes once, writes both JSON files, includes valid/failed counts, emits 15-minute aggregate records, and never writes raw price matrices.

- [ ] **Step 2: Extract computation helpers**

Move symbol parsing, batched history download, signal ranking, breadth, NTSS, momentum, phase classification and daily-close payload logic out of the FastAPI module. The build script must not import FastAPI or HTML constants.

- [ ] **Step 3: Add CLI and atomic two-file publication**

Support `python scripts/build_dashboard_snapshots.py --output-dir data`. Validate and serialize both payloads before replacing either public artifact.

- [ ] **Step 4: Verify offline and live**

Run unit tests, then build into `/tmp/mvs-snapshot-check` and validate both files with `python -m json.tool`.

- [ ] **Step 5: Commit**

Commit as `feat: precompute MVS dashboard snapshots`.

### Task 4: Schedule 15-minute refreshes

**Files:**
- Create: `.github/workflows/refresh_dashboard.yml`
- Modify: `tests/test_build_dashboard_snapshots.py`

- [ ] **Step 1: Add a failing workflow contract test**

Assert the workflow provides `workflow_dispatch`, a 15-minute weekday schedule covering US hours, runtime market-hours gating, concurrency cancellation, the snapshot command, and staging limited to the two JSON artifacts.

- [ ] **Step 2: Create the workflow**

Use:

```yaml
concurrency:
  group: mvs-dashboard-refresh
  cancel-in-progress: true
```

Install dependencies, run the builder, stage only `data/dashboard_snapshot.json` and `data/breadth_15m.json`, and commit only on a non-empty staged diff.

- [ ] **Step 3: Verify and commit**

Run the workflow contract and builder suites. Commit as `ci: refresh MVS snapshots every 15 minutes`.

### Task 5: Convert Render to a snapshot-only service

**Files:**
- Modify: `live_stock_signal_app.py`
- Modify: `test_live_stock_signal_app.py`

- [ ] **Step 1: Write failing display tests**

Add tests proving `/`, `/api/signals`, `/breadth`, and `/api/breadth` do not call yfinance; stale snapshots return 200 with `stale=true`; incompatible schemas return an unavailable API state while HTML remains renderable.

- [ ] **Step 2: Implement the loader**

Add `DATA_DIR`, `load_snapshot(name)`, schema validation and freshness evaluation. Cache only small decoded JSON values keyed by file modification time.

- [ ] **Step 3: Remove live computation from Render**

Remove the lifespan background thread and all request-time market downloads. After helpers move to the build layer, remove yfinance/pandas/numpy imports from the display module. `/api/signals` and `/api/breadth` serve snapshot data only.

- [ ] **Step 4: Verify and commit**

Run the root suite and confirm no display route invokes yfinance. Commit as `refactor: serve precomputed MVS snapshots`.

### Task 6: Build the action-first homepage

**Files:**
- Modify: `live_stock_signal_app.py` (`SIGNALS_HTML`)
- Modify: `test_live_stock_signal_app.py`

- [ ] **Step 1: Add failing HTML contract tests**

Require stable elements for current action, phase, freshness banner, Strong/Breakdown/NTSS/Momentum cards, short radar, data quality, and `buy-target-table`.

- [ ] **Step 2: Implement the approved C professional table**

Render rank, symbol, universe, MA200 distance, target weight, price, ADV rank and data time. On mobile, keep rank/symbol/weight prominent and make secondary columns horizontally scrollable.

- [ ] **Step 3: Verify visually and commit**

Run API/HTML tests, serve locally with uvicorn, inspect desktop and mobile layouts in the in-app browser, then commit as `feat: redesign MVS decision dashboard`.

### Task 7: Build the 15-minute breadth radar

**Files:**
- Modify: `live_stock_signal_app.py` (`BREADTH_HTML`)
- Modify: `test_live_stock_signal_app.py`

- [ ] **Step 1: Add failing radar contract tests**

Require current phase/action, Strong/Breakdown/NTSS values and deltas, intraday chart, latest transition, stale state and expandable MA20/50/200 details.

- [ ] **Step 2: Implement the approved A radar**

Plot current-day Strong and Breakdown with lightweight SVG or canvas, annotate state transitions, and keep research metrics in a disclosure panel. Avoid loading Plotly or large client datasets.

- [ ] **Step 3: Verify visually and commit**

Test fresh, stale, market-closed and unavailable states on desktop/mobile. Commit as `feat: add 15-minute breadth radar`.

### Task 8: Add snapshots and verify the memory budget

**Files:**
- Create: `data/dashboard_snapshot.json`
- Create: `data/breadth_15m.json`
- Modify: `render.yaml`
- Modify: `requirements.txt`

- [ ] **Step 1: Generate and validate committed snapshots**

Run the builder into `data/`. Validate both with `python -m json.tool` and confirm neither contains raw stock-history matrices.

- [ ] **Step 2: Configure display deployment**

Set `DATA_DIR=data` in `render.yaml`. Keep a single web worker. Split or trim runtime dependencies where safe, while retaining separate Action build dependencies.

- [ ] **Step 3: Run a memory smoke test**

Start one uvicorn worker, record RSS after startup, repeatedly request all four routes, and record RSS again. Require every route to succeed, RSS to remain comfortably below 512MB (target below 256MB locally), no large monotonic growth, and no market-data network call.

- [ ] **Step 4: Run complete verification**

Because two test files share a basename, run separately:

```bash
PYTHONPATH="$PWD" python -m pytest -q -c /dev/null --rootdir="$PWD" tests
PYTHONPATH="$PWD" python -m pytest -q -c /dev/null --rootdir="$PWD" test_live_stock_signal_app.py
python -m json.tool data/dashboard_snapshot.json >/dev/null
python -m json.tool data/breadth_15m.json >/dev/null
git diff --check
```

- [ ] **Step 5: Commit**

Commit deployment artifacts as `chore: deploy precomputed MVS dashboard`.

### Task 9: Integrate and publish

**Files:**
- No new source files.

- [ ] **Step 1: Review scope**

Review `git log --oneline origin/main..HEAD` and `git diff --stat origin/main...HEAD`. Confirm only the NASDAQ fix, breadth fix, snapshot architecture, UI, tests, and documentation are present.

- [ ] **Step 2: Verify the exact push commit**

Repeat both pytest commands, JSON validation, memory smoke test and `git diff --check` on the exact commit intended for `origin/main`.

- [ ] **Step 3: Update and push**

Update local `main` through the isolated integration workflow without staging or overwriting unrelated user changes. Push with `git push origin codex/integrate-main-push:main`; never force-push.

- [ ] **Step 4: Confirm remote state**

Run `git fetch origin` and confirm `origin/main` equals the verified integration commit.
