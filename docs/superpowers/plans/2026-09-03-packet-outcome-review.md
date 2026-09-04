# Packet Outcome Review Implementation Plan

**Goal:** let an operator reopen one exact persisted NVDA action packet, inspect
an honest local outcome/paper-risk attribution, and atomically save one
restart-safe review without changing any trading authority.

**Scope:** one 24–48 hour vertical slice. Use targeted TDD during implementation,
one combined boundary review with at most one correction round, then one broad
slice gate. Python license closure remains the separate final-PR task.

**Forbidden:** Provider/OpenD, real trading, new/exit orders, external
notifications, schedulers, AI review, performance dashboards, other symbols,
0021 soak, packet schema/identity changes, model-framework work, and side-defect
expansion.

## Step 1 — Outcome/review contracts and store

- [x] Start RED in `tests/test_packet_reviews.py` for strict immutable contracts,
  canonical outcome/review IDs, one review per exact action packet, idempotence,
  conflict, corruption and clean-restart replay.
- [x] Implement `src/quantmesh/instruments/reviews.py` with a single atomic
  `DecisionReviewRecord` append that embeds the outcome snapshot.
- [x] Validate exact non-draft action packet and root analysis lineage; never use
  `latest`, a workspace draft, or a recomposed packet as authority.
- [x] Prove packet, proposal, order, monitoring, account and Copilot ledgers are
  byte-identical before and after preview/save.

Targeted command:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_packet_reviews.py -q --basetemp .superpowers/sdd/2026-09-03-packet-outcome-review/pytest-domain
```

## Step 2 — Honest local attribution

- [x] Bind the exact 30-session forecast target/calendar; missing binding is
  unavailable and never falls back to weekdays or another path.
- [x] Freeze strictly ordered post-decision daily OHLC evidence with provenance
  and digest. Reject future knowledge, wrong instruments, gaps and incompatible
  evidence.
- [x] Implement the disclosed close-based Bull/Base/Bear threshold observations,
  strict equality boundaries, first-observed times and same-bar ambiguity. Keep
  narrative triggers and Bear invalidation explicitly unavailable.
- [x] Separate planned R, gross path R, entry-fill deviation, mark-to-market R
  and realized R. Realized R stays unavailable without proposal-bound exit fills,
  attributable quantity and complete fees.
- [x] Read exact proposal/order/fill/risk-refusal and monitoring records without
  invoking confirmation, recovery, monitoring evaluation or any external call.
- [x] Cover Reject, Watch, pending/blocked, risk-rejected, accepted-unfilled and
  filled-open states. Event absence must not claim full-horizon non-trigger.

## Step 3 — Read-only preview and atomic save API

- [x] Add GET/POST on
  `/api/decision-packets/{packet_id}/outcome-review` with generated contracts.
- [x] GET is read-only. POST accepts only expected outcome identity,
  classification and note; it recomposes under the injected clock and returns
  409 on drift, conflict or corruption.
- [x] Apply exact scheme/host/port same-origin browser protection and the existing
  explicit absent-Origin non-browser exception.
- [x] Wire normal and demo runtimes under `decisions/reviews`; seed ownership and
  reset files; reconstruct the app on the same root and reopen identical state.
- [x] Keep missing evidence typed unavailable. Unknown packet is 404; draft or
  invalid classification is 409/422 as appropriate.

Targeted command:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_packet_reviews.py tests/test_decision_packet_api.py tests/test_runtime.py -q --basetemp .superpowers/sdd/2026-09-03-packet-outcome-review/pytest-api
```

## Step 4 — Instrument Workspace review panel

- [x] Start RED component tests for save-first draft, exact action packet,
  complete/partial/unavailable evidence, accepted/risk-rejected/Watch/Reject,
  saved read-only state and recovery copy.
- [x] Add `PacketOutcomeReview` below PacketMonitoring in the evidence rail; no
  route hop, modal, new chart or layout replacement.
- [x] Show horizon/evidence state, scenario observations, paper/risk timeline,
  distinct R labels, classification, optional note and one Save review action.
- [x] Isolate query/mutation state by context, exact packet and outcome identity;
  discard late responses after range/instrument/new-analysis switches.
- [x] Generate OpenAPI client, add English/Simplified-Chinese copy, keyboard and
  390 px coverage. Rebuild the packaged SPA only after UI settles.

Targeted command:

```powershell
Set-Location frontend
npm exec vitest -- run src/screens/instrument/PacketOutcomeReview.test.tsx src/screens/InstrumentWorkspace.test.tsx
npm run check:api
npm run typecheck
Set-Location ..
```

## Step 5 — NVDA browser and restart proof

- [x] Prove a confirmed/filled-open paper entry can save an inconclusive or
  evidence-supported review while realized R remains unavailable.
- [x] Prove deterministic risk refusal saves/reopens its exact reason without an
  order fill or fabricated zero result.
- [x] Cover operator Reject/Watch in targeted service/API tests.
- [x] Reconstruct the app on the same root and reopen exact packet, outcome and
  review IDs in Instrument Workspace. Assert no Provider/OpenD/model/notification
  call and no mutation outside the review store.

Focused command:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_packet_reviews.py tests/test_decision_packet_api.py tests/test_spa_e2e.py -q --basetemp .superpowers/sdd/2026-09-03-packet-outcome-review/pytest-focused
```

## Step 6 — One review boundary and one broad gate

- [x] Submit the demonstrable slice to one combined Reviewer. Correct at most one
  Critical/Important round; a remaining structural problem shrinks the feature.
- [x] Immediately before final UI verification, load the Impeccable craft floor;
  run the detector exactly once after the UI is final.
- [x] Run the broad gate once after review:

```powershell
.\.venv\Scripts\python.exe -m pytest -q --basetemp .superpowers/sdd/2026-09-03-packet-outcome-review/pytest-slice4-final
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
.\.venv\Scripts\python.exe tools/build_frontend.py --check
git diff --check
git status --short
```

Do not run or repair the direct Python release-license gate here. That approved
maintenance item runs once at the final PR boundary.

## Step 7 — Checkpoint and final-PR transition

- [x] Record the completed user loop, honest unavailable states, review result
  and exact verification evidence in the iteration and Active Goal.
- [x] Commit and push the Slice 4 checkpoint.
- [x] Advance the Goal only to license-closure repair and the final 0027 PR gate;
  do not add another product slice.
