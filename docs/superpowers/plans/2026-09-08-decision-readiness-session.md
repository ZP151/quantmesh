# Decision Readiness Session Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add one Decision Inbox session that truthfully shows exact
trusted-data readiness, explicitly refreshes existing local watch conditions,
and opens the exact triggered, blocked or review-due DecisionPacket.

**Architecture:** Keep iteration 0021 as an independent data plane and expose
only an optional exact-manifest `lineage()` reader to an instruments-owned
readiness service. Extend the existing read-only `DecisionInboxService`, then
add one same-origin session command that reuses `DecisionWatchService.check()`
and the existing server-owned workspace facts. Persist no new Inbox or session
aggregate; durable per-registration evaluations remain authoritative.

**Tech Stack:** Python 3.14, Pydantic v2, FastAPI, existing append-only JSONL
stores, React 19, TypeScript, TanStack Query, Vitest, pytest/Playwright.

**Spec:**
`docs/superpowers/specs/2026-09-07-decision-readiness-session-design.md`

## Global Constraints

- Baseline is
  `origin/main@4fb810e1268f5f0e13599d7198aee4fa78cc4717` on
  `codex/0029-decision-readiness-session`.
- Iteration 0021 owns Scheduler, Provider/OpenD, network collection,
  trusted-data roots, soak reports, outbox and GitHub witness state.
- The readiness boundary may call only `lineage(exact_manifest_id)` supplied by
  the packet; it must not call `entries()`, inspect alternate roots or choose a
  different manifest/evaluation.
- Session refresh is an explicit same-origin request. It has no provider,
  symbol, root, price, forecast or time input and creates no registration.
- `DecisionWatchService.check()` remains the only evaluation writer. No new
  mutable Inbox/session aggregate is permitted.
- Demo evidence stays labelled `demo`; it is never reported as trusted real
  evidence.
- Missing, stale, failed, mismatched or corrupt real evidence fails closed and
  cannot be hidden by AI confidence.
- Paper proposals still require the existing risk kernel and second
  confirmation. Session refresh cannot create/confirm a proposal or place an
  order.
- No Provider/OpenD call, Scheduler or automation change, trusted-data write,
  external notification, new symbol, model/framework expansion, testnet/live
  trading, 0021 repair or unrelated cleanup.
- NVDA, AAPL, BTC and SOL are the only acceptance identities.
- Each task is one 24–48 hour vertical slice, gets at most two review rounds,
  and records user-visible progress in the iteration ledger.
- Use targeted checks during implementation. Run the expensive clean release
  gate once on the final exact PR head, not after micro-edits.

---

## File structure

- `src/quantmesh/instruments/readiness.py`: strict readiness contracts and the
  exact-ID, read-only packet evidence qualifier.
- `src/quantmesh/instruments/session.py`: refresh result contracts and the
  explicit multi-registration session coordinator.
- `src/quantmesh/instruments/watch_observations.py`: one shared constructor for
  server-owned `DecisionWatchObservation` facts.
- `src/quantmesh/instruments/inbox.py`: compose readiness, monitoring time and
  the derived session summary into the existing read-only projection.
- `src/quantmesh/instruments/api.py`: expose the Inbox GET and one same-origin
  refresh POST; keep error bodies typed and sanitized.
- `src/quantmesh/api/workstation.py`: inject optional catalog and reset-safe
  providers into readiness/session services.
- `frontend/src/screens/Watchlist.tsx`: render readiness/session facts, the
  explicit refresh action and compact attention filters.
- `frontend/src/lib/api.ts`, `frontend/src/api/client.ts` and
  `frontend/src/lib/messages.ts`: generated/public client contract and reviewed
  English/zh-CN copy.
- `tests/test_decision_readiness.py`: exact closure, demo and failure semantics.
- `tests/test_decision_session.py`: observation reuse, multi-watch refresh,
  partial results, idempotency and prohibited collaborator checks.
- `tests/test_decision_inbox.py` and
  `frontend/src/screens/Watchlist.test.tsx`: read model and component behavior.
- `tests/test_decision_session_e2e.py`: packaged browser/restart/two-minute
  acceptance.
- `docs/adr/0020-decision-readiness-data-plane-boundary.md`: durable module and
  authority decision.
- `docs/iterations/0029-decision-readiness-session.md` and
  `docs/goals/ACTIVE.md`: resumable evidence and frontier.

---

### Task 1: Readiness truth in Decision Inbox

**User action:** Open Decision Inbox and understand whether the exact packet
evidence is trusted, demo, blocked or unavailable without opening an ops page.

**Stop condition:** NVDA/AAPL and evidence-blocked BTC/SOL render exact
readiness, evidence time, mark time/reason and last local check after an app
reconstruction; no refresh endpoint exists yet.

**Files:**

- Create: `docs/adr/0020-decision-readiness-data-plane-boundary.md`
- Create: `src/quantmesh/instruments/readiness.py`
- Create: `tests/test_decision_readiness.py`
- Modify: `src/quantmesh/instruments/inbox.py`
- Modify: `src/quantmesh/instruments/__init__.py`
- Modify: `src/quantmesh/api/workstation.py`
- Modify: `tests/test_decision_inbox.py`
- Modify: `frontend/src/screens/Watchlist.tsx`
- Modify: `frontend/src/screens/Watchlist.test.tsx`
- Modify: `frontend/src/screens/NavigationAndValuation.test.tsx`
- Modify: `frontend/src/lib/messages.ts`
- Modify: `frontend/src/lib/api.ts`
- Regenerate: `frontend/src/api/client.ts`
- Modify: `docs/iterations/0029-decision-readiness-session.md`
- Modify: `docs/goals/ACTIVE.md`

**Interfaces:**

- Consumes: `DecisionPacket.evidence`,
  `DataCatalogReader.lineage(manifest_id: str) -> CatalogLineage`, existing
  `DecisionInboxService`, `DecisionWatchStore.evaluations(registration_id)`.
- Produces:

```python
class DecisionReadinessEvidenceRef(StrictContract):
    manifest_id: str
    evaluation_id: str
    report_id: str
    evaluated_at: datetime

class DecisionReadiness(StrictContract):
    status: Literal["ready", "demo", "blocked", "unavailable"]
    checked_at: datetime
    limiting_evidence_at: datetime | None
    reason_code: str
    reason: str
    history: DecisionReadinessEvidenceRef | None = None
    forecast: DecisionReadinessEvidenceRef | None = None

class DecisionSessionSummary(StrictContract):
    generated_at: datetime
    last_checked_at: datetime | None
    registered_count: int
    triggered_count: int
    blocked_count: int

class ExactCatalogReader(Protocol):
    def lineage(self, manifest_id: str) -> CatalogLineage: ...

class DecisionReadinessService:
    def evaluate(self, packet: DecisionPacket, *, checked_at: datetime) -> DecisionReadiness: ...
```

`DecisionInboxMonitoringSummary` gains `last_checked_at`, `latest_status` and
`latest_reason`. `DecisionInboxEntry` gains non-null `readiness`.
`DecisionInbox` gains non-null `session`. `DecisionInboxService.snapshot()`
becomes `snapshot(*, at: datetime | None = None)` so Task 2 can freeze one
session clock while ordinary GET keeps its current call shape.

- [ ] **Step 1: Prepare the isolated development toolchain**

Use the existing reviewed shared Python dependency environment only for fast
targeted checks, always with the 0029 source first on `PYTHONPATH`. Install the
locked frontend dependencies inside this worktree.

```powershell
$env:PYTHONPATH = (Resolve-Path .\src).Path
& 'C:\Users\15492\Develop\QuantMesh\.venv\Scripts\python.exe' -m pip check
Push-Location frontend
npm ci
Pop-Location
```

Expected: `pip check` exits 0 and `npm ci` exits 0. Do not install or update any
Provider/OpenD component.

- [ ] **Step 2: Write exact readiness RED tests**

Create `tests/test_decision_readiness.py` with a narrow fake whose
`entries()` method raises if called and whose `lineage()` accepts only the
packet's exact IDs. Cover these assertions:

```python
result = DecisionReadinessService(catalog_provider=lambda: catalog).evaluate(
    real_packet,
    checked_at=NOW,
)
assert result.status == "ready"
assert result.history.manifest_id == real_packet.evidence.history_manifest_id
assert result.history.evaluation_id == real_packet.evidence.history_quality_evaluation_id
assert catalog.requested == [real_packet.evidence.history_manifest_id]
assert result.limiting_evidence_at == min(
    real_packet.evidence.history_generated_at,
    result.history.evaluated_at,
)
```

Add independent tests for:

- `history_source == "demo-synthetic"` returning `demo` without a catalog call;
- a real packet missing its history binding returning `blocked`;
- a present closure with FAIL/unknown rights/evaluation mismatch returning
  `blocked` and retaining the supplied exact IDs;
- an absent reader, missing referenced manifest or corrupt lineage returning
  `unavailable` without trying another ID;
- optional forecast absence not changing an otherwise valid history closure;
- an advertised real forecast requiring its exact manifest/evaluation closure;
- naive clocks and malformed returned identities being rejected.

- [ ] **Step 3: Run the readiness tests and verify RED**

```powershell
& 'C:\Users\15492\Develop\QuantMesh\.venv\Scripts\python.exe' -m pytest `
  tests/test_decision_readiness.py -q `
  --basetemp "$env:TEMP\quantmesh-0029-task1-red"
```

Expected: collection fails because
`quantmesh.instruments.readiness` does not exist.

- [ ] **Step 4: Implement the exact-ID readiness service**

Implement `DecisionReadinessService` with a reset-safe provider:

```python
CatalogProvider = Callable[[], ExactCatalogReader | None]

class DecisionReadinessService:
    def __init__(self, *, catalog_provider: CatalogProvider) -> None:
        self._catalog_provider = catalog_provider

    def evaluate(self, packet: DecisionPacket, *, checked_at: datetime) -> DecisionReadiness:
        checked_at = _utc(checked_at, "checked_at")
        if packet.evidence.history_source == "demo-synthetic":
            return _demo_readiness(packet, checked_at)
        if packet.evidence.history_manifest_id is None:
            return _blocked(checked_at, "missing_history_binding", packet)
        catalog = self._catalog_provider()
        if catalog is None:
            return _unavailable(checked_at, "catalog_unavailable", packet)
        history = _qualify_exact(
            catalog,
            manifest_id=packet.evidence.history_manifest_id,
            evaluation_id=packet.evidence.history_quality_evaluation_id,
        )
        forecast = _qualify_packet_forecast(catalog, packet)
        return _combine(packet, checked_at, history, forecast)
```

`_qualify_exact()` calls only `catalog.lineage(manifest_id)`. Validate returned
manifest ID, quality/report/checkpoint agreement, evaluation ID,
`trusted_for_research`, `source_rights_known` and timezone-aware times. Catch
expected missing/integrity/qualification failures into stable sanitized reason
codes; do not catch programming errors such as an invalid clock or malformed
contract construction.

- [ ] **Step 5: Run readiness GREEN and static checks**

```powershell
& 'C:\Users\15492\Develop\QuantMesh\.venv\Scripts\python.exe' -m pytest `
  tests/test_decision_readiness.py -q `
  --basetemp "$env:TEMP\quantmesh-0029-task1-green"
& 'C:\Users\15492\Develop\QuantMesh\.venv\Scripts\ruff.exe' check `
  src/quantmesh/instruments/readiness.py tests/test_decision_readiness.py
git diff --check
```

Expected: all commands exit 0.

- [ ] **Step 6: Write Inbox projection RED tests**

Extend `tests/test_decision_inbox.py` to assert one deterministic demo row and
one exact real row:

```python
payload = client.get("/api/decision-packets").json()
nvda = _entry(payload, "moomoo", "NVDA")
assert nvda["readiness"]["status"] == "demo"
assert nvda["readiness"]["reason_code"] == "demo_evidence"
assert payload["session"]["generated_at"] == payload["generated_at"]
assert payload["session"]["registered_count"] == 1
assert nvda["monitoring"]["last_checked_at"] == expected_evaluated_at
```

Also prove GET remains byte-for-byte read-only, venue-less/no-packet rows carry
typed unavailable readiness, a corrupt exact catalog closure returns a
sanitized unavailable row rather than a favorable fallback, and reconstructing
the application produces the same readiness/monitoring/session fields.

- [ ] **Step 7: Run the Inbox tests and verify RED**

```powershell
& 'C:\Users\15492\Develop\QuantMesh\.venv\Scripts\python.exe' -m pytest `
  tests/test_decision_inbox.py -q `
  --basetemp "$env:TEMP\quantmesh-0029-task1-inbox-red"
```

Expected: assertions fail because `readiness`, monitoring timestamps and
`session` are absent.

- [ ] **Step 8: Integrate readiness into the read-only Inbox**

Inject `DecisionReadinessService` into `DecisionInboxService`. Evaluate only
the packet already selected by the existing attention algorithm. Derive the
monitoring summary from replay-validated evaluations and calculate the session
summary from the final entries:

```python
evaluation = monitoring.evaluations[-1] if monitoring.evaluations else None
readiness = self._readiness.evaluate(packet, checked_at=generated_at)
last_checked_at = None if evaluation is None else evaluation.observation.evaluated_at
session = DecisionSessionSummary(
    generated_at=generated_at,
    last_checked_at=max(checked_times, default=None),
    registered_count=sum(entry.monitoring is not None for entry in entries),
    triggered_count=sum(entry.attention_state is DecisionAttentionState.WATCH_TRIGGERED for entry in entries),
    blocked_count=sum(entry.readiness.status in {"blocked", "unavailable"} for entry in entries),
)
```

For no-packet and venue-less rows construct explicit `unavailable` readiness
without invoking a catalog. Keep the existing packet priority, mark fence,
paper/review projection and exact navigation unchanged. In
`create_workstation_app`, supply
`catalog_provider=lambda: getattr(app.state, "data_catalog", None)` so demo
reset and application reconstruction cannot leave a stale catalog reference.

- [ ] **Step 9: Write the frontend readiness RED tests**

Extend the typed fixtures in `Watchlist.test.tsx` and
`NavigationAndValuation.test.tsx`. Assert the visible contract, not CSS:

```tsx
expect(await screen.findByText('Demo evidence')).toBeVisible()
expect(screen.getByText('Last checked 12:04 UTC')).toBeVisible()
expect(screen.getByText('Mark received 12:03 UTC')).toBeVisible()
expect(screen.getByText('Trusted evidence unavailable')).toBeVisible()
expect(screen.getByText('Exact quality evaluation does not match this packet.')).toBeVisible()
```

Add equivalent zh-CN assertions and ensure mark reason is visible whenever the
mark is stale/unavailable. The row still has exactly one primary recovery or
exact-packet link.

- [ ] **Step 10: Run frontend RED**

```powershell
Push-Location frontend
npm run test -- --run src/screens/Watchlist.test.tsx `
  src/screens/NavigationAndValuation.test.tsx
Pop-Location
```

Expected: tests fail because readiness/session copy is not rendered.

- [ ] **Step 11: Render the readiness surface and regenerate the client**

Add concise English/zh-CN messages for readiness state, evidence time, mark
time/reason and last check. Keep the existing separator-first table and stack
the new facts within the Decision cell at compact widths. Do not add a card
dashboard or refresh control in this task.

```tsx
<ReadinessFacts readiness={entry.readiness} monitoring={entry.monitoring} />
{entry.mark_context.received_at && (
  <p>{t('screen.watchlist.markReceived', {
    time: dateTime(entry.mark_context.received_at, locale),
  })}</p>
)}
{entry.mark_context.reason && <p>{entry.mark_context.reason}</p>}
```

Import the existing `dateTime` formatter and read `locale` from
`usePreferences()`; do not add a second time-formatting helper.

Regenerate and verify the OpenAPI client:

```powershell
Push-Location frontend
npm run generate:api
npm run check:api
npm run test -- --run src/screens/Watchlist.test.tsx `
  src/screens/NavigationAndValuation.test.tsx src/lib/messages.test.ts
npm run typecheck
npm run lint
Pop-Location
```

Expected: all commands exit 0.

- [ ] **Step 12: Verify, review, record and commit Slice 1**

Run the coherent slice selection:

```powershell
& 'C:\Users\15492\Develop\QuantMesh\.venv\Scripts\python.exe' -m pytest `
  tests/test_decision_readiness.py tests/test_decision_inbox.py `
  tests/test_data_catalog.py tests/test_data_catalog_api.py -q `
  --basetemp "$env:TEMP\quantmesh-0029-task1-final"
& 'C:\Users\15492\Develop\QuantMesh\.venv\Scripts\ruff.exe' check `
  src/quantmesh/instruments/readiness.py src/quantmesh/instruments/inbox.py `
  src/quantmesh/api/workstation.py tests/test_decision_readiness.py `
  tests/test_decision_inbox.py
git diff --check
```

Perform Quant Researcher review of quality/freshness semantics and one
Standards+Spec review. Correct only in-scope findings; stop after a second
review round. Record commands, counts, warnings and verdict in the iteration
ledger. Then commit:

```powershell
git add docs/adr/0020-decision-readiness-data-plane-boundary.md `
  src/quantmesh/instruments/readiness.py src/quantmesh/instruments/inbox.py `
  src/quantmesh/instruments/__init__.py src/quantmesh/api/workstation.py `
  tests/test_decision_readiness.py tests/test_decision_inbox.py `
  frontend/src/screens/Watchlist.tsx frontend/src/screens/Watchlist.test.tsx `
  frontend/src/screens/NavigationAndValuation.test.tsx frontend/src/lib/messages.ts `
  frontend/src/lib/api.ts frontend/src/api/client.ts `
  docs/iterations/0029-decision-readiness-session.md docs/goals/ACTIVE.md
git commit -m "feat(decisions): expose exact readiness in inbox"
```

---

### Task 2: Explicit local session refresh

**User action:** Press **Refresh session** once and reevaluate every existing
registration from server-owned local facts.

**Stop condition:** The command returns complete, partial or no-registration
truthfully, updates NVDA/AAPL Inbox state, and demonstrably has no Provider,
OpenD, Scheduler, proposal, confirmation or order collaborator.

**Files:**

- Create: `src/quantmesh/instruments/watch_observations.py`
- Create: `src/quantmesh/instruments/session.py`
- Create: `tests/test_decision_session.py`
- Modify: `src/quantmesh/instruments/api.py`
- Modify: `src/quantmesh/instruments/__init__.py`
- Modify: `src/quantmesh/api/workstation.py`
- Modify: `tests/test_packet_monitoring.py`
- Modify: `frontend/src/lib/api.ts`
- Regenerate: `frontend/src/api/client.ts`
- Modify: `frontend/src/screens/Watchlist.tsx`
- Modify: `frontend/src/screens/Watchlist.test.tsx`
- Modify: `frontend/src/lib/messages.ts`
- Modify: `docs/iterations/0029-decision-readiness-session.md`
- Modify: `docs/goals/ACTIVE.md`

**Interfaces:**

- Consumes: Task 1 `DecisionInboxService.snapshot(at=...)`,
  `DecisionWatchService.state()`, `DecisionWatchService.check()`,
  `InstrumentWorkspaceService.render()` and exact packet selection.
- Produces:

```python
class DecisionSessionRefreshItem(StrictContract):
    packet_id: str
    registration_id: str
    evaluation_id: str | None = None
    status: Literal["evaluated", "failed"]
    triggered: bool = False
    not_comparable_codes: tuple[str, ...] = ()
    reason_code: str | None = None
    reason: str | None = None

class DecisionSessionRefreshResult(StrictContract):
    started_at: datetime
    completed_at: datetime
    status: Literal["complete", "partial", "no_registered_watches"]
    registered_count: int
    evaluated_count: int
    items: tuple[DecisionSessionRefreshItem, ...]

def build_watch_observation(
    *,
    packet: DecisionPacket,
    workspace: InstrumentWorkspace,
    evaluated_at: datetime,
) -> DecisionWatchObservation: ...

class DecisionSessionService:
    def refresh(self) -> DecisionSessionRefreshResult: ...
```

- [ ] **Step 1: Write shared observation and session RED tests**

In `tests/test_decision_session.py`, create two watch registrations and inject
a workspace renderer that records exact `(venue, symbol, range)` calls. Assert:

```python
result = service.refresh()
assert result.status == "complete"
assert result.registered_count == 2
assert result.evaluated_count == 2
assert [item.packet_id for item in result.items] == [aapl_packet_id, nvda_packet_id]
assert all(item.evaluation_id is not None for item in result.items)
assert renderer.calls == [
    (Venue.MOOMOO, "AAPL", HistoryRange.SIX_MONTHS),
    (Venue.MOOMOO, "NVDA", HistoryRange.SIX_MONTHS),
]
```

Cover no registrations, one corrupt/missing packet producing `partial`, same
observation returning the same evaluation ID, strictly newer price sequence
advancing the durable cursor, stale-only evaluation without a quote, and
invalid clock. Add sentinels named `provider`, `scheduler`, `proposal`,
`confirmation` and `order` whose methods raise; prove the session constructor
does not accept or call them.

In `tests/test_packet_monitoring.py`, add parity tests showing the existing
single-packet endpoint and `build_watch_observation()` produce equal model
dumps from the same packet/workspace/time.

- [ ] **Step 2: Run session RED**

```powershell
& 'C:\Users\15492\Develop\QuantMesh\.venv\Scripts\python.exe' -m pytest `
  tests/test_decision_session.py tests/test_packet_monitoring.py -q `
  --basetemp "$env:TEMP\quantmesh-0029-task2-red"
```

Expected: collection fails because the new modules do not exist.

- [ ] **Step 3: Extract the observation builder**

Move only the existing server-side mapping into
`build_watch_observation()`:

```python
live = workspace.live
return DecisionWatchObservation(
    evaluated_at=_utc(evaluated_at),
    price=live.last,
    instrument=packet.instrument if live.last is not None else None,
    source=live.source,
    provenance=live.provenance,
    data_time=live.data_time,
    received_at=live.received_at,
    sequence=live.sequence,
    sequence_gap=live.sequence_gap,
    candidate_forecast_artifact_id=(
        workspace.forecast.artifact_id if workspace.forecast is not None else None
    ),
)
```

Change the existing packet watch POST to call this function after its same
workspace render. Preserve registration/activation behavior and response bytes.

- [ ] **Step 4: Implement the session coordinator**

Freeze `started_at` once, request `inbox.snapshot(at=started_at)`, sort selected
packet IDs deterministically by `(venue, symbol, packet_id)`, and process only
packets whose exact registration exists:

```python
for entry in selected_entries:
    registration, _ = watches.state(entry.packet_id)
    if registration is None:
        continue
    try:
        packet = packets.get(entry.packet_id)
        workspace = renderer.render(
            packet.instrument.venue,
            packet.instrument.symbol,
            packet.selected_range,
        )
        observation = build_watch_observation(
            packet=packet,
            workspace=workspace,
            evaluated_at=started_at,
        )
        evaluation = watches.check(registration.registration_id, observation)
        items.append(_evaluated_item(packet, registration, evaluation))
    except (OSError, ValueError) as error:
        items.append(_failed_item(entry.packet_id, registration, error))
```

Use stable sanitized reason codes for expected item failures. If Inbox replay
or registration enumeration itself is corrupt, fail the whole request with a
typed error instead of skipping records. `completed_at` comes from the same
injected UTC clock after processing; it must not precede `started_at`.

- [ ] **Step 5: Add the same-origin API and verify backend GREEN**

Mount `POST /api/decision-session/refresh` in the existing instruments router.
Call `_guard_json_origin(request, "decision session refresh")`; accept no body.
Return `DecisionSessionRefreshResult`, 404 when the service is unattached and a
sanitized 409 contract for whole-session replay failure.

Wire `app.state.decision_session` using providers that resolve current app state
after demo reset. Then run:

```powershell
& 'C:\Users\15492\Develop\QuantMesh\.venv\Scripts\python.exe' -m pytest `
  tests/test_decision_session.py tests/test_packet_monitoring.py `
  tests/test_decision_inbox.py -q `
  --basetemp "$env:TEMP\quantmesh-0029-task2-green"
& 'C:\Users\15492\Develop\QuantMesh\.venv\Scripts\ruff.exe' check `
  src/quantmesh/instruments/session.py `
  src/quantmesh/instruments/watch_observations.py `
  src/quantmesh/instruments/api.py src/quantmesh/api/workstation.py `
  tests/test_decision_session.py tests/test_packet_monitoring.py
git diff --check
```

Expected: all commands exit 0.

- [ ] **Step 6: Write the refresh-button RED test**

Mock `api.refreshDecisionSession` and assert one click, pending/terminal status,
and Inbox invalidation:

```tsx
await userEvent.click(await screen.findByRole('button', { name: 'Refresh session' }))
expect(mockedRefresh).toHaveBeenCalledTimes(1)
expect(await screen.findByText('2 watches checked · 1 triggered')).toBeVisible()
expect(mockedDecisionInbox).toHaveBeenCalledTimes(2)
```

Also assert the button is keyboard reachable, disables while pending, renders
partial/no-registration reasons, never renders an automatic-refresh timer, and
uses equivalent zh-CN copy.

- [ ] **Step 7: Run frontend RED**

```powershell
Push-Location frontend
npm run test -- --run src/screens/Watchlist.test.tsx
Pop-Location
```

Expected: failure because the client method and button are absent.

- [ ] **Step 8: Add the explicit refresh interaction**

Add the generated client method and one TanStack mutation. Invalidate only the
Decision Inbox query after a successful or partial 200 response:

```tsx
const refresh = useMutation({
  mutationFn: api.refreshDecisionSession,
  onSuccess: async () => {
    await queryClient.invalidateQueries({ queryKey: ['decision-inbox'] })
  },
})
```

Keep the result as transient UI feedback; do not persist it in localStorage or
create polling. Regenerate the API client, then run check:api, focused Vitest,
typecheck and lint.

- [ ] **Step 9: Verify, review, record and commit Slice 2**

Run the Task 2 coherent backend/frontend set and `git diff --check`. Perform at
most two Standards+Spec review rounds focused on idempotency, chronology,
same-origin and absence of operational/order authority. Record exact results in
the iteration ledger. Commit:

```powershell
git add src/quantmesh/instruments/watch_observations.py `
  src/quantmesh/instruments/session.py src/quantmesh/instruments/api.py `
  src/quantmesh/instruments/__init__.py src/quantmesh/api/workstation.py `
  tests/test_decision_session.py tests/test_packet_monitoring.py `
  frontend/src/lib/api.ts frontend/src/api/client.ts `
  frontend/src/screens/Watchlist.tsx frontend/src/screens/Watchlist.test.tsx `
  frontend/src/lib/messages.ts docs/iterations/0029-decision-readiness-session.md `
  docs/goals/ACTIVE.md
git commit -m "feat(decisions): refresh local decision session"
```

---

### Task 3: Compact action queue and exact navigation

**User action:** Filter the refreshed Inbox to Triggered, Blocked, Review due or
No action and open the exact owning packet.

**Stop condition:** All four categories are textual, keyboard operable and
stable at 390 px; no second dashboard, notification or background refresh is
introduced.

**Files:**

- Modify: `frontend/src/screens/Watchlist.tsx`
- Modify: `frontend/src/screens/Watchlist.test.tsx`
- Modify: `frontend/src/lib/messages.ts`
- Modify: `tests/test_instrument_workspace_e2e.py`
- Modify: `docs/iterations/0029-decision-readiness-session.md`
- Modify: `docs/goals/ACTIVE.md`

**Interfaces:**

- Consumes: Task 1 `DecisionInboxEntry.readiness`, existing
  `attention_state`, `decisionPacketPath()` and Task 2 refresh mutation.
- Produces one frontend-only function:

```typescript
type AttentionBucket = 'triggered' | 'blocked' | 'review_due' | 'no_action'

function attentionBucket(entry: DecisionInbox['entries'][number]): AttentionBucket
```

Mapping is exact: `watch_triggered -> triggered`; readiness
`blocked|unavailable` or attention `blocked|unavailable -> blocked`;
`review_available -> review_due`; every other state -> `no_action`.

- [ ] **Step 1: Write action-filter RED tests**

Build a four-row typed fixture and assert counts, `aria-pressed`, filter result
and exact href:

```tsx
expect(await screen.findByRole('button', { name: 'Triggered 1' })).toBeVisible()
await userEvent.click(screen.getByRole('button', { name: 'Blocked 1' }))
expect(screen.getByText('BTC-USD')).toBeVisible()
expect(screen.queryByText('NVDA')).not.toBeInTheDocument()
expect(screen.getByRole('link', { name: 'Open exact packet' })).toHaveAttribute(
  'href',
  '/instruments/hyperliquid/BTC-USD?range=6m&packet=packet-222222222222222222222222',
)
```

Add Tab/Enter keyboard coverage, no-color text checks, filter stability after
query invalidation, and zh-CN labels. Assert no notification permission,
interval or provider wording appears.

- [ ] **Step 2: Run frontend RED**

```powershell
Push-Location frontend
npm run test -- --run src/screens/Watchlist.test.tsx src/lib/messages.test.ts
Pop-Location
```

Expected: action-filter controls are absent.

- [ ] **Step 3: Implement the compact filters**

Add one compact, wrapping button row above the existing separator table. Keep
`all` as the initial view so no item disappears by default. Use native buttons,
`aria-pressed`, visible count text and no animation dependency. Compute buckets
purely from the API row; never alter API priority or packet identity.

```tsx
const visible = bucket === 'all'
  ? inbox.entries
  : inbox.entries.filter((entry) => attentionBucket(entry) === bucket)
```

Preserve the one primary exact/recovery link per row and keep ShadowRecords as
progressive disclosure.

- [ ] **Step 4: Verify frontend and browser behavior**

```powershell
Push-Location frontend
npm run test -- --run src/screens/Watchlist.test.tsx `
  src/screens/NavigationAndValuation.test.tsx src/lib/messages.test.ts
npm run typecheck
npm run lint
npm run build
Pop-Location
& 'C:\Users\15492\Develop\QuantMesh\.venv\Scripts\python.exe' `
  tools/build_frontend.py --check
git diff --check
```

Run the relevant existing packaged-SPA browser selection with a worktree-local
or system-temp basetemp. Verify 390 px has no document-level horizontal
overflow and Tab/Enter opens the exact packet. Run the project-scoped
Impeccable detector once at this demonstrable UI boundary; correct only findings
inside the approved Watchlist session surface.

- [ ] **Step 5: Review, record and commit Slice 3**

Perform at most two review rounds focused on exact mapping, keyboard/a11y,
compact layout and absence of recommendation language. Record evidence, then:

```powershell
git add frontend/src/screens/Watchlist.tsx `
  frontend/src/screens/Watchlist.test.tsx frontend/src/lib/messages.ts `
  src/quantmesh/api/static/app tests/test_instrument_workspace_e2e.py `
  docs/iterations/0029-decision-readiness-session.md docs/goals/ACTIVE.md
git commit -m "feat(ui): focus the daily decision queue"
```

---

### Task 4: Restart-safe two-minute acceptance

**Execution amendment (2026-09-08):** Deliver this parent slice in two bounded
implementation steps without changing its interfaces or acceptance semantics.
Task 4A owns durable API/restart, read-only snapshots, chronology and
fail-closed degradation tests. Task 4B owns the packaged-browser journey and
the one coherent 0029 gate. The parent Task 4 receives one review at the
combined demonstrable boundary; neither step opens a new product scope or a
separate broad review loop.

**User action:** Complete the entire deterministic NVDA/AAPL daily session and
reopen its exact results after a clean application reconstruction.

**Stop condition:** Browser and API acceptance prove the flow in under two
minutes, BTC/SOL degradation and corrupt/stale cases fail closed, and all
slice-level checks pass.

**Files:**

- Create: `tests/test_decision_session_e2e.py`
- Modify: `tests/test_decision_session.py`
- Modify: `tests/test_decision_inbox.py`
- Modify: `frontend/src/screens/Watchlist.test.tsx`
- Modify: `docs/iterations/0029-decision-readiness-session.md`
- Modify: `docs/goals/ACTIVE.md`

**Interfaces:**

- Consumes every Task 1–3 public contract without adding production APIs.
- Produces only acceptance evidence and any strictly test-discovered bounded
  correction required for those contracts.

- [ ] **Step 1: Write the restart/API acceptance RED test**

Create one root, save Watch packets for NVDA/AAPL, register deterministic
conditions, refresh, destroy the app, rebuild from the same root and compare:

```python
before = client.post("/api/decision-session/refresh").json()
before_inbox = client.get("/api/decision-packets").json()
restarted = create_demo_app(root=root, seed=SCENARIO.seed, host="127.0.0.1")
with TestClient(restarted) as client:
    after_inbox = client.get("/api/decision-packets").json()
assert _durable_ids(after_inbox) == _durable_ids(before_inbox)
assert before["registered_count"] == 2
assert before["evaluated_count"] == 2
```

Add exact real-catalog mismatch, catalog absent, stale quote, newer-sequence
trigger, one-item partial failure and BTC/SOL missing-evidence cases. Snapshot
filesystem bytes around Inbox GET and prove only watch-evaluation files may
change around refresh POST.

- [ ] **Step 2: Run acceptance RED**

```powershell
& 'C:\Users\15492\Develop\QuantMesh\.venv\Scripts\python.exe' -m pytest `
  tests/test_decision_session_e2e.py -q `
  --basetemp "$env:TEMP\quantmesh-0029-task4-red"
```

Expected: the new acceptance file fails on the first uncovered contract or is
RED until the final Task 1–3 behavior exists.

- [ ] **Step 3: Add the real packaged browser acceptance**

Drive the user-visible route, not direct internal calls:

```python
started = time.perf_counter()
page.goto(f"{base_url}/app/markets/watchlist")
page.get_by_role("button", name="Refresh session").click()
page.get_by_role("button", name=re.compile("Triggered|Blocked|Review due")).first.click()
with page.expect_navigation():
    page.get_by_role("link", name="Open exact packet").first.click()
assert time.perf_counter() - started < 120
```

Assert exact `packet` query identity, readiness/last-check/mark text,
English/zh-CN, keyboard path, 390 px overflow, partial feedback and absence of
real/provider/automatic wording. Reconstruct the app and repeat the exact link
check without re-registering conditions.

- [ ] **Step 4: Run the coherent 0029 acceptance gate**

```powershell
& 'C:\Users\15492\Develop\QuantMesh\.venv\Scripts\python.exe' -m pytest `
  tests/test_decision_readiness.py tests/test_decision_session.py `
  tests/test_decision_session_e2e.py tests/test_decision_inbox.py `
  tests/test_packet_monitoring.py tests/test_instrument_workspace_api.py `
  tests/test_instrument_workspace_e2e.py -q `
  --basetemp "$env:TEMP\quantmesh-0029-task4-final"
Push-Location frontend
npm run check:api
npm run test -- --run
npm run typecheck
npm run lint
npm run build
Pop-Location
& 'C:\Users\15492\Develop\QuantMesh\.venv\Scripts\ruff.exe' check `
  src tests tools
& 'C:\Users\15492\Develop\QuantMesh\.venv\Scripts\python.exe' `
  tools/build_frontend.py --check
git diff --check
```

Expected: every command exits 0. Record exact counts, duration, warnings and
the measured user-flow duration. Do not substitute targeted success for a
failed coherent selection.

- [ ] **Step 5: Final slice review and commit**

Run Quant Researcher, Standards and Spec review at the demonstrable slice
boundary. The same two-round maximum applies; a third structural issue shrinks
the design rather than extending patch loops. Commit only reviewed acceptance
and bounded corrections:

```powershell
git add tests/test_decision_session_e2e.py tests/test_decision_session.py `
  tests/test_decision_inbox.py frontend/src/screens/Watchlist.test.tsx `
  docs/iterations/0029-decision-readiness-session.md docs/goals/ACTIVE.md `
  src frontend/src frontend/src/api/client.ts src/quantmesh/api/static/app
git commit -m "test(decisions): prove restart-safe daily session"
```

---

### Task 5: Exact-head integration, PR and iteration closeout

**User action:** Receive one reviewed, reproducible merged iteration rather
than an unverified local branch.

**Stop condition:** The final exact head passes release gate and CI, the
implementation PR is merged, issue #131 closes, main CI is green, and the
iteration/Goal state agrees. Do not mark complete before all evidence exists.

**Files:**

- Modify: `docs/iterations/0029-decision-readiness-session.md`
- Modify: `docs/goals/ACTIVE.md`
- Modify: `docs/roadmap/ROADMAP.md` only if completion wording is not already
  correct at the candidate head

**Interfaces:**

- Consumes the exact reviewed Task 1–4 commits and repository release harness.
- Produces one final PR, merge commit, post-merge CI evidence and completed Goal.

- [ ] **Step 1: Audit the branch against the approved specification**

For every spec section, point to its production contract and test. Confirm no
code or documentation under the 0021 repair branch, Scheduler, automation,
Provider/OpenD runner, soak root or witness path changed. Check:

```powershell
git diff --name-status origin/main...HEAD
git diff --check origin/main...HEAD
git status --short --branch
git submodule status
```

Expected: only approved 0029/product/docs/test files differ; worktree is clean
after the closeout documentation commit.

- [ ] **Step 2: Record the final candidate before the expensive gate**

Update the iteration ledger and Active Goal with completed slice results,
remaining warnings and the exact next gate. Commit those docs so the release
gate verifies the same tree that will be pushed:

```powershell
git add docs/iterations/0029-decision-readiness-session.md `
  docs/goals/ACTIVE.md docs/roadmap/ROADMAP.md
git commit -m "docs: prepare iteration 0029 integration"
git rev-parse HEAD
git status --short
```

Expected: one exact candidate SHA and a clean worktree.

- [ ] **Step 3: Run the one exact-head clean release gate**

Keep the process handle and poll the same session until its final exit; never
restart because output is delayed.

```powershell
$env:PYTHONPATH = (Resolve-Path .\src).Path
& 'C:\Users\15492\Develop\QuantMesh\.venv\Scripts\python.exe' `
  tools/release_gate.py
```

Expected: all release steps pass, including constrained dependency/license
closure, PowerShell parse, frontend, full pytest, golden path and clean-checkout
invariants. Record exact test totals, duration and exit code. If it fails, stop
and preserve the precise evidence; diagnose before proposing a bounded repair.

- [ ] **Step 4: Push and open the implementation PR**

```powershell
git push origin codex/0029-decision-readiness-session
gh pr create --repo ZP151/quantmesh `
  --base main `
  --head codex/0029-decision-readiness-session `
  --title "Iteration 0029: Decision Readiness Session" `
  --body "Closes #131. Adds exact read-only readiness, explicit local watch refresh, compact attention queue, restart/two-minute acceptance, and no 0021 or execution authority."
```

Wait for exact-head CI and inspect every check. Address only bounded findings,
with at most two final review rounds; any code change creates a new exact head
and requires the final relevant gate/CI evidence for that head.

- [ ] **Step 5: Merge and verify main**

After exact-head CI and review are green, merge through the repository's normal
protected-branch flow without force-push. Read back the PR merge commit and
wait for post-merge main CI. Then append the immutable merge/CI evidence to the
iteration ledger on a follow-up branch/PR only if protected-main policy
requires it; do not make an unreviewed direct main commit.

Confirm:

```powershell
gh pr view --repo ZP151/quantmesh --json state,mergedAt,mergeCommit,url
gh issue view 131 --repo ZP151/quantmesh --json state,labels,url
git ls-remote origin refs/heads/main
```

Expected: PR merged, issue closed, remote main at the returned merge commit and
post-merge CI green. Only then mark the active Goal complete.
