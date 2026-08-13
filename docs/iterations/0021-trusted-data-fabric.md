# Iteration 0021 — Trusted Data Fabric

- Status: active
- Started: 2026-08-14
- Completed: pending
- Tracking issue: [#110](https://github.com/ZP151/quantmesh/issues/110)
- Integration branch: `0021-trusted-data-fabric`
- Baseline: `origin/main` at `d4aeed3`; immutable `v0.1.1-rc1` at `b6b05b9`
- Design:
  `docs/superpowers/specs/2026-08-14-trusted-data-fabric-design.md`
- Executable plan:
  `docs/superpowers/plans/2026-08-14-trusted-data-fabric.md`
- Delivery mode: solo fast lane, one integration branch and one final PR

## Objective

Deliver one unified, read-only, trustworthy data path for Moomoo AAPL/NVDA and
Hyperliquid BTC/ETH/SOL. The path must preserve raw evidence, canonicalize and
adjust data through immutable lineage, support deterministic features,
backfill/recover idempotently, expose quality and catalog state, and produce a
qualifying seven-day real-data evidence window.

## Scope boundaries

- Keep `v0.1.1-rc1` immutable and do not promote `v0.1.1`.
- Keep every external venue read-only and every execution path paper-only.
- Do not add algorithms, models, AI workflows or trading permissions.
- Do not use fixture, demo or synthetic rows to repair or qualify real data.
- Stop for credentials, paid services or a major architecture change.

## Role evidence

### Planner — 2026-08-14

The Planner recommended seven dependency-ordered tracer bullets: immutable AAPL
daily lineage, real Moomoo, Hyperliquid BTC candles, multi-asset
microstructure, durable recovery, catalog/downstream lineage and a frozen
seven-day soak. It recommended evolving the owned contracts with v1 read
compatibility instead of creating a permanent parallel subsystem.

### Quant Researcher — 2026-08-14

The Quant Researcher identified acceptance-blocking weaknesses in knowledge
time, mutable manifests, Moomoo pagination, equity adjustment semantics,
calendar handling, Hyperliquid trade identity, checkpoints and quality
evidence. The approved design incorporates every blocking requirement.

### Implementer

The main Codex thread is the only source writer. Implementation begins after
the tracked TDD plan is committed.

### Reviewer and Verifier

Both roles remain read-only. Task 1 required three corrective review rounds;
the final implementation review was clean, with only this ledger update
requested before commit. Verification evidence is recorded at each durable
checkpoint.

## Delivery ledger

| Slice | Status | Dependency | Evidence |
| --- | --- | --- | --- |
| 1. Immutable AAPL daily tracer | in progress | None | Task 1 complete |
| 2. Moomoo AAPL/NVDA | planned | Slice 1 | pending |
| 3. Hyperliquid BTC candles | planned | Slice 1 | pending |
| 4. Hyperliquid BTC/ETH/SOL microstructure | planned | Slice 3 | pending |
| 5. Idempotent collection and recovery | planned | Slices 2 and 4 | pending |
| 6. SLA catalog and downstream lineage | planned | Slice 5 | pending |
| 7. Seven-day real-data evidence | planned | Slice 6 | pending |

## Acceptance ledger

- [ ] Clean installation collects and replays real AAPL/NVDA and BTC/ETH/SOL.
- [ ] Restart and disconnect drills have no silent duplicate or hidden gap.
- [ ] Historical and live-tail paths share canonical instrument/calendar
  semantics.
- [ ] Charts, features, experiments and forecasts resolve immutable source and
  quality evidence.
- [ ] Missing software, rights and entitlements are explicit product states.
- [ ] No synthetic row appears in or repairs a real dataset.
- [ ] One frozen baseline records at least 168 continuous hours and seven daily
  quality reports, including at least four completed XNYS sessions.
- [ ] Full clean-checkout, safety, security, license and browser gates pass.
- [ ] Issue #110 and the final milestone PR contain exact evidence.

## Checkpoint 0 — Activation and design, 2026-08-14

- Issue #110 created as the single iteration tracker.
- Integration branch `0021-trusted-data-fabric` created from `origin/main` in an
  isolated worktree. User-owned changes in the original checkout remain
  untouched.
- Planner and Quant Researcher completed independent read-only audits.
- Official Moomoo and Hyperliquid documentation was rechecked for pagination,
  adjustments, corporate actions, candle limits and trade identity.
- The approved design records the immutable-object, bitemporal, checkpoint,
  quality and seven-day evidence contracts.
- The executable plan maps every requirement to 14 reviewed TDD tasks and one
  final milestone PR.
- No source behavior, execution authority, release tag or provider credential
  changed in this checkpoint.

## Checkpoint 1 — Capability-aware provider resolution, 2026-08-14

- RED: `python -m pytest tests/test_provider_capabilities.py -q` failed at
  collection because `quantmesh.data.capabilities` did not exist.
- GREEN: the final capability suite passed 28 tests. The provider/ingestion and
  existing Moomoo, Hyperliquid, Polymarket and Kalshi regression selection
  passed 160 tests with repository-local `--basetemp` isolation.
- Static verification: Ruff passed for every changed Python file and
  `git diff --check` passed.
- The registry now resolves exact provider, venue, access, data-kind, symbol
  and interval capabilities without access upgrades. Legacy fixture providers
  remain available through `get(Venue)` but their implicit descriptors are
  explicitly legacy-only and cannot qualify as real data.
- Capability metadata now has structured history, pagination, rate-limit,
  entitlement-probe, rights, calendar and latency contracts. Every operation
  declares either no history or enforceably bounded history; cursor paging
  requires a bounded page size.
- Review round 1 found unbounded fixture resolution, incomplete capability
  metadata, invalid-mode admission, legacy membership drift and stale ADR
  wording. Review round 2 found fixture-to-live misclassification,
  provider-scoped fixture identity and non-bar history partition defects.
  Review round 3 found default fixture-mode leakage, incomplete historical
  semantics, weak timezone awareness and remaining ADR wording. All findings
  were reproduced or converted to regression tests and resolved.
- Final read-only Reviewer verdict: implementation clean; this checkpoint was
  the only remaining requested change. No provider credential, order method,
  execution authority, release tag or synthetic repair path was added.
- A Windows global pytest temporary-link cleanup error affected the first
  baseline command after all collected test bodies reached 100%. All recorded
  GREEN commands use an isolated repository-local `--basetemp`; the complete
  post-change suite is tracked separately from the Task 1 focused gate.

## Current frontier

Implement Task 2, canonical instruments and versioned calendars. Start the seven-day
evidence window only after Slices 1–6 are merged into a frozen candidate
configuration.

## Resume instructions

1. Read `AGENTS.md`, `CONTEXT.md`, `docs/goals/ACTIVE.md`, this file, the design
   and the executable plan.
2. Inspect `git status`, branch history, issue #110 and open PRs.
3. Resume the first incomplete plan task; do not redispatch completed commits.
4. Keep the main thread as the only source writer and use read-only reviewers.
5. Mirror every green checkpoint and review verdict into this ledger.
