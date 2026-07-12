# Selectable Breadth and NTSS History Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add selectable 1D/5D/20D/3M history to the 15-minute breadth page and render synchronized Strong/Breakdown and NTSS panels without increasing Render-side market computation.

**Architecture:** The snapshot builder merges new aggregate records with the prior valid breadth snapshot, deduplicates by aware timestamp, and retains a rolling three-calendar-month window. The browser filters the compact record list for the selected range and renders two lightweight synchronized SVG panels with a shared cursor. Render remains a snapshot-only service.

**Tech Stack:** Python 3.12 Action builder, FastAPI display service, vanilla JavaScript/SVG, pytest, Node-based renderer tests

---

### Task 1: Merge and retain three months of breadth records

**Files:**
- Modify: `scripts/build_dashboard_snapshots.py`
- Modify: `tests/test_build_dashboard_snapshots.py`

- [ ] **Step 1: Write failing history-merge tests**

Cover first run without an old snapshot, overlap where new records replace matching old timestamps, strict ascending order, invalid/naive timestamps, and three-calendar-month cutoff relative to the newest record.

- [ ] **Step 2: Verify RED**

Run the focused builder suite and confirm failures are caused by missing merge behavior.

- [ ] **Step 3: Implement pure history merge**

Add a pure helper with an explicit API:

```python
def merge_breadth_history(
    existing_records: list[dict[str, Any]],
    new_records: list[dict[str, Any]],
    *,
    months: int = 3,
) -> list[dict[str, Any]]:
    ...
```

Parse timezone-aware timestamps, deep-copy values, let new records win duplicate timestamps, sort ascending, and calculate the calendar-month cutoff from the latest timestamp.

- [ ] **Step 4: Integrate without weakening atomic publication**

Before building `breadth_15m.json`, read the prior snapshot only if it passes strict schema/provenance validation. A missing or invalid old file must not crash first deployment. Both new public files must still publish as a validated generation pair.

- [ ] **Step 5: Verify and commit**

Run builder, publication and pair-validator tests. Commit as `feat: retain three months of breadth history`.

### Task 2: Add selectable range filtering and persistence

**Files:**
- Modify: `dashboard_html.py`
- Modify: `test_live_stock_signal_app.py`

- [ ] **Step 1: Add failing renderer tests**

Execute the actual embedded JavaScript through the existing Node harness. Require:

- default `5D` when storage is empty;
- accepted stored values `1D`, `5D`, `20D`, `3M`;
- invalid stored values fall back to `5D`;
- 1D/5D/20D select the latest distinct trading dates;
- 3M uses a calendar-month cutoff;
- selected range persists to localStorage;
- actual coverage start/end is displayed.

- [ ] **Step 2: Verify RED**

- [ ] **Step 3: Implement accessible range controls**

Add a radiogroup or tab-like control with stable IDs/data attributes, keyboard navigation, visible selected state and an `aria-live` coverage label. Filtering must use aware record timestamps and defensive dedupe/sort.

- [ ] **Step 4: Verify and commit**

Run root display/Node tests. Commit as `feat: add selectable breadth history ranges`.

### Task 3: Render synchronized Strong/Breakdown and NTSS panels

**Files:**
- Modify: `dashboard_html.py`
- Modify: `test_live_stock_signal_app.py`

- [ ] **Step 1: Add failing two-panel tests**

Require two SVG viewports sharing record X positions; top 0–100 scale; bottom NTSS scale including zero; positive/negative background regions; safe gaps for missing series; current-range transitions only; title/description accessibility for both panels.

- [ ] **Step 2: Implement the upper breadth panel**

Reuse the hardened finite-value and segment logic. Draw Strong and Breakdown with a fixed 0–100 scale. Across multiple sessions, use equal record spacing rather than wall-clock weekend gaps.

- [ ] **Step 3: Implement the lower NTSS panel**

Compute a padded range containing every finite NTSS value and zero. Draw a zero axis, low-saturation positive/negative regions, and discontinuous segments around missing NTSS values. Never coerce missing values to zero.

- [ ] **Step 4: Add transitions and shared accessibility summaries**

Only annotate phase changes within the selected records. Generate safe SVG title/description and visually hidden textual summaries for both series.

- [ ] **Step 5: Verify and commit**

Run Node renderer and HTML contract tests. Commit as `feat: add synchronized NTSS breadth panels`.

### Task 4: Add shared cursor and mobile behavior

**Files:**
- Modify: `dashboard_html.py`
- Modify: `test_live_stock_signal_app.py`

- [ ] **Step 1: Write failing interaction tests**

Test pointer and keyboard selection of the nearest record, identical cursor X in both panels, safe tooltip text for time/Strong/Breakdown/NTSS/phase, reset on loading/error/closed state, and range change resetting to the latest record.

- [ ] **Step 2: Implement shared cursor**

Use one selected-record index and render cursor lines in both SVGs. Build tooltip content with DOM nodes/textContent. Make chart focusable and support left/right/home/end keys.

- [ ] **Step 3: Implement mobile layout**

Keep range controls horizontally usable, stack panels with readable minimum heights, and retain the research disclosure below them. Avoid horizontal page overflow.

- [ ] **Step 4: Verify and commit**

Commit as `feat: synchronize breadth chart inspection`.

### Task 5: Validate maximum history, memory and deployment

**Files:**
- Modify: `tests/test_deployment_contract.py`
- Modify: `scripts/memory_smoke.py` if needed
- Modify: `docs/verification/2026-07-11-mvs-snapshot-deployment.md`
- Modify: `data/breadth_15m.json`
- Modify: `data/dashboard_snapshot.json` only when a paired generation is published

- [ ] **Step 1: Build a maximum expected fixture**

Generate about 1,700 aggregate 15-minute records with finite/missing NTSS variants and multiple transitions. Do not commit fabricated market values as the live snapshot; use the fixture only for tests.

- [ ] **Step 2: Run browser renderer stress tests**

Execute range switching, two-panel rendering and cursor interaction against the maximum fixture. Assert bounded SVG node counts or path segmentation so DOM size does not grow excessively.

- [ ] **Step 3: Run guarded Render memory smoke**

Use the large fixture through the same snapshot-only app, 50 route cycles, the hardened no-egress guard, 256 MiB absolute limit and 32 MiB peak-growth limit. Record API payload size, startup, peak and final RSS.

- [ ] **Step 4: Generate a real snapshot pair**

Run the live Action-equivalent builder if network access succeeds. Merge it with existing valid history. Validate JSON, schema, provenance, generation identity, timestamp order, three-month cutoff and no raw matrices. If live generation is blocked, keep the last real pair rather than committing fabricated data.

- [ ] **Step 5: Run complete verification**

```bash
PYTHONPATH="$PWD" python -m pytest -q -c /dev/null --rootdir="$PWD" tests
PYTHONPATH="$PWD" python -m pytest -q -c /dev/null --rootdir="$PWD" test_live_stock_signal_app.py
python scripts/validate_dashboard_snapshots.py data/dashboard_snapshot.json data/breadth_15m.json
python scripts/memory_smoke.py --iterations 50 --limit-mib 256 --growth-limit-mib 32
git diff --check origin/main...HEAD
```

- [ ] **Step 6: Visual QA and commit**

Inspect populated desktop/mobile layouts in the in-app browser if available. Otherwise retain Node-executed DOM evidence and explicitly update the screenshot caveat. Commit as `chore: verify extended breadth history`.

### Task 6: Final review and publish

**Files:**
- No new source files.

- [ ] **Step 1: Review scope against current `origin/main`**

Confirm only the history merge, range controls, double panels, cursor, tests, verification documentation and valid snapshot data are present.

- [ ] **Step 2: Run independent final review**

Require no open Critical/Important findings and repeat the exact verification on the intended push commit.

- [ ] **Step 3: Push without force**

Fetch current `origin/main`, integrate any Action-generated data-only commit, rerun pair validation, then push the verified release branch to `main`. Confirm remote SHA.
