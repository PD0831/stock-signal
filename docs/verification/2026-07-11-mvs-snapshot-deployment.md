# MVS snapshot deployment verification

- Snapshot generation: live builder run at `2026-07-11T17:27:04.511989+00:00`.
- Provider contract: `yfinance/Yahoo Finance`, unadjusted prices; daily signals use
  `1d/2y`, and breadth uses `15m/5d + 1d/2y`.
- Constituent provenance remains in each artifact's `quality` field. NASDAQ-100
  used the Wikipedia constituent table. S&P 500 used the Wikipedia fallback
  because the local environment could not verify the primary SPY holdings TLS
  certificate.
- Pair validation: schema version 1 and generation ID
  `2026-07-11T17:27:04.511989+00:00-bf6f80e48a79` match.
- Memory smoke: one network-guarded uvicorn worker, 45 iterations over all four
  public routes; startup RSS 67.67 MiB, peak/final RSS 68.98 MiB, growth 1.31 MiB.
  The intentional external-connect probe was blocked, and the route run recorded
  no attempted egress.
- Automated verification: 98 tests in `tests/` and 18 root app tests passed;
  strict JSON and pair validation passed. The display import loaded none of
  pandas, numpy, or yfinance.
- Visual QA caveat: the in-app browser runtime reported no available browser and
  Playwright was not installed. Screenshot-level desktop/mobile inspection was
  therefore blocked. Static DOM inspection found all expected dashboard/radar
  nodes, and the populated-data JavaScript rendering contract tests passed.
