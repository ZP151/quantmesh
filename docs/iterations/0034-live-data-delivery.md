# Iteration 0034 — Deployed read-only live market data

- Status: prioritized design; implementation and deployment not started
- Planned: 2026-09-12
- Issue: [#140](https://github.com/ZP151/quantmesh/issues/140)
- Planning branch: `codex/0034-live-data-delivery-plan`, from `origin/main@6ea9a13`
- Dependency: reconcile private staging integration in [#135](https://github.com/ZP151/quantmesh/issues/135); do not overwrite its independent worktree

## User action and outcome

Open the AWS private workstation and inspect real Hyperliquid BTC/ETH/SOL
prices, source timestamps and connection/freshness state. The first bounded
slice succeeds when a five-minute observation records at least two distinct
upstream timestamps for each selected symbol, source data reaches the browser,
and a controlled disconnect/reconnect demonstrates stale/recovery behavior.
Record source-to-browser delay observations rather than claiming an exchange
latency SLA. No order is required for acceptance.

## Evidence and scope decision — 2026-09-12

- **Planner/Product:** the operator identified AWS as the deployment in question.
  Prioritize deployed data delivery before adding more models or research UI.
  Code completion, deployed build identity and live-provider acceptance are
  separate statuses. Iteration 0033 is merged through PR #139 at `6ea9a13`.
- **Read-only deployment audit:** iteration 0031's independent branch
  `codex/0031-aws-private-staging` at `9a177c6` records a 2026-09-09 activation of
  `402294248406fa865d601633f4e5ba3bd3521b5b`. Its health evidence is
  `runtime_mode=demo`, `paper_mode=true`, `live_trading=false`; its tracked
  `deploy/aws/lightsail/quantmesh-staging.service` explicitly uses `--demo`.
  These are recorded deployment facts, not a fresh server probe. The current
  server SHA and runtime must be observed before changing a deployment.
- **Implementer assessment:** main already has LiveFeed/LiveBuffer, venue
  supervisors, replay and local stream delivery. `--demo` and `--live` are
  exclusive. Reuse this path instead of constructing another market-data plane.
  The staging integration has private-origin/build-identity support absent from
  this main baseline; deploying main directly is not a sufficient update plan.
- **Quant Researcher:** live ticks are observations, not trusted daily history,
  qualified forecasts or calibrated confidence. Preserve upstream timestamps,
  venue/instrument identity, calendar and quality semantics. Delayed equity
  entitlements and closed sessions must remain visible. Stream connectivity
  alone cannot satisfy DecisionPacket evidence or paper promotion gates.

## Sequential delivery order

| Priority | Bounded delivery | Exit evidence |
| --- | --- | --- |
| 0 | Reconcile #135 deployment support with merged product code; read current private health and service mode | Exact candidate SHA, preserved private-origin checks, retained rollback target; no assumption that merging updates AWS |
| 1 — this iteration | Hyperliquid BTC/ETH/SOL public feed through the existing cockpit/watchlist and replay | Five-minute real-source/browser witness, stale/reconnect test, reload/replay and paper-only state |
| 2 — follow-up | Moomoo AAPL/NVDA with reachable OpenD and actual quote entitlements | Market-session witness, observed timestamp freshness, explicit delayed/unavailable states; current five-second polling labelled honestly |
| 3 — follow-up | Polymarket active contracts, then authenticated Kalshi streaming | Verified current subscription payloads, token/ticker and expiry mapping; authenticated Kalshi handshake or an explicit unavailable reason |
| 4 — follow-up | Trusted historical datasets feeding the Lab and outcome review | Pinned manifests, quality/calendar acceptance and replayable 7/30-session evidence from real data |

Do not run these as parallel market tracks. Finish and review each visible
user loop before widening venue coverage. The 0021 soak remains independent.

## Existing capability and gaps

- Hyperliquid: public WebSocket/recovery implementation exists. The first
  slice validates the actual deployment path and fixes only blockers to it.
- Moomoo: `src/quantmesh/live/moomoo.py` polls OpenD (default five seconds).
  This is not native tick push. An AWS process cannot assume the operator's
  Windows-local OpenD is reachable; choose a private supported placement first.
  Existing last-price rows lack bid/ask and must not be promoted to executable
  quotes by this work.
- Polymarket: public market feed and REST book adapters exist; validate current
  protocol against real active contracts before declaring deployment acceptance.
- Kalshi: current assembly reuses `LiveHyperliquidTransport`, whose WebSocket
  connection has no signing/authentication headers. The official
  [WebSocket quickstart](https://docs.kalshi.com/getting_started/quick_start_websockets)
  requires handshake authentication. This needs an adapter change and secure
  credential configuration, not merely a watchlist setting.
- `src/quantmesh/api/workstation.py` currently requires a nonempty
  `QUANTMESH_LIVE_WATCHLIST` for `--live`; independent non-crypto enablement is
  a later composition concern, not a reason to expand the first slice.

Protocol references checked 2026-09-12:
[Hyperliquid subscriptions](https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/websocket/subscriptions),
[Polymarket real-time data](https://docs.polymarket.com/market-data/realtime-data).

## Acceptance gates for the first implementation

- [ ] Inspect the actual AWS build/mode and reconcile #135 ownership before
  preparing a deployment candidate; retain private HTTPS and rollback behavior.
- [ ] Write the executable test-first implementation plan against that reconciled
  baseline, naming exact affected runtime/configuration/UI/test files. This
  document is a prioritized design, not an executable implementation plan.
- [ ] Preserve source identity and freshness through existing APIs to the
  rendered prices. Demo, disconnected, stale and live states must be distinct.
- [ ] Record the five-minute BTC/ETH/SOL witness with timestamps and build SHA;
  verify reload/replay and stale detection within the configured threshold.
- [ ] Test disconnect/reconnect using a controlled harness; do not interrupt
  unrelated production or soak connections to manufacture evidence.
- [ ] Run targeted regression checks while developing and required broad gates
  at the reviewed slice/PR boundary; attach exact commands/results to this ledger.
- [ ] Verify `paper_mode=true`, `live_trading=false` and unchanged order/risk
  authority before and after the user loop.
- [ ] Publish an exact-build deployment acceptance checkpoint separately from
  the merge checkpoint. A green CI run is not a live-provider witness.

## Non-goals and boundaries

No live trading, order placement, new forecasting framework, UI redesign,
unrelated soak repair, historical backfill or multi-market expansion in the
first slice. No credentials in prompts/logs/fixtures. This planning change
performs no server update, account subscription or infrastructure mutation.
Deployment execution follows the existing operator scope recorded in #135;
do not infer authority to purchase data or expose new public services.

## Planning verification

- **Reviewer:** one independent read-only review found no actionable issues.
  It checked scope, historical merge dates, issue links and the distinction
  between recorded AWS evidence and a fresh server probe.
- **Verifier:** controller re-read PR #139 merge state, issue #138 closure and
  exact CI run/head; checked all 25 relative Markdown link targets across the
  seven changed documents. `git diff --check` passed. Documentation only; no
  application behavior changed and no new runtime test pass is claimed.
- **Publication:** issue #140 tracks the proposed delivery; this planning PR
  references it without closing it. Implementation and live-provider acceptance
  remain outstanding.
