# MVS Dip-Aware Portfolio Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the dashboard's independent 60/20/20 market lists with one NASDAQ-100 MVS portfolio that implements the validated two-leg selection rules and shows account-level dollars and whole-share quantities.

**Architecture:** The market-data provider exposes a unique ADV Top15 list and the EMA200 Top3 selected from that pool. A checked-in trade ledger determines whether the account is holding a regular Long, holding a Dip Long, or flat; breadth watch labels cannot open or close it. The planner combines duplicate symbols across the two 50% sleeves, applies the latest completed month-end review, and uses 1.15x development exposure. The JSON snapshot carries strategy metadata and aggregated target weights; the display-only browser converts those weights into dollar and whole-share quantities for the user's account value.

**Tech Stack:** Python 3.12, FastAPI, pytest, dependency-free browser JavaScript.

---

### Task 1: Add deterministic MVS portfolio construction

**Files:**
- Modify: `scripts/build_dashboard_snapshots.py`
- Test: `tests/test_build_dashboard_snapshots.py`

- [x] **Step 1: Write failing portfolio tests**

Add tests that supply ADV-ranked and EMA200-ranked fixtures and assert regular mode aggregates two 50% sleeves to 115%, Dip Long uses ten equal ADV names in the second sleeve, and a flat ledger returns no buy targets.

- [x] **Step 2: Run the focused tests and verify RED**

Run: `python3 -m pytest -q --import-mode=importlib tests/test_build_dashboard_snapshots.py -k 'mvs_portfolio'`

Expected: failures because `build_mvs_portfolio` does not exist.

- [x] **Step 3: Implement the planner and provider fields**

Add `MVS_GROSS_EXPOSURE = 1.15`, build the liquidity sleeve as ADV Top3 equal weight, build the regular trend sleeve as ADV15-to-EMA200 Top3 with 60/20/20 weights, build the dip sleeve as ADV Top10 equal weight, aggregate duplicate symbols, and return explicit strategy metadata. Extend `SnapshotMarketData.compute_signals()` to return `adv_ranked`, select EMA200 names from the first 15 unique issuers, and rank at an explicit review date while retaining latest prices for sizing.

- [x] **Step 4: Run focused tests and verify GREEN**

Run: `python3 -m pytest -q --import-mode=importlib tests/test_build_dashboard_snapshots.py -k 'mvs_portfolio or dashboard_snapshot or run_computes'`

Expected: all selected tests pass.

### Task 2: Validate and render buy amounts

**Files:**
- Modify: `live_stock_signal_app.py`
- Modify: `dashboard_html.py`
- Test: `tests/test_live_stock_signal_app.py`

- [x] **Step 1: Write failing schema and UI tests**

Require strategy metadata and per-target sleeve weights, and assert the HTML includes an account-value input plus planned-dollar and whole-share columns.

- [x] **Step 2: Run focused tests and verify RED**

Run: `python3 -m pytest -q --import-mode=importlib tests/test_live_stock_signal_app.py -k 'strategy or account or buy_target'`

Expected: failures for the missing strategy contract and UI controls.

- [x] **Step 3: Implement validation and rendering**

Validate `strategy`, `liquidity_leg_weight_pct`, and `trend_leg_weight_pct`. Render the strategy mode, gross exposure, target dollars, and floor-to-whole-share quantity from a default $100,000 account value, recalculating safely when the input changes.

- [x] **Step 4: Run focused tests and verify GREEN**

Run: `python3 -m pytest -q --import-mode=importlib tests/test_live_stock_signal_app.py -k 'strategy or account or buy_target'`

Expected: all selected tests pass.

### Task 3: Regenerate artifacts and verify the repository

**Files:**
- Modify: `data/dashboard_snapshot.json`
- Modify: `data/breadth_15m.json`
- Modify: `docs/verification/2026-07-11-mvs-snapshot-deployment.md`

- [x] **Step 1: Generate and validate a fresh snapshot pair**

Run: `python3 scripts/build_dashboard_snapshots.py --output-dir data`

Run: `python3 scripts/validate_dashboard_snapshots.py data/dashboard_snapshot.json data/breadth_15m.json`

Expected: both schema-compatible artifacts validate and the dashboard target weights sum to either 0% in cash mode or 115% in a holding mode.

- [x] **Step 2: Run the full suite**

Run: `python3 -m pytest -q --import-mode=importlib`

Expected: all tests pass outside the filesystem sandbox; the local socket smoke test may require the approved unrestricted test command.

- [x] **Step 3: Document and inspect**

Update the verification note with the stateful trade ledger, two-leg rules, 1.15x development status, account sizing behavior, and test evidence. Serve the app and inspect desktop and mobile layouts for clipping and legibility.

- [x] **Step 4: Commit and publish for review**

Commit the tested implementation on `feat/mvs-dip-portfolio`, push the branch, and create a pull request describing the new selection and sizing behavior plus its development-status limitations.
