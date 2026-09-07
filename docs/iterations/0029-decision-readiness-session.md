# Iteration 0029 — Decision Readiness Session

- Status: executable plan review
- Started: 2026-09-07
- Tracking issue: [#131](https://github.com/ZP151/quantmesh/issues/131)
- Integration branch: `codex/0029-decision-readiness-session`
- Baseline: `origin/main@4fb810e1268f5f0e13599d7198aee4fa78cc4717`
- Design:
  `docs/superpowers/specs/2026-09-07-decision-readiness-session-design.md`
- Executable plan:
  `docs/superpowers/plans/2026-09-08-decision-readiness-session.md`

## Outcome

Give a research-minded individual active trader one explicit session in the
existing Decision Inbox that shows whether watched decisions have usable data,
refreshes all registered local conditions, and opens the exact triggered,
blocked or review-due DecisionPacket within two minutes.

## Product boundary

Iteration 0029 unifies the user experience but does not merge iteration 0021's
data-plane authority. It may consume exact trusted-data readiness through a
read-only adapter. It cannot operate Scheduler, Provider/OpenD, trusted-data
roots, soak evidence, outbox or GitHub witness state.

## Success criteria

- [ ] Decision Inbox shows exact readiness, evidence time, mark time/reason and
  last local check for every scoped identity.
- [ ] Real readiness is qualified only through the packet's exact manifest and
  evaluation bindings; demo remains explicitly labelled.
- [ ] One explicit action evaluates all and only registered local watches from
  server-owned facts without provider or order calls.
- [ ] Complete, partial and no-registration refresh outcomes are honest and
  deterministic.
- [ ] Triggered, blocked and review-due entries open the exact packet.
- [ ] Refreshed evaluations and exact links survive clean application restart.
- [ ] NVDA/AAPL complete the session in under two minutes; BTC/SOL remain
  evidence-blocked where required.
- [ ] Targeted, browser, restart, final release and CI checks pass.

## Delivery slices

1. Readiness truth in Decision Inbox.
2. Explicit local session refresh.
3. Action queue and exact navigation.
4. Restart and two-minute acceptance.

Each slice must produce visible user value within 24–48 hours, has one bounded
deliverable and stop condition, and receives at most two review rounds.
Targeted verification is normal; broad gates occur at meaningful slice and
final PR boundaries rather than after every micro-change.

## Prohibited expansion

- Provider/OpenD or real market calls
- Scheduler, automation, external notifications or GitHub witness changes
- trusted-data writes, new roots, overlap resolution or soak migration
- proposal confirmation, new order authority, testnet or real trading
- AI priority/readiness authority
- symbols beyond NVDA, AAPL, BTC and SOL
- Qlib/Darts/model-ranking work
- 0021 source, evidence or operational-state modification
- unrelated cleanup or frontend sidecar maintenance

## Checkpoints

### 2026-09-08 — Slice 1 readiness truth in Decision Inbox

- Added `DecisionReadinessService`, which reads only exact packet manifest IDs
  through `lineage(manifest_id)` and validates quality/evaluation/checkpoint,
  rights and trusted-for-research closure. Demo evidence remains explicitly
  labelled and missing/corrupt closures fail closed as blocked or unavailable.
- Inbox now projects non-null readiness plus session and local-monitoring
  timestamps without writing state. The workstation passes a reset-safe
  `app.state.data_catalog` provider; no Scheduler, Provider/OpenD, trusted-data
  root, soak, witness, outbox, network or trading behavior changed.
- The Watchlist preserves its separator-first table and one row action while
  rendering readiness, evidence time, received mark/reason and last check in
  the existing decision cell, in English and Simplified Chinese.
- TDD evidence and targeted verification are recorded in
  `.superpowers/sdd/2026-09-08-decision-readiness-session/task-1-report.md`.

### 2026-09-08 — Task 1 review-fix evidence

- Review findings fixed: a readiness evaluation timestamp was incorrectly
  presented as a local check; demo history returned early despite an advertised
  real forecast; failure paths could omit packet generation time; and reviewed
  reason codes were not fully localized. The Inbox now labels the two clocks
  distinctly, presents persisted monitoring status/reason only when present,
  validates every advertised real forecast by its exact packet IDs, and
  computes the oldest packet-bound generation/evaluation time for ready,
  blocked and unavailable states. Valid historical packet evidence is not
  wall-clock-aged.
- TDD RED: `python -m pytest tests/test_decision_readiness.py -q --basetemp
  ...task1-fix-red` produced 2 expected failures and 11 passes (demo+real
  forecast fail-open; missing limiter). `npx vitest run
  src/screens/Watchlist.test.tsx` produced 2 expected assertion failures and
  3 passes (the old evidence/local-check conflation and English zh-CN reason).
- GREEN: `C:\Users\15492\Develop\QuantMesh\.venv\Scripts\python.exe -m
  pytest tests/test_decision_readiness.py -q --basetemp
  ...task1-fix-final` passed 15 in 1.34s. `npx vitest run
  src/screens/Watchlist.test.tsx src/screens/NavigationAndValuation.test.tsx
  src/lib/messages.test.ts` passed 21 in 3 files in 3.68s. `npm run typecheck`
  passed; `npm run lint` exited 0 with the pre-existing four Fast Refresh
  warnings. `npm run generate:api` regenerated the client and `npm run
  check:api` confirmed it current. Targeted Ruff check/format and `git diff
  --check` passed.
- UI detector: `node C:\Users\15492\Develop\QuantMesh\.codex\skills\impeccable\scripts\detect.mjs
  --json frontend/src/screens/Watchlist.tsx frontend/src/lib/messages.ts`
  returned `[]`.
- Self-review: all catalog reads remain `lineage(exact_manifest_id)`; no
  entries traversal, provider/network call, state write, refresh affordance,
  polling, clock formatter, Scheduler or trading change was introduced.
  Focused tests additionally cover unavailable demo forecast closure and a
  returned wrong manifest identity. The remaining frontier is the controller's
  one final stable combined backend selection at this exact head.

### 2026-09-08 — Task 1 controller final verification

- Controller-owned stable selection passed with the worktree `src` first on
  `PYTHONPATH` and the reviewed shared virtualenv Scripts directory first on
  `PATH`:

  ```text
  python -m pytest tests/test_decision_readiness.py tests/test_decision_inbox.py tests/test_data_catalog.py tests/test_data_catalog_api.py -q --basetemp %TEMP%\quantmesh-0029-task1-controller-final
  exit 0; 47 passed, 1 warning in 930.56s (0:15:30)
  ```

- The sole warning was `StarletteDeprecationWarning` from the shared
  `.venv\Lib\site-packages\fastapi\testclient.py:1`, concerning
  `httpx`/`starlette.testclient` and httpx 2. It is an inherited dependency
  warning, recorded rather than hidden; it is not a Task 1 product defect.
- The exact-head combined boundary is now evidenced. Task 1 is at scoped
  re-review; do not advance the next slice until that review resolves.

### 2026-09-08 — Task 1 review round 2/2: NOT APPROVED

- The capped second review found four remaining load-bearing defects:
  1. Forecast-closure failure omits `forecast_generated_at` from
     `limiting_evidence_at`.
  2. A demo packet with a real forecast can place blocked forecast
     qualification evidence in the `history` field.
  3. Exact-real and corrupt Inbox rows, session reconstruction, and persisted
     monitoring status/reason still lack complete behavioral evidence.
  4. Reachable known readiness/monitoring reason codes remain unmapped for
     Simplified Chinese.
- Task 1 is **NOT APPROVED** after review round 2/2. Task 2 has not started.
  The next action is to re-scope Slice 1 against these findings, not to open a
  third review loop.
- No 0021, Scheduler, Provider/OpenD, external, trusted-data, soak/witness,
  outbox, testnet, live-trading or other execution state changed during this
  documentation-only closeout.

### 2026-09-08 — Slice 1 recovery re-scope

- The approved recommendation is to shrink the four residual findings into
  two independent recovery tasks rather than open a third broad review loop.
- Recovery Task A owns only exact forecast limiting clocks and evidence-field
  placement. Recovery Task B owns only Inbox/restart behavioral proof and the
  exhaustive known-reason localization map.
- The executable recovery plan is
  `docs/superpowers/plans/2026-09-08-decision-readiness-slice1-recovery.md`.
  It preserves the approved design and 0021 authority boundary. Parent Task 2
  remains frozen until both recovery tasks and the single Slice 1 integration
  boundary pass.
- Recovery Task 1 passed its scoped quant/spec review at `4e9e296`. The
  original combined Recovery Task 2 was interrupted without changes after it
  produced no implementation evidence; it is now split into independent
  backend Inbox/restart proof and frontend known-reason localization tasks.

### 2026-09-08 — Recovery Task A implementation

- `fix(decisions): preserve exact forecast evidence` is implemented on the
  recovery branch; exact forecast qualification failures now retain the
  packet-bound `forecast_generated_at` clock and place any returned reference
  in `forecast`, leaving `history` reserved for history qualification.
- Focused RED: `pytest tests/test_decision_readiness.py -q` exited 1 with
  `6 failed, 15 passed` in 1.76s after the new clock/placement assertions.
  GREEN: the same selection exited 0 with `21 passed` in 0.83s.
- Scoped Ruff check, Ruff format check and `git diff --check` exited 0 after
  formatting. No wall-clock ageing, catalog traversal, provider/network,
  Scheduler, 0021, trading or unrelated state changed. Task B remains frozen
  pending the scoped recovery review.

### 2026-09-08 — Recovery Task 2 backend Inbox/restart proof

- Added only Inbox behavior coverage: a real packet now proves its exact
  manifest/evaluation/report projection and persisted monitoring/session facts;
  mismatched, corrupt and untrusted exact closures prove fail-closed sanitized
  output without a catalog fallback; both direct snapshot and HTTP GET prove
  packet, marks, registration and evaluation inputs remain byte-equivalent;
  and a fresh application reconstruction proves equal Inbox row and
  `DecisionSessionSummary` facts, including `last_checked_at`,
  `latest_status` and `latest_reason`.
- No production file changed. The tests use the real `DecisionInboxService`,
  packet/watch stores and `DecisionWatchService`, with the existing exact-ID
  catalog fake; no catalog enumeration, Provider/network, Scheduler, 0021,
  refresh, UI or trading scope was introduced.
- Focused new-case selection: `6 passed, 23 deselected, 1 warning` in
  `188.97s`. Required target:
  `pytest tests/test_decision_inbox.py -q --basetemp
  %TEMP%\quantmesh-0029-slice1-recovery-b-full-20260908` exited 0 with
  `29 passed, 1 warning` in `985.24s (0:16:25)`. The sole warning is the
  inherited `StarletteDeprecationWarning` from the shared FastAPI TestClient
  dependency. `git diff --check` is recorded with the task commit.
- This coverage may pass initially by recovery ruling: the mutation rationale
  is recorded in
  `.superpowers/sdd/2026-09-08-decision-readiness-slice1-recovery/task-2-report.md`.
  The scoped Spec review remains the stop-condition frontier; Task 3 has not
  started.

### 2026-09-08 — Recovery Task 3 known-reason localization

- Completed one explicit frontend map for all 23 reachable Inbox/readiness
  codes: `demo_evidence`, `catalog_unavailable`,
  `missing_history_binding`, `trusted_evidence`,
  `missing_forecast_binding`, the eight `history_*` exact-closure results,
  the eight `forecast_*` exact-closure results, `no_saved_packet`, and
  `venue_unavailable`. It also covers the four persisted monitoring states
  (`armed`, `not_triggered`, `triggered`, `not_comparable`) and all six
  persisted unavailable-fact reasons (`unusable_price_evidence`,
  `future_reference`, `calendar_unavailable`, `missing_forecast`,
  `candidate_not_comparable`, `candidate_incompatible`).
- Table-driven message tests pin reviewed English and Simplified-Chinese copy
  for all 33 stable values. Component tests prove each known reason is
  localized while the original server text remains in `title`; unknown
  readiness, monitoring status, and monitoring reason values remain verbatim.
  The existing separator-first row, one link per row, `dateTime`,
  `usePreferences`, wrapping, and focus classes are unchanged.
- TDD RED: `npx vitest run src/screens/Watchlist.test.tsx
  src/lib/messages.test.ts --reporter=verbose` exited 1 with `36 failed,
  25 passed` in `22.33s`; every failure was an expected missing reviewed
  message or the corresponding known-code fallback. GREEN: the required
  three-file frontend target passed `88` tests in `3` files in `6.26s`.
  `npm run typecheck` passed. `npm run lint` exited 0 with the pre-existing
  four Fast Refresh warnings in `state.tsx`, `badge.tsx`, `button.tsx`, and
  `preferences.tsx`.
- No backend, Provider/network, Scheduler, 0021, trading, new-symbol, action,
  polling, refresh, card, time-helper, or layout change was introduced. The
  next frontier is the required scoped Standards+Spec review, then the single
  Slice 1 recovery integration boundary; parent Task 2 remains frozen.

### 2026-09-08 — Recovery Task 3 review-fix round 1/2

- Localized persisted monitoring status now retains its original server value
  in `title`, matching the existing known-reason disclosure. All code-map
  lookups now use an own-property check, so inherited names are never treated
  as supported values.
- Focused RED: `npx vitest run src/screens/Watchlist.test.tsx
  src/lib/messages.test.ts --reporter=verbose` exited 1 with `7 failed,
  71 passed` in `5.99s`: four missing status-title assertions and the three
  inherited-property values `constructor`, `toString`, and `__proto__`.
  GREEN: the same focused selection passed `78` tests in `2` files in `3.04s`.
  `npm run typecheck` passed; `npm run lint` exited 0 with the same four
  inherited Fast Refresh warnings; `git diff --check` passed. The UI layout
  did not change, so the already-recorded one-pass Impeccable detector was not
  rerun.

### 2026-09-08 — Slice 1 recovery integration: COMPLETE

- Recovery Task 1 is accepted at `4e9e296` (`fix(decisions): preserve exact
  forecast evidence`): its scoped quant/spec review found no open
  Critical/Important finding. Recovery Task 2 is accepted at `88bce75`
  (`test(decisions): prove inbox readiness recovery`) with its reviewed
  blocked-exact-closure proof pin at `44d95f7`; its scoped Spec review found
  no open Critical/Important finding. Recovery Task 3 is accepted at
  `9390456` (`fix(decisions): localize readiness reasons`) with the review-fix
  at `ad2a367` (`fix(decisions): preserve localized source values`); its scoped
  Standards+Spec review found no open Critical/Important finding. The final
  import-order-only recovery fix is `be5949a` (`style: sort decision inbox
  imports`).
- The mandated four-file backend selection was run exactly once on the recovery
  head with this worktree's `src` first on `PYTHONPATH` and the shared virtual
  environment Scripts directory first on `PATH`: `59 passed, 1 warning in
  1068.63s (0:17:48)`, exit `0`. The sole warning remains the inherited
  `StarletteDeprecationWarning` from shared FastAPI TestClient/httpx usage and
  is recorded, not hidden.
- The remaining exact-head boundary passed once after the import-order repair:
  scoped Ruff exit `0`; `npm run generate:api` exit `0` in `12.3s`; `npm run
  check:api` exit `0` in `4.8s`; targeted Vitest exit `0` with `91 passed` in
  `3` files in `3.93s` (command wall time `7.0s`); `npm run typecheck` exit
  `0` in `1.5s`; `npm run lint` exit `0` in `1.9s`; and `git diff --check`
  exit `0` in `0.4s`. Lint retained the four inherited Fast Refresh warnings
  in `state.tsx`, `badge.tsx`, `button.tsx`, and `preferences.tsx`.
- The prior Impeccable detector evidence remains `[]`; it was not rerun because
  the final localization review-fix changed no layout. No Provider/network,
  0021, Scheduler, trusted-data, external, or trading state changed.
- Parent Slice 1 / Task 1 is complete. The parent plan resumes at Task 2:
  explicit local session refresh; no other slice is authorized by this
  checkpoint.

### 2026-09-07 — Activation and architecture approval

- Operator approved the Decision Readiness Session boundary: one unified
  product entry with separate 0021 and 0029 engines.
- Issue #131 records the user outcome, acceptance criteria and prohibitions.
- A fresh worktree and branch were created from merged
  `origin/main@4fb810e1268f5f0e13599d7198aee4fa78cc4717`.
- At this checkpoint the written design was pending operator review. No product
  code had started, and no 0021, Provider/OpenD, Scheduler, evidence, trading or
  external-notification state changed.

### 2026-09-08 — Written design approval and executable plan

- Operator approved the written specification at commit `1e4cce6`.
- The executable plan maps the approved design into four 24–48 hour vertical
  slices plus one exact-head integration/PR closeout task. Every slice names one
  user action, one stop condition, precise files/interfaces, TDD commands and a
  two-round review ceiling.
- The plan reuses `DecisionInboxService`, `DecisionWatchService.check()` and
  exact `TrustedDataCatalog.lineage(manifest_id)`; it creates no second Inbox,
  monitoring or session ledger and gives 0029 no 0021 operational authority.
- Execution approach selection is the next frontier. Product code remains
  unchanged at this checkpoint.
