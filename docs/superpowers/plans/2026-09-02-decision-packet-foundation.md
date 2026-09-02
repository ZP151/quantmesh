# DecisionPacket Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let an operator turn the deterministic NVDA Instrument Workspace into a durable Reject, Watch, or guarded Paper-proposal `DecisionPacket` and reopen the exact saved version after restart.

**Architecture:** Extend the existing point-in-time workspace with a pure deterministic packet composer and a fail-closed JSONL packet store. A packet-bound action service appends immutable child versions and delegates Paper proposal creation and confirmation to the existing `PaperDecisionService`; the React workspace consumes generated OpenAPI types and keeps market, scenarios/evidence, and risk/actions in its existing three-column surface.

**Tech Stack:** Python 3.11+, Pydantic v2, FastAPI, shared `JsonlStore`, React 19, TypeScript 5.9, TanStack Query, Vitest, Playwright, Ruff.

**Spec:** `docs/superpowers/specs/2026-09-02-evidence-backed-decision-copilot-design.md`

## Global Constraints

- Slice 1 only: deterministic DecisionPacket foundation for NVDA; do not implement Copilot, watch-condition evaluation, outcome attribution, or review.
- Keep external venues read-only and execution paper-only; do not add credentials, signing, mainnet, or live-order authority.
- AI is absent from the Slice 1 dependency graph and cannot affect packet composition or actions.
- Scenario probability is `None`; current forecast quantiles and empirical coverage yield `confidence="qualitative"`, never fabricated Bull/Base/Bear percentages.
- Real evidence may enable Paper only when manifest and quality evaluation IDs are present together; explicit `demo-synthetic` evidence may use the existing demo exception without being relabeled real.
- Cost evidence records the account fee and matcher slippage assumptions. Quote half-spread remains explicitly `confirmation-quote-required` until the existing second-confirmation fence supplies an exact quote; it is never represented as zero.
- Stale, ineligible, missing, low-quality, leakage-affected, chronology-invalid, untrusted-lineage, valuation-incomplete, or kill-switch evidence fails closed for Paper while Reject and Watch remain available.
- Every production behavior follows RED → GREEN → REFACTOR; targeted tests run during tasks, broad Python/frontend/OpenAPI/bundle checks run at the Slice 1 boundary.
- Reviewer gets at most two rounds at a demonstrable task boundary; a third structural finding stops patching and shrinks the design.
- Do not modify 0021 soak code, Scheduler, Provider, evidence roots, or maintenance ledgers.

---

### Task 1: Fix packet identity and implement the deterministic domain boundary

**Files:**
- Create: `docs/adr/0019-decision-packet-identity-and-authority.md`
- Create: `src/quantmesh/instruments/decision_analysis.py`
- Create: `src/quantmesh/instruments/decision_packets.py`
- Modify: `src/quantmesh/instruments/contracts.py:1025-1227`
- Modify: `src/quantmesh/instruments/__init__.py`
- Test: `tests/test_decision_packets.py`

**Interfaces:**
- Consumes: `HistoricalSeries`, `WorkspaceForecast | None`, `WorkspaceLiveEvidence`, `WorkspaceRisk`, `ProposalCapability`, `PaperAccount`, `HistoryRange`, and one aware UTC `datetime`.
- Produces: `DecisionPacket`, `DecisionWorkspaceState`, `DecisionPacketStore`, `compose_decision_packet(...) -> DecisionPacket`, `decision_packet_id(packet) -> str`.
- `DecisionPacketStore(root: Path)` exposes `record(packet)`, `get(packet_id)`, `lineage(packet_id)`, and `latest(venue, symbol, selected_range)`; every read revalidates canonical identity and parent/version continuity.

- [ ] **Step 1: Write the ADR before production code**

Record these exact decisions: packet identity is `packet-` plus the first 24 lowercase hex characters of SHA-256 over canonical JSON excluding only `packet_id` and `created_at`; `as_of`, version, parent, disposition, reason, proposal reference, all analysis values, typed blockers, evidence IDs, metrics, and cost assumptions remain identity-bearing. Version 1 has no parent and `draft`; every child increments by one and names its parent. No probability is populated from price quantiles. Demo lineage is an explicit exception, not trusted evidence. Account fee/slippage are pinned; spread is deferred to confirmation and labeled unavailable rather than zero. Existing paper risk/confirmation remains authoritative.

- [ ] **Step 2: Write failing contract/identity/store tests**

Add literal, hand-derived fixtures covering:

```python
def test_packet_identity_ignores_only_created_at() -> None:
    first = packet(created_at=NOW)
    later = packet(created_at=NOW + timedelta(seconds=1))
    assert decision_packet_id(first) == decision_packet_id(later)
    assert decision_packet_id(first) != decision_packet_id(first.model_copy(update={"as_of": LATER}))

def test_store_rejects_missing_parent_or_wrong_next_version(tmp_path: Path) -> None:
    store = DecisionPacketStore(tmp_path / "packets")
    with pytest.raises(ValueError, match="parent"):
        store.record(packet(version=2, parent_packet_id="packet-" + "1" * 24))

def test_store_reopens_exact_lineage_after_new_instance(tmp_path: Path) -> None:
    root = tmp_path / "packets"
    first = DecisionPacketStore(root).record(packet())
    child = DecisionPacketStore(root).record(watch_child(first))
    assert DecisionPacketStore(root).lineage(child.packet_id) == (first, child)
```

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_decision_packets.py -q`

Expected: FAIL because packet contracts, composer, and store do not exist.

- [ ] **Step 3: Add strict frozen packet contracts**

Add Pydantic contracts with these names and shapes (field validators must enforce aware UTC, positive prices/sizes, ordered unique blockers, exactly Bull/Base/Bear, and disposition/reference consistency):

```python
class DecisionDisposition(StrEnum):
    DRAFT = "draft"
    REJECT = "reject"
    WATCH = "watch"
    PAPER_PROPOSAL = "paper_proposal"

class DecisionBlocker(StrictContract):
    code: Literal[
        "history-quality", "history-lineage", "history-freshness", "forecast-missing",
        "forecast-ineligible", "forecast-freshness", "leakage", "chronology",
        "cost-evidence", "valuation", "kill-switch", "proposal-service"
    ]
    message: str
    evidence_ref: str

class DecisionScenario(StrictContract):
    kind: Literal["bull", "base", "bear"]
    thesis: str
    trigger: str
    invalidation: float
    target: float
    probability: None = None
    confidence: Literal["qualitative"] = "qualitative"
    confidence_reason: str

class DecisionCostEvidence(StrictContract):
    fee_bps: float
    slippage_bps: float
    half_spread_bps: float | None = None
    spread_status: Literal["confirmation-quote-required"]

class DecisionPacket(StrictContract):
    packet_id: str
    version: int
    parent_packet_id: str | None
    instrument: InstrumentSnapshot
    selected_range: HistoryRange
    as_of: datetime
    created_at: datetime
    market_state: DecisionMarketState
    scenarios: tuple[DecisionScenario, DecisionScenario, DecisionScenario]
    risk_plan: DecisionRiskPlan
    evidence: DecisionEvidence
    paper_capability: DecisionPaperCapability
    disposition: DecisionDisposition
    operator_reason: str | None = None
    proposal_id: str | None = None

class DecisionWorkspaceState(StrictContract):
    draft: DecisionPacket
    latest: DecisionPacket | None = None
```

Add required `decision: DecisionWorkspaceState` to `InstrumentWorkspace` and validate instrument/range/as-of agreement with history.

- [ ] **Step 4: Implement the pure composer**

`compose_decision_packet(...)` must use only chronological bars at or before `as_of`, a 20-session key-level lookback, SMA20/SMA50 trend state, observed drawdown/volatility, and the 30-session forecast path. Bull/Base/Bear targets are final p75/p50/p25 values and their probability remains `None`. Entry/stop/target/R and suggested quantity are deterministic, bounded by account order/notional/position limits, and explicitly remain proposal inputs. Preserve every horizon's literal metrics and chronology in evidence.

Typed blockers must be created from gaps/duplicates/limitations, missing manifest/quality for non-demo sources, missing/ineligible/stale forecast, invalid chronology, incomplete valuation, kill switches, and existing proposal blockers. Cost evidence reads `account.fee_model.fee_bps` and `account.matcher.slippage_bps`; half spread is `None` with `confirmation-quote-required` and does not invent a zero.

- [ ] **Step 5: Implement fail-closed JSONL replay**

Use `JsonlStore` with `decision-packets.jsonl`. Before and after every append, validate ID, unique packet ID, one root per lineage, exact parent availability, version `parent.version + 1`, immutable instrument/range lineage, and at most one child for the same parent plus identical transition facts. `latest(...)` sorts by `(as_of, version, packet_id)` only after validation.

- [ ] **Step 6: Verify Task 1 GREEN and refactor**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_decision_packets.py tests/test_persistence_jsonl.py tests/test_price_forecast.py -q
.\.venv\Scripts\ruff.exe check src/quantmesh/instruments/decision_analysis.py src/quantmesh/instruments/decision_packets.py src/quantmesh/instruments/contracts.py tests/test_decision_packets.py
git diff --check
```

Expected: all pass; no packet test asserts source text or mock behavior.

- [ ] **Step 7: Commit**

```powershell
git add docs/adr/0019-decision-packet-identity-and-authority.md src/quantmesh/instruments/contracts.py src/quantmesh/instruments/decision_analysis.py src/quantmesh/instruments/decision_packets.py src/quantmesh/instruments/__init__.py tests/test_decision_packets.py
git commit -m "feat(decisions): add deterministic DecisionPacket domain"
```

---

### Task 2: Bind persistence and actions to Instrument Workspace and paper authority

**Files:**
- Modify: `src/quantmesh/instruments/workspace.py:134-357`
- Modify: `src/quantmesh/instruments/decision_packets.py`
- Modify: `src/quantmesh/instruments/api.py:38-305`
- Modify: `src/quantmesh/api/workstation.py:1020-1195,1769-1803`
- Modify: `src/quantmesh/runtime.py`
- Modify: `src/quantmesh/demo/seeder.py:236-256,1536-1768`
- Modify: `src/quantmesh/demo/runtime.py:380-470`
- Modify: `frontend/src/api/client.ts` (generated)
- Modify: `frontend/src/lib/api.ts:540-815`
- Test: `tests/test_decision_packet_api.py`
- Test: `tests/test_runtime.py`
- Test: `tests/test_instrument_workspace_api.py`
- Test: `tests/test_instrument_workspace_e2e.py`
- Test: `tests/test_demo_instrument_workspace.py`

**Interfaces:**
- Consumes: Task 1 contracts/store/composer and existing `PaperDecisionService.propose(...)` / `confirm(...)`.
- Produces: `DecisionPacketService.save_draft(...)`, `DecisionPacketService.transition(...)`, exact packet GET, packet save POST, and packet action POST.
- API requests: `DecisionPacketSaveBody(venue, symbol, selected_range, expected_packet_id)` and `DecisionPacketActionBody(disposition, operator_reason, side, quantity, limit_price)`.
- API result: `DecisionPacketActionResult(packet: DecisionPacket, proposal: PaperProposal | None)`.

- [ ] **Step 1: Write failing workspace/API/restart tests**

Cover one fixed-clock NVDA draft, expected-ID mismatch refusal, exact save/reopen, idempotent Reject and Watch children, Paper blocked on stale/untrusted packet, mismatched artifact/packet refusal, valid packet-bound proposal, second-confirmation risk refusal, and a new demo app instance reopening the exact packet bytes.

```python
saved = client.post("/api/decision-packets", json={
    "venue": "moomoo", "symbol": "NVDA", "selected_range": "6m",
    "expected_packet_id": workspace["decision"]["draft"]["packet_id"],
})
assert saved.status_code == 200

watch = client.post(f"/api/decision-packets/{saved.json()['packet_id']}/actions", json={
    "disposition": "watch", "operator_reason": "Wait for entry zone",
    "side": None, "quantity": None, "limit_price": None,
})
assert watch.json()["packet"]["version"] == 2
assert client.get(f"/api/decision-packets/{watch.json()['packet']['packet_id']}").json() == watch.json()["packet"]
```

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_decision_packet_api.py tests/test_instrument_workspace_api.py tests/test_instrument_workspace_e2e.py tests/test_demo_instrument_workspace.py -q`

Expected: FAIL because workspace/API/runtime bindings are absent.

- [ ] **Step 2: Compose packet state once at the workspace clock**

Inject `DecisionPacketStore | None` into `InstrumentWorkspaceService`. After history, forecast, valuation, live, risk, and proposal capability are composed, create `draft = compose_decision_packet(...)` and read `latest` for the same venue/symbol/range. Return both through `DecisionWorkspaceState`. A missing store still produces the deterministic draft but adds `proposal-service`/persistence capability blocking for durable actions.

- [ ] **Step 3: Implement packet-bound action service**

Implement:

```python
class DecisionPacketService:
    def save_draft(self, venue: Venue, symbol: str, selected_range: HistoryRange,
                   *, expected_packet_id: str) -> DecisionPacket: ...
    def transition(self, parent_packet_id: str, *, disposition: DecisionDisposition,
                   operator_reason: str | None = None, side: Side | None = None,
                   quantity: float | None = None, limit_price: float | None = None
                   ) -> DecisionPacketActionResult: ...
```

Reject/Watch require a nonblank operator reason and never call the proposal service. Paper requires an allowed parent plus side/quantity; it resolves the parent forecast ID, delegates exactly once to `PaperDecisionService.propose`, then appends a child referencing the immutable proposal. Before any delegate call, return an already-recorded identical child so retries are idempotent. Never confirm inside this action.

- [ ] **Step 4: Mount same-origin APIs and close the direct proposal bypass**

Add:

```text
GET  /api/decision-packets/{packet_id}
POST /api/decision-packets
POST /api/decision-packets/{packet_id}/actions
```

All writes call `_guard_json_origin`. Refactor workspace GET to use `app.state.instrument_workspace` so packet composition and storage cannot drift. The legacy `/api/paper/proposals` route must require a persisted DecisionPacket binding or refuse with 409; it may not accept a bare artifact ID in a configured workstation.

- [ ] **Step 5: Bind production and demo roots**

Add `decision_packets: DecisionPacketStore` to `WorkstationStores`; construct it at `settings.decisions_dir / "packets"` for configured production workstations and `root / "decisions" / "packets"` for demo. Add it to `DemoSeeded` load/seed results, the demo mutable-file allowlist, status/provenance counts, and reset accounting without weakening demo-root ownership checks. A clean `create_demo_app` restart must read existing packets without reseeding or recomputing them.

- [ ] **Step 6: Regenerate and wrap the OpenAPI client**

Run `npm run generate:api` in `frontend/`, then expose readonly `DecisionPacket`, `DecisionPacketActionResult`, `saveDecisionPacket`, `decisionPacket`, and `applyDecisionPacketAction` wrappers in `frontend/src/lib/api.ts`. Do not hand-edit generated schema shapes.

- [ ] **Step 7: Verify Task 2 GREEN and commit**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_decision_packets.py tests/test_decision_packet_api.py tests/test_runtime.py tests/test_instrument_workspace_api.py tests/test_instrument_workspace_e2e.py tests/test_demo_instrument_workspace.py tests/test_paper_proposals.py -q
Set-Location frontend
npm run check:api
npm run typecheck
Set-Location ..
.\.venv\Scripts\ruff.exe check src/quantmesh/instruments src/quantmesh/api/workstation.py src/quantmesh/demo tests/test_decision_packet_api.py tests/test_instrument_workspace_api.py tests/test_instrument_workspace_e2e.py tests/test_demo_instrument_workspace.py
git diff --check
git add src/quantmesh frontend/src/api/client.ts frontend/src/lib/api.ts tests/test_decision_packet_api.py tests/test_runtime.py tests/test_instrument_workspace_api.py tests/test_instrument_workspace_e2e.py tests/test_demo_instrument_workspace.py tests/test_paper_proposals.py
git commit -m "feat(decisions): bind packet actions to paper authority"
```

---

### Task 3: Deliver the one-page DecisionPacket interaction

**Files:**
- Create: `frontend/src/screens/instrument/ScenarioEvidence.tsx`
- Create: `frontend/src/screens/instrument/ScenarioEvidence.test.tsx`
- Modify: `frontend/src/screens/InstrumentWorkspace.tsx:40-267`
- Modify: `frontend/src/screens/InstrumentWorkspace.test.tsx`
- Modify: `frontend/src/screens/instrument/MarketCanvas.tsx:25-153`
- Modify: `frontend/src/screens/instrument/MarketCanvas.test.tsx`
- Modify: `frontend/src/screens/instrument/ForecastEvidence.tsx:23-187`
- Modify: `frontend/src/screens/instrument/DecisionRail.tsx:18-230`
- Modify: `frontend/src/screens/instrument/DecisionRail.test.tsx`
- Modify: `frontend/src/screens/instrument/ProposalConfirmation.tsx`
- Modify: `frontend/src/lib/messages.ts`
- Modify: `frontend/src/lib/messages.test.ts`

**Interfaces:**
- Consumes: `workspace.decision.draft`, `workspace.decision.latest`, and Task 2 packet API methods.
- Produces: a single Instrument Workspace flow with phase, market levels, exactly three scenarios, exact evidence/cost semantics, risk plan, Reject/Watch/Paper actions, saved packet identity, and existing confirmation UI.

- [ ] **Step 1: Write failing component tests**

Tests must assert real rendered behavior: one desktop grid; Draft/Evidence blocked/Ready/Watching/Paper proposed phase text; support/resistance/invalidation; exactly Bull/Base/Bear; no percentage when probability is null; fee/slippage plus “spread captured at confirmation”; entry/stop/target/R/size; Reject and Watch enabled while Paper is blocked; saved packet ID after action; persisted latest packet remains visible through background draft refresh; keyboard-accessible labels; and no fixed-width overflow class at 390 px.

Run: `npm exec vitest -- run src/screens/InstrumentWorkspace.test.tsx src/screens/instrument/ScenarioEvidence.test.tsx src/screens/instrument/DecisionRail.test.tsx src/screens/instrument/MarketCanvas.test.tsx src/lib/messages.test.ts`

Expected: FAIL on missing DecisionPacket UI.

- [ ] **Step 2: Render market state and scenarios without duplicating analysis**

`MarketCanvas` receives the packet market state and labels support/resistance/invalidation on the existing chart/screen-reader evidence. `ScenarioEvidence` renders exactly the server-provided Bull/Base/Bear facts and qualitative-confidence reason. It must never derive scenarios, probability, levels, or blockers in TypeScript.

- [ ] **Step 3: Replace the free-form proposal rail with the risk-first packet rail**

Default quantity/limit fields from `risk_plan.suggested_quantity` and entry zone but keep them editable. Place ordered typed blockers immediately above actions. Reject and Watch first persist the draft if necessary and then append their child. Paper persists the draft and applies a packet-bound paper action; existing `ProposalConfirmation` remains the only second-confirmation control. Show terminal risk refusal and packet/proposal IDs until dismissed.

- [ ] **Step 4: Preserve persisted context during refresh and compact layout**

Background workspace refresh may update `decision.draft` but cannot replace the displayed persisted `decision.latest` without an explicit “New analysis” choice. At compact width keep context → market → scenarios/evidence → risk/action, no horizontal document overflow, visible focus, and text/shape semantics independent of red/green alone.

- [ ] **Step 5: Verify Task 3 GREEN, run the Impeccable detector once, and commit**

```powershell
Set-Location frontend
npm exec vitest -- run src/screens/InstrumentWorkspace.test.tsx src/screens/instrument/ScenarioEvidence.test.tsx src/screens/instrument/DecisionRail.test.tsx src/screens/instrument/MarketCanvas.test.tsx src/lib/messages.test.ts
npm run typecheck
npm run lint
Set-Location ..
node C:\Users\15492\Develop\QuantMesh\.codex\skills\impeccable\scripts\detect.mjs --json frontend/src/screens/InstrumentWorkspace.tsx frontend/src/screens/instrument/ScenarioEvidence.tsx frontend/src/screens/instrument/DecisionRail.tsx frontend/src/screens/instrument/MarketCanvas.tsx frontend/src/screens/instrument/ForecastEvidence.tsx
git diff --check
git add frontend/src/screens frontend/src/lib/messages.ts frontend/src/lib/messages.test.ts
git commit -m "feat(workspace): add risk-first DecisionPacket flow"
```

Expected: targeted Vitest/typecheck/lint pass; detector has no unresolved blocking finding. Perform at most one batched correction and one confirmation pass.

---

### Task 4: Prove the NVDA slice and record the user loop

**Files:**
- Modify: `tests/test_demo_instrument_workspace.py`
- Modify: `tests/test_spa_e2e.py`
- Modify: `docs/iterations/0027-evidence-backed-decision-copilot.md`
- Modify: `docs/goals/ACTIVE.md`

**Interfaces:**
- Consumes: the complete Slice 1 backend/API/UI from Tasks 1–3.
- Produces: deterministic NVDA happy, stale, risk-refusal, timing, and restart evidence plus a resumable Slice 2 frontier.

- [ ] **Step 1: Write failing end-to-end acceptance cases**

Add browser/API cases for:

1. NVDA ticker activation to durable Reject, Watch, and Paper-proposal packet identity in under 120 seconds.
2. Market state, three scenarios, risk, evidence, blockers, and actions visible without route navigation.
3. No model service configured while deterministic save still succeeds.
4. Stale/ineligible evidence disables Paper but leaves Reject/Watch and creates no proposal/order.
5. A second-confirmation risk refusal stays visible, binds its proposal/packet, and creates no accepted order.
6. A clean app restart reopens the exact saved packet JSON and disposition.
7. English/Chinese safety copy, keyboard operation, reduced motion, and 390 px no horizontal overflow.

Run the new exact tests first and confirm expected RED failures before changing production code.

- [ ] **Step 2: Make only acceptance-blocking corrections**

Fix only defects that prevent the seven Slice 1 behaviors. Record unrelated findings under follow-ups without implementation. Do not add Copilot, watch triggers, review, more instruments, or new models.

- [ ] **Step 3: Run coherent Slice 1 verification**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_decision_packets.py tests/test_decision_packet_api.py tests/test_persistence_jsonl.py tests/test_price_forecast.py tests/test_paper_proposals.py tests/test_instrument_workspace_api.py tests/test_instrument_workspace_e2e.py tests/test_demo_instrument_workspace.py tests/test_spa_e2e.py -q
.\.venv\Scripts\ruff.exe check .
.\.venv\Scripts\python.exe -m pip check
Set-Location frontend
npm exec vitest -- run
npm run typecheck
npm run lint
npm run check:api
npm run build
Set-Location ..
git diff --check
git status --short
```

Read every final exit code and the complete test statistics. If Playwright/browser software is unavailable, record that exact external blocker and do not claim browser E2E completion.

- [ ] **Step 4: Update durable iteration evidence and ACTIVE Goal**

Record Planner, Quant Researcher, Implementer, Reviewer, and Verifier outputs; exact commands/counts/durations; measured user-loop elapsed time; packet/proposal/restart evidence; limitations; and any deferred side defects. If and only if all Slice 1 gates pass, mark Slice 1 complete and set the frontier to a separately planned Slice 2. Otherwise keep the exact failed gate as the active frontier.

- [ ] **Step 5: Commit the Slice 1 boundary**

```powershell
git add tests/test_demo_instrument_workspace.py tests/test_spa_e2e.py docs/iterations/0027-evidence-backed-decision-copilot.md docs/goals/ACTIVE.md
git commit -m "test(iteration): prove NVDA DecisionPacket slice"
```

Stop after the Slice 1 commit and review gate. Do not begin Slice 2 without a separate approved executable plan.
