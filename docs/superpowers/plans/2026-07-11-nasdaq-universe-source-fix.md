# NASDAQ-100 Universe Source Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restore the Market Vital Signs signal page by loading NASDAQ-100 constituents from Wikipedia's current constituent-list page.

**Architecture:** Keep the existing fetch, parse, normalize, cache, and fallback pipeline unchanged. Add a focused regression test that intercepts the HTTP boundary and proves the NASDAQ branch requests the constituent-list URL and parses its `Ticker` table, then change only the source URL constant.

**Tech Stack:** Python 3.11, FastAPI, pandas, requests, pytest, unittest.mock

---

### Task 1: Lock the NASDAQ constituent source with a regression test

**Files:**
- Create: `tests/test_live_stock_signal_app.py`
- Test: `tests/test_live_stock_signal_app.py`

- [ ] **Step 1: Write the failing test**

```python
from unittest.mock import Mock

import live_stock_signal_app as app


def test_fetch_current_nasdaq_symbols_uses_constituent_list(monkeypatch):
    response = Mock()
    rows = "".join(
        f"<tr><td>TEST{i:02d}</td><td>Company {i}</td></tr>" for i in range(80)
    )
    response.text = f"""
        <table>
          <thead><tr><th>Ticker</th><th>Company</th></tr></thead>
          <tbody>{rows}</tbody>
        </table>
    """
    response.raise_for_status.return_value = None
    requested_urls = []

    def fake_get(url, **kwargs):
        requested_urls.append(url)
        return response

    monkeypatch.setattr(app.requests, "get", fake_get)
    app._memory_cache.clear()

    assert app.fetch_current_symbols("nasdaq100") == [
        f"TEST{i:02d}" for i in range(80)
    ]
    assert requested_urls == [
        "https://en.wikipedia.org/wiki/List_of_NASDAQ-100_companies"
    ]
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest -q tests/test_live_stock_signal_app.py`

Expected: FAIL because the observed URL is `https://en.wikipedia.org/wiki/Nasdaq-100` rather than the constituent-list URL.

- [ ] **Step 3: Commit the failing regression test**

```bash
git add tests/test_live_stock_signal_app.py
git commit -m "test: reproduce Nasdaq universe source failure"
```

### Task 2: Point the loader at the current constituent-list page

**Files:**
- Modify: `live_stock_signal_app.py:25`
- Test: `tests/test_live_stock_signal_app.py`

- [ ] **Step 1: Apply the minimal implementation**

Replace the URL constant with:

```python
NASDAQ100_URL = "https://en.wikipedia.org/wiki/List_of_NASDAQ-100_companies"
```

- [ ] **Step 2: Run the focused regression test**

Run: `pytest -q tests/test_live_stock_signal_app.py`

Expected: `1 passed`.

- [ ] **Step 3: Run existing application tests**

Run: `pytest -q tests/test_app.py`

Expected: all tests pass.

- [ ] **Step 4: Verify the live constituent source and signal endpoint**

Run:

```bash
python - <<'PY'
import live_stock_signal_app as app

app._memory_cache.clear()
symbols = app.fetch_current_symbols("nasdaq100")
print("nasdaq_count", len(symbols))
response = app.api_signals()
print("status", response.status_code)
print("has_universe_error", b"Could not load current universe symbols" in response.body)
PY
```

Expected: `nasdaq_count` is at least 80, `status` is 200, and `has_universe_error` is `False`.

- [ ] **Step 5: Commit the fix**

```bash
git add live_stock_signal_app.py
git commit -m "fix: update Nasdaq universe source"
```
