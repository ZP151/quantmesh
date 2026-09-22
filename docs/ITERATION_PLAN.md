# QuantMesh Iteration Plan

Updated: 2026-09-23. This replaces the original conceptual iterations 0–5;
historical delivery IDs and evidence remain in the [iteration index](iterations/INDEX.md).
Use the [roadmap](roadmap/ROADMAP.md) for product direction and
[ACTIVE](goals/ACTIVE.md) for the resumable frontier.

## Current resumable goal

Iteration 0035 is complete. Iteration 0036 remains active after the 8 GB
private AWS migration passed its bounded restore, smoke, chart and restart
checks. The 24-hour capacity/freshness observation, rollback rehearsal and
host reboot gate are still open; the old collection gap is recorded rather
than backfilled. Code-only work for iteration 0037 may proceed during the
observation, but its deployment and merge acceptance remain behind the gate.
See the [0036 recovery plan](superpowers/plans/2026-09-17-staging-recovery.md),
the [8 GB observation plan](superpowers/plans/2026-09-23-8gb-observation-gate.md)
and the [0037 readiness ledger](iterations/0037-moomoo-opend-readiness.md).

## Confirmed state

| Area | Code/integration | Deployment/real-source acceptance |
| --- | --- | --- |
| Decision Inbox and Readiness, 0028–0029 | Merged PRs #130 / #133 | No new deployment claim here |
| Scenario Lab, 0032 | Merged PR #137 | Merge does not establish the AWS version |
| Forecast outcome review, 0033 | Merged PR #139; final-head CI passed | AWS not updated by the merge |
| Private AWS workstation, 0031 / #135 | Integrated through merged PR #142 | Private HTTPS, exact build, loopback bind and retained demo rollback remain verified; the original 2 GB recovery is superseded operationally by the 8 GB handoff tracked in iteration 0036 |
| Deployed live data, 0034 / #140 | Merged PR #142 as `e185c3b`; final-head CI passed | AWS BTC/ETH/SOL five-minute API/browser witness and reload/replay passed; paper true/live trading false |
| Multi-market live runtime, 0015/0019 | Connectors, buffering, replay and stream/UI foundations exist | All-market real-time operation in AWS has not been established |
| Real instrument charts, 0035 / #144 | Integrated through PR #149; lookup and refresh repairs merged | AWS `76203e0` passed a 601.662-second paired witness: six entry paths, real revisions/appends, reload retention, 296 completed workspace requests, no failures/timeouts; paper on/live execution off. Replay API reports 1,074,523 retained observations. Earlier failures and snapshot limits remain in the ledger |
| 8 GB private staging handoff, 0036 / PR #159 | Documentation and operator evidence are open; exact runtime remains merged `33aa0521` | New private origin is healthy with paper mode on/live trading off; archive/WAL/JSON restore, 13-check smoke, real BTC/ETH/SOL charts and controlled restart passed. A 24-hour capacity/freshness observation, rollback rehearsal and host reboot remain open; the September 17–22 source gap is preserved |

## Next delivery order

0. **Capacity gate: iteration 0036 / PR #159.** The new 8 GB private AWS
   origin passes exact-build health, read-only live smoke, real BTC/ETH/SOL
   charts and controlled restart. Keep the 24-hour observation, rollback
   rehearsal and reboot test ahead of the next provider slice; the old source
   gap remains explicit.
1. **Completed user priority: iteration 0035 / #144.** BTC/ETH/SOL real charts
   from Markets and Watchlist now have renewed AWS acceptance. Preserve the
   observed-coverage labels and five-second delay after each completed refresh.
   See [0035](iterations/0035-live-instrument-charts.md), its compact evidence,
   and the [operator steps](runbooks/live-chart-acceptance.md). This is a measured
   ten-minute result, not an indefinite uptime or complete historical-data claim.

2. **Equities: Moomoo/OpenD after capacity acceptance.** Establish private OpenD reachability and quote
   entitlement, then prove AAPL/NVDA observations during the market session.
   Current five-second polling is not native tick push; delayed or unavailable
   data must be labelled. Do not expose OpenD publicly to solve reachability.
3. **Iteration 0037 code slice (in progress).** The read-only
   `quantmesh-moomoo readiness --json` command now performs a private TCP
   preflight and a bounded quote/daily-history report for `US.AAPL` and
   `US.NVDA`. It is local, paper-safe and order-free. Run it on AWS only after
   the capacity gate and an approved private route are available; a closed
   route is recorded as `route_unavailable` rather than degraded into fixture
   data.
4. **Prediction markets.** Verify Polymarket active-contract subscription and
   mapping; then implement/configure Kalshi's required WebSocket authentication.
   Each venue has its own real-data acceptance; missing credentials are an
   unavailable state, not a healthy feed.
5. **Real history through decisions and review.** Bind trusted, calendar-correct
   historical datasets to the existing Lab/DecisionPacket loop. A few minutes
   of streaming ticks do not create months of qualified daily history. Preserve
   lineage, quality gates, costs and frozen review evidence.

The [0034 ledger](iterations/0034-live-data-delivery.md) records the completed
deployment loop: 304.88 seconds of API sampling, 60 distinct source quote times
per BTC/ETH/SOL, zero disconnected samples, and 323.567 seconds of browser
observations with replay/reload. Keep `4022942` as the demo rollback target.
Later market slices are priorities, not parallel commitments or completed feeds.

## Current bounded gate: 8 GB capacity and data continuity

- User action: let the read-only observer run against the new private origin,
  then review its five-minute API/freshness samples and host capacity log.
- Measurable exit: 24 hours complete with exact build/safety flags, real
  BTC/ETH/SOL quote and candle ages under 60 seconds, no service restart/OOM/
  swap activity, and reviewed memory/disk/latency trends.
- Separate operator gates: rehearse rollback while preserving new observations,
  and test a host reboot before retiring the old rollback resource. These are
  disruptive Class C operations and are not performed implicitly by a smoke
  observer.
- Historical boundary: retain and display the known source gap; do not invent
  bars or silently merge a later live replay into qualified history.
- CI boundary: PR #159 stays open while CI is paused; no merge or deployment
  claim is made from a cancelled check.

## Next bounded slice after capacity acceptance: AWS equity observations

- Local readiness is confirmed on Windows: OpenD listens on `127.0.0.1:11111`
  and the read-only capability probe reports quote/history access with
  `auth_required=false`. This does not make localhost reachable from AWS;
  establish an approved private route or AWS-side OpenD placement first. A
  direct AAPL/NVDA quote request is currently rejected because the vendor
  requires a Basic data subscription, so no real equity quote is accepted yet.
- User action: open AAPL/NVDA in the private workstation and inspect an actual
  source observation, its timestamp, entitlement and market-session state.
- Readiness first: identify the existing licensed OpenD host, verify an approved
  private route from AWS, and inspect the actual quote entitlement. AWS cannot
  use an operator's Windows localhost implicitly. Do not add public OpenD access,
  purchase subscriptions or place an order as a connectivity test.
- Measurable exit: an open-session witness records at least two distinct source
  timestamps for each symbol; closed, delayed and unavailable observations remain
  distinguishable. Keep the existing five-second polling label explicit.
- Deliver one adapter/configuration-to-page loop. Last-price data without bid/ask
  remains research-only; do not fabricate an executable quote. Preserve the
  completed Hyperliquid deployment and the independent 0021 soak.
- Only after readiness is established, write the exact-file test-first plan and
  its issue/iteration record. Additional model/framework work remains sequenced
  behind verified data access and trusted historical evidence.

## Current bounded development slice: Moomoo/OpenD readiness report

- User action: run `quantmesh-moomoo readiness --json` with the private OpenD
  endpoint and inspect route, capability, quote and daily-history statuses for
  AAPL/NVDA.
- Measurable code outcome: the command returns stable `ready`, `partial`,
  `route_unavailable`, `sdk_missing`, `auth_required`, `unavailable` and
  `protocol_error` states, exits non-zero for any incomplete symbol and never
  opens an order context.
- Current operational result: AWS `100.86.41.64` to Windows
  `100.91.234.68:11111` is closed. No public port is opened; the real-source
  acceptance remains pending.
- Local verification: the readiness/CLI/OpenD suite is `69 passed, 1 skipped`;
  Ruff and `git diff --check` pass. CI is paused, so no remote check or deploy
  is claimed.
- Next evidence: after the capacity gate and private route are ready, run the
  probe in an open US session and capture two source timestamps for each symbol,
  with paper mode true and live execution false.

## Execution and completion rules

- One bounded product slice at a time; 0021 soak remains an independent track.
  #132 validation gates and #127 connection witness are tracked separately.
- Before implementation, create the exact-file test-first plan against the
  reconciled baseline. Reuse adapters; preserve license and data-authority gates.
- Record three checkpoints separately: reviewed/merged code, exact deployed
  build, and real-source operator acceptance. CI alone proves neither of the
  latter two.
- Keep paper mode by default and live execution disabled. Real market-data
  reads do not authorize orders or strategy promotion. Promotion still requires
  out-of-sample evidence, costs/slippage, paper observation and a rollback rule.
