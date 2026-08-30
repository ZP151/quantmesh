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

## Product direction and readiness decision

- Current product stage: accepted local research-workstation prototype with a
  credible paper-trading safety boundary; it is not yet a trusted-data alpha or
  an autonomous trading product.
- Primary constraint: feature breadth is ahead of real-data trust. The next
  product threshold therefore depends on immutable real-provider evidence,
  truthful gaps, recovery and operator-visible quality state rather than more
  strategies, AI features or execution adapters.
- Approved direction: complete this Trusted Data Fabric across Moomoo and
  Hyperliquid first, then integrate catalog-qualified datasets into charts,
  experiments, forecasts and paper automation. Prediction-market expansion
  remains downstream of the same source-rights and lineage contract.
- Delivery distance: iteration 0021 is the gate to a real-data acceptance
  alpha. A dependable local research beta still requires subsequent vertical
  slices for operator workflows, strategy evaluation and guarded paper
  orchestration. Any live-money product remains a separate, explicitly
  authorized program with additional security, risk and operational evidence.
- Next-stage decision rule: do not advance the product stage on UI presence or
  endpoint reachability alone. Advance only when the frozen candidate satisfies
  this iteration's seven-day evidence, replay, quality, safety and clean-checkout
  acceptance ledger.

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

Both roles remain read-only. Tasks 1–11 received independent Standards and
implementation reviews; every finding was reproduced before correction and
each final task verdict was clean. Verification evidence is recorded at each
durable checkpoint.

## Delivery ledger

| Slice | Status | Dependency | Evidence |
| --- | --- | --- | --- |
| 1. Immutable AAPL daily tracer | complete | None | Checkpoint 4 |
| 2. Moomoo AAPL/NVDA | complete | Slice 1 | Task 6; Checkpoints 6A–6D |
| 3. Hyperliquid BTC candles | complete | Slice 1 | Checkpoint 7 |
| 4. Hyperliquid BTC/ETH/SOL microstructure | complete | Slice 3 | Checkpoint 8 |
| 5. Idempotent collection and recovery | complete | Slices 2 and 4 | Checkpoint 9 |
| 6. SLA catalog and downstream lineage | complete | Slice 5 | Tasks 10–12; Checkpoint 12 |
| 7. Seven-day real-data evidence | in progress | Slice 6 | Functional acceptance passed (Checkpoint 16); real 168h deferred post-merge |

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

## Checkpoint 6B — Moomoo trusted-lineage implementation candidate, 2026-08-14

- Official `get_rehab` factor rows and the independently collected stock-split
  action rows are normalized only when one unique forward- or reverse-split
  pair agrees on type, ratio, announcement time and effective date. Dividend
  rows remain a separate immutable raw surface and are not represented as a
  total-return adjustment.
- Each qualifying bundle publishes eight content-addressed manifests: raw
  history pages, raw factors, raw split actions, raw dividends, canonical bars,
  canonical split actions, split-adjusted bars and `log_return(window=2)`
  features. Publication reopens immutable bytes and recomputes every derivation;
  a forged adjusted object is rejected even when its manifest shape and parent
  identifiers are otherwise valid. Exact retry input returns the same IDs.
- Equity history no longer copies a raw close into `adjusted_close` because a
  legacy binding label says `split-adjusted`. XNYS daily coverage uses the
  pinned exchange calendar, so weekends and market holidays are not reported
  as missing sessions. The existing live-tail path remains fail-closed for
  adjusted series and never fabricates an adjusted live value.
- The isolated worker now preserves only the non-secret Windows runtime paths
  required by Python and the official SDK while continuing to strip proxy,
  token, password and API-key variables. Provider market metadata is explicit,
  an unreachable local OpenD socket is classified before the SDK's unbounded
  retry loop, and the outer whole-process deadline remains authoritative.
- Real read-only probe: the audited SDK reported version `10.10.7008`; local
  `127.0.0.1:11111` was not listening, so the result was the honest typed state
  `unavailable/daemon-unavailable`, `manifest_ids=[]`, with no dataset directory
  created. No credential, entitlement, synthetic fallback or positive real-data
  claim was introduced.
- RED evidence reproduced missing validator imports, strict JSON/datetime
  deserialization failure, omitted provider market metadata, missing child
  home/APPDATA runtime paths and daemon misclassification. GREEN verification:
  `172 passed, 1 skipped` across collection, adjustment, fabric, history, OpenD
  and provider regressions; focused Ruff and `git diff --check` passed. The five
  warnings remain the recorded pinned `exchange-calendars` NumPy deprecations.
- This checkpoint records an implementation candidate, not Task 6 completion.
  Two fresh read-only reviews are in progress; Step 5 and the Task 6 commit stay
  open until every Critical/Important finding is resolved.

## Checkpoint 6C — Moomoo review correction round 1, 2026-08-14

- The first fresh specification review returned FAIL with two Important
  findings. The independent integrity review returned CHANGES_REQUIRED with two
  Critical and three Important findings. Task 6 therefore remained open and no
  completion commit was created.
- Official Moomoo documentation resolved the reviewers' conflicting ratio
  interpretations: `get_rehab.split_ratio` is old/new for both a forward split
  and a share consolidation. The adjustment factor consumed by QuantMesh is its
  inverse, new/old. Official-shape forward and reverse fixtures now pin this
  contract. Equal-ratio actions are paired by effective-date order with the
  latest unique preceding announcement, independent of provider row order.
- A worker-provided receipt timestamp is no longer authoritative publication
  knowledge. The collector overwrites it with a parent-observed UTC completion
  time before validating or publishing any payload, preventing a staged result
  from backdating historical availability.
- Publication validation now requires eight distinct roles, exact raw data kind
  and endpoint, envelope/manifest time and rights agreement, canonical raw
  transformation declarations, and exact normalized/action/adjusted/feature
  layer, schema, policy, row identity and parent declarations. Raw-role
  substitution and feature-transformation forgery have direct regressions.
- Child stdout and stderr now go to the null device rather than unbounded memory
  pipes; the bounded staged JSON file remains the worker's sole accepted output.
  Runtime home/APPDATA paths remain allowlisted while API keys and credentials
  remain excluded.
- Bundle-level crash recovery is intentionally owned by Task 9. Task 6 collects
  every provider result before its first write, and every individually published
  child is truthful and independently valid; unavailable provider states still
  publish nothing. A fresh reviewer must confirm this phase boundary before Task
  6 can close.
- Correction GREEN: six new reviewer-driven regressions passed. The complete
  Task 6 selection passed `176 passed, 1 skipped`; focused Ruff and
  `git diff --check` passed. A fresh scoped re-review is in progress.

## Checkpoint 6D — Moomoo trusted lineage accepted, 2026-08-14

- Scoped review round 2 confirmed factor orientation, chronological action
  matching, parent-observed knowledge time and bounded worker output, but kept
  Task 6 open because self-consistent raw identity/range declarations were not
  yet recomputed from source bytes. It also found missing source-symbol binding.
- Raw validation now recomputes bar, factor, split and dividend identities plus
  event coverage from immutable provider bytes; bar interval is source-derived.
  Factor, split and dividend `code` values must match the canonical provider
  symbol, preventing cross-symbol evidence substitution. Empty normalized-action
  coverage is pinned to empty factor/split evidence time rather than inherited
  from the bar request window.
- Three source-declaration attacks and two final source-symbol/empty-coverage
  attacks were reproduced RED before correction. Final Task 6 verification is
  `181 passed, 1 skipped`; focused Ruff and `git diff --check` passed. The real
  negative OpenD probe remained `unavailable/daemon-unavailable`, zero manifest
  IDs and no dataset directory. `pip check` and the 72-package deterministic
  license review passed.
- Final fresh read-only scoped review verdict: PASS. Both remaining findings are
  addressed, prior source-derived checks remain intact, and no new Critical or
  Important issue exists. Bundle-level crash atomicity remains explicitly owned
  by Task 9 and is non-blocking at this boundary.
- Task 6 and Slice 2 are complete. No positive real OpenD/entitlement evidence,
  credential, synthetic repair, execution authority or release change is
  claimed.

## Checkpoint 7 — Hyperliquid candle lineage accepted, 2026-08-14

- Commit `97fee3087345` completes bounded BTC, ETH and SOL candle collection
  from Hyperliquid's public-mainnet `/info` endpoint. `PublicInfoTransport`
  exposes only candle and L2-book reads against the immutable pinned URL; it has
  no wallet, signing, account, exchange, cancel or order surface.
- The provider capability contract records exact per-interval history limits.
  Collection accepts no more than 5,000 inclusive opens, requires exact
  interval-aligned UTC boundaries, verifies a complete requested window and
  publishes only exclusively closed candles. The provider's inclusive final
  millisecond is normalized only at the collection boundary.
- Direct transport identity, exact endpoint identity and a clean producing Git
  commit are mandatory qualification gates before every request and again
  before publication. Injected or scripted clients remain reproducible fixture
  paths and cannot qualify as real data. Public data requires no entitlement,
  but fixture provenance remains disqualifying.
- Candidate publication constructs, rederives and validates the complete raw,
  normalized, identity-adjusted and log-return graph before activating its
  first catalog pointer. Dataset IDs, canonical-byte digests, media types,
  schema and transformation digests, declarations and parent links are exact.
  Multi-pointer crash recovery remains the explicit Task 9 boundary.
- RED/GREEN and reviewer-driven correction cycles closed invalid zero intervals,
  malformed wire rows, host-timezone drift, mutable transport state, dirty-tree
  races, source substitution and partial-graph publication. Final independent
  Standards and specification reviews both returned PASS with no Critical or
  Important finding.
- Final verification passed 116 focused tests and 348 scoped regressions, with
  only five recorded `exchange-calendars` NumPy deprecation warnings. Ruff,
  `pip check`, the deterministic 72-package license review and
  `git diff --check` passed.
- A clean post-commit public-mainnet smoke used UTC window
  `2026-08-13T21:54:00Z` through `2026-08-13T21:56:00Z`. BTC, ETH and SOL each
  qualified as real and produced four immutable manifests:
  - BTC: raw `11812e8d7e1b657a58c14c5c608c13aad229fd522595bf07ce08e6a696826e10`,
    normalized `f43308861c59494cfc1877fd6f3188d3e1a7694461b199235adb414c75fc9058`,
    adjusted `80facac599048ead6b3dc5ace4e452c5ce2388fb70775f92cb89b125957a684a`,
    feature `6157ca9ba295ca124d27037c94a2d1e2bca743d94e776997f71ad1d698583307`.
  - ETH: raw `1004f766785948ab55ad203f52236f518f8cd4495989a997c61dc52e6711d98a`,
    normalized `9e722bc2f52e75601def3714ef8d35fd5585bed37013106ff228b8052262edd9`,
    adjusted `3682b831f3eb6ff29637afe83b9b489e516652ab929904bce44228e451e33d2d`,
    feature `08815b1e6058930511318817bc25a6a7c6498c847edf3c03b530f73b0f04ca60`.
  - SOL: raw `b4e6bd4ebae844222b178eb7ecd1499aaa40cb56d99afdb315483e782be62aea`,
    normalized `84b23602ace57f76ab6d51cc2bad8f2011e93a2d228a7a7b508ff378dfd5189a`,
    adjusted `bcb92243aaa326ec4e2dd79d215e7d178624d6388c38b53c897827c792017650`,
    feature `e03b02f93c8086797cb4fb444992ed7fba763b05ef845d45d18987b476712798`.
- Task 7 and Slice 3 are complete. The smoke evidence is tied to the producing
  code commit rather than this later record-only commit.

## Checkpoint 8 — Hyperliquid microstructure identity and gap evidence, 2026-08-14

- Task 8 implementation is committed at `11f99cc`. A shared identity module
  defines Hyperliquid trade IDs from canonical `(block_time_ms, uppercase coin,
  tid)` and bid/ask IDs from one content-derived L2 snapshot epoch. Nonconsecutive
  `tid` values are valid identities and never imply missing trades.
- `MarketUpdate` now carries a canonical content digest, scoped source event ID,
  snapshot epoch and structured continuity evidence. Contradictory states fail
  validation. LiveBuffer schema v2 performs an idempotent legacy migration,
  rejects newer schemas before mutation, deduplicates exact redelivery and
  quarantines same-identity/different-content corrections without overwriting
  accepted evidence.
- Hyperliquid reconnect recovery starts from the last database-acknowledged final
  candle, requests only the completed provider window, ignores a provider's
  extra provisional row and keeps every partial-recovery row visibly gapped.
  Trades are explicitly unrecoverable because no official public trade-history
  endpoint is used; books recover through an authoritative public `/info`
  snapshot and receive a new epoch.
- The production `--live` assembly injects `PublicInfoRecoverySource`, a sealed
  data-only adapter exposing only candles and L2 books. No wallet, signing,
  account, exchange, order or cancel method is reachable. WebSocket failure
  closes the dead transport before reconnecting.
- Supervisor output is row-bounded under backpressure while preserving one L2
  bid/ask epoch as an indivisible two-row unit. Findings identify the stream
  actually dropped and survive into reconnect surfacing. Retention prunes L2
  epochs atomically. Restart hydration restores the last proven candle cursor,
  trade identity, both book sides and both `allMids`/`activeAssetCtx` channels.
- The API and React workstation retain continuity and identity declarations.
  Poll snapshots and WebSocket updates reconcile monotonically under the full
  `(venue, instrument, kind, source_event_id)` identity; delayed HTTP responses
  cannot roll back badges, evidence, quotes, metrics or books. Depth is rendered
  only when bid and ask belong to the same newest complete epoch.
- Corrective review rounds reproduced and closed every reported Important issue,
  including pre-persistence cursor advancement, process-restart cursor loss,
  partial-gap clearing, split book backpressure/pruning, future-schema downgrade,
  dead-socket reuse, incomplete state hydration and delayed-snapshot rollback.
  Final independent Standards and implementation verdicts were both CLEAN with
  no Critical or Important finding.
- Verification evidence: `711 passed` for the broad live, Hyperliquid and
  workstation selection; final corrected focus `122 passed`; frontend Vitest
  `147 passed`; Ruff, TypeScript, production build, OpenAPI-client consistency,
  packaged-bundle freshness and `git diff --check` all passed. Four existing
  Fast Refresh warnings are unchanged. One broad-run Uvicorn shutdown warning
  occurred after a WebSocket test had already passed and did not fail the gate.
- Task 8 and Slice 4 are complete. Task 9 owns immutable collection-run state,
  one-writer compare-and-swap checkpoints and crash-boundary recovery; this
  checkpoint does not claim those later guarantees.

## Checkpoint 9 — Atomic collection graph recovery, 2026-08-14

- Task 9 defines collection-job schema v2 over the complete bounded provider
  request, producing Git commit and explicit collection cycle. Exact-cycle
  retries keep one deterministic run identity while attempts increase
  monotonically; a later cycle may preserve a provider correction as a new
  knowledge-time revision.
- Exact provider output is captured before transformation as one immutable
  aggregate source object plus the ordered digest sequence of all raw endpoint
  payloads. Duplicate payload multiplicity is preserved and a changed payload
  for the same job is quarantined rather than rebound.
- `CollectionCoordinator` stages raw, derived and canonical manifest evidence,
  creates a typed integrity-only preflight and advances the complete graph in
  one compare-and-swap DuckDB transaction. Quality remains deliberately
  unclaimed until Task 10.
- ADR-0017 records the graph authority: canonical manifests retain their
  ADR-0016 paths; immutable, hash-chained commit journals independently verify
  DuckDB; permanent graph-owner markers fence legacy publication; and the exact
  legacy predecessor remains required after migration.
- Every public control-plane read verifies the complete journal, checkpoint,
  history, current, row-level commit identity and ownership graph. Every graph
  member records an immutable manifest/revision high-water and is permanently
  owned even when its manifest is unchanged. Deleted or coherently rolled-back
  legacy pointers cannot weaken that anchor.
  Cross-dataset corruption, coherent checkpoint forgery, missing rows and
  reservation/owner crash windows fail closed instead of exposing stale legacy
  state.
- Recovery runs only under the cross-process writer lease. It reconstructs
  committed markers, source rows and owner evidence; recovers both pre-link and
  post-link publication interruptions; and reuses a complete pending graph
  without contacting the provider. Source batch identity is independently
  anchored before graph construction and repeated in pending/commit evidence.
- Completed retries re-read the aggregate source object, all raw/derived
  objects, integrity preflight and committed parent lineage. External staged
  parents are rejected unless included in the same graph. Positive one-page
  and multi-page Moomoo collector-to-coordinator tests prove source digest
  granularity agrees with the four raw endpoint envelopes per request.
- The crash matrix covers every public publication stage in a fresh subprocess;
  eight independent processes converge on one logical graph publication.
  Historical retries, source conflicts, duplicate source bytes, graph-history
  deletion, checkpoint tampering and Windows lock boundaries have dedicated
  regressions.
- Verification evidence is `220 passed` for the final Task 9 integration
  selection and `120 passed` for the final control-plane, recovery, manifest
  and Moomoo focus.
  Ruff and `git diff --check` passed. Final fresh Standards and adversarial
  reviews returned CLEAN with no Critical or Important finding.
- Task 9 and Slice 5 are complete. No credential, execution authority, quality
  qualification, release tag or synthetic repair path changed.

## Checkpoint 10 — Immutable quality SLA evidence, 2026-08-14

- Task 10 adds content-addressed quality policies, evaluations and graph-level
  reports with `pass`, `fail`, `not-due` and `unavailable` states. The report
  hashes the checkpoint projection before the checkpoint records its report ID,
  avoiding a manifest hash cycle while preserving an exact job/run/preflight
  and graph-member binding.
- Measurements are derived from immutable objects, typed artifacts and raw
  envelopes. Raw event identities are reconciled with row-level payload
  fingerprints; normalized split actions and features are decoded through their
  bounded contracts; historical overlaps carry exact conflict fingerprints.
  An amendment can reconcile only the identical prior conflict set.
- Exact calendar behavior covers continuous UTC grids, XNYS regular and early
  closes, venue-local daily identities, DST-aware inclusive terminal bounds and
  session-close availability. Premature daily bars, out-of-session rows,
  missing terminal bars and hard integrity failures all fail rather than being
  hidden by grace or provider unavailability.
- Real graphs must use the authoritative policy, job window and checkpoint
  evaluation time. Fixture graphs cannot carry qualifying reports. Public
  checkpoint and manifest reads verify only the owning job/dataset quality
  closure, so one corrupt independent report fails closed without blocking
  unrelated datasets; completed retries additionally remeasure semantics.
- ADR-0018 records the authority and rollback boundary. Reviewer-driven RED
  probes closed false passes, policy/window bypass, broad corruption blast
  radius, batch-level overlap false positives, amendment overreach and
  checkpoint/report tampering.
- Final verification is `93 passed` for quality, calendar and graph-recovery
  integration and `58 passed` for complete Hyperliquid/Moomoo provider
  regressions. Ruff, `git diff --check`, `pip check` and the deterministic
  72-package license closure passed. The final fresh adversarial review verdict
  is CLEAN.
- Task 11 is now active: expose catalog and downstream immutable lineage without
  changing release, execution, credential or synthetic-data authority.

## Checkpoint 11 — Trusted lineage catalog backend, 2026-08-14

- Task 11 adds a read-only catalog over v2 manifests, exact quality evidence,
  source rights, entitlement, provider access, checkpoint state and recursive
  immutable parents. `GET /api/data/catalog` lists dataset heads and `GET
  /api/data/catalog/{manifest_id}` returns one exact manifest plus lineage;
  exact identity and dataset-current identity are represented separately.
- Production workstation assembly now binds one `TrustedDataCatalog` to the API,
  history service and forecast registry. History, feature, experiment and
  forecast contracts carry an all-or-none `manifest_id` and
  `quality_evaluation_id` pin while legacy v1 JSON bytes and deterministic IDs
  remain unchanged when those fields are absent.
- Downstream readers reopen the exact qualified manifest and fail closed on
  failed quality, a mismatched dataset/revision/evaluation, wrong layer/kind/
  interval, adjustment drift, source-rights drift or instrument mismatch.
  Unrelated quality corruption is scoped away from exact lineage reads; direct
  legacy-v2 catalog reads remain non-mutating.
- The first independent review found four Important issues: target corruption
  was masked as not-found, exact reads could create control state, historical
  entries mislabeled themselves as current, and the production composition
  root left the catalog unbound. TDD regressions closed all four. Main-thread
  review additionally restored two accidentally nested legacy feature tests
  and closed trusted-feature cross-instrument substitution.
- Final verification passed `185` data/catalog/history/research/quality tests and
  `193` API/workstation regressions. OpenAPI generation and freshness,
  TypeScript, Oxlint, Ruff and `git diff --check` are green; Oxlint retains only
  four pre-existing Fast Refresh warnings. A fresh read-only re-review returned
  CLEAN/PASS with no Critical or Important finding.
- Task 11 completes the backend half of Slice 6 without changing release,
  credential, execution or synthetic-repair authority. Task 12 is now active:
  deliver the bilingual operator data-catalog screen from these exact contracts.

## Checkpoint 12 — Bilingual trusted-data catalog, 2026-08-14

- Task 12 completes Slice 6 with the package-served `/app/ops/data` operator
  screen. The English and Simplified-Chinese surface lists provider/access,
  canonical instrument, artifact layer, event and knowledge coverage, exact
  manifest identity, source rights, entitlement and checkpoint state without
  introducing a new frontend dependency.
- Keyboard-operable disclosure loads one exact manifest on demand and presents
  its immutable parents, complete quality evaluation and bound collection
  checkpoint. Pass, fail, not-due, unavailable and freshness-stale evidence use
  distinct text states; a freshness failure remains visibly failed as well as
  stale, and stale evidence follows the design system's amber semantics.
- Loading, empty and API-unavailable states are instructive and do not claim
  that collection guarantees qualification. The typed OpenAPI client remains
  current, and all material identifiers wrap rather than truncate or widen the
  workstation.
- Independent review first found incomplete quality/checkpoint evidence and a
  production-length mobile overflow gap. A second standards review also found
  raw-button drift, status-insensitive issue styling and overpromising empty
  copy. RED regressions closed each issue: all generated quality/checkpoint
  fields are visible, the owned Button primitive is used, issue colors follow
  qualification state, and a package-served populated plus expanded catalog
  with 64-character identities has zero horizontal overflow at 390 px.
- Final verification is frontend Vitest `152 passed`, TypeScript clean,
  OpenAPI-client freshness clean, package-bundle freshness clean and Oxlint
  clean apart from four pre-existing Fast Refresh warnings. Focused backend/API
  regression passed `132` tests, the explicit plain-app API boundary passed,
  Ruff and `git diff --check` passed, the populated/expanded 390 px Playwright
  check passed, and the Impeccable detector returned no findings. Final fresh
  read-only review verdict: CLEAN/PASS.
- Task 12 and Slice 6 are complete. No release, credential, real-order,
  wallet/signing or synthetic-repair authority changed. Task 13 now owns the
  clean-install collector, replay, inspection and daily evidence tooling.

## Checkpoint 13 — Clean-install acceptance tooling, 2026-08-14

- Commits `c069a15`, `e801e31`, `a594408`, `e1f75c9` and `0a97967` deliver the
  bounded installed CLI, immutable soak observer/verifier, the practical
  post-grace quality window, deterministic connector-test isolation and
  race-free live-prediction E2E server lifecycle. Production still contacts
  real OpenD when explicitly probed; only tests receive offline injected state.
- `quantmesh-data collect` requires an exact clean producing commit, bounded
  provider/symbol/window inputs and read-only adapters. `replay` reopens hashes
  and typed contracts before output, while `inspect` exposes the verified
  catalog/quality/checkpoint state. The soak verifier fixes the target matrix to
  Hyperliquid BTC/ETH/SOL 1-minute adjusted bars and Moomoo AAPL/NVDA daily
  adjusted bars, rederives policy/calendar/schema/config identities and rejects
  stale, incomplete, linked, late-created or noncanonical evidence.
- Reviewer corrections closed four initial Important findings and two follow-up
  findings: complete closure reopening, per-target freshness/progress, honest
  Windows timestamp claims, report/ancestor link rejection, trusted fixed
  target/config identities and all-or-nothing first observation. Final scoped
  read-only review returned CLEAN/PASS. The documented filesystem boundary does
  not claim defense against a local administrator coherently rewriting every
  evidence file and timestamp; Task 14's daily remote issue/CI checkpoint is the
  independent witness.
- The final clean-checkout release gate passed all 18 steps on
  `0a9796769c1ca98f0fc5f4dab187950167f4d0ab`: release consistency, fresh
  `.[dev,research,e2e,moomoo]` installation, Ruff, installed CLI probe,
  Python/frontend license and vulnerability audits, reproducible frontend
  bundle, Vitest, `3039 passed, 6 skipped`, golden path `60` checks and a clean
  clone at both boundaries. Three earlier attempts were preserved as negative
  evidence: one API connector probe and one SPA probe contacted OpenD when the
  optional SDK was installed, and one live-prediction E2E used a racy fixed
  port. All three received focused regressions before the passing run.
- The isolated final-candidate Hyperliquid collection used UTC window
  `2026-08-14T08:12:00Z/2026-08-14T08:14:00Z`. The catalog contains 12 passing
  layers, no issue codes, no synthetic rows, three adjusted rows per symbol and
  379–380 second latency. The adjusted manifest IDs are BTC
  `12562839ec2cd8b1af697e55911e2bc86b25d18c78d5029e06c88c82eacfdedf`, ETH
  `b77395c4198615dca0ef80535d9848fd1f0e6fd05e454b6d47648992ef4b79f2`
  and SOL
  `68966758e583b6645cd9b22fe026ab253b7c41551e808cea3cc0583267710aa1`.
  Each exact manifest replayed twice from separate CLI processes with
  `verified=true` and three rows. Shared quality report
  `7a4dc2290e6c55d2fff0c15311c0b14bdc52fc46159e948edac6e7103568bbd6`
  binds collection run
  `874300d501c1f66188bb34b508311cbb8758b72fb40b07c73a887f8a2d7bbcfd`.
- The same candidate's bounded Moomoo AAPL/NVDA attempt returned
  `status=unavailable`, `reason_code=daemon-unavailable`, detail
  `local OpenD is unavailable` and `manifest_ids=[]`. No candidate or soak
  report was created. Task 13 Step 4 is complete; Step 5 remains pending local
  OpenD plus entitlement. Task 14 is not started, and no release, milestone PR,
  credential, execution or synthetic-repair authority changed.

## Checkpoint 14 — Real OpenD unblock, 2026-08-15

- Local OpenD is running with US Stocks LV3 entitlement; `quantmesh-moomoo
  probe` reports `quote=True history_kline=True order=True order_query=True
  auth_required=False`.
- Real Moomoo collection exposed three latent defects in the daily critical
  path, fixed and committed: `b49e7b4` (canonical bar identity drops `market`
  metadata per ADR-0003, and revalidation filters history bars to the UTC window
  so venue-date widening cannot fail the canonical-derivation check) and
  `2b59ca8` (the split-rate parser accepts the Unicode arrow `1→4` alongside
  `1->4`).
- A clean-checkout `quantmesh-data collect` of Moomoo AAPL/NVDA daily bars for
  UTC `2026-08-10T00:00:00Z/2026-08-15T00:00:00Z` published 16 manifests (five
  bars per symbol), passed the full `validate_publication` recomputation, and
  re-collecting the same window returned the identical manifest set (idempotent);
  `replay` returned `verified=true` with five rows.
- Follow-up (not in the soak matrix): the Moomoo 1-minute path fails
  `validate_publication` with `raw declarations are not source-derived` because
  the raw history surface stores the complete SDK pages (including out-of-window
  bars) while its envelope declares the window-filtered range. The fixed
  five-target soak matrix uses Moomoo AAPL/NVDA at the daily interval only, so
  this does not block Step 5 or Task 14; fix before any intraday Moomoo
  collection.

## Checkpoint 16 — Historical-replay functional acceptance, 2026-08-15

- Operator decision: split acceptance into two gates. Functional acceptance
  (real historical data replayed with virtual time) blocks the merge; the real
  168-hour run becomes a post-merge stability gate that blocks the release, not
  the merge.
- Added `trusted_data_soak.py replay` (`7ce9ac2`, `bd3e73d`): an explicitly
  labeled historical-replay that validates the daily frontier, lineage and
  calendar invariants against real per-day collections using each manifest's
  own event time, ignoring real-time freshness/latency SLAs and never rewriting
  timestamps.
- The replay passed at `bd3e73d` on real data: seven distinct Hyperliquid
  BTC/ETH/SOL 1-minute adjusted windows with a monotonic frontier, five
  completed XNYS sessions (2026-08-10 through 2026-08-14), and no functional
  issue codes or synthetic rows (`accepted=true`).
- Constraint discovered: Hyperliquid 1-minute candle history is provider-pruned
  to about three days, so a seven-day 1-minute frontier can only be observed in
  real time; the replay uses seven windows within the available horizon to
  exercise the frontier mechanism.
- Task 13 Step 5 (freeze) and the functional half of Task 14 are complete. The
  real 168-hour run is deferred to post-merge.

## Checkpoint 17 — Daily witness fail-closed repair, 2026-08-24

- Resumed issue #124 from remote branch `0021-soak-finalize` at `dfff3df`.
  The issue's latest workstation reports name candidate `d78f489`, but that
  object is absent from the repository, remote refs and GitHub commit API, so
  its exact code cannot be reconstructed on this host.
- A clean local run reproduced an actionable daily-driver defect: the Moomoo
  CLI honestly returned `status=unavailable`, `reason_code=daemon-unavailable`
  and exit zero, but `tools/soak_daily.py` trusted only the process exit code,
  discarded the typed result and entered observation. The resulting message
  was the generic missing-target qualification failure rather than the actual
  unavailable-input boundary.
- Commit `d6e9b23` validates the read-only Moomoo CLI envelope and the strict
  `MoomooCollectionResult` contract before observation. Unavailable, failed,
  malformed and evidence-free `published` results now exit non-zero before an
  observe call; only a published result with manifest evidence can advance.
  Diagnostics expose only typed status/reason fields, not untrusted detail.
- The test-first proof covers typed unavailable, malformed JSON, published
  without manifests and a valid published path. Focused driver checks passed
  `4`; the collection/CLI/soak regression passed `96`, with `1` expected skip;
  Ruff and `git diff --check` passed. Fresh independent standards/spec review
  returned no actionable finding.
- The task environment uses CPython `3.14.7`. The research dependency contract
  now admits `arch>=8,<9`, the first line with a CPython 3.14 Windows wheel;
  the resolver-generated 72-package audit lock, ADR-0009, NCSA license policy
  and inventory were updated together. The complete
  `.[dev,research,e2e,moomoo]` closure installs without MSVC, `pip check` and
  the deterministic license review pass, and focused research/portfolio/
  security compatibility is `79 passed`. The full CPython 3.14 suite then
  passed `3106`, with `9` expected platform skips and no failures in
  `1119.85s`; all GARCH compatibility tests exercised `arch 8.0.0`.
- A real clean-tree run on `d6e9b23` now stops with
  `moomoo collect unavailable: daemon-unavailable`, exit `1`, before creating
  an observation. Windows task `QuantMesh Daily Soak` is registered for 08:00
  Asia/Singapore (00:00 UTC); the next scheduled run is 2026-08-25. It runs in
  the interactive operator session so it can use local OpenD. The host task is
  configured to wake/start when available, run on battery, ignore overlapping
  starts and retry three times at 15-minute intervals; it remains fail-closed
  while OpenD is absent.
- This host initially had only Python SDK `moomoo_api 10.10.7008`; there was no
  OpenD installation, uninstall entry or listener on `127.0.0.1:11111`. Three
  stale probe processes that had retried refused connections indefinitely were
  stopped; bounding that standalone probe is a follow-up outside the daily
  collector.

## Checkpoint 18 — Correct Moomoo OpenD activation, 2026-08-25

- The first downloaded gateway was the wrong account-family package: its UI
  identified itself as `Futu OpenD` and rejected the operator's Moomoo
  Singapore credentials. No credential was captured or written by QuantMesh.
- The official Moomoo download surface supplied
  `moomoo_OpenD_10.10.7008_Windows`. Its archive SHA-256 is
  `9326cfd13e6d6226a44f2693be388b10d252106064e6c7de80f4d2d2961c8890`;
  the GUI installer has a valid `Moomoo Technologies Inc.` Authenticode
  signature. The correct gateway is installed under the operator's roaming
  profile, authenticated interactively and listening only on
  `127.0.0.1:11111`.
- The read-only capability probe completed in `2.61s` with quote and historical
  K-line access available. A first real daily run at `2026-08-24T17:01:22Z`
  published complete AAPL/NVDA manifests through the latest completed XNYS
  session (Friday `2026-08-21T20:00:00Z`) but correctly failed qualification:
  freshness/latency were `248482s`, beyond the `172800s` policy while Monday's
  session was still open. No daily observation was accepted.
- Fixed-clock verification shows the registered `00:00 UTC` (`08:00`
  Asia/Singapore) run occurs after Monday close: the latest completed close is
  then `2026-08-24T20:00:00Z` and its age is `14400s`. The policy remains
  unchanged; the scheduler, rather than a weakened SLA or synthetic timestamp,
  is the authorized next attempt.

## Checkpoint 19 — Isolated multi-day soak simulation, 2026-08-25

- Three independent temporary-root runs of the existing soak and daily-driver
  suites each passed `21` tests with one expected Windows symlink skip. The
  retained simulations exercised a valid seven-report chain plus rejection of
  after-the-fact generation, forged modification times, duplicate UTC days,
  candidate drift, incomplete market evidence and invalid Moomoo publication
  envelopes.
- A focused audit repeated the accepted chain, after-the-fact rejection,
  forged-time rejection and one-report-per-UTC-day boundary (`4 passed`). A
  fresh read-only OpenD probe confirmed quote and historical K-line
  capabilities, and the four daily-driver fail-closed paths passed again.
- Independent Standards and Spec review rejected a proposed broader metadata
  simulation before commit: it replaced repository-owned Catalog/ManifestStore
  components and manually assembled reports, so it could not honestly claim
  end-to-end observation or artifact reopening. That test was removed. The
  production CLI intentionally exposes no virtual-clock option because such an
  option could fabricate Task 14 evidence; complete five-target persistence
  therefore remains a real-time daily gate, not a simulation claim.
- Every simulation used `C:\QuantMesh\pytest-soak-*` temporary roots. The real
  `C:\QuantMesh\trusted-data-evidence` root remained absent, so no virtual time
  or synthetic report can be mistaken for Task 14 evidence. Historical replay
  against the earlier pre-close real data remained honestly rejected for the
  already-recorded Moomoo `not-trusted` quality state; no SLA or evidence was
  rewritten. The registered real task remains ready for `08:00`
  Asia/Singapore on 2026-08-25.

## Checkpoint 20 — Repeated-soak incident diagnosis and repair design, 2026-08-29

- Issue #124's complete witness history shows multiple candidate restarts for
  distinct control-plane failures: an unavailable Moomoo result accepted by
  the old driver, a 39.5-hour host sleep/hibernate cadence gap and the current
  NVDA historical/live overlap rejection. Issue #127 independently records
  long-running probes, `0x41306` termination and an 08:00 false failure while
  the formal daily task was legitimately `Running/0x41301`.
- The NVDA rejection is a real provider correction, not floating-point noise.
  Raw revision 5 and 6 differ on only
  `NVDA:2026-08-27T04:00:00+00:00`: turnover changed from
  `67,700,954,784.651` to `67,628,318,193`, fingerprint
  `6e30bad00d3e0df50794a426c09c6ca01701b2bcda98a39f1cd684bfde1eb0a9`.
  OHLCV-derived normalized, adjusted and feature rows are unchanged. The raw
  failure remains valid and must not be deleted, tolerated or relabeled PASS.
- Production does not currently expose ADR-0018's exact amendment semantics,
  and immediate-predecessor overlap comparison allows an identical later
  revision to heal without acknowledgement. The formal daily script also
  omits the complete verifier, so a report with critical issues can still
  leave the Windows task at exit zero. Existing `21 passed, 1 skipped` focused
  tests demonstrate a coverage gap rather than a passing operational contract.
- The formal task and connection probe start at the same minute. The external
  probe has no child deadline or guaranteed terminal receipt, and its latest
  pointer can remain stale after termination. Both tasks execute a mutable
  checkout whose candidate commit is not remotely reachable. The GitHub
  publisher's check-then-post sequence is not a single-writer protocol; the
  issue history contains duplicate publication evidence.
- Planner output defines six bounded gates: immutable overlap resolution,
  fail-closed daily runner, scheduler round-trip, deadline-bounded connection
  witness, single-authority GitHub publication and a new real 168-hour root.
  Quant-research output requires `operator-acknowledged` semantics when no
  external source proves which turnover is correct, preserves knowledge-time
  boundaries, permits only unchanged OHLCV descendants and fences turnover,
  liquidity, cost and slippage use. Implementer work has not started.
- The proposed architecture is recorded in
  `docs/superpowers/specs/2026-08-29-trusted-data-soak-reliability-repair-design.md`.
  It preserves the failed evidence, adds content-addressed exact resolutions
  and a stable accepted-overlap baseline, makes the complete verifier determine
  daily exit status, requires immutable operational receipts and deadlines,
  staggers the tasks, and moves remote publication behind a durable outbox.
  The operator approved the design on 2026-08-29. The executable TDD plan is
  `docs/superpowers/plans/2026-08-29-trusted-data-soak-reliability-repair.md`;
  Implementer, Reviewer and Verifier gates remain pending.

## Checkpoint 21 — Cross-host handoff and local scheduler retirement, 2026-08-31

- The operator selected a different host for continued work and directed this
  laptop to push its complete branch state and then stop all local scheduling.
  This is the remote-Windows-worker topology implied by the approved repair
  design: Codex Cloud or another clean host may implement and review, while an
  always-on Windows host retains the interactive Moomoo OpenD boundary.
- The full operational state, two Windows task definitions, Codex heartbeat,
  incident chronology, old-root status, safety boundaries and new-host resume
  sequence are recorded in
  `docs/runbooks/trusted-data-soak-host-handoff.md`. The old `evidence-v2` root
  is rejected and contributes no time to a future 168-hour claim.
- The final pre-retirement connection result started at
  `2026-08-31T00:00:03+08:00`, run ID
  `a69920e151191373bfe398f11cfeee5bcd46d986342a13b8f6280115a6bcd1b8`.
  Scheduler, OpenD process/TCP, Moomoo, Hyperliquid and repository import were
  healthy; the witness remained failed because the formal task's latest run
  was `0x00000001`. This does not qualify #124 evidence.
- Local retirement is deliberately reversible: the two Task Scheduler entries
  are disabled rather than deleted and the Codex heartbeat is paused. The old
  trusted-data, evidence, candidate and witness-result files are retained
  without modification for audit.
- The receiving host must resume the first incomplete task in the approved
  reliability plan. It must push and verify the repaired runner before
  creating a new empty evidence root, registering the staggered schedule or
  starting a replacement 168-hour clock. Recreating the old scheduler is not
  an accepted migration.

## Current frontier

On the receiving host, execute the approved Checkpoint 20 reliability-repair
plan one bounded TDD slice at a time, with an independent read-only review and
recorded verification at every phase boundary. Keep the retired laptop's
schedulers disabled and do not count time from the rejected evidence root
toward the replacement 168-hour candidate.

## Resume instructions

1. Read `AGENTS.md`, `CONTEXT.md`, `docs/goals/ACTIVE.md`, this file, the design
   and the executable plan.
2. Read `docs/runbooks/trusted-data-soak-host-handoff.md`, then inspect
   `git status`, branch history, issues #124/#127 and open PRs.
3. Resume the first incomplete plan task; do not redispatch completed commits.
4. Keep the main thread as the only source writer and use read-only reviewers.
5. Mirror every green checkpoint and review verdict into this ledger.
