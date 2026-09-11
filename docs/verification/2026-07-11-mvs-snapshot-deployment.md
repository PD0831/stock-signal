# MVS snapshot deployment verification

## Dip-aware portfolio update (2026-09-11)

- Trading universe: NASDAQ-100 only. S&P 500 remains an input to breadth and
  market-state quality, but it no longer creates a second, duplicate buy list.
- Liquidity sleeve: 50% of strategy capital in ADV Top3, equal-weighted.
- Regular Long trend sleeve: 50% of strategy capital; select EMA200-distance
  Top3 from the unique ADV Top15 pool and weight them 60% / 20% / 20%.
- Position state comes from the trade ledger. The open `2026-06-04 Long`
  remains invested; the `2026-07-09 Offen` row is an open-position mark, not an
  exit. Breadth `short_watch` labels do not flatten it.
- Dip sleeve applies only when the ledger entry is `Dip Long`. It replaces the
  trend sleeve with ADV Top10 equal weight.
- Exposure: 1.15x development candidate. On account equity, the liquidity
  sleeve contributes 19.167% per name; the regular trend sleeve contributes
  34.5% / 11.5% / 11.5%; the dip sleeve contributes 5.75% per name.
  Duplicate symbols are aggregated and the published target sum must equal the
  strategy's gross exposure.
- Sizing UI: the user supplies account equity in USD. The page renders each
  target's two sleeve weights, combined account weight, target dollars, and
  floor-to-whole-share quantity from the latest close.
- Holding state is independent from the current breadth label. During an open
  position, rankings use the latest completed month-end and execute next open.
- Research status: `dipADV10_pool15 × 1.15` reproduced 45.022% CAGR and
  -29.129% MaxDD on the already-seen development history. The parameters remain
  frozen candidates pending genuinely unseen data; financing and execution can
  remove the narrow strict-target margin.

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
- Automated verification: 110 tests passed with importlib collection;
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
