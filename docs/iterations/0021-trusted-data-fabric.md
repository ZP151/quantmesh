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

Both roles remain read-only. Tasks 1–5 received independent Standards and
implementation reviews; every finding was reproduced before correction and
each final task verdict was clean. Verification evidence is recorded at each
durable checkpoint.

## Delivery ledger

| Slice | Status | Dependency | Evidence |
| --- | --- | --- | --- |
| 1. Immutable AAPL daily tracer | complete | None | Checkpoint 4 |
| 2. Moomoo AAPL/NVDA | in progress | Slice 1 | Task 6 foundation complete; Checkpoint 6A |
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

## Checkpoint 2 — Canonical instruments and versioned calendars, 2026-08-14

- RED: `python -m pytest tests/test_trusted_instruments.py
  tests/test_market_calendars.py -q` failed at collection because both owned
  modules were absent. Two later RED cycles reproduced bitemporal, session
  policy, forged-window and support-boundary defects found during review.
- GREEN: 56 focused instrument, calendar, security and release-lock checks
  passed; the Task 1–2 integration selection passed 82 tests. Ruff,
  `pip check`, `git diff --check` and the deterministic license review passed.
- The five bounded canonical IDs now resolve from exact Task 1 provider IDs
  through immutable aliases with independent effective and knowledge windows.
  Each catalog exposes a stable SHA-256 content identity; cross-provider and
  cross-instrument mappings fail closed.
- `CalendarService` pins `exchange-calendars==4.13.2`, fixed support ranges and
  explicit `regular`, `extended` and `continuous` policies. XNYS extended
  sessions remain an explicit unavailable state. XNYS windows validate against
  the pinned schedule, including holidays, DST and early closes; 24/7 windows
  cover exact UTC days.
- The release closure grew from 64 to 68 packages. The direct Apache-2.0
  dependency and its permissive transitive closure are pinned in
  `requirements-audit.txt`, inventoried in `docs/licenses.md` and recorded in
  the reuse matrix. The local license gate reviewed all 68 packages.
- Review round 1 found provider-ID drift, conflated effective/knowledge time,
  missing session policy, cross-provider mappings, forgeable window identity
  and missing adversarial tests. Review round 2 found direct forged XNYS
  sessions and an invalid documented lower bound. All findings have direct
  regressions and are resolved. Final read-only Reviewer verdict: CLEAN, with
  no remaining Critical or Important finding.
- The full-suite diagnostic reached `2622 passed, 4 skipped` and exposed one
  Task 2 audit-lock ordering failure while this task's lock edit was present.
  The ordering defect was fixed and its exact release-lock test is GREEN; the
  next complete milestone verification will run from the committed tree.
- The pinned upstream calendar emits five NumPy deprecation warnings in the
  focused suite. They are upstream warnings under the current supported NumPy
  range, not suppressed or represented as project failures.

## Checkpoint 3 — Content-addressed objects and immutable manifests, 2026-08-14

- RED began with absent object and artifact modules. Every later Reviewer
  finding was reproduced as a focused regression before correction.
- GREEN: the final Task 1–3 integration, v1 manifest/Lake compatibility and
  security selection passed `195 passed, 3 skipped`. Ruff passed all changed
  Python files and `git diff --check` passed. The five warnings are the already
  recorded pinned `exchange-calendars` NumPy deprecations.
- V2 objects, manifests and immutable revision reservations live beneath
  `.trusted-data-v2`, which cannot collide with a legal v1 dataset name. Exact
  readers validate content hashes plus typed bar instrument, interval, event
  coverage and row identity declarations.
- Genesis is one atomic same-filesystem directory activation. Later revisions
  use a hard-link- and reparse-safe cross-process lock, append/fsync
  hash-chained history, immutable revision binding and compare-and-swap
  pointer. Old readers remain stable; rollback, deletion reset and revision
  reuse fail closed.
- Crash tests cover before/after genesis activation, manifest before pointer,
  missing pending evidence, concurrent publishers and torn history. Tail
  repair requires matching CAS, exact candidate identity and compatible
  reservation/manifest evidence; committed, conflicting or ambiguous tails
  are never repaired.
- A real Windows junction probe returned `JUNCTION_REJECTED=True` and left its
  external target empty. Independent Standards review and final implementation
  review were CLEAN after all reproduced Critical/Important findings closed.
- ADR-0016 records the v1 boundary, v2 storage contract and local-filesystem
  trust-root limitation. No provider credential, execution authority, release
  tag or synthetic repair path changed.

## Checkpoint 4 — Bitemporal raw-to-feature AAPL tracer, 2026-08-14

- RED began with the three planned modules absent. Later RED cycles reproduced
  raw tampering, future-event leakage, retroactive knowledge time, pending
  manifest visibility, fabricated source identities, stale cross-revision
  feature linkage and historical-retry non-idempotence.
- GREEN: 25 focused envelope, lineage, derivation, tamper, correction, crash
  and knowledge-time tests passed. The final Task 1–4 integration, v1
  compatibility, feature and security selection passed `277 passed, 3
  skipped`; Ruff and `git diff --check` passed. The five warnings are the
  already recorded pinned `exchange-calendars` NumPy deprecations.
- `RawEnvelope` now binds exact provider bytes to request, event, receipt,
  ingestion, rights, entitlement, schema, canonical instrument and source
  event identities. Fixture provenance is structurally isolated and cannot
  qualify as real data.
- The AAPL daily tracer publishes raw, normalized, explicitly unadjusted and
  `log_return(window=2)` feature artifacts through four immutable linked
  manifests. Lineage validation recomputes canonical parent-to-child
  derivation and rejects metadata, transformation or object substitution.
- Knowledge-time reads expose only current-pointer-committed revisions. A
  crash after manifest creation but before pointer advance cannot leak the
  pending vintage; changed revisions move knowledge forward, while retries of
  old requests return their original IDs without changing current state.
- Eight corrective review cycles identified 16 Important integrity gaps,
  including uncommitted-vintage visibility, retroactive knowledge, unrooted
  provenance, unverified derivation and preflight partial publication. Every
  finding received a direct regression and was corrected. Final read-only
  security and implementation verdicts: CLEAN. No real provider, credential,
  order authority, release tag or synthetic repair path changed.

## Checkpoint 5 — Complete read-only Moomoo evidence transport, 2026-08-14

- RED began with seven missing pagination/action behaviors, then expanded with
  adversarial regressions for silent truncation, cursor cycles, structural
  legacy transports, malformed SDK result envelopes, per-row instrument drift,
  strict scalar/timestamp handling and reversed UTC windows.
- GREEN: 106 focused OpenD, adapter and provider tests passed. The final Task
  1–5 integration, security and release/audit selection passed `310 passed`;
  Ruff and `git diff --check` passed. The five warnings are the already
  recorded pinned `exchange-calendars` NumPy deprecations.
- History collection now follows every opaque cursor under cumulative page and
  row bounds while keeping one quote context for the chain. Repeated cursors,
  empty nonterminal pages, out-of-window rows, malformed result tuples/status,
  metadata drift, duplicates and non-monotonic rows fail closed.
- Raw pagination evidence encodes cursor bytes losslessly as base64 and
  normalizes SDK values to strict JSON. Missing `NaN`/`NaT`/`NA` values become
  null; infinities, unsupported scalars, booleans/numeric strings in OHLCV,
  wrong row symbols and date-only intraday timestamps are rejected.
- Adjustment factors, stock splits and dividends use official quote-only
  surfaces and remain unadjusted source evidence. No trade context, unlock,
  credential or execution authority was added. A legacy one-page transport can
  still serve compatibility reads but cannot qualify as a complete raw bundle.
- The repository's `10.02.6208` audit snapshot lacks the split/dividend
  methods. Apache-2.0 candidate `moomoo-api==10.10.7008` was inspected and has
  the required surfaces, but was deliberately not admitted: Task 6 must pin
  and audit its complete optional dependency closure before real collection.
- Repeated corrective review rounds closed every reproduced Critical/Important
  finding. Fresh final Standards and adversarial implementation/security
  verdicts were both CLEAN. ADR-0004 and
  the reuse matrix now record the exact compatibility, timeout and dependency
  boundaries.

## Checkpoint 6A — Moomoo adjustment and process foundation, 2026-08-14

- RED first proved the adjustment, bounded-plan, XNYS holiday, unavailable
  result and process-deadline contracts were absent. The implemented tests now
  reject future-known or ambiguous splits, closed-session false gaps,
  out-of-scope targets, escaped worker results and timed-out workers.
- `moomoo-api==10.10.7008` is now part of the full release closure
  `.[dev,research,e2e,moomoo]`, not an unaudited side extra. CI, Security and
  the clean-checkout release gate install the same closure. The regenerated
  lock contains 72 packages; `moomoo_api`, `protobuf`, `pycryptodome` and
  `simplejson` are inventoried and the local deterministic license review
  passed all 66 packages installed on Windows, with six documented Linux-only
  members.
- The split-adjustment kernel pins independent factor/action manifest IDs and
  a UTC knowledge cutoff. It backward-adjusts OHLC by division and volume by
  multiplication, refuses later-announced actions and conflicting effective
  ratios, and never relabels unadjusted bars as adjusted.
- The synchronous SDK now has a credential-free subprocess boundary with a
  whole-process deadline, sanitized environment, bounded staged JSON and
  process-tree termination. Timeout/failure output is removed and cannot be a
  manifest. Parent-side strict decoding revalidates symbol, interval, window,
  payload code, ordering and SDK version before publication is possible.
- Verification: dependency/license/security/release selection passed 41 tests;
  adjustment, collection, OpenD and provider selection passed 81 tests with
  one expected missing-SDK-era skip; focused Ruff passed. The five warnings
  remain the already recorded pinned `exchange-calendars` NumPy deprecations.
- This is a durable mid-task checkpoint, not Task 6 acceptance. The collector
  and real manifest publication are intentionally still pending, and no real
  OpenD evidence, credential, execution authority or synthetic repair was
  claimed.

## Current frontier

Finish Task 6 by cross-checking official factor/split evidence and publishing
bounded raw, normalized and split-adjusted AAPL/NVDA manifests or an honest
typed unavailable state. The compatible SDK closure and enforceable process
deadline are complete. Start the seven-day evidence window only after Slices
1–6 are merged into a frozen candidate configuration.

## Resume instructions

1. Read `AGENTS.md`, `CONTEXT.md`, `docs/goals/ACTIVE.md`, this file, the design
   and the executable plan.
2. Inspect `git status`, branch history, issue #110 and open PRs.
3. Resume the first incomplete plan task; do not redispatch completed commits.
4. Keep the main thread as the only source writer and use read-only reviewers.
5. Mirror every green checkpoint and review verdict into this ledger.
