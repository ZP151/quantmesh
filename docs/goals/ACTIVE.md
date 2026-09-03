# Active Goal

- Status: active — iteration 0027 Slices 1–4 and license closure complete; final PR gate pending
- Objective: enable a research-minded individual active trader to turn a
  ticker into a verifiable, risk-first decision package in no more than two
  minutes, save it as Reject, Watch or Paper proposal, and replay its evidence,
  risk outcome and review after a clean restart.
- Started: 2026-09-02
- Tracking issue: [#122](https://github.com/ZP151/quantmesh/issues/122)
- Active iteration:
  `docs/iterations/0027-evidence-backed-decision-copilot.md`
- Design:
  `docs/superpowers/specs/2026-09-03-packet-outcome-review-design.md`
- Executable plan:
  `docs/superpowers/plans/2026-09-03-packet-outcome-review.md`
- Integration branch: `codex/0027-evidence-backed-decision-copilot`
- Baseline: `origin/main` at `f77b565`; immutable `v0.1.1-rc1` remains
  `b6b05b9`
- Delivery mode: one 0027 product track and one independent 0021 soak
  maintenance track at most. Each track uses one integration branch and one
  final PR; neither may opportunistically modify the other's files or state.
- Current frontier: run only the final 0027 PR gate. Slices 1–4 and the approved
  Python release-license closure repair are complete; do not add another product
  slice or expand into exit orders, a performance dashboard, AI review,
  another model framework, Provider/OpenD, another symbol, external notification
  or any 0021 soak work.
- External gate: none for the deterministic product slice. Model services,
  OpenD and real providers are optional degraded-state inputs and never merge
  gates.

## Product-readiness decision

The product wedge is an evidence-backed decision copilot, not an AI signal
generator or a framework laboratory. The shortest path begins with a ticker or
watchlist row and stays inside Instrument Workspace while QuantMesh composes
market state, key levels, Bull/Base/Bear scenarios, risk parameters, evidence
and one explicit action. The durable product artifact is a versioned
`DecisionPacket`; AI may explain or challenge its deterministic analysis but
cannot create evidence, waive a blocker or gain order authority.

Iteration 0021's 168-hour soak continues as a maintenance/release-confidence
track. It does not block 0027 product work, and 0027 must not repair, migrate,
backfill or otherwise modify soak Scheduler, provider or evidence state.

## Non-negotiable constraints

- Keep external venues read-only and execution paper-only. Live trading,
  signing, credentials and mainnet authority remain outside iteration 0027.
- AI is advisory and schema-validated. Missing or failed AI must leave the
  deterministic DecisionPacket usable.
- Stale, low-quality, leakage-affected or missing evidence must block a paper
  proposal with an actionable reason; it may not be hidden by AI confidence.
- Every paper proposal passes the existing deterministic risk kernel and a
  second operator confirmation.
- Decision, evidence, paper result and review state must survive a clean
  restart and remain replayable.
- Qlib, Darts and model ranking are internal support or later work, not 0027
  completion criteria. TradingView extensions, mobile clients, real trading,
  social features and broad pattern-recognition catalogs are out of scope.
- Each slice must expose user-visible value within 24–48 hours. Side defects
  are recorded and left out of scope unless they block the slice.

## Active delivery protocol

- Planner/Product defines one user action, one success measure and explicit
  expansion prohibitions per slice.
- Quant Researcher reviews metrics, leakage, costs and confidence semantics at
  slice start; the role does not independently expand the algorithm platform.
- Implementer delivers the API, page state and targeted tests for one small
  end-to-end loop.
- Reviewer works at demonstrable slice boundaries and gets at most two rounds.
  A third structural failure stops patching and shrinks the design.
- Verifier runs targeted checks during development; broad suites run at slice
  commit and final PR boundaries.
- Every agent prompt has one deliverable, one stop condition and explicit
  forbidden actions. Daily progress records completed user loops rather than
  test count, code volume or ledger length.

## Slice 1 execution checkpoint — 2026-09-02

- Operator approved the tracked design and authorized Slice 1 execution.
- Planner fixed one user action: save and reopen an NVDA Reject, Watch or
  guarded Paper-proposal packet inside Instrument Workspace. Success is a
  durable identity in at most two minutes; later Copilot, monitoring and review
  slices are prohibited expansions.
- Quant Researcher confirmed that forecast quantiles/coverage cannot become
  scenario probabilities, manifest/quality IDs remain inseparable for trusted
  claims, and freshness/chronology/leakage stay fail-closed. Account fee and
  matcher slippage are pinned cost assumptions; quote half-spread remains
  explicitly pending until the existing second-confirmation quote fence.
- Execution uses
  `docs/superpowers/plans/2026-09-02-decision-packet-foundation.md`, with one
  implementer deliverable and one two-round review ceiling per task.
- Task 1 is complete through `4409bcf9d630`: ADR-0019, strict frozen packet
  contracts, the deterministic composer and fail-closed JSONL lineage store
  now establish the reviewed domain boundary. Real forecast evidence cannot
  become paper-capable without paired manifest and quality IDs, including when
  a packet is constructed outside the composer.
- Task 1 final verification passed `76` tests with `3` expected skips; focused
  Ruff and `git diff --check` passed. The second and final review round returned
  APPROVED with no Critical, Important or Minor finding. Task 2 is the active
  frontier; no UI, Copilot, monitoring, review, provider or soak scope has been
  entered.
- Task 2 is complete through `9494d59a5c79`. Instrument Workspace now composes
  a current point-in-time draft while returning the separately persisted
  latest packet; exact staged save remains stable under a moving production
  clock and demo reset clears staged authority.
- Packet actions are same-origin, packet/forecast bound and recoverably
  idempotent. Reject and Watch never call paper authority; Paper only records a
  pending proposal after current session-aware freshness and full evidence
  binding checks, and confirmation remains a separate existing authority.
- Task 2 final verification passed `97` tests with `6` existing dependency
  warnings; OpenAPI freshness, TypeScript, Ruff and diff checks passed. The
  second and final review returned APPROVED with no new finding. Task 3 is now
  the active frontier.
- Task 3 delivered the single-screen flow through `d786ec26a791` and closed
  packet/context races, exact persisted selection, write/confirmation gating,
  terminal IDs, compact wrapping and archived/current time-domain separation.
  Its final allowed review retained one Important finding: per-horizon metrics
  omitted their own validation/test windows and could appear associated with
  artifact-wide chronology.
- Per the two-round ceiling, broad Task 3 patching stopped. The operator
  approved Task 3R: only render each stored metric with its own literal four
  sample-window timestamps and prove distinct-horizon association. State, API,
  chart and backend changes are prohibited.
- Task 3R is complete through `41b677f57734`. Every archived forecast metric
  now owns its literal validation/test boundaries; two distinct horizons prove
  there is no artifact-wide chronology inheritance. Default and UTC focused
  tests passed, and the independent review returned APPROVED/CLEAN.
- The UTC verification also exposed two older Task 3 assertions that hard-code
  local rendered dates in MarketCanvas and InstrumentWorkspace tests. They are
  recorded as Task 4 acceptance blockers; no Task 3R scope was expanded to fix
  them.
- Task 4 completes Slice 1. Three independent Chromium paths begin at the real
  Watchlist NVDA activation, remain in Instrument Workspace, and durably save
  Reject, Watch and pending Paper-proposal packets in `9.980s`, `9.759s` and
  `12.423s`; all expose market, three scenarios, risk, evidence, blockers and
  actions. The Watch path uses keyboard activation/save. The component and API
  acceptance proves one packet owns every workspace column, deterministic save
  works without a model service, stale evidence produces zero proposal/order,
  risk refusal produces zero accepted/filled order, blocker evidence is clear
  in English and Simplified Chinese, and exact JSON/disposition survives a
  clean application restart.
- Task 4's final coherent selection passed `176` tests with `3` skips in
  `2141.98s`; the final complete repository run passed `3150` tests with `9`
  skips in `2953.81s`, and the controller independently repeated it with
  `3150` passed, `9` skipped and `7` warnings in `2998.64s`. Full Ruff,
  dependency integrity, the exact installed license classification/inventory
  tests, UTC full Vitest (`167` tests), TypeScript, lint, OpenAPI freshness,
  packaged build and diff checks passed. The direct ambient license CLI
  correctly refused four baseline audit-lock omissions (`cloudpickle`,
  `formulaic`, `interface-meta`, `wrapt`); Slice 1 changes no dependency or
  license file, does not claim that release gate green, and leaves the
  inherited lock drift to separately scoped release maintenance. The first
  full run exposed only an incomplete
  local optional-extra install and a test whose local basetemp still belonged
  to the parent Git worktree; the constrained `[moomoo]` environment install
  and test-only Git discovery ceiling were verified together and by the final
  full run. No production commit resolver or external state changed.
- The exact browser/API packet, proposal, restart, stale/refusal, role and gate
  evidence is recorded in the active iteration ledger. Six pre-existing skill
  mirror Ruff blockers received only authorized mechanical import/line-wrap
  corrections; blocker taxonomy duplication remains a non-blocking follow-up.
  Slice 1 is complete. Slice 2 requires a separate approved design/plan.

## Slice 2 implementation checkpoint — 2026-09-03

- The persisted-packet Copilot vertical slice is implemented as a separate,
  immutable, packet-bound advisory record with strict analyst/critic schemas and
  packet-pointer/digest citations. AI output has no confidence, sizing, risk,
  blocker-override, proposal, confirmation or order authority.
- Default demo and blank-model workstation operation are explicitly degraded and
  make no model call. Accepted reports and both audit stages survive a clean app
  reconstruction; demo reset owns the new mutable ledgers explicitly.
- Service/API/component acceptance is green, including invalid outputs, citation
  failures, critic flags, unknown/corrupt/cross-origin handling, secret redaction,
  cache/context isolation, localization, keyboard use and compact wrapping.
- The coherent selection recorded `66 passed, 1 selector-only failure`; its valid
  scripted browser path reached accepted report, citation expansion, invariant
  counts, reload reopen and reset. The one authorized isolated rerun stopped on a
  second selector-only visibility assertion before degraded POST. The assertion
  now matches established suite semantics, but the corrected isolated E2E remains
  the sole unverified item. This checkpoint is `DONE_WITH_CONCERNS` pending the
  controller's browser verification, review, detector and broad gate.

## Slice 2 completion checkpoint — 2026-09-03

- Commit `60ee6f9` closed the final review's three Important findings: Copilot is
  withheld during range-placeholder drift and late responses bind context plus
  packet ID; accepted records reopen from the validated store without a configured
  model while POST remains degraded; generated Citation types are concrete without
  changing legacy wire bytes. It also closes naive timestamp acceptance.
- The second and final review found every item ADDRESSED with no new Critical or
  Important breakage. The single Impeccable detector run returned `[]`.
- After correcting test-only acceptance setup, the isolated Chromium path passed
  `1` test with `5` existing dependency warnings in `138.98s`, exit `0`. It proves
  valid report/citations/reload and unavailable persisted-draft action, packet,
  proposal and order invariance in the real packaged SPA.
- The one broad Slice 2 gate passed `3179` Python tests with `9` skips and `7`
  warnings in `3823.34s`, exit `0`; full Ruff, `pip check` and diff checks passed.
  UTC Vitest passed `19` files / `173` tests in `31.16s`; OpenAPI freshness,
  TypeScript, lint and production build (`2081` modules in `9.04s`) passed. Four
  existing Fast Refresh warnings, the ambient Node `22.11.0` versus Vite `22.12+`
  advisory, and the known final-PR Python license-lock drift are not expanded here.
- Slice 2 is complete. No real model/provider call, OpenD, real trading, another
  symbol, external notification, monitoring, outcome/review or 0021 soak work ran.

## Slice 4 completion checkpoint — 2026-09-03

- The exact persisted NVDA packet now reopens in Instrument Workspace with an
  immutable outcome/review closure. It binds the 30-session local path, exact
  proposal/order/fill and monitoring provenance, and clean-restart identities;
  unavailable exit/cost evidence never becomes realized R or zero P&L.
- The two allowed combined-review rounds completed. A final narrow test-first
  correction addressed only the already identified exact order-binding and full
  order-event timeline gaps; no third review or feature expansion occurred.
- Targeted proof passed: order-tamper regression `1 passed, 10 deselected` in
  `65.35s`; component `7 passed`; Chromium save/restart `1 passed, 14 deselected,
  5 warnings` in `154.97s`; targeted static and bundle checks all exited `0`.
- The one broad Slice 4 gate passed `3217 passed, 9 skipped, 7 warnings` in
  `3806.57s`, exit `0`; UTC Vitest passed `21` files / `187` tests. Ruff,
  `pip check`, OpenAPI, TypeScript, lint, build, packaged bundle freshness and
  diff checks passed. The existing Fast Refresh and local Node/Vite advisories
  remain non-blocking.
- Slices 1–4 are complete. The only active work is the final 0027 PR gate. No Provider/OpenD/model
  call, real trade, other symbol, external notification or 0021 soak state was
  touched.

## Final license-closure checkpoint — 2026-09-03

- The direct gate reproduced four missing transitive pins and bound them to their
  installed dependency chain: `cloudpickle==3.1.2`, `formulaic==1.2.2`,
  `interface_meta==2.0.1` and `wrapt==2.4.0`.
- `requirements-audit.txt` and `docs/licenses.md` now agree on the exact 76-package
  cross-platform closure. The license parser recognizes the exact `MIT` text used
  by `interface_meta` without weakening unknown or copyleft refusal.
- The MIT parser and exact-version enforcement tests both went RED then GREEN.
  The first fresh-clone gate exposed 17 resolver-advanced versions and stopped on
  `simplejson==4.1.2`; the lock/inventory and exact 4.1.1/4.1.2 reviewed
  exceptions now cover the fresh resolution and existing dev environment.
  Retained-fresh evidence is `21 passed` in `0.36s`,
  targeted Ruff/diff clean, and license review exit `0` after classifying all 70
  installed members and tolerating only the six documented Linux-only pins. No
  project dependency constraint or runtime behavior changed.
- A subsequent fresh gate passed Python license and `pip-audit` before two new
  frontend transitive advisories stopped `npm audit`. The lock-only fix updates
  exactly `fast-uri 3.1.5 -> 3.1.7` and `qs 6.15.3 -> 6.16.0`; `npm ci`, zero-
  vulnerability audit, the 646-package frontend license review and diff check
  now pass. No direct dependency or runtime source changed.
- The CI-aligned Node 22.12 runner passed the formerly blocked frontend build and
  reached 75% of pytest with no failure, but the gate's 2400-second timeout was
  shorter than the verified 3806.57-second suite baseline. A test-first gate-only
  correction raises that step to 5400 seconds; its three tests, Ruff and diff pass.
- The expanded-budget fresh suite reached 100% with `3219 passed, 9 skipped` and
  one lock-order failure in `4682.45s`. Swapping adjacent `cloudpickle`/`colorama`
  rows closed it; the exact release/security selection now passes `28` tests in
  `0.43s`, with Ruff and diff green. No product behavior changed.
- The only remaining work is the final fresh-clone release gate and PR boundary.

## Final-gate compatibility checkpoint — 2026-09-04

- The Node 22.12 fresh-clone gate passed source cleanliness, clone/version,
  fresh Python installation, Ruff, trusted-data tooling, Python and frontend
  license closure, `pip-audit`, `npm audit`, bundle freshness, Vitest and the
  complete Python suite (`3220 passed, 9 skipped` in `2825.5s`).
- Its sole failure was the historical golden-path script posting a bare legacy
  proposal and treating the required 409 response as the former flat proposal
  shape. Product code and tests were already green.
- `tools/golden_path.py` now exercises the accepted DecisionPacket workflow:
  save the exact draft, record a packet-bound paper action, then separately
  confirm its proposal. The kill-switch race uses a deterministic demo reset
  and a second exact NVDA packet; no Provider, OpenD or external state is used.
  The corrected walk passes all `60` checks with exit `0`.
- The only remaining work is one fresh-clone release gate on the corrected
  commit, followed by the final PR boundary. No additional product slice is
  authorized.

## Historical delivery record

The checkpoints below preserve prior goals and evidence. Their embedded
"current frontier" headings are historical; the metadata above is the
canonical current state.

## Checkpoint 0 — 2026-08-14

- Created issue #110 and the isolated integration branch.
- Recorded the product-readiness assessment, approved design and iteration
  ledger in English-primary project format.
- Planner and Quant Researcher completed independent read-only audits; their
  findings are incorporated into the design and iteration role evidence.
- Created a clean Python environment from `origin/main`; dependency setup
  succeeded. Baseline verification remains in progress before behavior changes.

## Checkpoint 1 — 2026-08-14

- Task 1 capability-aware provider resolution is GREEN after three corrective
  read-only review rounds and one final implementation-clean verdict.
- Exact evidence is recorded in
  `docs/iterations/0021-trusted-data-fabric.md`; the final focused gate is 160
  passed, with Ruff and `git diff --check` green.
- Legacy fixture access remains compatible but cannot be relabeled or resolved
  as real data. No execution authority, credential, release tag or synthetic
  repair path changed.

## Checkpoint 2 — 2026-08-14

- Task 2 canonical instruments and versioned market calendars is GREEN after
  two corrective read-only review rounds and a final CLEAN verdict.
- Exact evidence is recorded in
  `docs/iterations/0021-trusted-data-fabric.md`: 56 focused checks, 82 Task 1–2
  integration checks, Ruff, dependency integrity, release-lock ordering and
  the 68-package license closure are green.
- Alias history is bitemporal and content-addressed; XNYS regular sessions are
  schedule-validated, extended sessions fail explicitly, and 24/7 sessions are
  exact UTC days. No execution or release authority changed.

## Checkpoint 3 — 2026-08-14

- Task 3 content-addressed objects and immutable manifests is GREEN. The final
  Task 1–3 integration, v1 compatibility and security selection passed 195
  tests with 3 expected skips; Ruff and `git diff --check` passed.
- V2 state is isolated under `.trusted-data-v2`. Objects, manifests and
  revision reservations are write-once; canonical hashes and typed bar
  declarations are verified on exact-manifest reads.
- Genesis activates one complete staged directory atomically. Later
  publication uses a reparse- and hard-link-safe cross-process lock, immutable
  revisions, hash-chained history and compare-and-swap pointer. Strict recovery
  accepts only exact uncommitted evidence; committed or ambiguous damage fails
  closed.
- A real Windows junction probe was rejected before any external write. Review
  reproduced and closed the path, semantic, concurrency, crash, truncation and
  torn-tail attacks; the final read-only Reviewer verdict was CLEAN.
- ADR-0016 records the local filesystem trust root and does not claim defense
  against an administrator rolling back every local v2 evidence file together.
  No credential, order authority, release tag or synthetic repair path changed.

## Checkpoint 4 — 2026-08-14

- Task 4 completes Slice 1: one nonqualifying fixture AAPL response now traces
  through exact raw evidence, normalized daily bars, explicit
  `unadjusted-identity-v1` output and the existing `log_return(window=2)`
  feature implementation.
- Knowledge-time selection is committed-pointer bounded and idempotent across
  historical retries. Future-event, retroactive-correction and crash-pending
  leakage fail closed.
- Lineage validates canonical bytes, raw-envelope-rooted provenance, pinned
  XNYS sessions, declared policies and actual derivation rather than trusting
  parent IDs alone. Sixteen Important review findings were reproduced and
  corrected; both final read-only verdicts are CLEAN.
- Verification is `25 passed` focused and `277 passed, 3 skipped` for the
  Task 1–4 integration/security selection, with Ruff and `git diff --check`
  green. Exact evidence is in the active iteration ledger.

## Checkpoint 5 — 2026-08-14

- Task 5 completes bounded, quote-only Moomoo history and corporate-action
  transport. Opaque history cursors are followed in one context and encoded as
  strict-JSON evidence; factors, splits and dividends remain raw source data.
- Silent truncation, repeated cursors, malformed SDK tuples/status, row-symbol
  drift, invalid/missing scalars, non-finite or coercive OHLCV, timestamp shape,
  date bounds and reversed UTC windows all fail closed. Legacy one-page reads
  remain compatible but cannot qualify as complete trusted bundles.
- Verification is `106 passed` focused and `310 passed` for the Task 1–5,
  security and release/audit selection, with Ruff and `git diff --check` green.
  Repeated corrective review rounds closed every Critical/Important finding;
  final Standards and adversarial implementation/security verdicts were CLEAN.
- At this checkpoint the 10.10 compatible SDK candidate was not yet a release
  dependency; Checkpoint 6A records its later audited admission.

## Checkpoint 6A — 2026-08-14

- Task 6 foundation admits `moomoo-api==10.10.7008` into the same audited
  `.[dev,research,e2e,moomoo]` closure used by CI, Security and the release
  gate. The 72-pin inventory and local 66-package Windows license review pass.
- Split adjustment is knowledge-bounded and independently pins factor/action
  manifests. Ambiguous, future-known or wrong-instrument actions fail closed;
  OHLC and inverse-volume behavior is regression-tested.
- The SDK worker is process-isolated, deadline-bounded and credential-free.
  Staged output is bounded and removed after strict parent-side validation;
  timeout or unavailable results cannot claim manifests.
- Verification: 41 dependency/security/release tests and 81 focused
  adjustment/collection/OpenD/provider tests passed; focused Ruff passed.
  Publication and real OpenD evidence remain pending and are not claimed.

## Checkpoint 6B — 2026-08-14

- The Task 6 implementation candidate publishes separate real raw history,
  factor, split and dividend evidence, then canonical bars/actions,
  split-adjusted bars and deterministic log-return features. Publication
  validation recomputes the chain from immutable source bytes and rejects
  forged adjusted objects; idempotent input retains all eight manifest IDs.
- Forward and reverse splits require a unique agreement between official factor
  and action surfaces under a UTC knowledge cutoff. Dividends are recorded but
  total return remains explicitly unavailable. Historical and live-tail paths
  no longer fabricate `adjusted_close` from labels or raw closes.
- The process-isolated worker now carries the minimum non-secret Windows runtime
  paths required by Python/Moomoo, maps `US.*` market metadata explicitly and
  classifies a refused OpenD socket before the SDK retry loop. API keys and
  credential-bearing environment variables remain excluded.
- The real read-only probe used audited SDK `10.10.7008`; local OpenD was not
  listening and correctly returned `unavailable/daemon-unavailable` with zero
  manifest IDs and no dataset directory. This is honest negative evidence, not
  a positive real-data acceptance claim.
- Verification is `172 passed, 1 skipped`, focused Ruff clean and
  `git diff --check` clean. Two fresh read-only reviews are running; Task 6 is
  not complete and its final commit remains pending their verdicts.

## Checkpoint 6C — 2026-08-14

- Both fresh reviews rejected the 6B candidate. Reviewer-driven RED tests then
  reproduced official factor-orientation drift, order-dependent equal-ratio
  action pairing, worker-controlled knowledge time, raw-role substitution,
  forged feature declarations and unbounded stdout/stderr buffering.
- The corrected contract uses the inverse of Moomoo's documented old/new
  `split_ratio`, pairs actions chronologically, replaces worker receipt time with
  parent-observed UTC time, authenticates every raw and derived role/declaration,
  and accepts worker output only through the bounded staged JSON file.
- Six correction regressions and the full Task 6 selection are GREEN:
  `176 passed, 1 skipped`, Ruff clean and `git diff --check` clean. Task 9 owns
  bundle-level crash recovery; a fresh scoped reviewer is deciding whether that
  explicit phase boundary leaves any Task 6 blocker.

## Checkpoint 6D — 2026-08-14

- Final review corrections recompute every raw role's identities and event
  coverage from immutable source bytes, bind bar interval to decoded source,
  bind factor/split/dividend source codes to the canonical provider symbol and
  derive empty action coverage from empty source evidence.
- Final Task 6 verification is `181 passed, 1 skipped`, Ruff clean and
  `git diff --check` clean. The real negative OpenD probe remained honestly
  unavailable with zero manifests; `pip check` and the 72-package license review
  passed.
- Final fresh read-only scoped review: PASS, no Critical/Important issue. Task 6
  and Slice 2 are complete. Task 9 retains bundle crash atomicity ownership.

## Checkpoint 7 — 2026-08-14

- Commit `97fee3087345` completes public-mainnet Hyperliquid candle lineage for
  BTC, ETH and SOL through an immutable data-only `/info` transport pinned to
  `https://api.hyperliquid.xyz/info`. Wallet, signing, account, exchange and
  order surfaces remain structurally absent.
- Publication is bounded by the provider's 5,000-row contract, requires exact
  interval-aligned UTC windows and complete continuity, and fails closed unless
  each direct request and final publication occur on the exact clean producing
  commit. Scripted or injected clients remain fixture evidence and cannot
  qualify as real data.
- The collector publishes and rederives the complete immutable raw,
  normalized, identity-adjusted and log-return feature graph before activating
  any catalog pointer. Cross-pointer crash recovery remains explicitly owned by
  Task 9.
- Final independent Standards and specification reviews both returned PASS with
  no Critical or Important finding. Verification passed 348 scoped regressions,
  Ruff, `pip check`, the 72-package license review and `git diff --check`.
- A post-commit public-mainnet smoke collected the closed UTC window
  `2026-08-13T21:54:00Z` through `2026-08-13T21:56:00Z` for BTC, ETH and SOL.
  All three publications qualified as real, produced 12 immutable manifests
  and replayed without synthetic repair. Exact dataset IDs are recorded in
  iteration 0021 Checkpoint 7.
- Task 7 and Slice 3 are complete. Task 8 is the active frontier.

## Checkpoint 8 — 2026-08-14

- Commit `11f99cc` completes Task 8 and Slice 4. Hyperliquid trade identity is
  SHA-256 over canonical `(block_time_ms, uppercase coin, tid)`; `tid` remains
  a provider identity and is never treated as a consecutive sequence.
- Candle, trade and L2 continuity now uses explicit `complete`, `known-gap`,
  `unknown-after-disconnect`, `recovered` and `unrecoverable` states with
  disconnect time, last durable identity, first recovered identity and recovery
  source. Durable cursors advance only after LiveBuffer commits and restore
  from the replay lake after process restart.
- L2 data is admitted as atomic bid/ask snapshot epochs. Backpressure remains
  row-bounded without splitting an epoch, retention never prunes one side, and
  dropped-stream findings survive the reconnect pump. The production live
  workstation now has the read-only public `/info` candle/book recovery source;
  wallet, signing, account, exchange and order surfaces remain absent.
- LiveBuffer schema v2 migrates old lakes idempotently, rejects future schema
  versions before mutation, deduplicates scoped provider identities, quarantines
  content conflicts and restores both L2 sides and both Hyperliquid metrics
  channels. The frontend preserves identity/continuity evidence, reconciles
  snapshot polling monotonically and renders depth only from one complete epoch.
- Reviewer-driven regressions closed durable-cursor restart loss, partial-gap
  clearing, dead-socket reuse, unbounded reconnect batches, split pruning,
  wrong dropped-instrument evidence and delayed snapshot rollback. Final fresh
  Standards and implementation reviews both returned CLEAN with no Critical or
  Important finding.
- Verification is `711 passed` across the broad live/Hyperliquid/workstation
  selection, followed by `122 passed` for the final corrected backend focus and
  `147 passed` frontend tests. Ruff, TypeScript, production build, OpenAPI client,
  committed-bundle freshness and `git diff --check` passed. Four pre-existing
  Fast Refresh lint warnings remain unchanged.
- Task 8 and Slice 4 are complete. Task 9 is the active frontier and retains
  immutable collection-run publication, compare-and-swap checkpoints and
  crash-boundary recovery ownership.

## Checkpoint 9 — 2026-08-14

- Task 9 and Slice 5 are complete. Collection-job schema v2 binds the complete
  provider request, producing commit and explicit collection cycle; exact
  retries preserve a deterministic run while later cycles may capture provider
  corrections as new knowledge-time revisions.
- Provider batches are immutable source snapshots with ordered raw-payload
  digests and an independent per-job marker repeated in pending/commit evidence.
  Complete raw/derived/manifest/preflight graphs become visible only through
  one compare-and-swap DuckDB transaction; Task 9 makes no quality claim.
- ADR-0017 records the durable authority: hash-chained immutable commit
  journals, permanent dataset owner markers, canonical manifests, retained
  legacy predecessor evidence and full-graph fail-closed reads.
- Recovery under the one-writer lease repairs exact committed intents, owner
  markers, source rows and both pre-link and post-link hard-link interruptions.
  All graph members have exact immutable high-water anchors and are permanently
  owned, including unchanged manifests. Completed retries revalidate the
  aggregate source object and reject uncommitted external parents.
  Subprocess tests cover every public crash stage, and eight independent
  processes converge on one logical publication.
- Final evidence is `220 passed` for the Task 9 integration selection and `120
  passed` for the corrected control-plane/recovery/Moomoo focus. Ruff and `git diff --check`
  passed; fresh Standards and adversarial reviews returned CLEAN.
- Task 10 is now active: add versioned quality policies and immutable daily SLA
  evidence without changing release or execution authority.

## Checkpoint 10 — 2026-08-14

- Task 10 is GREEN. ADR-0018 defines versioned content-addressed policies,
  evaluations and checkpoint-bound reports without introducing a hash cycle.
- Immutable measurements now cover exact raw payload identities, typed bars,
  features and split actions, XNYS/continuous calendars, pagination, rights,
  entitlement, freshness, close-based latency and exact historical-overlap
  fingerprints. Explicit amendments can reconcile only the identical recorded
  conflict set.
- Real graphs are bound to the authoritative policy, job window and checkpoint
  time; fixture qualification, custom-policy relaxation, premature daily bars,
  hard-failure masking and cross-job corruption blast radius fail closed.
- Final evidence is `93 passed` for quality/calendar/recovery and `58 passed`
  for complete provider regressions. Ruff, `git diff --check`, `pip check`, the
  deterministic 72-package license closure and final fresh adversarial review
  are green/CLEAN.
- Task 11 is active: implement the catalog API and downstream manifest/quality
  lineage. No release, credential, execution or synthetic-repair authority
  changed.

## Checkpoint 11 — 2026-08-14

- Task 11 is GREEN. The read-only catalog exposes exact manifest identity,
  dataset-current identity, immutable parents, provider/access, coverage,
  rights, entitlement, checkpoint and complete immutable quality evidence.
- The live production composition root binds the same catalog to the catalog
  API, history service and forecast registry. History, features, experiments
  and forecasts preserve exact manifest/evaluation pins while legacy v1 records
  retain their historical bytes and identities.
- Fail-closed regressions cover failed quality, mismatched pins, wrong artifact
  semantics, cross-instrument feature substitution, target corruption,
  historical-vs-current labeling, non-mutating legacy-v2 reads and unrelated
  quality-corruption isolation.
- Final evidence is `185 passed` for the complete Task 11 data/research selection
  and `193 passed` for API/workstation regression. OpenAPI freshness,
  TypeScript, Oxlint, Ruff and `git diff --check` pass; four pre-existing Fast
  Refresh warnings remain. The final fresh read-only re-review is CLEAN/PASS.
- Task 12 is active: implement and verify the English/Simplified-Chinese operator
  data-catalog screen. No release, credential, execution or synthetic-repair
  authority changed.

## Checkpoint 12 — 2026-08-14

- Task 12 and Slice 6 are GREEN. The package-served `/app/ops/data` route now
  presents the exact provider, artifact, coverage, rights, entitlement,
  qualification, checkpoint and immutable parent-lineage evidence in English
  and Simplified Chinese.
- All trust states remain textual and fail closed. Freshness-stale evidence is
  amber and cannot hide a failed evaluation; loading, empty and unavailable
  states make no qualification promise. The complete quality and checkpoint
  contracts are inspectable through one keyboard-operable disclosure.
- Reviewer-driven regressions closed incomplete exact evidence, raw-control
  drift, status-insensitive issue styling, optimistic empty copy and long-ID
  mobile overflow. A package-served populated and expanded catalog with
  production-length identities passed the 390 px browser check with zero
  horizontal overflow; final fresh read-only review returned CLEAN/PASS.
- Final evidence is frontend Vitest `152 passed`, focused backend/API `132
  passed`, explicit API-boundary and Playwright checks green, TypeScript,
  OpenAPI freshness, package-bundle freshness, Ruff and `git diff --check`
  green, with only four unchanged Fast Refresh warnings from Oxlint.
- Task 13 is active: add bounded clean-install collect/replay/inspect commands
  and immutable daily soak evidence without changing release or execution
  authority.

## Checkpoint 13 — 2026-08-14

- Task 13 tooling is implemented and reviewed. The installed `quantmesh-data`
  entry point provides bounded clean-checkout `collect`, exact hash-verifying
  `replay` and catalog `inspect`; `tools/trusted_data_soak.py` binds immutable
  daily reports to the exact code/configuration and fixed BTC/ETH/SOL plus
  AAPL/NVDA target matrix. Its verifier reopens the complete catalog,
  checkpoint, quality, manifest and object closure. Detectable local rollback,
  late backfill, stale targets, noncanonical reports, links and incomplete
  evidence fail closed. A local administrator able to rewrite every file and
  timestamp remains outside ADR-0016's filesystem threat model; Task 14's daily
  issue/CI record is the independent witness.
- Review-driven corrections closed incomplete closure verification,
  stale-target reuse, link/reparse handling, candidate-controlled target and
  policy identities, and invalid first-observation freezing. Final focused
  review returned CLEAN/PASS. The acceptance run then found and fixed one real
  quality-policy defect: grace and maximum latency had been equal, leaving no
  practical post-grace PASS interval. Authoritative latency is now 600 seconds
  for Hyperliquid after a 300-second grace and 7,200 seconds for Moomoo after a
  3,600-second grace.
- Four clean-checkout release-gate attempts exposed two additional
  environment-dependent test defects and one fixed-port race. API and SPA
  connector probes now inject deterministic offline Moomoo behavior under
  test without changing the production OpenD path; live-prediction E2E reserves
  an OS-assigned socket and shuts down scripted venue loops normally. The final
  gate passed all 18 steps on exact candidate
  `0a9796769c1ca98f0fc5f4dab187950167f4d0ab`: `3039 passed, 6 skipped`, Ruff,
  dependency/license audits, frontend reproducibility and Vitest, golden path
  `60` checks, and clean-clone proof before and after.
- A fresh isolated collection from that candidate covered
  `2026-08-14T08:12:00Z/2026-08-14T08:14:00Z`. All 12 Hyperliquid
  raw/normalized/adjusted/feature layers for BTC, ETH and SOL passed immutable
  quality with three bars, no issue codes, no synthetic rows and 379–380 second
  latency. Adjusted manifests are BTC
  `12562839ec2cd8b1af697e55911e2bc86b25d18c78d5029e06c88c82eacfdedf`, ETH
  `b77395c4198615dca0ef80535d9848fd1f0e6fd05e454b6d47648992ef4b79f2`
  and SOL
  `68966758e583b6645cd9b22fe026ab253b7c41551e808cea3cc0583267710aa1`.
  Each replayed twice in separate CLI processes with `verified=true` and three
  rows.
- The final-candidate Moomoo probe returned
  `unavailable/daemon-unavailable`, detail `local OpenD is unavailable`, zero
  manifest IDs and no synthetic substitution. Consequently Task 13 Step 4 is
  complete, Step 5 remains open, no soak candidate/configuration is frozen and
  Task 14's 168-hour evidence window has not started. No milestone PR, release,
  credential, execution or synthetic-repair authority changed.

## Checkpoint 14 — 2026-08-15

- Real OpenD came online (US Stocks LV3; `quote=True history_kline=True`). The
  first real Moomoo collection exposed three latent defects that the earlier
  `daemon-unavailable` path could never exercise, fixed and committed on
  `0021-trusted-data-fabric`:
  - `b49e7b4` — canonical bar identity no longer carries `market` metadata
    (ADR-0003 keeps it request-side), and revalidation filters history bars to
    the UTC window so the SDK's venue-date widening cannot fail the
    canonical-derivation check.
  - `2b59ca8` — the split-rate parser accepts the official Unicode arrow (`1→4`)
    alongside the fixture ASCII form (`1->4`).
- A clean-checkout `quantmesh-data collect` of Moomoo AAPL/NVDA daily bars for
  UTC `2026-08-10T00:00:00Z/2026-08-15T00:00:00Z` published 16 manifests (eight
  per symbol, five bars each) with `status=published` and passed the full
  `validate_publication` recomputation. Re-collecting the same window returned
  the identical manifest set (idempotent), and `replay` returned
  `verified=true`.
- Follow-up (not blocking the soak): the Moomoo 1-minute intraday path fails
  validation with `raw declarations are not source-derived` because the raw
  history surface preserves the complete SDK pages (including out-of-window
  bars) while its envelope is declared from the window-filtered bars. The fixed
  five-target soak matrix uses Moomoo AAPL/NVDA only at the daily interval, so
  this does not block Task 13 Step 5 or Task 14.
- Task 13 Step 5 (freeze the exact five-target candidate) is now unblocked.
  Task 14's 168-hour soak has not started. No release, milestone PR, credential,
  execution or synthetic-repair authority changed.

## Iterations 0022–0026 — Post-RC hardening chain (all merged)

The iteration 0013 Phase E "Strong" hardening items are delivered one slice at
a time on the now-stable persistence layer:

- 0022/0023 (merged via #112/#113): shared `JsonlStore` seam and full ADR-0006
  registry consolidation (ADR-0016).
- 0024 (merged via #115): venue-neutral cross-venue reconciliation engine
  (ADR-0017).
- 0025 (merged via #117): characterize and pin the execution numeric policy
  (six-decimal quantization, bps convention, exact-default tolerance, tick-size
  status) with tests and ADR-0018; no representation change.
- 0026 (merged via #119): local runtime assembly seam.

Ledgers under `docs/iterations/0022…`–`0026…`. External venues read-only;
execution paper-only; no credential handling.

## Iteration 0020 planning checkpoint — 2026-08-11

The operator asked to prefer coherent upstream frameworks over assembling
isolated features. The durable review is
`docs/architecture/framework-adoption-review-2026-08-11.md`:

- FinRL-X/FinRL-Trading is the first permissive, Python, end-to-end research
  workflow candidate.
- NautilusTrader is the closest event-driven execution architecture and has
  relevant Hyperliquid, Polymarket and IB adapters, but remains an isolated
  comparator because LGPL-3.0 and its process boundary require an ADR.
- Hummingbot Dashboard, vn.py, LEAN, Freqtrade and OpenBB remain bounded
  companions or references rather than a replacement product shell.
- No reviewed project covers QuantMesh's full equities + crypto + prediction
  markets + evidence + forecast UI + deterministic paper-control target.

The immediate frontier is Phase 0 of iteration 0020: reproduce one pinned NVDA
workflow in FinRL-X, a narrower Hyperliquid replay/sandbox comparison in
NautilusTrader, score both, and record an adoption/rejection ADR before feature
implementation expands. The shared Codex/Claude execution contract is
`docs/agents/cross-agent-execution.md`.

## Iteration 0020 implementation checkpoint — 2026-08-11

The executable plan is
`docs/superpowers/plans/2026-08-11-integrated-instrument-workspace.md` and is
the task-level source of truth. It defines 16 test-first tasks with fresh
implementation/review boundaries, exact upstream pins, one integration branch
and one final PR. Task completion and exact verification evidence must be
mirrored into iteration 0020 and this file before every pushed checkpoint.

Task 1 completed at `e251d8c`: the owned `FrameworkRunEvidence` and
`FrameworkScore` contracts, immutable exact pins, and a deterministic,
manifest-gated 420-session NVDA fixture passed 14 focused cases, Lake/Manifest
regression and Ruff. Fresh review found no Critical or Important issue; one
manifest-byte comparison Minor is parked for the final review.

Task 2 completed through `5bdf32d`. The real pinned FinRL-X run is retained as
an honest failed evaluation: checkout and Apache-2.0 license verification
passed, but upstream dependency `bt` requires Microsoft Visual C++ 14.0+ on
this CPython 3.13 Windows host. No runtime dependency was admitted. The fake
adapter and hardened controller passed 50/50 focused tests; four independent
review rounds closed all Critical/Important findings around process, path,
chronology, leakage and portable evidence boundaries.

Task 3 completed through `9d416d6`. The pinned NautilusTrader comparator is
deterministic and passes installation, license, chronology, leakage and
paper-only gates, but honestly fails `contract_mapping`: MARGIN collateral
semantics differ from QuantMesh cash accounting and the pinned sandbox client
has no standalone offline replay API. It remains an LGPL process-isolated
comparator and is not a release dependency. Final scoped review found no open
Critical or Important issue.

Task 4 is complete through `46a0669` and independently accepted with zero
Critical, Important or Minor findings.
The generated scorecard gives both candidates an honest `0.0` total because
both committed evidence files lack soft-score inputs. It rejects FinRL-X after
the `bt`/MSVC install failure and retains NautilusTrader only as an isolated
comparator after its deterministic contract mismatch. ADR-0015 records zero
copied upstream files, zero release dependencies and the native QuantMesh
workspace fallback. Strict evidence and scorecard validation rejected 28/28
independent malformed/tampered probes, the Task 1-4 compatibility run passed
173/173 tests, and the clean release-closure license gate exited zero. Task 5
(venue-aware historical data contracts and service) is complete through
`036d89c`: independent review closed all four first-round findings with zero
remaining Critical, Important or Minor issue. Task 6 (historical/live-tail API)
is complete through `629d3c8`: 211 focused tests, independent transaction
fault probes and the 100-update/eight-writer exactly-once drill passed, with
zero remaining Critical, Important or Minor issue. Task 7 (truthful multi-
horizon forecast artifacts) is complete through `6c28df5`. Tasks 8-10 are
complete through `94006fc`; Tasks 11-14 are complete through `29d5a42`.
Lightweight Charts 5.2.0 is admitted only behind the licensed chart adapter.
Tasks 15 and the review/local-matrix portion of Task 16 are complete through
`2e54909`. Three broad review rounds closed journal/account reconstruction,
single-clock valuation, reset identity/rollback/no-delete behavior, canonical
navigation, live-history resolution, retained-path visibility, honest live
market discovery and the live-detail fallback while replay history warms. The
final independent rereview found no remaining Critical or Important source
issue. Current committed-tree evidence is Python `2591 passed, 4 skipped`,
browser E2E `35/35`, frontend Vitest `143/143`, golden path `60/60`, zero npm
vulnerabilities, 646 locked frontend licenses accepted, current generated API
and packaged SPA bundle. No merge or release tag is allowed until the fresh
clean-checkout gate and protected-branch CI pass.

The first clean-checkout gate attempt on `73ef855` proved every one of its 17
substantive steps, including clone-clean state, but the runner exited 1 while
printing a replacement character into a CP1252 console. `fafe519` closes that
release-tool bug with a failing-then-passing console regression. Because the
verified commit changed, the full clean-checkout gate must run again before
the PR; no partial result is promoted to PASS.

The complete rerun on `4e90a81` PASSED 17/17 and returned 0: `2592 passed,
4 skipped`, golden path `60/60`, Python/npm closure and audit gates green,
package bundle current, Playwright browser cache present and clone clean. This
record-only documentation commit is followed by exact-final-tree PR CI; after
merge, the immutable tag still requires its own clean tagged-tree gate.

PR #108 then caught a historical cross-platform lock defect in the newly
enabled Linux frontend job: a Windows-only Rolldown binding was declared as a
normal root dependency. The same PR now removes that direct dependency,
declares and pins Node `22.12.0`, and adds a platform-neutral direct-dependency
regression. Frozen install, lint and production build pass on both Windows and
Linux Node 22.12; Vitest is `143/143`, focused release/security tests are `8/8`,
the package bundle is current, and audit/license gates are green. The immediate
frontier is the exact-tree PR CI rerun, squash merge, `v0.1.1-rc1` tag,
tagged-tree gate and isolated operator acceptance.

That rerun passed the entire frontend surface and caught one Linux-only
portable-evidence assertion: the Python symlink spelling was not redacted when
its resolved target differed. The recorder now normalizes both spellings; the
credential boundary remains fail-closed, targeted coverage is `2/2`, and the
complete FinRL-X isolation suite is `37/37`. PR #108 must rerun once more on
this exact fix before merge.

## Iteration 0020 completion checkpoint — 2026-08-12

- PR #108 passed protected-branch CI and squash-merged at `b6b05b9`; issue #107
  closed automatically and the remote integration branch was deleted. Local
  `main` was reconciled by fast-forward only.
- Annotated remote tag `v0.1.1-rc1` points to the same merged commit. The exact
  immutable tagged tree passed all 17 clean-checkout release-gate steps:
  Python `2595 passed, 4 skipped`, frontend Vitest `143/143`, integrated golden
  path `60/60`, Ruff, browser E2E, TypeScript, Oxlint, production/package bundle,
  Python/frontend license closure, pip-audit, npm audit and clone-clean proof.
- A fresh detached acceptance clone reports package/import/API version
  `0.1.1rc1`. Its deterministic demo and read-only live/degraded stations passed
  the actual browser walk, keyboard/zh-CN/reduced-motion/390 px checks, paper
  proposal-to-audit lineage, kill-switch 409 drill and live smoke `15/15`.
  The dead-station drill failed `4/4` with exit 1 as required.
- Hyperliquid supplied real read-only BTC frames before the external stream
  disconnected; the retained frame is labeled stale. Moomoo OpenD is absent,
  so AAPL/NVDA are labeled unavailable. No synthetic value is presented as
  live and no real-money authority was enabled.
- English-primary and Simplified-Chinese acceptance records live at the isolated
  acceptance root. The recorded verdict is PASS for prototype use only; no
  final `v0.1.1` tag exists and promotion remains a separate human decision.

## Current state

Iteration 0015 live-cockpit hardening is merged at `c47b83d` (PR #95), and the
replacement candidate `v0.1.0-rc5` is published at `cc8bde8` (PR #96). The
baseline has a deterministic demo workstation, live read-only cockpit,
Hyperliquid/Polymarket/Kalshi/Moomoo connector surfaces, replay lake,
provenance/freshness contracts and paper-only order authority. PR #100 merged
at `5069d1b`, completing global SPA localization; the old RC6 station remains
a historical pre-0017 build and must not be used to verify the fix.

The operator authorized immediate continuation after that merge. Therefore we
will not cut an interim localization-only RC: the next candidate will include
the bounded iteration-0019 live-research improvements. RC6 remains immutable;
formal promotion still requires a clean tagged-tree gate and explicit operator
acceptance.

Iteration 0019 was squash-merged by PR #101 at `298825b` on 2026-08-10. It
delivered the unified bounded live board, evidence/metric panels, compact
charts including watchlist sparklines, recorded replay and truthful degraded
state drills. Final evidence: backend `2131 passed, 3 skipped` from an
external-temp run, SPA E2E `5 passed`, Ruff clean, and the GitHub CI run for
the merged PR green. The fixed SPA E2E fixture reserves an OS-selected socket,
eliminating the shared-runner fixed-port race caught by CI.

## rc7 cycle

Released `v0.1.0-rc7` at `c1ea037` (PR #103), verified on the tagged tree:

| Step | Result |
|------|--------|
| clone current commit | PASS (1.9 s) |
| release version consistent (metadata, notes, tag) | PASS (0.2 s) |
| fresh venv | PASS (16.3 s) |
| install `.[dev,research,e2e]` | PASS (241.6 s) |
| ruff check src tests tools | PASS (3.0 s) |
| license review (closure contract) | PASS (2.2 s) |
| audit venv (isolated tooling) | PASS (14.2 s) |
| install pip-audit (isolated) | PASS (34.5 s) |
| pip-audit over requirements-audit.txt | PASS (12.7 s) |
| npm ci (frontend deps) | PASS (49.6 s) |
| frontend bundle current (build_frontend --check) | PASS (55.3 s) |
| frontend unit tests (vitest 73/73) | PASS (39.1 s) |
| full pytest suite (2134) | PASS (446.6 s) |
| golden path 53/53 | PASS (3.4 s) |
| clean-checkout proof | PASS (0.3 s) |

Workstation tested once from the tagged tree: `pip show quantmesh` → `0.1.0rc7`,
`import __version__` → `0.1.0rc7`, `/api/health` → `0.1.0rc7`, golden path
53/53 on the isolated install.

**RC7 is superseded by RC8 as the acceptance candidate.** RC7's documented
`--port` command was not accepted by its CLI; RC8 adds the tested loopback-only
override and its clean-checkout gate passed 15/15 on `085d0ad` (full pytest
353.2 s, golden path 53/53, browser cache present). The operator delegated
acceptance and promotion after the corrected candidate's automated browser
walk. Do not enable live-market execution as part of promotion.

## v0.1.0 promotion

The accepted RC8 line was promoted through the dedicated `release/v0.1.0`
tree. The formal clean-checkout gate passed 15/15 on `a317157`: version
consistency, full release extras, Ruff, license review, pip-audit, frontend
bundle and Vitest, full pytest (373.7 s), golden path and clean-checkout proof.
The final `v0.1.0` tag must point only at the green merged promotion commit;
all market access remains read-only or paper-only.

## Current frontier

1. Preserve the immutable accepted candidate and its acceptance evidence.
2. Await an explicit `promote v0.1.1-rc1 to v0.1.1` command before creating the
   final tag. A defect report keeps the candidate unchanged and starts a repair
   candidate instead.
3. The next product-planning frontier is iteration 0021, trusted data fabric;
   it does not implicitly authorize promotion or real-money execution.

## Historical delivery frontier

1. ~~Approve ADR-0013 through implementation evidence~~ (done, checkpoint
   bfa097c): the SPA spike is served from the packaged bundle with the
   rollback switch, `/api` double mount and a green 1811-test suite.
2. ~~Build deterministic `--demo` runtime assembly with provenance, freshness,
   reset/replay and representative cross-market/research/paper/risk/audit
   data.~~ (done, Phase B boundary): `src/quantmesh/demo/` seeds a labeled
   deterministic root under an operator-selected path — real fixture-provider
   market data with a reproducible cross-market cluster, forecast/report/
   experiment/promotion/alert/citation/audit surfaces through the public
   services, byte-identical replay and marker-guarded reset, provenance
   contract in `/api/demo/status` and response headers; `tests/test_demo.py`
   18/18 green.
3. ~~Deliver one browser tracer bullet from market evidence to paper fill,
   portfolio, risk and audit before migrating the remaining legacy pages.~~
   (done, Phase C boundary): the SPA shell, command palette and responsive
   navigation are live, the full research→paper-order→fill→position/P&L→
   risk/audit loop was verified over HTTP end to end (including kill-switch
   409, idempotent replay and reset), all 12 legacy routes 302 to `/app`,
   and the backend suite is 1,840/1,840 green.
4. ~~Add one public-data connector path and validated file import~~ (done,
   Phase D boundary): `src/quantmesh/demo/datalink.py` adds a 5-connector
   diagnostics panel, a credential-free testnet-pinned Hyperliquid l2Book
   path with rate-limit retry, `.datalink` caching, provenance and labeled
   synthetic fallback, and CSV/JSON/Parquet import with preview, mapping,
   per-row rejection reasons and `operator-import` manifests — missing
   software/credentials/network are instructive states, never blank pages.
   `tests/test_datalink.py` 20/20 green; live smoke on 8794 verified the
   fallback path, rejections and reset isolation.
5. ~~Complete bounded design, accessibility, E2E and clean-checkout
   verification~~ (done, Phase E boundary): 18/18 frontend unit tests
   (vitest), 5/5 SPA Playwright E2E, Impeccable one-pass detector
   `[]` with a programmatic visual audit clean at 28 route×viewport
   combos (0 overflow/clip/contrast/focus failures), real Tab-press
   keyboard walks, WCAG 2.2 AA contrast, non-color status cues,
   `prefers-reduced-motion` support, compact/desktop/tablet layouts,
   and the frontend build (`npm ci` → bundle-freshness check →
   vitest) added to the clean-checkout release gate; release notes
   (EN + zh-CN) written. Evidence in iteration 0014 Checkpoint 4.
6. ~~Run the full release gate from a clean checkout, merge the single
   RC2 PR, tag the verified merge commit `v0.1.0-rc2`~~ (done, Phase F):
   gate run 4 PASSED on HEAD `737f8c9` (14/14 steps, 1865 tests /
   0 failed, golden path 53/53, clone clean), PR #75 squash-merged
   into main at `710a931`, tag `v0.1.0-rc2` pushed, isolated install
   reproduced and the workstation live on 8766. **The operator then
   rejected RC2 (2026-08-09): the tag claimed `v0.1.0-rc2` while the
   package still reported `0.1.0rc1` in pyproject.toml, `__init__.py`
   and the pinned test — the gate could not see it because the test
   pinned rc1. Promotion to `v0.1.0` is forbidden.** The published rc2
   tag is the historical record and is not rewritten (iteration 0014
   Checkpoint 6).
7. ~~Fix the version drift and release `v0.1.0-rc3`~~ (done, rc3
   cycle, iteration 0014 Checkpoints 6–8): the three version
   locations read `0.1.0rc3`; new gate step
   `tools/check_release_version.py` asserts Git tag == package
   version == newest release notes (fails on the old rc2 commit,
   passes at the rc3 tag; PEP 440 tag comparison fixed post-tag,
   Checkpoint 7); gate run 5 PASSED 15/15, PR #80 merged, tag
   pushed; gate run 6 PASSED 15/15 on the exact tagged tree
   `e83e30c` after the checker fix; the isolated acceptance
   environment was regenerated from the tag (rejected rc2 build and
   workstation removed) and all four rejection items re-verified
   (`git describe` → `v0.1.0-rc3`, pip show → `0.1.0rc3`, import →
   `0.1.0rc3`, `/api/health` → `0.1.0rc3`); golden path 53/53 on the
   rc3 tree; workstation live at http://127.0.0.1:8766/app/ (PID
   41852) with `OPERATOR-ACCEPTANCE.md` at the acceptance root.
   **RC3 acceptance was subsequently re-run by an authorized automated
   browser review and found two product defects: Forecasts exposed neither a
   probability nor a calibration explanation, and the SPA chrome displayed
   `rc2` despite API/package RC3 metadata. RC3 must not be promoted.**
8. ~~Fix the two acceptance-surface defects, package a new RC, and re-run
   the clean-checkout release gate before asking for human sign-off.~~
   (done, rc4 cycle, iteration 0014 Checkpoint 10): the operator's locally
   fixed candidate (commit `8f462de`, both defects re-verified) was
   packaged as `v0.1.0-rc4`; gate run 1 PASSED 15/15 on the branch head,
   PR #83 squash-merged at `c9444ba`, tag `v0.1.0-rc4` pushed with the
   tag==version invariant verified at the tag; gate run 2 failed on the
   port-8643 environment flake (5 E2E setup errors, 0 product failures),
   gate run 3 PASSED 15/15 on the exact tagged tree; the isolated
   acceptance environment was regenerated from the tag (fresh clone +
   venv + install: import `0.1.0rc4`, golden path 53/53); the tag-build
   workstation is live at http://127.0.0.1:8766/app/ (PID 13196) with
   `OPERATOR-ACCEPTANCE-rc4.md` at the acceptance root. **Promotion to
   `v0.1.0` remains forbidden until the operator replies "accept RC4,
   promote to v0.1.0".**
9. Deliver iteration 0015 — Live Market Cockpit (operator `/goal`,
   2026-08-09): a local, read-only, replayable multi-venue real-time
   research workstation for a bounded watchlist (4–8 Hyperliquid perps,
   read-only Polymarket/Kalshi, Moomoo OpenD when locally available),
   built on the `MarketUpdate` contract, venue supervisors, DuckDB replay
   lake, local WS/SSE feed, cockpit screens, deterministic quote fence —
   all venues read-only, no credentials, no autonomous execution.
   Phase A (ADR-0014, contract, buffer, fixture WS server) merged via
   PR #85 (f48d4fd); Phase B (supervisor protocol + Hyperliquid venue
   supervisor, drill-tested 84/84 on the live surface) merged via
   PR #86 (641f3c6); Phase C (feed + cockpit screens + browser E2E,
   1983/1983 backend, 5/5 E2E) merged via PR #87 (553e944); Phase D
   (deterministic quote fence — provenance/age/sequence gates with
   explicit rejections over paper-order consumption, demo unchanged;
   2003/2003 backend, ruff clean) merged via PR #89; Phase E
   (read-only Polymarket + Kalshi public WS supervisors and the
   prediction comparison board — implied probability/bid-ask/spread/
   depth/liquidity per venue, signed cross-venue diff, honest
   distinct states; 71/71 board drills, 226/226 regression, 47/47
   vitest, 5/5 browser E2E on port 8646) landed on branch
   `0015-phase-e`; Phase F (Moomoo OpenD — poll-driven read-only venue
   supervisor + transport, METRICS last/volume + TRADE ticks with
   venue sequences and side, the venue-clock gate so a closed market
   or delayed feed is never labeled real, honest unavailable/
   disconnected/stale ladder; 13/13 F drills, 2066/2066 regression,
   ruff clean) landed on branch `0015-phase-f`; Phase G (replay
   determinism + live smoke drill + gate + acceptance, 8/8 replay
   drills including the TZ-determinism fix, 20/20 smoke checks E2E-
   verified healthy and degraded, full E2E 31/31 + frontend gate
   green, release gate 15/15 on the branch head `90c1d9c`, isolated
   acceptance env with degraded-state live station verified honestly
   unavailable and the smoke drill PASS/FAIL both proven) landed on
   branch `0015-phase-g` and merged into main via PR #92 (`e7ade9d`);
   **Phase G complete — its original self-acceptance record is preserved in
   `OPERATOR-ACCEPTANCE-0015.md` but superseded by the operator-authorized
   review in item 10.**
10. ~~Integrate the post-Phase-G acceptance hardening
    ([issue #94](https://github.com/ZP151/quantmesh/issues/94)): hydrate
    instrument details from `/api/live/state`, make shell/overview behavior
    runtime-aware, strengthen the read-only smoke contract, add an inclusive
    `through_local_seq` replay boundary, rebuild the packaged SPA, and retain
    browser evidence. The repaired candidate passed 82 targeted backend
    tests, 48 frontend tests, 5/5 live browser E2E, bundle freshness, Ruff,
    live smoke 14/14, desktop browser review with zero console errors, and a
    390 px walk with no horizontal overflow. The first PR CI run also exposed
    and fixed a fixed-port E2E bootstrap race (2,085 tests had passed before
    the setup-only collision; the repaired workstation E2E is 16/16). The
    single integration PR merged at `c47b83d` (PR #95), and the
    clean-checkout release gate on the merged tree PASSED 15/15 (pytest
    761.4 s, golden path 53/53; a first gate attempt was killed by the host
    mid-pytest with zero test failures — the passing run was detached and
    used the repo venv interpreter, since the version-consistency step runs
    before the gate's own venv exists). The replacement candidate
    `v0.1.0-rc5` is being cut: version metadata and tests pinned, release
    notes (EN + zh-CN) written, then tag, tagged-tree gate run and a
    regenerated isolated acceptance environment. Do not promote RC4; do not
    promote `v0.1.0` without the recorded operator verdict.~~ (done: PR #95
    merged at `c47b83d`; replacement RC5 tagged at `cc8bde8`; the rc5
    tagged-tree gate run is recorded in iteration 0015 Checkpoint H2; RC5
    awaits operator acceptance.)
11. Deliver iteration 0016 — Global Preferences and Workstation Continuity:
    persist English/Simplified Chinese language and system/light/dark theme
    preferences, apply them to the shell/navigation/command palette/settings,
    preserve first-paint theme state, add responsive/accessibility regression
    tests, rebuild the packaged SPA, then integrate through one tested PR.
    The single integration PR (#97) merged at `3514c18` with CI green, and
    the rc6 candidate is being cut from the merged tree (version metadata
    and tests pinned `0.1.0rc6`, release notes EN + zh-CN written; branch
    `0016-rc6`). After the branch-head gate: tag `v0.1.0-rc6`, run the
    tagged-tree gate, regenerate the isolated acceptance environment
    (superseding the rc4 build) and prepare the operator checklist. RC5
    remains immutable. Detailed evidence is in
    `docs/iterations/0016-global-preferences.md`.
12. Deliver iteration 0017 — roadmap vertical slice 1, domain-screen
    translations: extend the reviewed en / 简体中文 preference layer to
    all 12 scoped domain screens (Overview, Markets, Watchlist, Trading
    Orders/Positions/P&L, Order form, Risk, Research
    Experiments/Promotions/Forecasts, Connectors, Imports, Audit, Live
    Cockpit watchlist + instrument detail + freshness labels) via a
    standalone `screen.*` message table (`lib/messages.ts`), keeping
    every English string byte-identical, API-facing values raw, and
    provenance/freshness/paper-safety wording byte-exact in both
    locales. Prediction comparison, Ops kill-switch/enablement and
    legacy Jinja pages stay on the reviewed English fallback (safety-
    critical copy awaits explicit review). Extracted in 5 tested
    batches on one branch (`0017-translations`); locale coverage is now
    pinned by compile-time (`MessageKey` as-const) and runtime tests
    (en/zh-CN key parity, placeholder parity, zh-CN render smoke).
    Verification: tsc clean, oxlint 0, vitest 57/57, build clean,
    ruff clean, pytest 2116 passed (incl. browser E2E), clean-checkout
    release gate 15/15 on the branch head `c913df0`, CI green, PR #99
    squash-merged into main. No version bump; `v0.1.0-rc6` unchanged
    and still awaiting operator acceptance. Detailed evidence in
    `docs/iterations/0017-domain-translations.md`.
13. ~~Deliver iteration 0018 — global localization completion: translate the
    remaining Prediction, Kill switch, Enablement, NotFound, Loading and shell
    accessibility/provenance copy using the shared en/zh-CN dictionary; keep
    API-facing values and server safety verdicts semantically raw; rebuild the
    package-served SPA; merge one tested PR; then cut and verify a replacement
    RC because RC6 is immutable. Evidence belongs in
    `docs/iterations/0018-global-localization.md`.~~ (done: PR #100 merged at
    `5069d1b`; replacement candidate is deliberately deferred to include 0019.)
 14. ~~Deliver iteration 0019 — the bounded live research surface: quote/book/trade and
     prediction-market metrics, freshness/sequence semantics, compact charts,
     replay and degraded-stream drills. Reuse existing normalized contracts,
     lake, cockpit primitives and smoke fixtures; keep all venues read-only,
     bounded and provenance-first. Detailed scope is in
     `docs/iterations/0019-live-research-surface.md`.~~ (all four scope items
     merged by PR #101 at `298825b`: unified live board with
     filter model, research-grade metrics, compact charts including price-trend
     sparkline, recorded replay workflow with operator drills and browser
     acceptance; 6 slices, full suite 2134 backend + 73 frontend, E2E 7/7,
     SPA bundle current. The final GitHub CI is green after the E2E socket-race
     fix; all behavior remains read-only or paper-only.)

## Standing authority

Use the solo-developer fast lane: one integration branch, tested commits at
phase boundaries and one final PR. Do not pause for routine issue creation,
branch pushes or merging a green PR. Preserve protected main, branch from
`origin/main`, never force-push, and record every checkpoint in the iteration
file. Major language, database, financial representation or process-boundary
changes still require an ADR.

## External and safety gates

Moomoo OpenD simulated access and Hyperliquid testnet drills are optional
operator-dependent checks. Real-money orders, mainnet wallet signing,
credentials, paid infrastructure and AI order authority require separate
explicit approval and are outside this goal. Demo and imported data must be
labeled and isolated from non-demo operator state.

## Resume instruction

Resume from the metadata and active delivery protocol at the top of this file,
then read `PRODUCT.md`, `docs/product-strategy.md`, the active 0027 iteration,
its tracked design and executable plan, ADR-0015, the roadmap, issue #122 and
current Git/PR state. Start from the first incomplete vertical slice; do not
reopen framework bake-offs unless a DecisionPacket requirement proves the
native contracts insufficient. Treat 0021 soak as an independent maintenance
track and never infer real-money, mainnet, credential or AI order authority.
