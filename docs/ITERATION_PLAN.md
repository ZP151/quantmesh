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
| Private AWS workstation, 0031 / #135 | Integrated through merged PR #142 | Private HTTPS, exact build, loopback bind and retained demo rollback verified; #135 stays open for operator-deferred instance firewall acceptance |
| Deployed live data, 0034 / #140 | Merged PR #142 as `e185c3b`; final-head CI passed | AWS BTC/ETH/SOL five-minute API/browser witness and reload/replay passed; paper true/live trading false |
| Multi-market live runtime, 0015/0019 | Connectors, buffering, replay and stream/UI foundations exist | All-market real-time operation in AWS has not been established |

## Next delivery order

1. **Equities: Moomoo/OpenD.** Establish private OpenD reachability and quote
   entitlement, then prove AAPL/NVDA observations during the market session.
   Current five-second polling is not native tick push; delayed or unavailable
   data must be labelled. Do not expose OpenD publicly to solve reachability.
2. **Prediction markets.** Verify Polymarket active-contract subscription and
   mapping; then implement/configure Kalshi's required WebSocket authentication.
   Each venue has its own real-data acceptance; missing credentials are an
   unavailable state, not a healthy feed.
3. **Real history through decisions and review.** Bind trusted, calendar-correct
   historical datasets to the existing Lab/DecisionPacket loop. A few minutes
   of streaming ticks do not create months of qualified daily history. Preserve
   lineage, quality gates, costs and frozen review evidence.

The [0034 ledger](iterations/0034-live-data-delivery.md) records the completed
deployment loop: 304.88 seconds of API sampling, 60 distinct source quote times
per BTC/ETH/SOL, zero disconnected samples, and 323.567 seconds of browser
observations with replay/reload. Keep `4022942` as the demo rollback target.
Later market slices are priorities, not parallel commitments or completed feeds.

## Next bounded slice: AWS equity observations

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
