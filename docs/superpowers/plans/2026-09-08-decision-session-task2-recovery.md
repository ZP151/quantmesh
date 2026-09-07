# Decision Session Task 2 Recovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:subagent-driven-development` to implement this plan task by
> task. Each task uses RED → GREEN → REFACTOR, one fresh bounded implementer,
> one fresh scoped reviewer, and at most two review rounds.

**Goal:** Close only the two load-bearing Task 2 review findings, prove the
real durable/API/UI boundaries independently, and restore the parent frontier
at Task 3.

**Architecture:** The existing session command remains the only product path.
Recovery first gives `DecisionWatchStore` one read-only whole-ledger validation
operation and makes session refresh call it before deriving an empty result.
Separate proof tasks then exercise the unchanged coordinator through real
stores, HTTP/current app state and the existing Watchlist control.

**Tech Stack:** Python 3.12, Pydantic, FastAPI/TestClient, JSONL stores,
React 19, TanStack Query, Vitest and Testing Library.

**Spec:**
`docs/superpowers/specs/2026-09-07-decision-readiness-session-design.md`

**Parent plan:**
`docs/superpowers/plans/2026-09-08-decision-readiness-session.md`

**Recovery base:** `bafec720e10bced3d9545cb4ef7f7789e56e9dae`

## Global Constraints

- Preserve `POST /api/decision-session/refresh` as a same-origin, no-input,
  explicit command over server-owned local facts.
- `DecisionWatchService.check()` remains the only writer. Validation, Inbox
  snapshot and UI projection remain read-only.
- Do not create registrations, polling, localStorage state, Provider/OpenD or
  Scheduler calls, trusted-data/evidence writes, proposals, confirmations,
  orders, paper/live trades, external notifications or 0021 changes.
- Use only the already approved NVDA/AAPL fixtures. Do not add symbols,
  algorithms, models or adjacent refactors.
- Targeted checks run per task. Run the coherent recovery selection once in
  Task 4, never after each micro-edit. The final repository release gate stays
  owned by parent Task 5.
- The original Task 2 patch loop is closed at review round 2/2. These smaller
  tasks have independent review budgets because each can be accepted or
  rejected without changing another task's files or outcome.

---

### Task 1: Fail-closed decision-watch ledger replay

**User-visible invariant:** Refresh never reports an empty healthy session when
any registration, activation or evaluation ledger cannot be replayed.

**Files:**

- Modify: `src/quantmesh/instruments/monitoring.py`
- Modify: `src/quantmesh/instruments/session.py`
- Modify: `tests/test_decision_session.py`
- Modify: `tests/test_packet_monitoring.py`
- Modify: `docs/iterations/0029-decision-readiness-session.md`
- Modify: `docs/goals/ACTIVE.md`

**Interfaces:**

- Consumes: `DecisionWatchStore.registrations()`, the activation records
  folded into registrations, persisted `DecisionWatchEvaluation` records and
  `_validate_evaluation_chain()`.
- Produces:

```python
class DecisionWatchStore:
    def validate_replay(self) -> None: ...

class DecisionWatchService:
    def validate_replay(self) -> None: ...
```

- [ ] **Step 1: Write the ledger RED tests**

Create a real `DecisionWatchStore` under `tmp_path`, write malformed JSON to
each of `watch-registrations.jsonl`, `watch-activations.jsonl` and
`watch-evaluations.jsonl` in separate parameterized cases, and assert
`validate_replay()` raises the store's existing sanitized `ValueError` family.
Add a semantic orphan-evaluation case and assert it fails instead of being
ignored. In `test_decision_session.py`, use an empty Inbox plus the real store
with corrupt evaluation bytes and assert `DecisionSessionError` and zero
workspace renders/check writes.

- [ ] **Step 2: Run RED**

```powershell
$env:PYTHONPATH = (Resolve-Path .\src).Path
& 'C:\Users\15492\Develop\QuantMesh\.venv\Scripts\python.exe' -m pytest `
  tests/test_packet_monitoring.py -k validate_replay `
  tests/test_decision_session.py -k corrupt_evaluation -q `
  --basetemp "$env:TEMP\quantmesh-0029-task2-recovery-ledger-red"
```

Expected: failure because `validate_replay()` is absent and the session path
does not read the evaluation ledger for an empty Inbox.

- [ ] **Step 3: Implement one read-only closure validator**

Read registrations, activations and raw evaluations once under the existing
store transaction/lock. Reject duplicate registrations, evaluations referring
to no known registration, invalid canonical identities and invalid per-
registration chronology/cursor chains. Validate activation evaluations in the
same chain as ordinary evaluations. Append nothing and return `None`.

Delegate from `DecisionWatchService.validate_replay()` and replace the direct
`watches.store.registrations()` call in `DecisionSessionService.refresh()` with
the service method. Translate replay failure through the existing
`DecisionSessionError`; do not add a new HTTP contract.

- [ ] **Step 4: Run GREEN and static checks**

Run the exact RED selection again, then scoped Ruff, format check and
`git diff --check`. Record counts, duration and exit codes.

- [ ] **Step 5: Commit and review**

Commit only Task 1 files with:

```text
fix(decisions): validate the watch ledger closure
```

Stop after a fresh Standards+Spec review finds no Critical/Important issue, or
after review round 2/2. Do not start Task 2 if this invariant is not approved.

---

### Task 2: Real durable coordinator and HTTP proof

**User-visible invariant:** One explicit refresh produces canonical persisted
evaluations, survives service/app reconstruction, and refuses malformed local
state without exposing raw errors.

**Files:**

- Modify: `tests/test_decision_session.py`
- Modify: `tests/test_packet_monitoring.py`
- Modify only if a RED test exposes an in-scope defect:
  `src/quantmesh/instruments/session.py`
- Modify only if a RED test exposes an in-scope defect:
  `src/quantmesh/instruments/api.py`
- Modify only if a RED test exposes an in-scope defect:
  `src/quantmesh/api/workstation.py`
- Modify: `docs/iterations/0029-decision-readiness-session.md`
- Modify: `docs/goals/ACTIVE.md`

**Interfaces:**

- Consumes: real `DecisionPacketStore`, `DecisionWatchStore`,
  `DecisionWatchService`, `DecisionSessionService`,
  `create_workstation_app()` and the existing refresh route.
- Produces: load-bearing integration proof only; no new product interface.

- [ ] **Step 1: Add real-store coordinator proof**

Seed an action packet and registration using the real stores. Drive the
coordinator with a renderer returning deterministic server-owned workspace
facts. Assert the response `evaluation_id` equals the canonical ID stored by
`DecisionWatchStore`; repeated byte-equivalent observation returns the same ID
and does not append; a strictly newer sequence advances the durable cursor and
creates the expected new ID after service reconstruction. Assert a stale-only
workspace with no quote persists a valid evaluation, mixed missing packet plus
success returns `partial`, and no new registration appears.

Add invalid initial clock and backwards completion clock cases. Each assertion
must name the production mutation it would catch. Coverage that is already
correct may start GREEN; do not manufacture a defect.

- [ ] **Step 2: Add route/current-state proof**

Using `TestClient(create_workstation_app(...))`, assert:

1. the OpenAPI operation has no `requestBody` and a bodyless same-origin POST
   returns the typed result;
2. a foreign `Origin` is rejected before any evaluation write;
3. replacing the app-state packet/watch/workspace services (the same mechanism
   used after demo reset) makes the existing `decision_session` lambdas use the
   replacements rather than stale construction-time objects;
4. malformed evaluation-ledger bytes return sanitized HTTP 409 without the raw
   injected text and append no evaluation;
5. an unattached service remains 404.

Where practical, include one actual demo reset request and assert the next
refresh reads the reset app-state services. Do not make Provider/network calls.

- [ ] **Step 3: Run the focused backend proof**

```powershell
$env:PYTHONPATH = (Resolve-Path .\src).Path
& 'C:\Users\15492\Develop\QuantMesh\.venv\Scripts\python.exe' -m pytest `
  tests/test_decision_session.py tests/test_packet_monitoring.py -q `
  --basetemp "$env:TEMP\quantmesh-0029-task2-recovery-real"
& 'C:\Users\15492\Develop\QuantMesh\.venv\Scripts\ruff.exe' check `
  tests/test_decision_session.py tests/test_packet_monitoring.py `
  src/quantmesh/instruments/session.py src/quantmesh/instruments/api.py `
  src/quantmesh/api/workstation.py
git diff --check
```

- [ ] **Step 4: Commit and review**

Commit with:

```text
test(decisions): prove durable session refresh
```

If an in-scope production correction was required, use
`fix(decisions): preserve durable session refresh` instead. Stop after a fresh
Standards+Spec review finds no Critical/Important issue, or round 2/2.

---

### Task 3: Explicit refresh interaction proof

**User-visible invariant:** The existing control is keyboard operable, disabled
while pending, and explains complete, partial, empty and failed outcomes in
English and Simplified Chinese without starting automatic work.

**Files:**

- Modify: `frontend/src/screens/Watchlist.test.tsx`
- Modify only if a RED assertion exposes an in-scope defect:
  `frontend/src/screens/Watchlist.tsx`
- Modify only if copy is missing: `frontend/src/lib/messages.ts`
- Modify: `docs/iterations/0029-decision-readiness-session.md`
- Modify: `docs/goals/ACTIVE.md`

**Interfaces:**

- Consumes: existing `api.refreshDecisionSession`, one TanStack mutation and
  `['decision-inbox']` invalidation.
- Produces: component behavior proof only; no new UI control or state store.

- [ ] **Step 1: Add deferred-mutation and bilingual table tests**

Use a manually controlled Promise. Focus the `Refresh session` button, trigger
it with Enter, assert one API call, retained focus and `disabled` while pending,
resolve it, and assert exactly one Inbox invalidation/refetch. Table-test
`complete`, `partial`, `no_registered_watches` and rejected request output for
`en-US` and `zh-CN`. Partial output must include exact failed packet ID, known
localized reason and sanitized server fallback in `title`.

Assert no timer text, interval call, second automatic request, registration
request or localStorage refresh payload occurs. Observe RED only for genuine
missing behavior; coverage-only cases may pass with a named mutation rationale.

- [ ] **Step 2: Make only test-required corrections**

Keep the current compact control and transient feedback. Do not add cards,
dialogs, polling, persistence, row actions or new navigation. If rejected
requests currently lack safe feedback, map the existing sanitized API error to
one localized transient line without exposing raw response bodies.

- [ ] **Step 3: Verify frontend and commit**

```powershell
Push-Location frontend
npx vitest run src/screens/Watchlist.test.tsx src/lib/messages.test.ts
npm run typecheck
npm run lint
Pop-Location
git diff --check
```

Run the existing Impeccable detector once only if production TSX/CSS changes;
test-only changes do not need a detector rerun. Commit with:

```text
test(decisions): prove explicit refresh states
```

Use `fix(decisions): preserve explicit refresh states` if production UI/copy
changes. Stop after one fresh Standards+Spec review has no Critical/Important
issue, or round 2/2.

---

### Task 3B: Post-success scheduler proof

**User-visible invariant:** Automatic refresh cannot start in a success effect
after terminal feedback appears.

**Files:**

- Modify: `frontend/src/screens/Watchlist.test.tsx`
- Modify: `docs/iterations/0029-decision-readiness-session.md`
- Modify: `docs/goals/ACTIVE.md`

**Interfaces:**

- Consumes: the existing deferred-Promise test and its pre-mount interval,
  storage, monitoring and refresh spies.
- Produces: one lifecycle-closed negative proof; no production interface.

- [ ] **Step 1: Write the post-success assertion**

After resolving the mutation, await terminal success feedback and flush the
committed React effects. Then repeat the zero assertions for `setInterval`,
`api.checkPacketMonitoring`, non-preference localStorage writes and automatic
`api.refreshDecisionSession` calls. Keep exact one-call Inbox invalidation and
refetch assertions.

- [ ] **Step 2: Prove the named mutation RED**

Temporarily add a `useEffect([refresh.isSuccess])` that schedules
`setInterval(api.refreshDecisionSession, 60_000)` after success. Run only the
named keyboard/pending test and require it to fail at the new post-success
scheduler assertion. Restore production exactly; do not retain the mutation.

- [ ] **Step 3: Verify, commit and review**

Run focused Watchlist/messages Vitest, typecheck, lint and `git diff --check`.
Commit only test/docs with:

```text
test(decisions): close refresh scheduler proof
```

One fresh Standards+Spec reviewer must reproduce or inspect the mutation and
find no Critical/Important issue. Stop at round 2/2; do not begin Task 4 before
approval.

---

### Task 4: Recovery integration and parent-frontier decision

**Files:**

- Modify: `docs/iterations/0029-decision-readiness-session.md`
- Modify: `docs/goals/ACTIVE.md`
- Modify: `.superpowers/sdd/2026-09-08-decision-readiness-session/progress.md`

- [ ] **Step 1: Run one coherent recovery gate**

On the exact recovery HEAD, once only, with a retained session handle:

```powershell
$env:PYTHONPATH = (Resolve-Path .\src).Path
& 'C:\Users\15492\Develop\QuantMesh\.venv\Scripts\python.exe' -m pytest `
  tests/test_decision_session.py tests/test_packet_monitoring.py `
  tests/test_decision_inbox.py -q `
  --basetemp "$env:TEMP\quantmesh-0029-task2-recovery-integration"
```

Then run scoped Ruff/format/diff, OpenAPI generation/freshness, Watchlist plus
messages Vitest, typecheck and lint. Record exact counts, duration, warnings,
exit codes and HEAD. Do not run the repository release gate.

- [ ] **Step 2: Whole-recovery review**

A fresh Reviewer reads this plan, both parent Task 2 reviews and the complete
recovery diff. It may inspect but must not repeat the coherent gate. It returns
`SAFE TO RESUME PARENT TASK 3` only when all durable/API/UI proof and
fail-closed requirements are satisfied with no Critical/Important finding.

- [ ] **Step 3: Close or freeze**

If safe, mark parent Task 2 complete, set parent Task 3 BASE to the reviewed
HEAD, update Issue #131 and delete only this recovery's ignored SDD workspace
after its evidence is mirrored into the parent ledger. Otherwise keep Task 3
frozen and report the exact residual finding; do not begin a third recovery
review loop.
