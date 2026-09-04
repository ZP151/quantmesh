# Local Packet Monitoring Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:subagent-driven-development` for this one vertical deliverable,
> followed by one combined boundary review (maximum two rounds).

**Goal:** Let an operator save and evaluate packet-bound local conditions in
Instrument Workspace, then reopen the same deterministic conditions and typed
events after restart.

**Architecture:** Add a standalone monitoring domain/store/service under the
decisions root. It reloads one exact persisted packet, derives immutable rules,
and atomically appends evaluations that contain both the observation cursor and
per-condition events. The API supplies a current local workspace observation; the
frontend exposes one compact packet-keyed disclosure. No provider, scheduler,
notification, model, or order surface participates.

**Tech stack:** Python 3.11+, Pydantic v2, FastAPI, `JsonlStore`, versioned
`CalendarService`, React 19, TypeScript 5.9, TanStack Query, Vitest, Playwright,
Ruff.

**Spec:**
`docs/superpowers/specs/2026-09-03-local-packet-monitoring-design.md`

## Global constraints

- Slice 3 only: no outcome/review, external notification, background scheduler,
  Provider/OpenD, real trading, other symbol, model work, 0021 soak, or license
  repair.
- Exact persisted packet only. Never mutate or add packet/proposal/risk/order
  authority and never accept a client packet or price body.
- Preserve full observation lineage and crossing cursor in each atomic evaluation;
  identical replay is idempotent and triggered conditions are terminal.
- Use pinned market calendars and exact same-target p50 comparisons. Never turn a
  missing/uncomparable fact into zero, success, confidence, or probability.
- Follow RED → GREEN → REFACTOR with focused tests. Run broad gates only once after
  the boundary review.
- Preserve the current workspace design and run the Impeccable detector exactly
  once after the Slice 3 UI is complete.

---

### Task 1: Deliver the packet-bound local monitoring loop

**Single deliverable:** On a persisted NVDA packet, one Save & check action stores
one or more fixed conditions, renders typed initial results, supports a later local
check, and reopens identical registration/evaluation/event identity after restart.

**Stop condition:** Deterministic backend/API/component/browser tests prove trigger
and non-trigger replay for all four kinds, including stale evidence, while packet,
proposal, risk, order, Copilot, and external state remain unchanged.

**Primary files:**

- Create: `src/quantmesh/instruments/monitoring.py`
- Create: `tests/test_packet_monitoring.py`
- Create: `frontend/src/screens/instrument/PacketMonitoring.tsx`
- Create: `frontend/src/screens/instrument/PacketMonitoring.test.tsx`
- Modify: `docs/adr/0019-decision-packet-identity-and-authority.md`
- Modify: `src/quantmesh/instruments/api.py`
- Modify: `src/quantmesh/api/workstation.py`
- Modify: `src/quantmesh/instruments/__init__.py`
- Modify: `src/quantmesh/runtime.py`
- Modify as required for reset ownership: `src/quantmesh/demo/seeder.py`,
  `src/quantmesh/demo/runtime.py`
- Modify: `frontend/src/lib/api.ts`, `frontend/src/lib/messages.ts`,
  `frontend/src/screens/InstrumentWorkspace.tsx`
- Generated: `frontend/src/api/client.ts`, packaged SPA assets
- Focused integration: `tests/test_decision_packet_api.py`,
  `tests/test_demo_instrument_workspace.py`, `tests/test_runtime.py`,
  `tests/test_spa_e2e.py`, `frontend/src/screens/InstrumentWorkspace.test.tsx`

#### Step 1: Write domain/store RED tests

- [x] Define strict frozen contracts for condition, registration, price/forecast
  observation, typed condition result, and atomic evaluation.
- [x] Test canonical identities, exact packet reload, fixed kind ordering, one
  registration per packet, duplicate/concurrent convergence, conflict refusal,
  corruption, and restart replay.
- [x] Test entry outside→inside, initial inside, inside→inside, invalidation
  `>=→<`, equality, duplicate/reversed/gapped sequence, pre/as-of/future times,
  and at-most-once trigger behavior.
- [x] Test XNYS weekend, holiday, early close, exact close/threshold boundary and
  24/7 UTC day close with the pinned `CalendarService`.
- [x] Test same-target forecast p50 below/equal/above one-risk-unit threshold,
  missing target, incompatible or future/corrupt candidate, and absence of any
  probability field.
- [x] Snapshot packet/proposal/order files around failures and evaluations.

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_packet_monitoring.py tests/test_decision_packets.py tests/test_market_calendars.py -q
```

Expected initially: FAIL because the monitoring contracts and service do not exist.

#### Step 2: Implement domain/store/service GREEN

- [x] Extend ADR-0019 with monitoring reverse binding, identity, atomic evaluation,
  fixed rule definitions, and no-authority decisions before production code.
- [x] Implement the strict contracts and canonical hash helpers.
- [x] Implement a root-locked, fail-closed store for registrations/evaluations and
  replay validation, using one evaluation record as the price cursor.
- [x] Implement exact packet-derived registration and deterministic evaluation.
- [x] Re-run Step 1 until green and refactor without broadening the API.

#### Step 3: Write API/runtime/demo RED tests and bind the service

- [x] Prove GET is read-only; POST requires same origin, an exact persisted packet,
  and one to four unique fixed kinds.
- [x] Prove the first POST registers/checks, a later identical POST checks again,
  exact observation replay is idempotent, conflicting registration is 409, and
  missing/corrupt packet or monitoring state remains 404/409.
- [x] Build the observation only from the current local workspace and exact local
  forecast registry, retaining live lineage. No arbitrary browser price body and
  no provider call are allowed.
- [x] Bind `DecisionWatchStore` under `decisions/monitoring` for normal/demo stores;
  make demo reset replace it and include its owned files without seeding a trigger.
- [x] Reconstruct an app on the same root and prove byte-identical recovery plus
  unchanged packet/proposal/order/Copilot state.

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_packet_monitoring.py tests/test_decision_packet_api.py tests/test_demo_instrument_workspace.py tests/test_runtime.py -q
```

#### Step 4: Write UI RED tests and implement the compact disclosure

- [x] Fresh packet: localized save-first state and no enabled monitoring action.
- [x] Persisted packet: four keyboard-selectable fixed kinds, disclosed derived
  facts, one Save & check action, loading isolated to the panel, and exact typed
  results.
- [x] Registered packet: immutable definitions, latest event/facts, Check now, and
  no change to DecisionRail or Copilot behavior.
- [x] Packet/range/instrument switching discards late results; zh-CN and 390 px
  wrapping remain correct.
- [x] Generate OpenAPI types rather than hand-shaping the client contract.

Run:

```powershell
Set-Location frontend
npm exec vitest -- run src/screens/instrument/PacketMonitoring.test.tsx src/screens/InstrumentWorkspace.test.tsx
npm run check:api
npm run typecheck
Set-Location ..
```

#### Step 5: Prove the NVDA loop and no-authority boundary

- [x] Add one Chromium path from Watchlist NVDA to an exact persisted packet,
  selecting conditions and showing initial typed results without leaving the
  workspace.
- [x] Inject later local observations for entry/invalidation/drift/stale trigger
  and non-trigger paths; restart and reopen identical event identity.
- [x] Assert no provider/OpenD/notification call and byte-identical packet,
  proposal, order, risk, and Copilot files.

Focused coherent selection:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_packet_monitoring.py tests/test_decision_packet_api.py tests/test_demo_instrument_workspace.py tests/test_spa_e2e.py -q --basetemp .superpowers/sdd/2026-09-03-local-packet-monitoring/pytest-focused
Set-Location frontend
npm exec vitest -- run src/screens/instrument/PacketMonitoring.test.tsx src/screens/InstrumentWorkspace.test.tsx
npm run check:api
npm run typecheck
Set-Location ..
```

#### Step 6: Review and verify once at the slice boundary

- [x] Submit the complete vertical slice to one combined Reviewer. Correct at most
  one Critical/Important round; a further structural problem reduces scope.
- [x] Immediately before final UI verification, read the Impeccable craft floor;
  after UI is final, run its detector exactly once and record the result.
- [x] After review, run the broad slice gate once:

```powershell
.\.venv\Scripts\python.exe -m pytest -q --basetemp .superpowers/sdd/2026-09-03-local-packet-monitoring/pytest-slice3-final
.\.venv\Scripts\ruff.exe check .
.\.venv\Scripts\python.exe -m pip check
Set-Location frontend
$env:TZ='UTC'
npm exec vitest -- run
npm run check:api
npm run typecheck
npm run lint
npm run build
Set-Location ..
git diff --check
git status --short
```

Do not run the direct Python release-license gate in Slice 3; its known lock drift
is the approved final-PR maintenance item.

#### Step 7: Record the slice checkpoint

- [x] Update the active iteration and Goal with the completed user loop, exact
  review/verification evidence, degraded behavior, and narrow known limits.
- [x] Commit and push the coherent Slice 3 checkpoint, then advance the Goal only
  to the separately approved Slice 4 outcome/review design and plan.

Suggested implementation commit:

```powershell
git add docs src tests frontend
git commit -m "feat(monitoring): add packet-bound local watch conditions"
git push origin codex/0027-evidence-backed-decision-copilot
```
