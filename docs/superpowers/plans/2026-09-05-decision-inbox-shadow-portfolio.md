# Decision Inbox & Bounded Paper Shadow Portfolio Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:subagent-driven-development` (recommended) or
> `superpowers:executing-plans` to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn Watchlist into an exact-packet Decision Inbox, prove the
deterministic loop for NVDA and AAPL, preserve honest Reject/Watch-only
degradation for BTC-USD and SOL-USD, and show a bounded paper/order/position/
monitoring/review summary that survives clean restart.

**Architecture:** Add one read-only `instruments` query service that projects
existing replay-validated stores without persisting a second aggregate. Expose
it at `GET /api/decision-packets`, let Watchlist deep-link with an exact
`packet` query parameter, and make Instrument Workspace treat that identity as
authoritative. Reuse `DecisionOutcomeReviewService.preview()` for exact
proposal/order/watch/review binding; current marks and positions remain context.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, durable JSONL, React 19,
TypeScript 5.9, TanStack Query, React Router, Vitest, Playwright, Ruff, Oxlint.

**Spec:**
`docs/superpowers/specs/2026-09-05-decision-inbox-shadow-portfolio-design.md`

## Global Constraints

- Work only in `C:\Users\15492\Develop\QuantMesh-iteration-0028` on
  `codex/0028-decision-inbox-shadow-portfolio`.
- Preserve exact packet, proposal, order, watch-evaluation, outcome and review
  identities. Never replace an explicit ID with context-wide latest state.
- The Inbox is read-only and owns no JSONL, proposal, order, watch, review or
  account mutation.
- AI and current marks never determine attention priority or Paper capability.
- Paper remains two-stage through existing quote/freshness/risk authority.
- Only NVDA and AAPL are complete Paper cases. BTC-USD and SOL-USD may save
  Reject and Watch but stay Paper-blocked without qualified evidence.
- No Provider/OpenD calls, real/testnet execution, external notification,
  Scheduler, new model framework, broad performance dashboard or 0021 work.
- Use RED → GREEN → REFACTOR for production behavior. If a new acceptance test
  is already green because behavior exists, record it and avoid gratuitous code.
- Use targeted checks during tasks, broad checks at coherent slice commits,
  and one final exact-head gate. Review each slice at most twice.
- Preserve en/zh-CN key parity, reduced motion, keyboard access and 390px no
  document overflow.

---

### Task 1: Read-only Decision Inbox projection and API

**Slice:** 1, backend half.

**Files:**

- Create: `src/quantmesh/instruments/inbox.py`
- Modify: `src/quantmesh/instruments/__init__.py`
- Modify: `src/quantmesh/instruments/api.py`
- Modify: `src/quantmesh/api/workstation.py`
- Create: `tests/test_decision_inbox.py`
- Modify: `tests/test_decision_packet_api.py`

**Interfaces:**

- Produces `DecisionAttentionState`, `DecisionInboxMarkContext`,
  `DecisionInboxPaperSummary`, `DecisionInboxPositionContext`,
  `DecisionInboxMonitoringSummary`, `DecisionInboxReviewSummary`,
  `DecisionInboxEntry`, `DecisionInbox`, `DecisionInboxError`, and
  `DecisionInboxService.snapshot() -> DecisionInbox`.
- The service consumes provider callables for current app-state stores so demo
  reset cannot leave it attached to replaced roots.
- Adds `GET /decision-packets`; the double mount exposes
  `/api/decision-packets` beside the existing POST.

- [x] **Step 1: Write RED service and API tests**

Use real demo stores and API calls. Pin the highest-risk selection rule:

```python
def test_inbox_is_read_only_and_pending_action_beats_newer_draft(tmp_path: Path) -> None:
    root = tmp_path / "demo"
    app = create_demo_app(root=root, seed=SCENARIO.seed, host="127.0.0.1")
    with TestClient(app) as client:
        pending = _save_and_act(client, "NVDA", disposition="paper_proposal")
        before = _owned_bytes(root)
        app.state.instrument_workspace._now = lambda: SCENARIO.anchor + timedelta(minutes=1)
        newer = _save_draft(client, "NVDA")
        response = client.get("/api/decision-packets")
        after = _owned_bytes(root)

    nvda = _entry(response.json(), "moomoo", "NVDA")
    assert nvda["packet_id"] == pending["packet"]["packet_id"]
    assert nvda["packet_id"] != newer["packet_id"]
    assert nvda["attention_state"] == "paper_pending_confirmation"
    assert before == after
```

Also assert `not_started`, venue-less `unavailable`, Reject=`rejected`,
Watch=`watching`, draft=`draft`, missing proposal link=`unavailable`, corrupt
packet JSONL=HTTP 409 with code `decision_inbox_replay_unavailable`, configured
untimestamped mark=unavailable freshness, and
`position_context.attribution == "current-account-context-only"`.

- [x] **Step 2: Run RED**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_decision_inbox.py tests/test_decision_packet_api.py -q
```

Expected: import/route failures because the Inbox does not exist.

- [x] **Step 3: Implement strict contracts**

Use frozen, strict Pydantic models. The core public shape is:

```python
class DecisionAttentionState(StrEnum):
    BLOCKED = "blocked"
    WATCH_TRIGGERED = "watch_triggered"
    PAPER_PENDING_CONFIRMATION = "paper_pending_confirmation"
    REVIEW_AVAILABLE = "review_available"
    PAPER_OPEN = "paper_open"
    WATCHING = "watching"
    REVIEWED = "reviewed"
    REJECTED = "rejected"
    DRAFT = "draft"
    NOT_STARTED = "not_started"
    UNAVAILABLE = "unavailable"


class DecisionInboxEntry(_Contract):
    venue: Venue | None
    symbol: str
    instrument_type: InstrumentType | None = None
    attention_state: DecisionAttentionState
    attention_reason: str
    packet_id: str | None = None
    parent_packet_id: str | None = None
    selected_range: HistoryRange | None = None
    disposition: DecisionDisposition | None = None
    evidence_status: Literal["complete", "partial", "pending", "unavailable"] | None = None
    mark_context: DecisionInboxMarkContext
    paper: DecisionInboxPaperSummary | None = None
    position_context: DecisionInboxPositionContext | None = None
    monitoring: DecisionInboxMonitoringSummary | None = None
    review: DecisionInboxReviewSummary | None = None
```

Require safe reasons for blocked/unavailable and canonical IDs everywhere.
`DecisionInboxError` carries a literal machine code plus a safe message; it
must never include filesystem paths or raw record text.

- [x] **Step 4: Implement deterministic selection and enrichment**

Read stores once, group by `(venue, symbol)`, resolve candidates without
writes, and select in two tiers. First, terminal actions requiring attention
win by the fixed priority unavailable, blocked, watch-triggered, pending-Paper,
review-available, then descending `(as_of, created_at, version, packet_id)`.
Otherwise, paper-open, watching, reviewed and rejected terminal actions compete
solely by that descending recency key. Drafts are considered only when no
terminal action exists.

At the Slice 1 boundary, resolve core packet/proposal states only: draft,
rejected, watching, pending Paper, blocked/rejected proposal, confirmed/open and
unavailable linkage. Leave `evidence_status`, monitoring and review summaries
absent; Task 5 completes them without changing the public contract. For pending
Paper, resolve the exact forecast and call `forecast_freshness_blocker`; keep
the label neutral and state any current blocker in the reason.

Use `LiveFeed.snapshot_exact` plus `QuoteFence.resolve` only as a local read.
Configured fallback marks retain their numeric display but say
`configured mark has no freshness evidence`. Compute current position context
only from the exact venue/symbol account key and an allowed mark.

- [x] **Step 5: Wire current app state and GET route**

Construct `app.state.decision_inbox` after packet/review services. Pass dynamic
providers:

```python
watchlist_provider=lambda: (
    app.state.page_context.watchlist.all()
    if app.state.page_context.watchlist is not None else []
),
packet_store_provider=lambda: getattr(app.state, "decision_packets", None),
review_service_provider=lambda: getattr(app.state, "packet_reviews", None),
account_provider=account_store.get,
markets_provider=lambda: app.state.page_context.markets,
now=clock,
```

The route returns 404 when absent and maps replay/identity failures to a 409
`DecisionInboxError(code="decision_inbox_replay_unavailable", ...)`.

- [x] **Step 6: Run GREEN and commit**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_decision_inbox.py tests/test_decision_packet_api.py tests/test_demo_reset_runtime.py -q
.\.venv\Scripts\ruff.exe check src/quantmesh/instruments/inbox.py src/quantmesh/instruments/api.py src/quantmesh/api/workstation.py tests/test_decision_inbox.py tests/test_decision_packet_api.py
git diff --check
git add src/quantmesh/instruments/inbox.py src/quantmesh/instruments/__init__.py src/quantmesh/instruments/api.py src/quantmesh/api/workstation.py tests/test_decision_inbox.py tests/test_decision_packet_api.py
git commit -m "feat: add read-only decision inbox projection"
```

---

### Task 2: Watchlist Decision Inbox and exact packet deep-link

**Slice:** 1, visible boundary.

**Files:**

- Modify/generated: `frontend/src/api/client.ts`
- Modify: `frontend/src/lib/api.ts`
- Modify: `frontend/src/lib/instrument-route.ts`
- Modify: `frontend/src/lib/messages.ts`
- Modify: `frontend/src/screens/Watchlist.tsx`
- Create: `frontend/src/screens/Watchlist.test.tsx`
- Modify: `frontend/src/screens/InstrumentWorkspace.tsx`
- Modify: `frontend/src/screens/InstrumentWorkspace.test.tsx`
- Modify: `tests/test_spa_e2e.py`
- Modify/generated: `src/quantmesh/api/static/app/`
- Modify: `docs/iterations/0028-decision-inbox-shadow-portfolio.md`

**Interfaces:**

- Consumes `GET /api/decision-packets` from Task 1.
- Produces `api.decisionInbox()`,
  `decisionPacketPath(venue, symbol, range, packetId)`, and exact URL selection
  through `?range=<range>&packet=<packet_id>`.

- [x] **Step 1: Write frontend RED tests**

Use a typed fixture with NVDA pending Paper, AAPL not started and a venue-less
unavailable row:

```tsx
expect(await screen.findByRole('link', { name: /Open exact packet/i }))
  .toHaveAttribute(
    'href',
    '/instruments/moomoo/NVDA?range=6m&packet=packet-111111111111111111111111',
  )
expect(screen.getByText('Pending confirmation')).toBeInTheDocument()
expect(screen.getByText('Identity unavailable')).toBeInTheDocument()
```

Add Instrument Workspace cases that open an explicit packet, refuse 404 and
venue/symbol/range mismatch without fallback, keep the exact ID during a
background refresh, update the URL to an action child, and remove `packet` on
“New analysis”.

- [x] **Step 2: Run frontend RED**

```powershell
Set-Location frontend
npm exec vitest -- run src/screens/Watchlist.test.tsx src/screens/InstrumentWorkspace.test.tsx
```

Expected: failures for missing generated GET type, wrapper, route helper and
URL-authoritative selection.

- [x] **Step 3: Generate and wrap the OpenAPI client**

```powershell
Set-Location frontend
npm run generate:api
```

Export `DecisionInbox` and add:

```typescript
async decisionInbox(): Promise<DecisionInbox> {
  const { data, error, response } = await generatedApi.GET('/api/decision-packets')
  if (!response.ok || data === undefined) throw generatedApiError(response, error)
  return data
},
```

- [x] **Step 4: Implement the compact Watchlist surface**

Use `api.decisionInbox` as the screen source. Keep one semantic desktop table
and responsive cells below `sm`; add no nested decorative dashboard cards.
Show symbol/venue, contextual mark status, decision state, short reason and one
exact primary link. Defer expanded paper/watch/review details to Task 5. Add
English and Simplified-Chinese keys for every state.

```typescript
export function decisionPacketPath(
  venue: string,
  symbol: string,
  range: HistoryRange,
  packetId: string,
): string {
  const query = new URLSearchParams({ range, packet: packetId })
  return `${instrumentPath(venue, symbol)}?${query.toString()}`
}
```

Teach `generatedApiError` to read either the existing string `detail` or the
new typed `{code, message}` detail without changing status handling.

- [x] **Step 5: Make exact URL selection authoritative**

Parse `requestedPacketId = search.get('packet')`. While its exact query is
pending, do not render workspace latest. On 404 or context mismatch, render
`WorkspaceError`. When exact data matches `venue:symbol:selected_range`, derive
the active persisted selection from it. Action results replace the URL packet
with the child ID; “New analysis” removes it. Background workspace refresh must
not replace the explicit packet.

- [x] **Step 6: Run GREEN and Slice 1 E2E**

```powershell
Set-Location frontend
npm exec vitest -- run src/screens/Watchlist.test.tsx src/screens/InstrumentWorkspace.test.tsx src/lib/messages.test.ts
npm run check:api
npm run typecheck
npm run lint
npm run build
Set-Location ..
.\.venv\Scripts\python.exe -m pytest tests/test_decision_inbox.py tests/test_spa_e2e.py -k "decision_inbox or exact_packet" -q
git diff --check
```

- [x] **Step 7: Commit and review Slice 1**

```powershell
git add frontend/src/api/client.ts frontend/src/lib/api.ts frontend/src/lib/instrument-route.ts frontend/src/lib/messages.ts frontend/src/screens/Watchlist.tsx frontend/src/screens/Watchlist.test.tsx frontend/src/screens/InstrumentWorkspace.tsx frontend/src/screens/InstrumentWorkspace.test.tsx src/quantmesh/api/static/app tests/test_spa_e2e.py docs/iterations/0028-decision-inbox-shadow-portfolio.md
git commit -m "feat: surface exact decision inbox"
```

Run one Standards+Spec review against `09fd169`. Correct only Critical or
Important findings; the second review is final. A third structural failure
shrinks the slice.

---

### Task 3: AAPL deterministic decision and pending Paper path

**Slice:** 2.

**Files:**

- Modify: `src/quantmesh/demo/seeder.py`
- Modify: `tests/test_demo_instrument_workspace.py`
- Modify: `tests/test_demo.py`
- Modify: `tests/test_spa_e2e.py`
- Modify: `docs/iterations/0028-decision-inbox-shadow-portfolio.md`

**Interfaces:**

- Reuses every DecisionPacket/API/UI contract from Slice 1.
- Changes only deterministic demo evidence: AAPL receives the same 650-session
  analytical history used by the existing drift-conformal pipeline. No new
  model, provider or adapter is introduced.

- [x] **Step 1: Write AAPL RED acceptance tests**

Change the existing seed assertion from intentionally ineligible to eligible,
then exercise AAPL Reject, Watch and pending Paper in independent roots:

```python
assert aapl.history_sessions == 650
assert aapl.eligible is True
assert aapl.blockers == ()
```

For pending Paper, assert proposal status is `pending`, `order_id is None`, and
the account/journal order count is unchanged. Measure ticker-to-saved-action
with `perf_counter()` and require less than 120 seconds. Add one browser path
from the AAPL Inbox row to a saved Watch, reload, and the same exact packet ID.

- [x] **Step 2: Run RED**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_demo_instrument_workspace.py tests/test_demo.py tests/test_spa_e2e.py -k "AAPL or seeded_demo_has_deep_history" -q
```

Expected: AAPL's current 420-session forecast is ineligible and Paper blocked.

- [x] **Step 3: Make the minimal deterministic seed correction**

Stop truncating AAPL daily analytical history to 420 rows. Run AAPL and NVDA
from the same manifest constant:

```python
for symbol in ("AAPL", "NVDA"):
    series = _forecast_series(
        lake_root,
        scenario=scenario,
        symbol=symbol,
        sessions=HISTORICAL_DAILY_SESSIONS,
    )
```

Update row-count/provenance assertions only where actual deterministic output
changes. Never hand-author eligibility or copy NVDA artifacts.

- [x] **Step 4: Run GREEN, commit and review Slice 2**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_demo_instrument_workspace.py tests/test_demo.py tests/test_demo_reset_runtime.py -q
.\.venv\Scripts\python.exe -m pytest tests/test_spa_e2e.py -k "AAPL" -q
.\.venv\Scripts\ruff.exe check src/quantmesh/demo/seeder.py tests/test_demo_instrument_workspace.py tests/test_demo.py tests/test_spa_e2e.py
git diff --check
git add src/quantmesh/demo/seeder.py tests/test_demo_instrument_workspace.py tests/test_demo.py tests/test_spa_e2e.py docs/iterations/0028-decision-inbox-shadow-portfolio.md
git commit -m "feat: extend decision loop to AAPL"
```

Review once against the Slice 1 commit; one correction review is the maximum.

---

### Task 4: Honest BTC/SOL Reject/Watch-only degradation

**Slice:** 3.

**Files:**

- Modify: `tests/test_demo_instrument_workspace.py`
- Modify: `frontend/src/screens/Watchlist.test.tsx`
- Modify: `tests/test_spa_e2e.py`
- Modify/generated: `src/quantmesh/api/static/app/`
- Modify only if RED proves a visible gap: `frontend/src/lib/messages.ts`
- Modify only if RED proves a visible gap: `frontend/src/screens/Watchlist.tsx`
- Modify only if RED proves a visible gap: `frontend/src/screens/InstrumentWorkspace.tsx`
- Modify: `docs/iterations/0028-decision-inbox-shadow-portfolio.md`

**Interfaces:**

- Reuses forecast-missing/history-quality blockers and creates no forecast,
  manifest, quality evaluation, proposal or order for BTC-USD/SOL-USD.

- [ ] **Step 1: Write the bounded acceptance matrix**

Parameterize BTC-USD/SOL-USD × Reject/Watch across independent demo roots:

```python
assert draft["evidence"]["forecast_artifact_id"] is None
assert "forecast-missing" in {
    item["code"] for item in draft["paper_capability"]["blockers"]
}
assert draft["paper_capability"]["allowed"] is False
assert paper_response.status_code == 409
assert action_response.json()["packet"]["disposition"] == disposition
assert app.state.proposal_service.ledger.all() == ()
assert app.state.account_store.get().orders == orders_before
```

Add one 390px browser walk that opens each crypto Inbox row, reads the Paper
blocker, confirms Reject/Watch remain enabled, saves Watch, reloads its exact ID,
and asserts `document.documentElement.scrollWidth <= window.innerWidth`.

- [ ] **Step 2: Run the matrix and classify RED honestly**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_demo_instrument_workspace.py tests/test_spa_e2e.py -k "BTC or SOL or crypto_degraded" -q
Set-Location frontend
npm exec vitest -- run src/screens/Watchlist.test.tsx
Set-Location ..
```

If all new assertions are already green, record that the existing domain plus
Slice 1 UI satisfies the requirement and make no production change. Otherwise,
confirm the failure is the intended missing visible state, then expose existing
blockers with the smallest UI/copy correction while keeping Paper disabled.

- [ ] **Step 3: Run GREEN, commit and review Slice 3**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_demo_instrument_workspace.py tests/test_decision_inbox.py tests/test_spa_e2e.py -k "BTC or SOL or crypto_degraded" -q
Set-Location frontend
npm exec vitest -- run src/screens/Watchlist.test.tsx src/screens/InstrumentWorkspace.test.tsx src/lib/messages.test.ts
npm run typecheck
npm run lint
Set-Location ..
.\.venv\Scripts\ruff.exe check tests/test_demo_instrument_workspace.py tests/test_spa_e2e.py
git diff --check
git add tests/test_demo_instrument_workspace.py frontend/src/screens/Watchlist.test.tsx tests/test_spa_e2e.py frontend/src/lib/messages.ts frontend/src/screens/Watchlist.tsx frontend/src/screens/InstrumentWorkspace.tsx docs/iterations/0028-decision-inbox-shadow-portfolio.md
git commit -m "test: prove evidence-blocked crypto decisions"
```

Review once; a second review is final.

---

### Task 5: Bounded paper shadow summary and clean-restart replay

**Slice:** 4.

**Files:**

- Modify: `src/quantmesh/instruments/inbox.py`
- Modify: `tests/test_decision_inbox.py`
- Modify: `frontend/src/lib/messages.ts`
- Modify: `frontend/src/screens/Watchlist.tsx`
- Modify: `frontend/src/screens/Watchlist.test.tsx`
- Modify: `tests/test_spa_e2e.py`
- Modify: `docs/iterations/0028-decision-inbox-shadow-portfolio.md`

**Interfaces:**

- Consumes exact `DecisionOutcomeReviewState.outcome.paper`, `.monitoring` and
  `.review`, plus current venue-scoped paper-account position context.
- Produces compact proposal/order/watch/review IDs and status facts. Exact order
  fill quantity is attributable; aggregate position/P&L is context only.

- [ ] **Step 1: Write backend RED exact-binding tests**

Use independent roots to pin:

```text
pending proposal        -> paper_pending_confirmation, proposal ID, no order ID
risk-rejected order     -> blocked, exact proposal and rejected order IDs
confirmed filled order  -> paper_open, exact proposal/order IDs and fill quantity
triggered Watch         -> watch_triggered, registration/evaluation/event IDs
saved review            -> reviewed, exact outcome and review IDs
```

Advance the injected clock after a pending proposal becomes stale and assert
the state remains neutral pending while its reason says confirmation currently
fails freshness. Tamper a linked proposal/order ID and assert unavailable,
never fallback. Recreate `create_demo_app` over the same root and assert stable
packet/proposal/order/watch/outcome/review IDs and states. Assert the current
position label remains `current-account-context-only`.

- [ ] **Step 2: Run backend RED**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_decision_inbox.py -k "paper or watch or review or restart" -q
```

Expected: final detail fields or attention mappings are absent from Slice 1.

- [ ] **Step 3: Complete summary derivation**

Reuse the review preview's validated `PaperOutcome` and `MonitoringOutcome`;
do not create weaker duplicate bindings. Return only compact immutable IDs,
statuses, fill quantity and trigger event IDs. Current position and unrealized
P&L stay visibly non-attributable.

- [ ] **Step 4: Write frontend RED, then implement GREEN**

Test a compact disclosure beneath decision status for proposal ID/status, order
ID/status, watch evaluation/event, outcome/review IDs and position-context
warning. IDs are monospace and safely wrap. Assert no Sharpe, ranking,
aggregate return or invented closed P&L text exists.

```powershell
Set-Location frontend
npm exec vitest -- run src/screens/Watchlist.test.tsx src/lib/messages.test.ts
npm run typecheck
npm run lint
npm run build
Set-Location ..
```

- [ ] **Step 5: Prove restart, exact navigation and responsive behavior**

Add one browser E2E that confirms an NVDA proposal, saves its review, restarts
from the same root, then checks the same packet/proposal/order/outcome/review IDs
in Watchlist before following the exact link. Include AAPL pending Paper in the
same read-only Inbox request without confirming it. At 390px/reduced motion,
assert keyboard access and no document overflow.

Run the Impeccable detector exactly once after all UI edits:

```powershell
node C:\Users\15492\Develop\QuantMesh\.codex\skills\impeccable\scripts\detect.mjs --json frontend/src/screens/Watchlist.tsx frontend/src/screens/InstrumentWorkspace.tsx
```

Fix only findings inside the changed surfaces.

- [ ] **Step 6: Run GREEN, commit and review Slice 4**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_decision_inbox.py tests/test_decision_packet_api.py tests/test_packet_monitoring.py tests/test_packet_reviews.py tests/test_demo_instrument_workspace.py -q
.\.venv\Scripts\python.exe -m pytest tests/test_spa_e2e.py -k "decision_inbox or shadow" -q
Set-Location frontend
npm exec vitest -- run src/screens/Watchlist.test.tsx src/screens/InstrumentWorkspace.test.tsx src/lib/messages.test.ts
npm run check:api
npm run typecheck
npm run lint
Set-Location ..
.\.venv\Scripts\ruff.exe check src tests tools
git diff --check
git add src/quantmesh/instruments/inbox.py tests/test_decision_inbox.py frontend/src/lib/messages.ts frontend/src/screens/Watchlist.tsx frontend/src/screens/Watchlist.test.tsx src/quantmesh/api/static/app tests/test_spa_e2e.py docs/iterations/0028-decision-inbox-shadow-portfolio.md
git commit -m "feat: add bounded paper shadow summary"
```

Review once with at most one correction round.

---

### Task 6: Iteration evidence, license closure and final exact-head gate

**Slice:** final integration boundary; no new product behavior.

**Files:**

- Modify only on actual tool evidence: `tools/license_review.py`
- Modify only with matching evidence: `docs/licenses.md`
- Modify: `docs/goals/ACTIVE.md`
- Modify: `docs/iterations/0028-decision-inbox-shadow-portfolio.md`
- Modify: `docs/iterations/INDEX.md`
- Modify: `docs/roadmap/ROADMAP.md`

- [ ] **Step 1: Run and, only if needed, repair license closure**

```powershell
.\.venv\Scripts\python.exe tools/license_review.py
.\.venv\Scripts\python.exe tools/npm_license_review.py
```

If refused, inspect the installed package metadata and shipped license, then
update the exact allowlist and `docs/licenses.md` with matching package,
version, license and justification. Never broadly allow `UNKNOWN`.

- [ ] **Step 2: Run one broad pre-PR verification**

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\ruff.exe check src tests tools
Set-Location frontend
npm run check:api
npm run typecheck
npm run lint
npm exec vitest -- run
npm run build
Set-Location ..
git diff --check
git submodule status
```

Read every exit code and final statistic. Diagnose any in-scope regression and
repair it only after a reproducing RED test.

- [ ] **Step 3: Record evidence and commit the iteration checkpoint**

Record command, exit code, test count, duration, exact parent HEAD and retained
warnings. Mark roadmap/index complete only after behavior and checks are green.

```powershell
git add docs/goals/ACTIVE.md docs/iterations/0028-decision-inbox-shadow-portfolio.md docs/iterations/INDEX.md docs/roadmap/ROADMAP.md tools/license_review.py docs/licenses.md
git commit -m "docs: complete iteration 0028 verification"
```

- [ ] **Step 4: Run the single exact-head release gate**

```powershell
$candidate = (git rev-parse HEAD).Trim()
.\.venv\Scripts\python.exe tools/release_gate.py
if ((git rev-parse HEAD).Trim() -ne $candidate) { throw "HEAD changed during gate" }
git status --short
```

Preserve the long-command session handle and read its final exit code. Do not
rerun the release gate unless candidate SHA changes.

- [ ] **Step 5: Push and open the one milestone PR**

Push `codex/0028-decision-inbox-shadow-portfolio`, open one PR linked to #129,
and wait for exact-head CI. Do not merge until CI and human review are green.
Complete the Goal only after an objective-by-objective audit proves every
requirement and repository evidence agrees.
