# QuantMesh Iteration Plan

Updated: 2026-09-12. This replaces the original conceptual iterations 0–5;
historical delivery IDs and evidence remain in the [iteration index](iterations/INDEX.md).
Use the [roadmap](roadmap/ROADMAP.md) for product direction and
[ACTIVE](goals/ACTIVE.md) for the resumable frontier.

## Confirmed state

| Area | Code/integration | Deployment/real-source acceptance |
| --- | --- | --- |
| Decision Inbox and Readiness, 0028–0029 | Merged PRs #130 / #133 | No new deployment claim here |
| Scenario Lab, 0032 | Merged PR #137 | Merge does not establish the AWS version |
| Forecast outcome review, 0033 | Merged PR #139; final-head CI passed | AWS not updated by the merge |
| Private AWS workstation, 0031 / #135 | Independent deployment branch; issue remains open | Last recorded activation: 2026-09-09, `4022942`, demo/paper; fresh server probe outstanding |
| Multi-market live runtime, 0015/0019 | Connectors, buffering, replay and stream/UI foundations exist | All-market real-time operation in AWS has not been established |

## Next delivery order

1. **Reconcile the deployment baseline.** Inspect the actual AWS health/build and
   service mode; integrate #135's private-origin and release/rollback support
   with current product main. Retain an exact rollback target. Do not deploy
   bare main over the independent staging integration.
2. **0034 / #140: real Hyperliquid prices in the deployed workstation.** One
   action: open BTC/ETH/SOL and see real source timestamps and fresh/stale state.
   Accept with a five-minute real-data witness, at least two distinct upstream
   timestamps per symbol, controlled stale/reconnect evidence and reload/replay.
   Use the existing runtime; orders and live execution stay outside this slice.
3. **Equities: Moomoo/OpenD.** Establish private OpenD reachability and quote
   entitlement, then prove AAPL/NVDA observations during the market session.
   Current five-second polling is not native tick push; delayed or unavailable
   data must be labelled. Do not expose OpenD publicly to solve reachability.
4. **Prediction markets.** Verify Polymarket active-contract subscription and
   mapping; then implement/configure Kalshi's required WebSocket authentication.
   Each venue has its own real-data acceptance; missing credentials are an
   unavailable state, not a healthy feed.
5. **Real history through decisions and review.** Bind trusted, calendar-correct
   historical datasets to the existing Lab/DecisionPacket loop. A few minutes
   of streaming ticks do not create months of qualified daily history. Preserve
   lineage, quality gates, costs and frozen review evidence.

The [0034 design](iterations/0034-live-data-delivery.md) contains evidence,
dependencies, acceptance criteria and non-goals. Later market slices are
priorities, not parallel implementation commitments or completed features.
Defer additional model/framework breadth until the deployed data loop works.

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
