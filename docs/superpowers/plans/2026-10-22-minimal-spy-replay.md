# Minimal SPY replay implementation plan

## Approved P1 pre/post correction —2026-10-24

Root approved diagnosis ea34bbd9406a84c552aecfa70e5c8b2351cf6d7c509e5c52f49a0c4834d777d9.
One writer owns only this plan/iteration and the original tool/test. Reused
ordinary worktree was clean; old b3 branch retained. New branch
codex/205-prepost-evidence starts at fetched mergedmain9348b2f664b4595dbdcf77523931880fb2dbe661.
90min window00:20:40–01:50:40SGT. No real SDK/data/host/financial calls.

- [x] First add offline behavioral REDs: authorized first bounded request with
  data facts unknown, genuine post-review later than as-of, unknown coverage
  refusal, timestamp/binding tamper, repeat-intent no-fetch and v1 immutable
  reopen. Capture a genuine synthetic v1 bag before editing for compatibility.
- [x] Implement explicit v2 preauthorization and post-review within this tool.
  Pre: scoped use/account/once/endpoint/asof/window and actual metadata freshness.
  Post: bind actual raw/auth hashes, history access/coverage, field semantics
  and explicit externally reviewed action coverage. UNKNOWN is not approval.
  Capture produces unreviewed raw only; offline freeze requires valid review.
- [x] Preserve v1 strict read-only reopening and original bytes; no new v1
  capture/freeze or mixed-format fallback. Reuse original bounded public client,
  one intent/journal,2pages/200rows/6calls/8MiB. No new framework or dependencies.
- [x] GREEN new and necessary same-file compatibility cases, Ruff/format/diff.
  Independent review at most2rounds, one aggregate correction; remaining round2
  structural failure returns to Planner. Commit exact source/evidence and STOP;
  unique release owner handles future CI/publication. No old48/root/native/UI runs
  as progress substitutes, no newGoal or Phase2 implementation.

Prechecked<=asof<=requested<=received<=reviewed<=frozen; metadata observation
fresh at actual request. Post time is not falsely required to precede asof.
Use PRECISE_UNKNOWN still blocks network; software repair grants no capture.
The prior plan and evidence below are retained history, not new acceptance.

### Current v2 operator contract

1. Before any capture, external review supplies `CaptureAuthorization` v2:
   explicit ALLOW_WITH_SCOPE for US.SPY/1d/private_research; source-use,
   account-metadata and one-capture authorization receipt hashes; login/program/
   quota facts; observed/prechecked/as-of UTC times; exact calendar-window digest;
   localhost endpoint/port and actual SDK/OpenD versions. No history availability,
   feed/units or action coverage is asserted before observing the responses.
   Metadata is at most30min old, as-of at most5min old at data dispatch.
2. Only the designated data owner may use `capture --authorization-json ...
   --as-of ... --port ... --root ... --execute-once` after actual use approval.
   The consumed fsynced intent binds the authorization and locked window.
   Checks run before setup and immediately before every tool transport call;
   session delay cannot reuse the earlier timestamp. Raw `requested_at_utc`
   records the first actual tool dispatch after session setup. Capture returns
   CAPTURED_UNREVIEWED/NOT_REVIEWED only; no automatic freeze or retry.
3. Review actual responses externally. `PostReview` v2 binds canonical raw and
   authorization SHA256s, actual history access, feed/currency/raw-price/session/
   volume/dividend/date semantics, and a nonzero receipt proving explicitly
   reviewed full locked-window/necessary-pay-date action coverage. Empty tables,
   RET_OK and terminal cursors are insufficient. Unknown coverage refuses freeze.
4. Offline `freeze --capture-json ... --authorization-json ... --review-json ...
   --as-of ... --root ...` validates requested<=received<=reviewed<=frozen and
   post-review age<=30min. Preauthorization freshness is evaluated at the recorded
   request, so a genuine later review is allowed. Separate authorization/review
   objects, raw/normalized members and v2 protocol are content-addressed.
   `verify --root ... --digest ...` reopens original bytes, with no financial run.
   Legacy v1 bags reopen strictly under original rules; no new v1 write/downgrade.

### Current correction evidence

Original behavioral RED:3failed/19passed, then22passed; necessary same-file
compatibility86passed. Genuine original v1 bag was generated from the unmodified
merged tool before editing, embedded as compressed JSON bytes in the existing
test file; five immutable-reopen/tamper cases do not manufacture v1 via v2 code.
Independent R1:38passed/48deselected; one Important setup-to-dispatch freshness
gap. Single aggregate batch added four advancing-clock REDs, then4passed:
metadata/as-of expiry stops history with retained CLI intent and no retry;
successful setup records actual first dispatch; expiry after history blocks
actions while retaining its plain response. Final necessary same-file check:
90passed/5upstream warnings. Independent R2: READY,42passed/48deselected,
no remaining Important/Critical findings; one aggregate correction only.
Changed-file Ruff/format and whitespace checks exit0. Tool SHA256
`22a76fc4d16d0877e16584ecd3af497d1091444fa5161d7ce43037580c8ba735`;
tests `2c8ebbed8ce164e70390c1bc8e2024374d32a96292a47d5c54671a9dea9f58bc`.
All logs are in the owned `output/205-prepost-evidence/` directory; synthetic
wire only. The historical Phase1 review rounds below are separate old evidence.
Commit/base/tree/diff and artifact hashes are recorded in the final handoff
manifest in that directory. Source STOP after checkpoint; sole release owner
performs any later exact-head CI. No publication or actual-data acceptance here.

> **For agentic workers:** use superpowers:executing-plans inline, with one
> independent bounded verifier at the Phase1 boundary. No additional implementer.

**Goal:** first freeze one qualified, recent US.SPY daily sample without invoking
financial arithmetic; only after actual sample acceptance, complete the approved
new job/report/Reject-or-Watch/cold-reopen loop in ResearchJobs.

**Tracking:** [issue205](https://github.com/ZP151/quantmesh/issues/205).

**Architecture:** reuse the existing public Moomoo provider/client, pinned
CalendarService and ObjectStore. A single opt-in operator tool bounds all reads
and freezes original and normalized bytes. Phase2 reuses existing SMA100 arithmetic
and local persistence; no generic queue, plans subsystem or baseline-schema change.

**Tech Stack:** existing Python, pytest, exchange-calendars4.13.2, Pydantic,
ObjectStore and public Moomoo client/provider. No dependencies installed.

**Spec:** the human approved
`output/0038-realdata-workstation-product/P-NEW-LOOP-20261020/MINIMAL-DELIVERY-20261022.md`
SHA256 `d677e47e40909279bfaec2e5aaaa88e071adc09feb8efeef887cb0f1a83791b2`
and Quant `MINIMAL-REALDATA-OPTION-20261022.md` SHA256
`3f14ee7cda9ef10899b38d777b96bd8d74b0c8153249d08369990596ab83aa9f`.
Both originals and the direct human approval are retained in the canonical
research-integration worktree. The user chose implementation here and necessary
independent agent verification; do not request another design/plan confirmation.

## Global constraints and ownership

- Base aa62faeddd84c31887e43bf0dae532e649a4ecbe, independent managed worktree,
  branch codex/0038-historical-development-replay. Preserve old P3 and local main.
- Phase1 owns only `tools/research/freeze_opend_spy_daily.py`,
  `tests/test_freeze_opend_spy_daily.py` and this plan/own iteration.
- One US.SPY/USD/1d,100 warmup+21 observed completed regular sessions; fixed
  as-of before capture; no calendar-day substitution, filling gaps or shifting
  windows after seeing outcomes. Use session close plus30-minute source grace.
- Raw prices, max2 history pages/200 rows, explicit finite dates and bounded action
  payloads. No subscribe, order, relogin, secret read, SSH, SDK/collector change.
- Source-use/account/quota and field review are external prerequisites. A receipt
  binds their evidence; the tool cannot turn operator assertions into legal proof.
  Actual capture is executed once only by the designated OpenD data owner.
- Freeze original/source/normalizer/runtime/engine/setup hashes before any numeric
  evaluation. This tool never imports/calls the old engine or experiment CLI.
- No economic/OOS/Paper qualification from this development sample. No dependency
  installation, old full-suite rerun, CI/merge or generated SPA work in Phase1.
- Keep targeted RED/GREEN, exact commands and failures in output/0038-spy-replay.
  At most two review rounds; third structural issue returns to Planner.

## Review focus

1. A US session still open, or a half-day close, must use actual calendar closes.
2. A terminal cursor is not calendar completeness; duplicated/out-of-range rows
   or more than two pages must refuse without fetching an unbounded third page.
3. Missing pay dates cannot become ex-date cash; unmatched/ambiguous units,
   multi-component dividends or unsupported splits must stop, not be guessed.
4. Reopening/failure must preserve original bytes, and no failed validation may
   publish a qualified freeze. Real provider payloads must match documented fields.
5. Gate failure must precede every market-data method; no credentials/raw errors
   or prototype synthetic evidence may be described as actual qualified data.

## Task1 — fixed window and bounded source validation

- [x] Write tests for as-of2026-10-21T16:00Z → last completed2026-10-20,
  warmup2026-04-29..09-21 and score09-22..10-20, plus half-day/weekend/grace cases.
- [x] Run `python -m pytest -q tests/test_freeze_opend_spy_daily.py`; distinguish
  initial missing-module collection failure from subsequent behavioral RED.
- [x] Implement only calendar/window and validation seams, then observe behavioral
  RED for malformed/duplicate/missing/unfinished/raw-vs-adjusted/hostile inputs.
- [x] Implement typed scope gates, strict normalized bars/events and bounded public
  provider adapter. Use wire-only fakes below the actual client/provider boundary.
- [x] GREEN the same targeted file. Inspect actual returned data and refusals,
  no test-only production callbacks or assertions on source text.

## Task2 — immutable freeze and executable operator handoff

- [x] Write failing tests for original/member hashes, persisted reopen, source
  binding, no-clobber failure and qualification refusal before any data method.
- [x] Add the minimal offline freeze/verify CLI and externally gated capture entry.
  Preserve raw pages/actions, calendar and exact normalized CSV/distributions,
  engine identity and fixed cost/benchmark protocol in ObjectStore.
- [x] GREEN the file and changed-file Ruff/format/whitespace checks. CLI --help and
  offline tiny fixture smoke prove assembly without real OpenD or financial calls.
- [x] Independent verifier reads only the two files and evidence; root separately
  performs a fresh targeted run. One aggregate correction batch at most.
  Round1 found3Important;8new RED/40prior PASS; final round2 READY with48PASS,
  then parent fresh48PASS. No remaining Important/Critical and no third round.
- [x] Commit the tested Phase1 checkpoint with actual tracking issue before PR;
  no CI/merge/deploy action. Update iteration/progress with source/runtime hashes
  and distinguish engineering tool readiness from actual data acceptance.

## Actual Phase1 acceptance and Phase2 boundary

- [ ] Consume external actual use/account/quota/field evidence; otherwise stop live
  capture only, retaining tested tool deliverable and concrete missing fact.
- [ ] Designated OpenD owner captures exactly the frozen121-session target once.
  Verify all raw/normalized/calendars/events and original byte references; actual
  returned fields/versions may refuse. No retries through different hosts/keys.
- [ ] Phase1 PASS requires genuine qualified input and final freeze with zero
  financial evaluation, not a wire fixture or a paper source-review report.
- [ ] Only after that PASS, report receipt and Phase2 precise source ownership to
  root, then execute the already approved seven-file narrow backend/UI boundary
  and five targeted tests from the approved design. Do not build a BLOCKED platform.
- [ ] Phase2 actual acceptance is one new UI submit→original report→bound Reject/
  Watch→same-key replay→owned cold restart→same ID/original bytes, with no second
  numerical run. Historical/development/INSUFFICIENT and Paper refusal stay visible.

## Plan self-review / ruling

The public provider's default history caps are too wide, so the tool wraps only
its injected client with explicit max2pages/max200rows before public provider
fetch_raw_bundle. No SDK source or AAPL/NVDA collector gate is changed.
The source grace is30minutes and belongs in the frozen request, not a claim of
historical PIT availability. Quant v1's `backtest` typo is corrected to the actual
`run_cashbook` callable. No protocol mismatch is silently bridged. Phase1 reviews
and checks remain targeted under the explicit human/root scope rather than the
skills' generic full-suite/install/reapproval defaults.
