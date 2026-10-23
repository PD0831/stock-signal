# Breadth and benchmark charts

The breadth page aligns four panels over the same visible records: SPY/QQQ price returns, the RSP − SPY spread, Strong/Breakdown percentages, and NTSS. Phase labels and phase transitions are no longer displayed on this page. The MVS portfolio and trading calculations are unchanged.

## Time and price definitions

- Labels and trading-day ranges use America/New_York (ET, including daylight saving). Non-trading intervals are compressed. The timestamp labels identify each 15-minute bar using the provider timestamp.
- SPY/QQQ values are raw 15-minute Close prices from the existing yfinance source. They are not dividend-adjusted total returns.
- If both benchmarks are present, both return series start at the first visible timestamp with valid prices for both. If only one is available, that series starts at its first valid timestamp and the other is marked unavailable. The hover/click/keyboard readout includes actual dollar prices and percent changes.
- Joins use exact timezone-aware timestamps. Missing/invalid/nonpositive prices remain gaps; no nearest-bar or forward fill is applied. An outage does not erase previously saved valid prices for the same instant.
- The routine snapshot builder fetches five days of benchmark bars and retains the rolling three-month breadth history. Old snapshots remain supported and show a price-unavailable message. The initial migration adds matching real prices from a 60-day provider query to the saved breadth history, without altering its generation timestamp or breadth values.

- RSP − SPY is the equal-weight S&P 500 (RSP) return minus the SPY return, in percentage points, from the first visible timestamp where both prices exist. Positive means equal-weight is outperforming cap-weight (broader participation). RSP is fetched with the provider's 60-day 15-minute window so saved history without RSP is backfilled at exact timestamps; older bars stay empty.

## Interaction and verification

Use 1D / 5D / 20D / 3M for the visible range. Hover or tap any panel to align all cursors; when focused, Left/Right/Home/End select records. Responsive SVG coordinates preserve readable labels on mobile. Resizing and range changes redraw all panels together.

Run `python3 -m pytest --import-mode=importlib -q` from the project root (the import mode avoids the existing same-name test modules). The deployment smoke test needs permission to bind a local port. Browser QA covers desktop and 390px mobile layouts, real benchmark traces, missing benchmark data, range changes, keyboard navigation, and the existing MVS portfolio view.
