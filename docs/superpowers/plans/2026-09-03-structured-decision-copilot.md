# Structured Decision Copilot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:subagent-driven-development` to implement this plan as one bounded
> vertical deliverable, followed by one boundary review (maximum two rounds).

**Goal:** Let an operator request and reopen a schema-valid explanation and challenge
of one persisted DecisionPacket, with every displayed statement cited to an exact
packet fact and every failure isolated to the Copilot panel.

**Architecture:** Add a packet-only citation source and a standalone
`PacketCopilotService` that uses the existing redaction, structured gateway, critic,
and DecisionLog primitives. Store accepted advisory output in an immutable ledger
keyed to the exact packet without mutating `DecisionPacket`. Expose one GET and one
POST endpoint, then add a compact packet-keyed panel to the current Instrument
Workspace evidence rail.

**Tech stack:** Python 3.11+, Pydantic v2, FastAPI, `JsonlStore`, existing AI gateway
and transports, React 19, TypeScript 5.9, TanStack Query, Vitest, Playwright, Ruff.

**Spec:**
`docs/superpowers/specs/2026-09-03-structured-decision-copilot-design.md`

## Global constraints

- Slice 2 only. Do not implement monitoring, outcome/review, another model
  framework, document search, Provider/OpenD access, real trading, another symbol,
  0021 soak, or the inherited license-lock repair.
- A persisted exact packet is the only input. Never substitute a draft, latest
  alias, client packet body, arbitrary retrieval result, or post-as-of fact.
- Copilot cannot mutate or unlock packet, evidence, blocker, proposal, risk,
  confirmation, order, position, or action state.
- Every model stage is structured and receives redacted context. Invalid output,
  unresolved citation, critic flag, timeout, missing service, or persistence error
  yields no partial commentary.
- Use deterministic scripted transports only in automated acceptance. No model key
  or network service is a test or merge gate.
- Follow RED -> GREEN -> REFACTOR. Run focused tests while implementing; run the
  broad slice gate only once after the boundary review.
- The Impeccable Operate floor owns UI quality. Preserve the current workspace
  layout; run its manual detector exactly once after the UI is complete.

---

### Task 1: Deliver the persisted-packet Copilot vertical slice

**Single deliverable:** From a persisted NVDA packet in Instrument Workspace, one
request renders a complete cited explanation/challenge or an isolated degraded
panel, and an accepted record reopens after a clean app restart.

**Stop condition:** Valid scripted and unavailable/invalid paths pass backend, API,
component, and browser acceptance while packet JSON, action availability,
proposal/order counts, and risk/confirmation behavior remain unchanged.

**Primary files:**

- Create: `src/quantmesh/instruments/copilot.py`
- Create: `frontend/src/screens/instrument/PacketCopilot.tsx`
- Create: `tests/test_packet_copilot.py`
- Create: `frontend/src/screens/instrument/PacketCopilot.test.tsx`
- Modify: `src/quantmesh/ai/retrieval.py`
- Modify: `docs/adr/0019-decision-packet-identity-and-authority.md`
- Modify: `src/quantmesh/instruments/api.py`
- Modify: `src/quantmesh/api/workstation.py`
- Modify: `src/quantmesh/instruments/__init__.py`
- Modify: `src/quantmesh/runtime.py`
- Modify: `frontend/src/lib/api.ts`
- Modify: `frontend/src/lib/messages.ts`
- Modify: `frontend/src/screens/InstrumentWorkspace.tsx`
- Modify/generated: `frontend/src/api/client.ts`
- Test/modify as needed: `tests/test_decision_packet_api.py`
- Test/modify as needed: `tests/test_demo_instrument_workspace.py`
- Test/modify as needed: `tests/test_spa_e2e.py`
- Test/modify as needed: `frontend/src/screens/InstrumentWorkspace.test.tsx`

Implementation may touch `src/quantmesh/demo/seeder.py` or
`src/quantmesh/demo/runtime.py` only as required to bind the new optional ledger to
the existing demo root and prove restart. Do not seed fabricated accepted Copilot
output into the default demo and do not change demo/provider authority.

#### Interfaces

Implement strict contracts in `src/quantmesh/instruments/copilot.py`:

```python
class PacketCopilotItem(BaseModel):
    text: str
    citations: tuple[Citation, ...]

class PacketCopilotDraft(BaseModel):
    packet_id: str
    base_explanation: PacketCopilotItem
    bull_challenge: PacketCopilotItem
    bear_challenge: PacketCopilotItem
    evidence_gaps_or_contradictions: tuple[PacketCopilotItem, ...]
    limitations: tuple[PacketCopilotItem, ...]
    operator_questions: tuple[PacketCopilotItem, ...]

class PacketCopilotCritic(BaseModel):
    packet_id: str
    verdict: Literal["pass", "flag"]
    flagged_items: tuple[PacketCopilotFlag, ...]

class PacketCopilotRecord(BaseModel):
    record_id: str
    schema_version: Literal[1]
    packet_id: str
    request_kind: Literal["explain-and-challenge"]
    report: PacketCopilotDraft
    analyst_decision_id: str
    critic_decision_id: str
    analyst_model: ModelMeta
    critic_model: ModelMeta
    recorded_at: datetime

class PacketCopilotState(BaseModel):
    status: Literal["idle", "ready", "degraded"]
    packet_id: str
    record: PacketCopilotRecord | None
    reason_code: str | None

PacketCopilotStore.record(record) -> PacketCopilotRecord
PacketCopilotStore.latest(packet_id) -> PacketCopilotRecord | None
PacketCopilotService.latest(packet_id) -> PacketCopilotState
PacketCopilotService.request(packet_id) -> PacketCopilotState
```

All models use `extra="forbid"`, bounded strings/collections, aware UTC timestamps,
exact packet-ID/digest patterns, and consistency validators. `PacketCopilotRecord`
is content-addressed and stores the full accepted draft plus analyst/critic decision
IDs and model metadata. `PacketCopilotStore` uses `JsonlStore`, rejects duplicate or
corrupt identities, and reopens the latest exact-packet record.

Extend `Citation` with packet-only `json_pointer` and `value_digest` fields and add
a `DecisionPacketSource`. The source must load through `DecisionPacketStore.get`,
canonical-render the exact packet, resolve only scalar or scalar-list leaves, and
recompute SHA-256 over canonical selected JSON. Preserve existing citation behavior
and serialization for document/experiment/audit sources.

The service accepts injected `DecisionPacketStore`, `PacketCopilotStore`,
`DecisionLog`, analyst `ModelGateway`, critic `ModelGateway`, and model metadata.
It redacts before both calls, validates all citations before and after the critic,
requires a pass with no flags, records both stages, and persists only the complete
accepted report. An identical accepted request returns the existing record without
calling either gateway.

#### Step 1: Write backend RED tests

- [ ] Add contract/source tests for legacy citation compatibility and valid packet
  pointer/digest resolution.
- [ ] Add failing cases for cross-packet IDs, draft substitution, missing/escaped or
  container pointer, bad digest, legacy span on packet, and packet fields on legacy
  sources.
- [ ] Add service tests using `ScriptedModelTransport` for a valid analyst + critic
  pair, unavailable/timeout, non-JSON, extra or authority-shaped fields, malformed
  critic, critic flag, and secret redaction before both requests.
- [ ] Snapshot packet bytes and packet/proposal/order ledgers before each failure;
  assert they are unchanged afterward.
- [ ] Prove idempotent accepted replay and a new store/service instance reopening
  the exact `PacketCopilotRecord` without a model call.

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_packet_copilot.py tests/test_ai_retrieval.py tests/test_ai_decisions.py -q
```

Expected: FAIL because packet citations and Copilot contracts/service/store do not
exist.

#### Step 2: Implement the domain and service GREEN

- [ ] Extend ADR-0019 before production code with the durable decision that advisory
  Copilot records reverse-bind to an exact packet and packet citations resolve a
  restricted JSON pointer plus canonical value digest; neither changes packet
  identity or authority.
- [ ] Add the source-specific citation validation and exact packet resolver without
  widening retrieval search.
- [ ] Implement canonical pointer selection/digest verification and strict Copilot
  analyst/critic contracts.
- [ ] Implement immutable record identity/store and service processing in the order
  fixed by the design.
- [ ] Normalize expected AI/redaction/citation/persistence failures to one internal
  degraded result; never expose unvalidated draft content or secrets in reason text.
- [ ] Re-run the Step 1 command until GREEN, then refactor without expanding scope.

#### Step 3: Write API RED tests and bind the optional service

- [ ] Prove GET returns `idle` for a persisted packet with no accepted record and
  `ready` after POST; a clean app reconstruction returns the same record.
- [ ] Prove missing service/model, invalid output, citation failure, and critic flag
  return a typed `degraded` state with the exact packet ID and no report.
- [ ] Prove unknown packet is 404, corrupt packet/store is 409, and cross-origin POST
  is 403.
- [ ] Re-read the packet and compare proposal/order counts after all cases; existing
  stale and paper-confirmation refusal tests must remain unchanged.

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_packet_copilot.py tests/test_decision_packet_api.py tests/test_demo_instrument_workspace.py -q
```

Expected before binding: FAIL on the missing routes/app state. Add the two routes to
`instrument_router`, inject the optional service in `create_workstation_app`, and
return strict `PacketCopilotState` envelopes. Add `PacketCopilotStore` to
`WorkstationStores` under the existing decisions root. The normal workstation may
construct the loopback-only `HttpModelTransport` only when `settings.model_name` is
non-empty; a blank model name and the default demo stay explicitly degraded and make
no model call. Deterministic tests inject scripted gateways.

#### Step 4: Write UI RED tests

- [ ] For a fresh packet, render localized “save first” guidance and no enabled
  request action.
- [ ] For an exact persisted packet, load its latest state, activate one “Explain &
  challenge” button by keyboard, show panel-only loading, then render all cited
  sections and field/digest disclosures.
- [ ] Render a localized degraded reason and retry without disabling or changing the
  existing DecisionRail controls.
- [ ] Switch packet, range, and instrument context and prove stale commentary never
  renders under the new packet; verify 390 px wrapping/no horizontal overflow.

Run:

```powershell
Set-Location frontend
npm exec vitest -- run src/screens/instrument/PacketCopilot.test.tsx src/screens/InstrumentWorkspace.test.tsx
Set-Location ..
```

Expected: FAIL because the component/client bindings do not exist.

#### Step 5: Implement the UI and generated client GREEN

- [ ] Add typed GET/POST wrappers in `frontend/src/lib/api.ts`; generate, never
  hand-shape, the OpenAPI types with `npm run generate:api`.
- [ ] Build `PacketCopilot.tsx` as an inline collapsible evidence section with fresh,
  idle, loading, ready, and degraded states. Key every query/mutation/cache update by
  exact packet ID and discard late responses for a changed context.
- [ ] Add English and Simplified Chinese labels/reasons in
  `frontend/src/lib/messages.ts` and mount the panel in the evidence rail without
  changing `DecisionRail` inputs or action state.
- [ ] Re-run the Step 4 command and `npm run check:api` plus `npm run typecheck` until
  GREEN.

#### Step 6: Prove the user loop and authority isolation

- [ ] Add or extend one Chromium acceptance path that starts from Watchlist NVDA,
  opens the existing persisted packet, requests the deterministic scripted report,
  expands citations in place, and never leaves Instrument Workspace.
- [ ] Add a model-unavailable path proving market/scenario/risk/evidence/actions
  remain visible and Reject/Watch/Paper behavior is unchanged.
- [ ] Restart the app against the same root and reopen the exact accepted record and
  citation digests.

Run the focused coherent selection:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_packet_copilot.py tests/test_decision_packet_api.py tests/test_demo_instrument_workspace.py tests/test_spa_e2e.py -q --basetemp .superpowers/sdd/2026-09-03-structured-decision-copilot/pytest-focused
Set-Location frontend
npm exec vitest -- run src/screens/instrument/PacketCopilot.test.tsx src/screens/InstrumentWorkspace.test.tsx
npm run check:api
npm run typecheck
Set-Location ..
```

#### Step 7: One boundary review, one detector run, and one broad slice gate

- [ ] Submit the complete vertical slice to one Reviewer for combined specification,
  correctness, architecture, licensing, accessibility, and trading-safety review.
- [ ] If Important/Critical findings exist, perform one bounded correction round and
  one re-review. A further structural problem stops patching and reduces scope.
- [ ] Immediately before final UI verification, read Impeccable
  `reference/craft-floor.md`. After UI changes are complete, run the project
  Impeccable detector exactly once over the changed UI files and record its result.
- [ ] After review, run the broad slice gate once:

```powershell
.\.venv\Scripts\python.exe -m pytest -q --basetemp .superpowers/sdd/2026-09-03-structured-decision-copilot/pytest-slice2-final
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

Do not run the direct Python release-license gate here; its known audit-lock drift is
the explicitly deferred final-PR maintenance item and this slice changes no
dependency file.

#### Step 8: Record and publish the slice checkpoint

- [ ] Update `docs/iterations/0027-evidence-backed-decision-copilot.md` and
  `docs/goals/ACTIVE.md` with the user loop, exact verification evidence, review
  verdict, degraded behavior, and any narrowly deferred risk.
- [ ] Self-review that every design requirement has implementation/test evidence,
  no placeholder remains, OpenAPI is current, and packet/proposal/order authority is
  unchanged.
- [ ] Commit the one coherent slice checkpoint and push the integration branch. Set
  the active frontier to the separately approved Slice 3 design/plan; do not start
  monitoring in this task.

Suggested commit:

```powershell
git add docs src tests frontend
git commit -m "feat(copilot): add packet-bound cited explanations"
git push origin codex/0027-evidence-backed-decision-copilot
```
