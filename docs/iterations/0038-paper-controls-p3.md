# Iteration0038 — guarded local paper controls, P3

Issue: [196](https://github.com/ZP151/quantmesh/issues/196).
Date: 2026-10-20. Status: actual loop verified; round2 READY; draft delivery pending.
Plan: `docs/superpowers/plans/2026-10-20-paper-controls-p3.md`.

## Planner

One user loop: in the existing kill-switch page, inspect synthetic paper state
and pause reason, pause fresh order acceptance, inspect resume evidence, then
explicitly confirm resume of that unchanged state with an audit receipt.
Success is an actual local pause/refusal/resume/dedup/cold-reopen loop with no
new fill while paused and readable desktop/375px evidence.

The operator explicitly approved the unique already-presented P3 short design
through main: “批准P3这份短设计，直接在产品会话继续实现和验收。” The exact
question SHA256 is
`d1bb86051f6be6bd4092e7467a2ca69dfa751797b1c17c8ce0fef13357d24717`.
Original question/reply/source are retained in P3-APPROVAL-CONSUMED.json.
That reply also conditionally authorizes PR195's normal merge after CI/security;
the release owner owns that action. It does not approve a future P3 source merge.

The branch initially stacks on PR195 head
`47083979d28981aa90a87235ad7a57c5a3090107`, which is unmerged at slice start.
P1/P2 source, raw artifacts and previews remain separate. Normal later dependency
reconciliation must preserve their routes/assets without force/reset.

Dependency update: consumed the release owner's existing PR195 postmerge receipt.
Its approved4708397head was squashed to dddc678; requiredCI39275587067 passed.
P3 normally merged that actual main in770341f without conflict, retaining the
independent PR194 server files. No repeated GH/CI/merge action or deployment.
P3 ADR is0033 because upstream PR194 already used0032.

## Quant researcher

This is a synthetic execution-control exercise. Explicit rehearsal risk caps are
not a real investment utility/risk budget. Existing fee/spread/slippage and paper
kernel semantics remain visible and effective. Evidence/version checks establish
current local consistency, not historical PIT, trading entitlement, strategy skill
or economic validity. No real market, broker or model is connected.

The historical SMA100/SPY verdict remains REJECT, formal R1/R2 INSUFFICIENT,
R3 NOT_AUTHORIZED; its OOS stays consumed. No strategy scheduler, replay of that
experiment or promotion is added. Source hashes never become order authority.

## Implementer

One writer owns the new control service/router, dedicated panel/API/copy/tests
and bounded hooks in workstation.py, demo/runtime.py, account_store.py and
Ops.tsx. Parent owns docs/env/evidence and generated resources after writer stop.
No App/nav/messages or UIowner DataReadiness/local copy/tests/CSS changes.

Bounded discovery: the existing CommandPalette advertises legacy disarm and demo
reset outside Ops. Its component and one dedicated test join the same sole-writer
boundary. In configured/loading/error states the command navigates to the guarded
existing page and reset is hidden; only verified503 retains old actions. Main was
notified before writing. No new screen, authority or additional source writer.

The account-store hook is an optional synthetic-mode transaction validator;
default/live behavior stays unset. This closes the pre-request/TOCTOU gap before
matching or journal writes, including existing proposal submission. Control
operations verify under the same account lock. One control/account writer lease,
durable intent/outcome audit and startup pause bound failures conservatively.

CLI opt-in requires demo mode and an audit root outside resettable demo storage.
Three explicit positive finite rehearsal caps are configured together or absent;
absent caps block resume. Legacy JSON/HTML disarm cannot bypass preflight. Reset
is refused in opted-in mode rather than implementing a new reset migration.

Ruling: an already corrupt account at cold construction may retain the existing
seeder's startup refusal. Do not invent/repair an account to render a blocked UI.
Valid cold state must reopen paused; corruption detected after attachment must
block execution before matching. Cost of this bound: no cold repair UI is offered.

## Reviewer

Round1 at actual missing-cap/startup/manual-pause boundary: NOT_READY, three
Important findings: alternate fresh paused proposal persists rejected journal/
account; guarded Ops description still promises unconditional disarm; blocked
evidence after resume can retain an allowed headline. Static source tracing
confirmed all three. One aggregate fix batch is prepared with exact tests and a
necessary optional default-unset fresh-submit hook in existing proposals.py,
bound only in explicit P3 under the same account lock after historical replay.
Default proposal rejection semantics remain intact. Parent corrected the minor
ADR0033 link. Consumed UI189's actual STOP (140096686) and notified main before
dispatch; the existing sole writer now owns this aggregate batch. Round2 is
limited to this batch and final actual
evidence; no third structural patch cycle. Review report:
`output/0038-paper-controls-p3/review-round1.md`.
No source merge or comprehensive release authorization is implied by that review.

Round2 final: READY, no remaining material finding. The same independent reviewer
checked only the sole correction batch and final actual receipts/desktop/three
phone/cold images, independently rehashed28source/generated files and original
audit/receipt/cold copies, and confirmed the expected one-fill and no-effect
replay behavior. Report: `output/0038-paper-controls-p3/review-round2.md`.
No third review or further product patch cycle was used.

The sole batch writer STOP is recorded in
`implementer/review-fix-deliverable.json` (SHA256
`dbaff5446b62605afdaa008de7616321836296fcf9afc757a073cb37b19c44ca`).
Nine changed-file hashes bind the optional fresh-submit hook and local UI fixes.
Meaningful proposal RED3→GREEN6; UI regression sensitivity RED7→GREEN29. The first
UI RED invocation overlapped slow transformation and is retained but not claimed
as chronological behavior RED. The deterministic prior-behavior substitution was
restored before final checks, explicitly recorded in the receipt. Final writer
backend72/frontend29/TypeScript/Ruff/format/lint/whitespace exited0. Parent now
owns fresh checks/build/actual acceptance; no source writer remains active.

## Verifier

Writer checkpoint:66backend tests passed with99deselected and21frontend tests
across4files passed. TypeScript, seven-file Ruff/format, eight-file frontend lint
and whitespace checks exited0. Source stopped with all15raw file hashes in
`output/0038-paper-controls-p3/implementer/deliverable.json` (SHA256
`0755e709dd2556673455e99f2e4025963fca5d01a4d8d3908353691664a6d263`).

Meaningful behavioral RED includes6API bypass/binding cases,3palette cases and
the generic503 unsafe fallback. Initial missing modules are collection RED,
not behavioral failures. All intermediate logs are retained. The writer reduced
runtime wrapping to a bounded lease-cleanup hook without reformatting assembly.

Pending fresh parent integration, actual page/kernel actions, original
audit/receipt downloads and desktop/phone evidence. No old full,
native,436frontend, old CI or consumed-OOS rerun. Existing dependency copies are
physical independent folders; no installation or upgrade is authorized.

### Final corrected-source verification and actual loop

Parent fresh verification:91backend tests (new control/API, affected account store
and proposal module),29frontend tests across4files, API currency, eight-file Ruff/
format, production bundle build and whitespace checks passed. Exact commands/
exits: `parent/review-fix-parent-checks.json`. Existing legacy kill-switch7cases
also passed at the initial integration boundary. No old full/native/436frontend
or consumed-OOS run was used as this slice's gate.

`parent/actual-acceptance-final.json` records ACTUAL_USER_LOOP_PASS. The final
16writer files plus generated API/static assets (28files) still match
`parent/acceptance-source-binding-reviewed.json`; actual HTTP index/JS/CSS equal
packaged bytes (`served-assets-final.json`). Bundle index-D4JNHYF8.js SHA256:
`8e3acb181ec6a386c143a462741d06c0f1d513d9a25ffd2b5665f918e084cecd`.

On retained owned port8868 roots, the actual final page/API/kernel proved:

- Missing configured caps keep pause+block and resume409, with unchanged account/
  journal bytes. The guarded page no longer promises unconditional disarm.
- A fresh paused demo order409 has no account/journal effect. Tiny proposal tests
  independently cover global/venue pause, evidence/fault and historical replay.
- A displayed preflight followed by another pause causes actual UI stale409 and
  invalidates confirmation; no new transition/account/journal effect follows.
- Refresh, fresh check, reason and explicit confirmation resume the current state;
  the shared header immediately agrees with the panel's disengaged global stop.
- Existing Order UI submits0.01synthetic AAPL, producing exactly one fill/order/
  journal/sequence increment. Same UI request key replays unchanged bytes. Fill
  price210.82, notional2.1082, native modeled fee0.002108, cash decrease2.110308.
- A later UI pause remains active when the old successful resume is replayed;
  it returns the original receipt with current paused state and no new effects.
- Actual browser audit/receipt downloads equal originals; SHA256 headers agree.
  Cold process restart50368 reopens paused, preserves account/journal bytes and
  first receipt bytes, and retains the audit's exact prefix. Cold UI redownload
  of the old receipt is byte-identical.

Ordinary desktop and three mobile views are saved, plus cold startup views.
Mobile CSS375x780/body and document scroll360 show no horizontal overflow. Native
unedited screenshot pixels are360x749; JPEG headers were read without resizing,
cropping or annotation. `screenshot-native-metadata.json` and `mobile-geometry.json`
record this distinction. All three phone views were visually inspected. Browser
console capture is empty; viewport reset to1280x720 and result tab retained.

Parent assembler initially used an unrounded cost formula and failed its own
cash assertion. It now reuses the existing public FeeModel.for_notional's six-
decimal rounding; original helper is preserved and no order/source was rerun.
An optional PIL metadata probe was unavailable; standard-library JPEG header
inspection succeeded without installation or image modification. These are
verifier-helper corrections, not hidden product changes or passing first runs.
All59original research source/copy file hashes remain unchanged.

First actual CLI boundary: ownedPID69600/port8868 failed during assembly, before
listening. Installed FastAPI lacks `app.add_event_handler`; mocked CLI pass-through
tests did not exercise that new attachment line. Original stderr, seeded account
and startup audit are retained under parent evidence. The same sole writer owns
only runtime.py and its API test for this bounded startup correction: reproduce
with real tiny demo assembly, compose the existing lifespan as vn.py attachment
already does, verify shutdown releases leases, then STOP again. No dependency
change, reset or independently repeated review was started. This failure is not
accepted as successful full-loop evidence.

Startup correction: the exact assembly failure was reproduced RED, then the
existing vn.py lifecycle composition pattern preserved prior lifespan and closed
control leases in finally. One real compact assembly test also reopens retained
state paused and retains its first resume receipt. Parent fresh API file:17passed
in `parent/startup-fresh.log`. Only runtime.py and its API test changed; original
failure and first writer receipt remain. Final hashes are separately bound in
`parent/acceptance-source-binding-final.json`. Source writer STOP was explicitly
reported to main to release the shared implementation window.
