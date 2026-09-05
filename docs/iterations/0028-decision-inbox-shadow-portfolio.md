# Iteration 0028 — Decision Inbox & Bounded Paper Shadow Portfolio

- Status: implementation and pre-PR verification complete; final integration pending
- Started: 2026-09-05
- Implementation verified: 2026-09-06
- Tracking issue: [#129](https://github.com/ZP151/quantmesh/issues/129)
- Branch: `codex/0028-decision-inbox-shadow-portfolio` from `origin/main` at
  `324d51d82ab4eae5e6176f7f91ce0631c5e76c32`
- Design:
  `docs/superpowers/specs/2026-09-05-decision-inbox-shadow-portfolio-design.md`
- Executable plan:
  `docs/superpowers/plans/2026-09-05-decision-inbox-shadow-portfolio.md`
- Ledger: this file

## Product outcome

From the existing watchlist, the operator can see which instrument needs
attention, open the exact saved DecisionPacket without losing identity, and
understand the packet's deterministic evidence, paper proposal/order,
monitoring and review state. The loop remains local-first and paper-only.

## Approved route

Route A reuses Watchlist as the Decision Inbox entry point and Instrument
Workspace as the only detailed decision surface. It adds no broad portfolio
dashboard and no second order authority. NVDA and AAPL prove the complete
deterministic loop; BTC and SOL remain honest Watch/Reject-only cases whenever
their forecast/evidence closure is insufficient for Paper.

## Slice boundaries

1. **Decision Inbox:** one read-only, cross-watchlist attention model with an
   exact packet deep-link, integrated into Watchlist.
2. **AAPL extension:** demonstrate the same saved decision and pending Paper
   proposal path for AAPL without adding a provider, model or execution path.
3. **Honest crypto degradation:** make BTC and SOL support saved Reject and
   Watch decisions while Paper is explicitly blocked by missing evidence.
4. **Paper shadow summary:** derive exact packet → proposal → order → monitoring
   → review state from existing durable ledgers and prove clean-restart replay.

Each slice has one user action, one visible outcome and a 24–48 hour boundary.
Reviewer feedback is capped at two rounds; a third structural failure shrinks
the slice instead of expanding repair work.

## Acceptance criteria

- Watchlist exposes a useful next action without requiring CLI navigation.
- Every decision link carries an exact `packet_id`; a newer draft cannot
  silently replace the selected packet.
- NVDA and AAPL can save and reopen Reject, Watch and a pending Paper proposal;
  order creation remains a separate confirmation in the final slice.
- BTC and SOL can each save and reopen Reject and Watch on independent packet
  lineages, while Paper is explicitly blocked before proposal creation by
  missing or insufficient evidence.
- The summary never upgrades AI output, marks, positions or inferred P&L into
  execution evidence.
- Paper remains two-stage and passes the existing deterministic risk kernel.
- Packet, proposal, order, monitoring and review identities survive a clean
  restart and replay fail closed on invalid ledgers.
- Desktop and 390px flows remain keyboard accessible with no document-level
  horizontal overflow.

## Prohibited expansion

No Provider/OpenD, real market calls, real trading, external notifications,
new model frameworks, broad performance dashboards, social/mobile/extension
work, other instruments, or 0021 soak changes. Impeccable sidecar refresh and
the known license-closure maintenance item do not block slice development; the
license closure must pass at the final PR boundary.

## Progress

### 2026-09-05 — kickoff

- PR #128 and PR #119 merge state were read from GitHub and stale repository
  metadata was corrected.
- Issue #129, the isolated 0028 worktree and the active resumable Goal were
  created from exact `origin/main`.
- Existing stores confirm that the new Inbox can be a read-only composition of
  replay-validated DecisionPacket, watch, proposal/order and review records.
- Route A is approved. The written design is awaiting operator review before
  an executable implementation plan or product-code change.
- Planner/Product review split the overloaded multi-instrument slice into an
  AAPL action slice and a separate BTC/SOL degraded-state slice. Quant/Risk
  review required exact outcome-preview eligibility and neutral pending-Paper
  wording; both corrections are incorporated in the design.
- The second and final Planner/Product and Quant/Risk review round both returned
  `APPROVED`. No authority, attribution or scope blocker remains; operator
  review of the written design is the only gate before plan generation.
- The operator approved the written design on 2026-09-05. The design is now
  frozen for implementation planning; changes to authority, attention
  semantics, symbols or slice boundaries require a new explicit review.
- The executable plan maps six reviewed tasks across four visible slices, uses
  RED/GREEN cycles, keeps broad verification at coherent boundaries and retains
  one final exact-head release gate. Slice 1 Task 1 is the active frontier.

### 2026-09-05 — Slice 1 Task 2: Watchlist Decision Inbox and exact packet route

- Watchlist now reads the strict Decision Inbox projection and renders one
  separator-first semantic table with mark context, attention state, safe reason
  and a single exact-packet deep link when packet identity is available.
- Instrument Workspace treats `?packet=` as authoritative: it waits for that
  exact packet, refuses 404 and context mismatch without a latest-packet
  fallback, preserves the explicit identity across background refreshes, writes
  action children back to the URL, and removes `packet` for New analysis.
- The generated OpenAPI client now includes the Inbox GET contract; the
  packaged SPA bundle was rebuilt from the same sources.
- Evidence: frontend focused suite 28 passed; API client check, typecheck,
  lint and build passed; generated-artifact check passed; selected inbox/exact
  Python suite 13 passed (15 deselected); action URL browser regression 3
  passed (13 deselected); `git diff --check` passed. The detailed Task 2 record
  is `.superpowers/sdd/2026-09-05-decision-inbox-shadow-portfolio/task-2-report.md`.

### 2026-09-05 — Slice 1 completion correction

- Final Important-finding correction keeps Watchlist recovery actionable without
  inventing a new surface: venue-scoped rows without a packet open their exact
  Instrument Workspace without `packet`, while venue-less legacy rows open the
  existing Markets venue-selection surface.
- The Inbox GET OpenAPI contract now documents its safe typed 409 replay error;
  the generated client is current and the frontend preserves its top-level safe
  message. Empty or malformed `packet` query values are rejected locally before
  any exact-packet request or latest-packet fallback.
- Slice 1 is complete after its allowed correction round. The next frontier is
  Slice 2 / Task 3: AAPL deterministic decision and pending Paper path.

### 2026-09-05 — Slice 1 final selection-rule correction

- The approved design overrides the plan's former flat attention ordering:
  attention-required terminal states retain stable priority, passive terminal
  states select solely by descending recency, and drafts are fallback only.
- A RED regression proved an older confirmed Paper packet previously hid a
  newer Reject action. The two-tier selector now returns that newer passive
  action while retaining pending-attention-over-newer-draft behavior.
- Evidence: named RED failed as expected; named GREEN passed; Inbox suite
  passed 13 tests; Ruff and `git diff --check` passed. See the Task 1 report.

### 2026-09-05 — Slice 2 Task 3: AAPL deterministic decision and pending Paper

- AAPL now uses the same `HISTORICAL_DAILY_SESSIONS` (650) analytical history
  as NVDA. The seed no longer truncates its daily bars, and both forecast runs
  derive from the same manifest constant; no eligibility flag, model, provider,
  adapter, or execution path was added.
- RED recorded the former 420-session/ineligible AAPL behavior in the seeded
  forecast and AAPL Reject, Watch, and Paper acceptance cases. The focused
  AAPL action GREEN passed 3 tests in 179.91 seconds, including pending Paper
  with no order ID and unchanged account/journal order records. The seed-level
  deep-history assertion passed in the same focused run before the action
  cases. Ruff and `git diff --check` passed.
- Browser evidence is retained as a precise skip: Playwright Chromium is not
  installed at `chromium_headless_shell-1234`; no browser was downloaded or
  installed. The AAPL Inbox-to-saved-Watch-reload assertion remains covered in
  the committed test, with API/unit acceptance evidence recorded above.

### 2026-09-05 — Slice 2 Task 3 verification correction

- Review round 1 found two verification gaps, not product defects. With the
  repository-declared Playwright Chromium installed in the standard cache, the
  exact AAPL Inbox → saved Watch → exact-packet reload browser acceptance passed
  (1 passed, 66.27 seconds).
- The required combined backend/demo check passed with 50 passed and 1 skipped
  in 711.78 seconds. Targeted Ruff and `git diff --check` passed. Task 3 is now
  complete; the active frontier advances to Slice 3 / Task 4, honest BTC/SOL
  Reject/Watch-only degradation.

### 2026-09-05 — Slice 3 Task 4: honest BTC/SOL Reject/Watch-only degradation

- Added the independent `BTC-USD`/`SOL-USD` × Reject/Watch acceptance matrix.
  Each case proves null forecast artifact, manifest, and quality-evaluation
  evidence fields on both draft and saved action packet; an unchanged public
  forecast registry with no matching crypto artifact; `forecast-missing`, a
  disabled Paper capability, a 409 Paper-action refusal, a durable non-Paper
  action and no proposal or account-order mutation across a fresh demo root and
  restart.
- Added an Inbox/unit assertion for an evidence-blocked crypto packet's exact
  route and a real 390px Chromium walk for each crypto row. The browser reads
  the missing-forecast explanation, fills the required operator reason, keeps
  Paper disabled, saves/reloads the exact Watch packet, and proves no document
  horizontal overflow.
- The first RED found only test assumptions: a generated-build ARIA selector
  did not match and safe actions correctly require an operator reason before
  becoming enabled. The visible Paper blocker and existing controls satisfied
  the product requirement, so no production or generated SPA artifact changed.
- Evidence: review-corrected focused matrix 4 passed, 12 deselected in 381.01s;
  review-corrected final selected Python matrix 6 passed, 42 deselected in
  530.33s; focused browser walk 2 passed in 78.48s; frontend suite 30 passed;
  typecheck, lint and targeted Ruff passed. Lint retains four existing Fast
  Refresh warnings. Detailed commands and red/green evidence:
  `.superpowers/sdd/2026-09-05-decision-inbox-shadow-portfolio/task-4-report.md`.
- Slice 3 is complete. The active frontier advances to Slice 4 / Task 5,
  bounded paper-shadow summary and clean-restart replay.

### 2026-09-05 — Slice 4 Task 5: bounded paper shadow summary

- Planner: one Watchlist disclosure exposes exact packet/proposal/order/watch/
  outcome/review records, then opens the same saved packet. Scope remains #129,
  paper-only, with no new authority or portfolio-performance surface.
- Quant researcher: filled quantity belongs only to the validated exact order;
  shared position and P&L remain `current-account-context-only`. Pending is
  neutral even when current confirmation freshness fails. Review availability
  requires a valid complete-horizon preview; missing evidence is never zero.
- Implementer: replaced the lighter proposal projection with
  `DecisionOutcomeReviewService.preview(packet_id)`, deriving compact IDs,
  status, fills and trigger events. Missing exact records remain unavailable;
  invalid linked identities fail closed. Saved-review outcome IDs remain
  separate from a changed current preview. Watchlist uses a native disclosure,
  wrapping monospace IDs and paired English/Simplified Chinese copy.
- Verifier: backend RED recorded six failures/six passes. Focused GREEN covers
  all seven new cases: six passed in the main selection, and the corrected
  Watch fixture passed independently. Final frontend group passed 31 tests;
  API freshness, TypeScript, lint, full Ruff and diff checks passed. Real
  Chromium clean-restart/390px/reduced-motion/keyboard acceptance passed one
  case in 209.17s. Desktop/mobile screenshots were inspected together; the
  required single Impeccable detector run returned `[]`, exit 0.
- Final targeted groups each ran once after focused GREEN: backend 98 passed,
  one existing Starlette/httpx deprecation warning in 5432.34s; selected real
  Chromium browser cases 3 passed, 17 deselected in 302.96s; frontend 31 passed
  across three files in 8.65s. All exited 0. The generated client and packaged
  SPA are current; lint retains four existing Fast Refresh warnings and build
  retains the existing large-chunk warning. No broad repository gate was run.
- Reviewer: one self-review found no new blocking issue; exact preview binding,
  read-only restart behavior, attention ordering, en/zh-CN parity and account
  attribution remain intact. No correction round was needed. A pre-existing
  edge where live-priced watch observations receive frozen InstrumentSnapshot
  metadata is recorded for separate monitoring follow-up, not repaired here.
  Temporary pytest roots are excluded from the commit.
- Slice 4 / Task 5 is complete. The active frontier is Task 6: license closure,
  final iteration evidence and integration gates; no Task 6 check ran here.
- Detailed command/exit evidence and local screenshots:
  `.superpowers/sdd/2026-09-05-decision-inbox-shadow-portfolio/task-5-report.md`.

### 2026-09-06 — Task 6 Steps 1–3: pre-PR integration checkpoint

- Planner: all four approved product loops are implemented under #129. This
  checkpoint closes license evidence, the broad verification attempt and its
  bounded test corrections. Final whole-branch review, the exact-head release
  gate, push/PR, exact-head CI and human review remain incomplete; the Goal and
  integration track stay active.
- Quant researcher: no new data, model, performance attribution or execution
  authority entered this checkpoint. The prior paper-only, exact-identity,
  evidence-blocked crypto and account-context boundaries remain the scope.
- Exact parent HEAD: `422c88ae73ea70d0873505c6fac1d8b8f8d28d84` on
  `codex/0028-decision-inbox-shadow-portfolio`. Checks ran in
  `C:/Users/15492/Develop/QuantMesh-iteration-0028`.

#### Verifier: environment and license closure

The shared interpreter is
`C:/Users/15492/Develop/QuantMesh/.venv/Scripts/python.exe`; Python application
checks explicitly set `PYTHONPATH` to the worktree's `src` and root, and
`PYTHONUTF8=1`. The frontend API check also prepended that interpreter's
`Scripts` directory to `PATH`.

- Shared Python `tools/license_review.py`: exit 1. It classified 66 installed
  closure members but correctly refused 60 ambient packages, 22 version
  mismatches and four absent pins (`cloudpickle`, `formulaic`,
  `interface_meta`, `wrapt`). This is development-environment drift, not a
  license-policy failure; no installed member was classified `UNKNOWN`.
- Created an isolated local `license-venv` with the shared Python `-m venv`,
  then ran its Python `-m pip install -q -c requirements-audit.txt -e
  '.[dev,research,e2e,moomoo]'`; both exited 0. This reuses the existing release
  extras and lock, without changing the shared environment.
- Isolated Python `tools/license_review.py`: exit 0, 70 installed Windows
  members reviewed from 76 pins, with six documented platform-only absences;
  2.07s. The unchanged focused test
  `tests/test_security.py::TestLicenseReview::test_every_installed_closure_member_classifies_allowed`
  also passed in that environment: 1 passed in 2.14s, exit 0. No license tool,
  allowlist, lock or `docs/licenses.md` change was justified.
- Shared Python `tools/npm_license_review.py`: exit 0, all 646 locked npm
  packages allowed. The isolated install retained only the pip upgrade notice
  (`25.2` to `26.2.1`); pip was not upgraded.

#### Verifier: one broad backend run and systematic failure classification

The one full repository run used shared Python with the explicit worktree
environment above:

```powershell
python -m pytest -q --basetemp=C:/Users/15492/AppData/Local/Temp/quantmesh-0028-task6-prepr-422c88ae-20260905
```

Session `34786` was retained through final exit 1: **3255 passed, 3 failed,
9 skipped, 1 warning in 8016.81s (2:13:36)**. It was not restarted or rerun.
The warning is the existing Starlette/httpx TestClient deprecation. This
checkpoint does not claim an overall full-pytest exit 0.

The failures were classified and addressed as follows:

1. `test_security.py::TestLicenseReview::test_every_installed_closure_member_classifies_allowed`
   failed because the shared environment lacked `cloudpickle`. The unchanged
   isolated test and complete isolated license CLI both passed as recorded
   above; no policy relaxation or shared-environment mutation was needed.
2. `test_spa_e2e.py::test_nvda_second_confirmation_refusal_keeps_packet_and_proposal_visible`
   passed its proposal-refusal, exact-identity and unchanged-order assertions,
   then timed out after 30000ms in its cleanup reset POST.
3. `test_spa_e2e.py::test_nvda_decision_safety_copy_keyboard_reduced_motion_and_mobile_boundary`
   then received HTTP 409 on its initial reset, before reaching UI assertions.
   The original response body was not retained.

The unchanged two-test SPA pair passed in session `66324`: 2 passed in 138.05s,
exit 0. One temporary observational rerun (session `85196`) reproduced the
cleanup timeout: 1 failed, 1 passed in 158.70s, exit 1. The failing reset first
drained two admitted requests for 6.8285s, then spent 21.7159s restoring/loading
and validating the root; state rebinding took 0.0062s. At the 30.0096s client
timeout, active requests were zero but the reset flag and lock were still held
while response work finished. The lock subsequently released and the next
focused test passed. The original next-test 409 is consistent with concurrent
reset refusal; that exact response reason is an inference from the code and
observed lock state, not a captured body.

- Implementer: the reset runtime and both failing test bodies were unchanged
  by 0028. The 30-second helper dates to 0027, and the request drain/lock to
  0020. The observed legitimate reset work exhausted a timing-sensitive test
  request budget. The sole correction is `timeout=120_000` on `_reset_demo`'s
  POST, preserving its `status == 200` assertion and all product semantics.
  There is no retry or swallowed 409. The temporary probe and bytecode were
  removed before GREEN.
- Focused GREEN ran the same two test node IDs with shared Python, `-q`,
  `--durations=2`, and unique basetemp
  `C:/Users/15492/AppData/Local/Temp/quantmesh-0028-task6-reset-green-20260906-c`.
  Session `5875`: 2 passed in 165.50s, exit 0; first test call 82.14s and setup
  43.86s. No warning was printed. Targeted Ruff passed after this correction.
- The unmodified reproduction and observational runs used distinct temp roots
  ending `reset-repro-20260906-a` and `reset-probe-20260906-b`. No
  `.pytest-task*` roots were added. Full output is retained locally in
  `task-6-pytest-final.md` and `task-6-reset-diagnosis-evidence.md` under the
  task report directory below.

#### Verifier: frontend and remaining pre-PR checks

| Command | Final observed result |
| --- | --- |
| Shared `ruff.exe check src tests tools` | Exit 0, all checks passed |
| `npm run check:api` | Exit 0, generated client current, 3.79s |
| `npm run typecheck` | Exit 0; after fixture correction 1.87s |
| `npm run lint` | Exit 0; after fixture correction 1.94s, four existing warnings |
| `npm exec vitest -- run` | Corrected run exit 0, 197 passed across 23 files, 16.63s |
| `npm run build` | Corrected run exit 0; 2083 modules, Vite build 483ms |
| `git diff --check` | Exit 0 after both bounded corrections |
| `git submodule status` | Exit 0, 1.49s; nine uninitialized `-` entries, no `+` drift or conflicts |

- Implementer: initial full Vitest RED was 2 failed/195 passed in 16.16s.
  Two legacy navigation tests still mocked `api.watchlist` and expected former
  link labels. Their fixtures now use `api.decisionInbox`; assertions retain
  each row's venue and fail-closed venue selection. Focused GREEN was 13 passed
  in 4.52s. The first build caught an overly broad fixture venue type; the
  generated API's exact venue union corrected it before the final build.
- Retained warnings: Fast Refresh component-export warnings in `state.tsx`,
  `ui/badge.tsx`, `ui/button.tsx`, and `preferences.tsx`; the existing Vite
  chunk-size warning above 500 kB. No product source, generated client or
  packaged SPA changed in Task 6.
- Reviewer: individual slice reviews remain recorded above. One final
  whole-branch review is the next gate; it has not run at this checkpoint.
  The previously noted frozen monitoring-metadata edge remains outside this
  task and was not implicated by the final verification failures.

#### Completion boundary

- [x] Four approved functional slices implemented and slice evidence recorded.
- [x] Python and npm license closure verified without changing license policy.
- [x] One broad pre-PR run captured; failures classified, focused corrections
  verified, and all other pre-PR checks recorded honestly.
- [x] Task 6 Steps 1–3: tracked integration evidence and tested checkpoint.
- [x] Final whole-branch review: round-2 source findings resolved; artifact refresh below.
- [ ] One exact-head release gate after review.
- [ ] Push, milestone PR, exact-head CI and human review.
- [ ] Final objective-by-objective Goal completion audit.

Local command outputs, retained sessions and detailed diagnosis:
`.superpowers/sdd/2026-09-05-decision-inbox-shadow-portfolio/task-6-report.md`.
This tracked ledger mirrors the material evidence so resumption does not
depend on the ignored local report.

### 2026-09-06 — Final review round 1: bounded correction wave

- Reviewer/controller: reviewed checkpoint
  `7dd644c7dbbde14a245cdb1fbfc02117fad4af3d`; authorized one focused fix commit
  for four findings, with TDD and directly related verification only. No broad
  pytest rerun, release gate, push or PR is part of this wave.
- Implementer: exact selection is now part of the workspace's DecisionRail
  state identity. Creating packet B from exact packet A and navigating
  Back/Forward remounts packet-bound local action state; B's reason/result
  cannot remain visible under A. Same-context fresh polling remains unchanged.
- Implementer: changing range from a pinned packet removes the `packet` query
  and selects fresh analysis for the requested range in the same interaction.
  Exact-URL rendering does not overwrite that pending fresh selection with a
  default archive. The loading transition keeps workspace/range controls, and
  the new range stays fresh even if that workspace also has a saved packet.
- Implementer: baseline workstation construction now attaches the existing
  DecisionInboxService outside the history/packet-service condition. Its
  existing optional providers still supply `None` when absent, while persisted
  watchlist membership and configured marks remain visible. No packet,
  proposal, monitoring or review state is fabricated; optional service
  injection, reset-safe providers and all Provider/OpenD boundaries remain.
- Quant researcher/UX: zh-CN `paper_open` now says `模拟订单进行中` rather than
  claiming a position opened. Accepted zero-fill and filled/open orders both
  fit this neutral workflow label; order status and filled quantity remain
  explicit in the record disclosure. Impeccable hardening preserved the
  existing interface and focused only on navigation state and truthful i18n.

#### Verifier: RED and focused GREEN

- Backend regression initially needed its required `PaperAccount.cash` fixture
  corrected (not a product RED). The valid pre-fix run failed on HTTP 404 versus
  expected 200: 1 failed, 1 warning in 1.60s, exit 1. After moving only service
  attachment, the same test passed: 1 passed, 1 warning in 1.32s, exit 0.
- Frontend RED used the three new regressions in `InstrumentWorkspace.test.tsx`
  and `Watchlist.test.tsx`. After correcting the test's range-button casing,
  the valid unchanged-product run was 3 failed / 28 skipped in 3.76s, exit 1:
  Back selected A in the URL while the rail still held B; range 1m retained
  `packet=C`; accepted zero-fill displayed `模拟仓位已开`.
- The first range correction exposed the old exact render's default-selection
  overwrite; the same regression drove the guard at that source. Focused final
  GREEN: 3 passed / 28 skipped in 4.24s, exit 0. The wait for the resolved
  one-month response uses the query's normal asynchronous notification.
- Relevant frontend suites: `InstrumentWorkspace`, `instrument/DecisionRail`,
  `Watchlist`, `NavigationAndValuation`, and `lib/preferences`: **69 passed in
  10.45s**, five files, exit 0. This includes the existing same-context polling,
  stale-action, confirmation, range-placeholder and exact-route checks.
- `npm run check:api`, `npm run typecheck`, and `npm run lint` exited 0;
  generated API client unchanged. Lint retains the same four Fast Refresh
  warnings recorded above. Targeted Ruff on `src/quantmesh/api/workstation.py`
  and `tests/test_decision_inbox.py` passed after wrapping the new test's long
  signature. `git diff --check` passed. The one Impeccable detector invocation
  for the changed UI sources returned `[]` (exit 0).
- A supplementary related backend run used session `70427`, shared
  Python, explicit worktree PYTHONPATH/PYTHONUTF8, and unique basetemp
  `C:/Users/15492/AppData/Local/Temp/quantmesh-0028-review-related-green-20260906`:
  `python -m pytest -q tests/test_decision_inbox.py tests/test_workstation.py
  --basetemp=... --durations=3`. The controller explicitly directed Ctrl+C to
  avoid repeating full Workstation coverage before the single final gate.
  Before interruption, 18 passing progress markers and no failures had been
  observed. The session returned exit 1 with no pytest final summary; no
  authoritative completed-test count or full-suite pass is inferred. Read-only
  process inspection confirmed no matching worker remained. This interrupted
  supplementary run is not classified as a test failure. The exact baseline
  wiring regression had already passed against the same implementation, so it
  was not rerun; its 1 passed / 1.32s / exit 0 is the backend fix evidence.
- Deferred: only the final review's non-blocking Spec Minor, mark timestamp
  and reason visibility in the Inbox. No performance claims or additional
  provider/monitoring/0021 work entered this correction.
- Final review acceptance, exact-head release gate, push/PR/CI/human review
  and Goal completion remain open. The original broad pytest exit 1 and its
  systematic classification above remain the historical broad evidence.

### 2026-09-06 — Task 6 mechanical SPA artifact completion

- Controller: final review round 2 resolved source findings at
  `e6e3acd0d633b643c5b13d68be2309894cd23c01`; the committed SPA still required
  refresh. No further review round or behavior change was authorized.
- Shared Python `tools/build_frontend.py` initially exited 1: `tsc -b` found
  three unsupported `getByRole` options in the new range regression. With
  explicit approval, removed only `exact: true` at those three calls; literal
  role/name assertions and runtime behavior are unchanged. The prior root
  `tsc --noEmit` command does not build its referenced TypeScript projects.
- Canonical `C:/Users/15492/Develop/QuantMesh/.venv/Scripts/python.exe
  tools/build_frontend.py`, with `PYTHONUTF8=1`, then exited 0: 2083 modules,
  Vite 11.97s, copied `frontend/dist` to the packaged SPA. The same interpreter
  with `tools/build_frontend.py --check` exited 0: 2083 modules, Vite 412ms,
  `bundle is current`. `git diff --check` exited 0.
- Generated diff: replaced `InstrumentWorkspace-BVCLqqdd.js` with
  `InstrumentWorkspace-B8WDwIX0.js`, `index-BrHmpXAo.js` with
  `index-SmewbZoZ.js`, and updated the index script reference. CSS/fonts are
  unchanged; the builder replaced the owned bundle tree, leaving no stale
  orphan assets. Retained warnings: existing >500 kB chunk warning and one
  build's plugin timing notice (27% of 12.0s in hooks); no optimization scope.
- No detector, additional pytest, release gate, push or PR ran. The single
  exact-head gate is next; CI/human review and Goal completion remain open.
