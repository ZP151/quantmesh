# Guarded local paper controls â€” P3 implementation checklist

**Goal:** Deliver the operator-approved existing manual paper pause/preflight/
resume loop with current evidence and durable receipts.

**Approved design:** exact question SHA256
`d1bb86051f6be6bd4092e7467a2ca69dfa751797b1c17c8ce0fef13357d24717`;
bound original human reply is retained locally. Scope and five-role record:
`docs/iterations/0038-paper-controls-p3.md`.

**Architecture:** Reuse PaperAccountStore/File, existing journal recovery and
PaperAccount risk/matching. One synthetic-mode service coordinates their current
state and atomic audit discipline; one router and dedicated panel extend the
existing kill-switch page. No scheduler, strategy engine or live interface.

## Constraints and ownership

One source writer; parent handles docs/env and final generation/acceptance only
after that writer stops. Initially stacked on frozen/unmerged PR195/4708397.
No App/nav/messages, DataReadiness/local copy/tests/CSS, P1/P2 mutation, new
dependency/provider/broker/model/paid resource, real OOS or deployment. Paper
rehearsal thresholds are explicitly synthetic, never a real investment budget.

New files: `src/quantmesh/ops/paper_controls.py`,
`src/quantmesh/api/paper_controls.py`, `tests/test_paper_controls.py`,
`tests/test_paper_controls_api.py`, `frontend/src/screens/PaperControlPanel.tsx`
and its test, `frontend/src/lib/paper-controls-api.ts` and its test,
`frontend/src/lib/paper-controls-copy.ts`.
Bounded hooks: `src/quantmesh/api/workstation.py`,
`src/quantmesh/demo/runtime.py`, `src/quantmesh/execution/account_store.py`,
`frontend/src/screens/Ops.tsx`.

Necessary existing-entry closure discovered during implementation: also bound
`frontend/src/components/shell/CommandPalette.tsx` and new dedicated
`CommandPalette.paper-controls.test.tsx` to that same writer. The palette must
offer navigation to verified controls and hide reset until a503 confirms opt-out;
loading/error cannot advertise an unchecked legacy disarm shortcut. No App/nav/
messages or other UIowner scope is added. Main was notified at this boundary.

Interfaces: the existing PaperAccountStore transaction boundary accepts an
optional validation callback (unset by default); the control service reuses it
for pre-match evidence validation and serialized control decisions. Router
`/api/paper-controls` exposes status, preflight, pause/resume and fixed evidence
downloads. The new panel consumes the same validated DTO and embeds in existing
KillSwitchScreen. All15files remain under one writer to preserve that contract.

Round1 correction adds only the existing `src/quantmesh/instruments/proposals.py`
optional default-unset fresh-submit guard, bound only in P3 after historical
replay under the account transaction. Total16sourcefiles. It prevents paused
proposal rejection persistence without changing legacy behavior. The other
bounded corrections remove the unconditional Ops disarm promise and ensure
blocked evidence overrides an allowed headline using local P3 copy. One fix
batch, begun after verified UI189 STOP/window release and notice to main, then
targeted round2 only.

## Review focus

- Old JSON/HTML/global/venue controls or demo reset must not bypass verification.
- Audit/account publication failures cannot claim successful resume or admit a
  fill; restart remains paused without overwriting corrupt evidence.
- Same request replay after a later pause returns its original receipt plus
  current state, never reapplies the old resume.
- Evidence changes between preflight and confirmation must be rechecked under
  the same account authority lock, including alternate proposal-order paths.
- Synthetic scope, current state/reason and allowed next action must be clear
  on ordinary375px views, with locally contained audit identifiers/downloads.

## Task1 â€” one bounded API-to-page control slice

- [x] Read approved contract, existing account persistence/recovery, kernel,
  demo request/reset serialization and both current kill-switch entry points.
- [x] Write tiny synthetic service/API tests; run `python -m pytest
  tests/test_paper_controls.py tests/test_paper_controls_api.py -q` with unique
  owned `--basetemp`; expected meaningful missing-behavior RED preserved in output.
- [x] Implement demo-only CLI opt-in, explicit three-cap configuration, startup
  pause, same-lock evidence/version checks, second-writer refusal and bounded
  durable intent/outcome/first receipts. Missing caps block resume; cold corrupt
  account may retain the existing fail-closed startup refusal, without repair.
- [x] Verify fresh paused orders have no new fill/journal/account effect;
  malformed/missing/corrupt/stale evidence, changed-key payload, old-resume replay,
  publication fault injection, both old controls and both resets fail closed.
- [x] Repeat the service/API command plus affected `tests/test_account_store.py`;
  expected GREEN with default-unset semantics preserved.
- [x] Write dedicated UI/API tests for unavailable fallback, busy/errors,
  evidence gaps, stale refusal, explicit confirmation, current vs original replay
  receipt and downloads; run the two dedicated Vitest files for expected RED.
- [x] Implement the local-copy panel on the current Ops route; repeat focused
  UI/API plus affected existing controls tests for expected GREEN. Run app/node
  TypeScript and changed-file Ruff/format/lint; expected exit0.
- [x] STOP source writing. Deliver exact files, command exits/counts, meaningful
  RED/GREEN, source hashes, intermediate failures and limitations. No generation,
  package build, commit/push/CI or further agents by the writer.

## Task2 â€” parent integration, actual loop and delivery

- [x] Verify writer stopped and bounded diff; reconcile only an actual verified
  upstream merge normally, preserving frozen PR195 and other owners' source.
- [x] Generate API client and packaged bundle with existing runtime after checking
  the builder's fixed absolute deletion target is inside this owned worktree.
- [x] Fresh focused backend/frontend integration, TypeScript/build/API currency,
  changed-file lint/format and `git diff --check`; preserve exact evidence.
- [x] On another owned loopback port/root, actual page proves missing-cap state,
  pause/fresh kernel refusal, stale-context resume refusal, valid human-confirmed
  resume, compatible small paper order, duplicate receipt and cold paused reopen.
- [x] Verify downloaded audit/receipts and no extra account/journal/fill effects;
  capture readable desktop/375px ordinary screenshots, preserving source binding.
- [x] Independent whole-slice review, at most two rounds and one bounded fix
  batch. Record every ruling, remaining limit and role result in the iteration.
- [x] Commit/push coherent green checkpoint and draft PR for issue196, attach PR,
  report exact head/evidence to main. Future P3 merge is a separate authority.
- [x] Evaluate full P1â†’P2â†’P3 objective using actual delivered evidence; do not
  relabel synthetic engineering success as strategy or production qualification.
