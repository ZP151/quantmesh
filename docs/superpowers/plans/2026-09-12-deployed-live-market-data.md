# Deployed Live Market Data Implementation Plan

> Use test-first implementation and independent review for each bounded task.

**Goal:** issue #140's AWS private cockpit shows real Hyperliquid BTC/ETH/SOL
prices, source times and freshness, with recorded replay and paper authority.
**Spec:** `docs/iterations/0034-live-data-delivery.md`, approved 2026-09-12.
**Architecture:** reuse the existing supervisors, LiveFeed, replay lake and
same-origin API/SPA; integrate the independent #135 staging support.
**Global constraints:** no orders, live trading, credentials, other providers,
trusted-history backfill, models, dependency upgrades or soak changes. Default
deployment remains demo. The explicit live-data profile is paper-only. Keep
exact-build health verification, private origin and retained-release rollback.

## Observed baseline and decisions

AWS HTTPS health was freshly read on 2026-09-12: `4022942`, demo, paper true,
live trading false. SSH needs the operator's Tailscale check; continue local
implementation while that is pending. Work in the existing isolated worktree.
#141 has a documentation-only archive correction awaiting fresh CI; its commits
are present locally, and its review thread is resolved. Do not bypass required CI.

Merge #135's branch `9a177c6` locally, preserving current product documents and
regenerating current API/bundle assets. Keep the old branch/worktree intact.
The private staging ADR is extended by a separate live-data ADR; real-money
authority does not change. A fresh deployment may have no qualified historical
chart or forecast. Replay acceptance uses recorded MarketUpdates and the
existing replay screen/API, not fabricated daily history.

## Task 1 — Reconciled release profile and rollback

Files: `deploy/aws/lightsail/deploy_release.py`,
`deploy/aws/lightsail/quantmesh-staging.service`,
`tests/test_aws_staging_assets.py`, `tests/test_deployment_identity.py`.
Existing #135 source/API/shell changes are integrated before new behavior.

- [x] Run existing staging/identity tests against the reconciled source.
- [x] Write tests proving explicit `live_market_data=True` produces `--live`,
  BTC/ETH/SOL and separate live roots, while default environment bytes remain
  compatible with retained demo releases. Bad runtime/paper/live health rolls
  back. Existing-release activation infers and validates its canonical profile.
- [x] Observe RED: `python -m pytest -q tests/test_aws_staging_assets.py`.
- [x] Add a default-false deployment argument/CLI flag. Unit defaults to demo
  arguments via `QUANTMESH_STAGING_ARGS`; canonical release env selects live.
  This lets the same unit roll back to legacy env files without a live flag.
  Bind only loopback; keep paper true/live trading false and persistent roots.
- [x] Verify expected mode AND exact identity AND paper safety in activation.
  Keep retained environment validation strict; never rewrite old releases.
- [x] GREEN: staging asset/identity tests and scoped Ruff. Controller performs
  generated API and bundle checks after integration. Commit with ledger evidence.

## Task 2 — Actual public protocol and connection lifecycle

Files: `src/quantmesh/live/hyperliquid.py`,
`src/quantmesh/hyperliquid/wire.py`, `tests/test_live_supervisor.py`,
`tests/test_hyperliquid_wire.py`, `tests/test_live_e2e.py`; other Hyperliquid
fixture files only where the same corrected contract requires alignment.

- [x] Add official-shaped ACK, per-coin `activeAssetCtx` and nested BBO tests:
  `{"coin":"BTC","time":1789200000000,"bbo":[{"px":"60000","sz":"1","n":1},{"px":"60001","sz":"2","n":1}]}`.
  Include null book sides and normal subscription acknowledgments.
- [x] RED: `python -m pytest -q tests/test_hyperliquid_wire.py tests/test_live_supervisor.py`.
- [x] Ignore valid ACKs, subscribe context per coin, parse `{coin,ctx}` and
  official BBO sides without inventing missing prices. Preserve timestamp and
  instrument validation. Close old sockets and clear obsolete pending sends
  on reconnect; prove cleanup via injected transports.
- [x] Correct fixture shapes and prove ACK -> data -> disconnect -> resubscribe
  and recovery, retaining existing gap semantics. GREEN same tests plus
  `tests/test_live_smoke.py`; controller runs bounded browser E2E once built.
- [x] Record official protocol source, RED/GREEN and review evidence; commit.

## Task 3 — Source freshness through browser display

Files: `src/quantmesh/live/feed.py`, `tests/test_live_feed.py`,
`frontend/src/lib/live.ts`, `frontend/src/lib/live.test.ts`,
`frontend/src/screens/Cockpit.tsx`, `frontend/src/screens/CockpitDetail.tsx`,
`frontend/src/screens/Cockpit.test.tsx`.
Only minimal compatible response typing in `frontend/src/lib/api.ts` and
existing bilingual messages if required; coordinate these shared files.

- [x] Add old-source/new-receipt tests and future-clock tests. For timestamped
  quotes, source age must not be reset by a new local receipt. Receipt-only
  metrics cannot satisfy upstream timestamp acceptance.
- [x] RED: `python -m pytest -q tests/test_live_feed.py` and
  `npx vitest run src/lib/live.test.ts src/screens/Cockpit.test.tsx` in frontend.
- [x] Preserve receipt/source semantics and age cached browser prices when
  snapshots/streams fail. Do not relabel an old quote fresh because mids arrive.
  Expose inspectable source time using the existing table/detail conventions;
  no dashboard redesign or strategy-authority change.
- [x] GREEN same tests plus affected live consumers; typecheck/lint. Controller
  owns one combined desktop/mobile browser inspection and correction batch.
- [x] Commit at reviewed coherent checkpoint with quant semantics recorded.
- [x] External-review correction, scoped by Planner: share monotonic aging with
  the existing detail consumer and retain disconnected status as an availability
  veto during snapshot/stream reconciliation and timer aging. No new surface.

## Controller verification and deployment

Use shared Python with explicit current-worktree `PYTHONPATH` and a unique
`--basetemp` to avoid unrelated Windows temp cleanup permissions. Never install
into the shared environment. Independent tasks use separate test temp roots.

- [x] Run focused protocol/feed/router/replay/staging and frontend checks.
- [x] Regenerate API via `npm run generate:api`; build via
  `python tools/build_frontend.py`; verify `npm run check:api`, actual `tsc -b`,
  Ruff and `git diff --check`. Required broad pytest runs in final-head CI;
  do not launch a duplicate multi-hour local suite or soak.
- [x] One independent Standards/Spec review at the user-loop boundary; at most
  two rounds, then reduce scope on structural failure.
- [x] Publish one integration PR referencing #135/#140, check required CI and
  unresolved review, merge dependencies in order under standing authority.
- [x] Inspect SSH service/user/disk/retained release without dumping env secrets.
  Install the reviewed unit and exact release through the checked deployment
  path; retain `4022942` rollback. No new AWS resource or public ingress.
- [x] Probe private HTTPS exact build, `runtime_mode=live`, paper true/live false.
  Observe five minutes; each BTC/ETH/SOL has >=2 distinct upstream quote/trade/
  book timestamps. Record receipt/browser timing and existing replay extent.
- [x] Open real cockpit in browser, inspect prices/source/freshness, reload and
  replay. Controlled disconnect is tested in the fixture, not induced in soak.
  Verify risk state unchanged and no order created.
- [x] Record separate merge/deployment/live-data checkpoints; archive completed
  goal, update ACTIVE and finish only when required acceptance is demonstrated.

Completion evidence: `docs/iterations/0034-live-data-delivery.md`, final AWS
acceptance checkpoint on 2026-09-12. PR #142 merged as `e185c3b`; the exact
build passed the separate source/API/browser witness.
