# Decision Readiness Slice 1 Recovery Plan

> **Execution:** Use `superpowers:subagent-driven-development` with strict
> RED → GREEN → REFACTOR, one fresh bounded implementer per recovery task,
> one scoped reviewer after each task, and no more than two review rounds per
> task. This plan narrows the failed Slice 1 review; it does not change the
> approved product design.

**Spec:**
`docs/superpowers/specs/2026-09-07-decision-readiness-session-design.md`

**Parent plan:**
`docs/superpowers/plans/2026-09-08-decision-readiness-session.md`

**Recovery base:**
`efa05d8237905085cbd92d963a7b16ffb3fe1d8e`

**Goal:** Close only the four load-bearing Task 1 review findings, prove the
smaller boundaries independently, then restore the parent plan frontier at
Task 2.

## Global constraints

- Preserve the exact-ID-only boundary: readiness may call only
  `lineage(packet-bound manifest_id)` and may never enumerate the catalog,
  inspect another root, choose a latest record, infer an ID, or call a
  Provider/network service.
- Historical packet evidence remains replayable. Do not add a wall-clock age
  threshold; packet evidence freshness and current watch-observation freshness
  are separate.
- Demo remains demo and cannot waive qualification for an advertised real
  forecast.
- The Inbox remains a read-only projection. No new mutable session, Inbox or
  evaluation writer is permitted.
- No refresh route/control, polling, registration creation, proposal/order
  action, Provider/OpenD, Scheduler, automation, trusted-data write, 0021
  repair, outbox/witness change, new symbol, framework/model work or unrelated
  cleanup.
- Use only NVDA, AAPL, BTC and SOL identities in acceptance fixtures.
- Use targeted checks during each recovery task. Run the slow four-file Slice 1
  backend selection exactly once after both recovery tasks, not after each
  micro-edit.

## Recovery Task A — Exact forecast evidence projection

**User-visible invariant:** A failed advertised forecast never appears as
history evidence and never hides an older forecast-generation clock.

**Files:**

- Modify: `src/quantmesh/instruments/readiness.py`
- Modify: `tests/test_decision_readiness.py`
- Modify: `docs/iterations/0029-decision-readiness-session.md`
- Modify: `docs/goals/ACTIVE.md`

**RED:** Add focused tests proving:

1. When an advertised real forecast fails qualification and
   `forecast_generated_at` is older than history generation/evaluation, the
   blocked/unavailable result uses it as `limiting_evidence_at`.
2. For demo history plus a blocked real forecast closure, the returned exact
   evidence reference is in `forecast`; `history` remains `None`.
3. The same field assignment holds for evaluation/checkpoint/rights/trust
   failures, while unavailable/corrupt identity responses expose no fabricated
   reference.

Run the new test selection and observe failures for the current defects.

**GREEN:** Make the smallest readiness-service change that passes the tests.
Compute limiting time from trustworthy packet-bound generation/evaluation
clocks for every status and make qualification evidence placement explicit at
the history/forecast call site. Do not add catalog traversal or freshness
policy.

**Verify:**

```powershell
$env:PYTHONPATH = (Resolve-Path .\src).Path
& 'C:\Users\15492\Develop\QuantMesh\.venv\Scripts\python.exe' -m pytest `
  tests/test_decision_readiness.py -q `
  --basetemp "$env:TEMP\quantmesh-0029-slice1-recovery-a"
& 'C:\Users\15492\Develop\QuantMesh\.venv\Scripts\ruff.exe' check `
  src/quantmesh/instruments/readiness.py tests/test_decision_readiness.py
& 'C:\Users\15492\Develop\QuantMesh\.venv\Scripts\ruff.exe' format --check `
  src/quantmesh/instruments/readiness.py tests/test_decision_readiness.py
git diff --check
```

**Stop condition:** Focused tests prove both clocks and both evidence fields;
one scoped quant/spec review has no open Critical/Important finding. Commit:

```text
fix(decisions): preserve exact forecast evidence
```

## Recovery Task B — Inbox recovery proof and complete known-reason copy

**User-visible invariant:** The reconstructed Inbox presents exact real and
blocked evidence plus the persisted monitoring result truthfully in English
and Simplified Chinese.

**Files:**

- Modify: `tests/test_decision_inbox.py`
- Modify: `frontend/src/screens/Watchlist.tsx`
- Modify: `frontend/src/screens/Watchlist.test.tsx`
- Modify: `frontend/src/lib/messages.ts`
- Modify: `docs/iterations/0029-decision-readiness-session.md`
- Modify: `docs/goals/ACTIVE.md`

**RED:** Add focused behavior tests proving:

1. An exact real packet projects its qualified manifest/evaluation/report and
   session facts through the Inbox.
2. A corrupt/mismatched exact closure becomes sanitized unavailable/blocked
   Inbox output without substituting any catalog record.
3. Snapshot/GET leaves packet, mark, registration and evaluation stores
   byte-equivalent.
4. A reconstructed app produces equal row and `DecisionSessionSummary` facts,
   including persisted `last_checked_at`, `latest_status` and `latest_reason`.
5. Every reachable stable readiness and monitoring reason code has reviewed
   English and zh-CN copy; known localized reasons retain original server text
   in `title`, while an unknown reason remains verbatim.

Observe the current missing assertions/mappings fail before editing the UI.

**GREEN:** Complete only the behavior evidence and known-reason mapping. Prefer
one explicit exhaustive typed map derived from the server's stable codes over
fallback heuristics. Preserve the separator-first one-link row, existing
`dateTime` formatter, wrapping and keyboard behavior. Add no new action.

**Verify:**

```powershell
$env:PYTHONPATH = (Resolve-Path .\src).Path
& 'C:\Users\15492\Develop\QuantMesh\.venv\Scripts\python.exe' -m pytest `
  tests/test_decision_inbox.py -q `
  --basetemp "$env:TEMP\quantmesh-0029-slice1-recovery-b"
Push-Location frontend
npx vitest run src/screens/Watchlist.test.tsx `
  src/screens/NavigationAndValuation.test.tsx src/lib/messages.test.ts
npm run typecheck
npm run lint
Pop-Location
git diff --check
```

Run the Impeccable detector once over the changed UI after it is complete.

**Stop condition:** Focused backend/frontend evidence passes and one scoped
Standards+Spec review has no open Critical/Important finding. Commit:

```text
test(decisions): prove inbox readiness recovery
```

## Slice 1 recovery integration

After both tasks are reviewed, run the parent plan's exact four-file backend
selection once on the recovery head, then the targeted frontend/API/type/lint,
Ruff and diff checks. Record exact counts, duration, warnings and commits in
the tracked iteration and Active Goal. Do not run the full release gate.

When this boundary is green, mark parent Task 1 complete and resume at parent
Task 2. Otherwise stop with the exact residual finding; do not reopen a third
review round or start Task 2.
