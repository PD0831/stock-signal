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
- Memory smoke: one network-guarded uvicorn worker, 50 iterations over all four
  public routes; startup RSS 67.55 MiB, peak/final RSS 69.00 MiB, peak and final
  growth 1.45 MiB. The growth limit is evaluated against peak RSS, not only the
  final sample. Each run uses and removes a unique temporary egress log.
- Network guard coverage: non-loopback TCP `connect`, `connect_ex` and
  `create_connection`; UDP `sendto` and platform-supported `sendmsg`; connected
  `send`/`sendall`; and public-hostname `getaddrinfo`/DNS are denied and audited.
  IPv4/IPv6 loopback and Unix sockets remain available. Adversarial probes for
  every path were blocked, while normal loopback HTTP completed successfully and
  recorded no attempted egress.
- Automated verification: 98 tests in `tests/` and 18 root app tests passed;
  strict JSON and pair validation passed. The display import loaded none of
  pandas, numpy, or yfinance.
- Visual QA caveat: the in-app browser runtime reported no available browser and
  Playwright was not installed. Screenshot-level desktop/mobile inspection was
  therefore blocked. Static DOM inspection found all expected dashboard/radar
  nodes, and the populated-data JavaScript rendering contract tests passed.

## Extended 15-minute history verification (2026-07-12)

- Range controls: 1D / 5D / 20D / 3M; default and persisted range 5D.
- Renderer stress fixture: 1,700 aggregate records with intermittent missing
  NTSS values. The synthetic fixture was temporary and was not committed as
  market data.
- SVG node bounds under that fixture: fewer than 100 upper-panel nodes and fewer
  than 150 NTSS-panel nodes.
- Synthetic breadth JSON size: 535,154 bytes.
- Guarded 50-cycle smoke with the large fixture: startup 66.47 MiB,
  peak/final 87.58 MiB, peak growth 21.11 MiB.
- Strong/Breakdown and NTSS panels use shared record positions. NTSS uses an
  independent scale that always contains zero.
- Screenshot-level desktop/mobile inspection remains subject to the caveat
  above.
