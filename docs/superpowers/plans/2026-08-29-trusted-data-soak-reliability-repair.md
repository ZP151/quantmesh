# Trusted-Data Soak Reliability Repair Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the five-target real-data soak fail closed from provider collection through local verification and unique remote witness publication, while preserving and explicitly resolving the exact NVDA provider correction.

**Architecture:** Add an immutable overlap-resolution store and v2 quality evaluation with an explicitly recorded accepted baseline. Feed exact collection receipts into a crash-safe daily runner whose terminal receipt and complete verifier determine process success. Move workstation probing, scheduling and GitHub publication intent into version-controlled, deadline-bounded single-writer components before starting a new evidence-v3 candidate.

**Tech Stack:** Python 3.14, Pydantic v2, existing content-addressed `ObjectStore`/`ManifestStore`/`CheckpointStore`, Windows Task Scheduler and PowerShell wrapper, pytest, Ruff.

**Spec:** `docs/superpowers/specs/2026-08-29-trusted-data-soak-reliability-repair-design.md`

## Global Constraints

- Preserve every object, evaluation and report in the rejected evidence-v2 root; corrections are additive only.
- Do not ignore `turnover`, add an overlap tolerance, wildcard a conflict set or relabel a failed evaluation PASS.
- The known NVDA resolution is `operator-acknowledged`; it may qualify unchanged canonical OHLCV descendants but never turnover, liquidity, cost, capacity or slippage use.
- Resolution knowledge begins at its UTC `reviewed_at`; it cannot change earlier point-in-time claims.
- Old v1 policies, evaluations, reports and soak evidence remain byte-verifiable.
- Every subprocess has a finite monotonic deadline and Windows process-tree termination.
- Success requires the complete local soak verifier; a critical report, missing proof or verifier exception exits non-zero.
- Registered runner commits must be clean and reachable from the configured remote integration ref.
- Keep all venue access read-only, paper mode default, credentials absent and real-order authority structurally unchanged.
- The main thread is the only source writer; each task receives an independent read-only review before the next begins.

---

## File Structure

- `src/quantmesh/data/overlap_resolutions.py`: immutable resolution contracts, create-once binding store and exact validation.
- `src/quantmesh/data/quality.py`: v1/v2 quality parsing, explicit overlap baseline measurement and resolution-aware verification.
- `src/quantmesh/data/collection.py`: select and record the stable quality baseline for new real publications.
- `src/quantmesh/data/catalog.py`: expose resolution qualification without changing the original FAIL status.
- `src/quantmesh/data/cli.py`: inspect and resolve exact overlap evidence; emit typed collection receipts.
- `src/quantmesh/ops/trusted_data_soak.py`: packaged authority for soak reports, observation and complete verification.
- `src/quantmesh/ops/immutable_runs.py`: shared atomic immutable receipts, slot leases and latest-pointer compare-and-swap.
- `src/quantmesh/ops/processes.py`: argv-only monotonic subprocess deadlines and Windows process-tree termination.
- `src/quantmesh/ops/source_contract.py`: clean/reachable commit and dependency/script/config digest verification.
- `src/quantmesh/ops/soak_runner.py`: typed formal-daily state machine, deadlines, exact-cycle binding and terminal proof.
- `src/quantmesh/ops/connection_witness.py`: deadline-bounded workstation/scheduler probe and typed state interpretation.
- `src/quantmesh/ops/witness_outbox.py`: immutable publish intents and create-once remote receipts.
- `tools/soak_daily.py`: thin installed-runner wrapper.
- `tools/connection_witness.py`: thin connection-witness wrapper.
- `tools/connection_witness.ps1`: tracked Task Scheduler wrapper.
- `tools/soak_schedule.ps1`: install and round-trip verify both staggered tasks.
- `tools/trusted_data_soak.py`: v2 exact-cycle reports, concurrent append recovery and complete verification.
- `tests/test_overlap_resolutions.py`: resolution identity, binding, tamper and concurrent-write tests.
- `tests/test_quality_evidence.py`, `tests/test_quality_policies.py`, `tests/test_quality_publication.py`, `tests/test_data_catalog.py`: v2 baseline and catalog qualification tests.
- `tests/test_immutable_runs.py`, `tests/test_operational_processes.py`, `tests/test_source_contract.py`, `tests/test_soak_daily.py`, `tests/test_trusted_data_soak.py`: daily-run state machine and crash/concurrency tests.
- `tests/test_connection_witness.py`, `tests/test_soak_schedule.py`, `tests/test_witness_outbox.py`: probe, scheduling and publication tests.
- `docs/adr/0019-overlap-resolution-and-operational-evidence.md`: durable resolution/baseline and operational-receipt authority.
- `docs/iterations/0021-trusted-data-fabric.md`: role outputs, rulings and exact verification evidence.

---

### Task 1: Package the Existing Soak Verification Authority

**Files:**
- Create: `src/quantmesh/ops/trusted_data_soak.py`
- Modify: `tools/trusted_data_soak.py`
- Modify: `tests/test_trusted_data_soak.py`
- Modify: `tests/test_trusted_data_tool.py`

**Interfaces:**
- Produces: importable `SoakStore`, `SoakCandidate`, `SoakReport`, `SoakVerification`, `observe()`, `verify_soak()`, `replay_historical()` and `main()` under `quantmesh.ops.trusted_data_soak`.
- Preserves: current v1 canonical bytes, IDs, CLI JSON and exit codes exactly.

- [x] **Step 1: Write RED wrapper-parity tests**

Characterize one v1 candidate/report's exact `candidate_id`, `report_id` and canonical bytes. Import both the packaged module and the tool wrapper and assert their `main(["verify", ...])` stdout/exit code match for accepted and rejected fixtures.

- [x] **Step 2: Run RED tests**

Run: `.venv\Scripts\python.exe -m pytest tests/test_trusted_data_soak.py tests/test_trusted_data_tool.py -q`

Expected: import failure for `quantmesh.ops.trusted_data_soak`.

- [x] **Step 3: Move the authority without behavior changes**

Move the implementation intact into the package. Replace the tool body with:

```python
from quantmesh.ops.trusted_data_soak import main

if __name__ == "__main__":
    raise SystemExit(main())
```

Keep every v1 model contract and canonical serialization unchanged. Fix imports in tests; do not add v2 behavior in this task.

- [x] **Step 4: Run GREEN parity tests**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_trusted_data_soak.py tests/test_trusted_data_tool.py -q
.venv\Scripts\python.exe -m ruff check src/quantmesh/ops/trusted_data_soak.py tools/trusted_data_soak.py tests/test_trusted_data_soak.py tests/test_trusted_data_tool.py
git diff --check
```

- [x] **Step 5: Commit and record role evidence**

Commit: `refactor(ops): package trusted-data soak authority`

Append Task 1 RED/GREEN commands, Implementer summary and Reviewer verdict to the Iteration 0021 ledger.

---

### Task 2: Immutable Exact Overlap Resolution

**Files:**
- Create: `src/quantmesh/data/overlap_resolutions.py`
- Create: `tests/test_overlap_resolutions.py`
- Modify: `src/quantmesh/data/quality.py`
- Modify: `src/quantmesh/data/cli.py`
- Modify: `tests/test_trusted_data_tool.py`

**Interfaces:**
- Produces: `OverlapFieldDiff`, `OverlapResolution`, `OverlapResolutionStore.record()`, `.load()`, `.for_evaluation()`, `.verify()`.
- Produces: `QualityEvaluator.overlap_conflicts(manifest_id, baseline_manifest_id, admitted_manifest_ids) -> tuple[OverlapConflict, ...]`.
- Produces CLI: `quantmesh-data overlap inspect --root ROOT --evaluation ID` and `quantmesh-data overlap resolve ...`.

- [ ] **Step 1: Write RED contract tests**

Add tests constructing two immutable raw manifests whose single shared NVDA row differs only in turnover. Assert exact conflict detail and fingerprint, then build:

```python
resolution = OverlapResolution.build(
    failed_evaluation_id=failed.evaluation_id,
    failed_report_id=report.report_id,
    policy_id=failed.policy_id,
    dataset_id="moomoo-nvda-1d-raw-bars",
    baseline_manifest_id=revision_5.manifest_id,
    candidate_manifest_id=revision_6.manifest_id,
    conflicts=conflicts,
    predecessor_known_at=revision_5.knowledge_end,
    candidate_known_at=revision_6.knowledge_end,
    reviewed_at=T_REVIEW,
    operator="local-operator",
    reason="Moomoo revised one historical turnover value; canonical OHLCV is unchanged",
    attestation=ResolutionAttestation.OPERATOR_ACKNOWLEDGED,
    use_policy=ResolutionUsePolicy.OHLCV_DERIVATIVES_ONLY,
)
```

Assert exact retry idempotence and rejection of changed fingerprint, partial set, wrong manifest, wrong dataset/policy, blank reason/operator, review before knowledge time, conflicting concurrent writer, deleted object and altered binding.

- [ ] **Step 2: Run RED tests**

Run: `.venv\Scripts\python.exe -m pytest tests/test_overlap_resolutions.py -q`

Expected: collection failure because `quantmesh.data.overlap_resolutions` and the public conflict API do not exist.

- [ ] **Step 3: Implement conflict details and immutable store**

Define strict frozen Pydantic contracts. `OverlapConflict` must hash canonical JSON containing `identity`, prior/current row fingerprints and sorted `OverlapFieldDiff` items. Persist the resolution body through `ObjectStore`; persist the evaluation binding at:

```python
root / FABRIC_NAMESPACE / "quality" / "overlap-resolutions" / f"{failed_evaluation_id}.json"
```

Create the binding with a temporary file, `os.link(temp, target)` and exact-byte retry comparison. Verify both manifests, the failed evaluation/report binding, exact re-derived conflict set and every knowledge-time relation before accepting it.

- [ ] **Step 4: Add exact inspect/resolve CLI**

Nest an `overlap` command with `inspect` and `resolve`. `resolve` requires all IDs, every repeated `--fingerprint`, UTC `--reviewed-at`, `--operator`, `--reason`, `--attestation` and fixed `--use-policy ohlcv-derivatives-only`. Print canonical resolution JSON only after a read-back verification.

- [ ] **Step 5: Run GREEN tests and compatibility selection**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_overlap_resolutions.py tests/test_quality_evidence.py tests/test_quality_policies.py tests/test_trusted_data_tool.py -q
.venv\Scripts\python.exe -m ruff check src/quantmesh/data/overlap_resolutions.py src/quantmesh/data/quality.py src/quantmesh/data/cli.py tests/test_overlap_resolutions.py tests/test_trusted_data_tool.py
git diff --check
```

Expected: all pass; old amendment tests remain unchanged.

- [ ] **Step 6: Commit and record role evidence**

Commit: `feat(data): add exact overlap resolution evidence`

Append Task 2 RED/GREEN commands, Implementer summary and Reviewer verdict to the Iteration 0021 ledger.

---

### Task 3: V2 Stable Quality Baseline and Bounded Catalog Qualification

**Files:**
- Modify: `src/quantmesh/data/quality.py`
- Modify: `src/quantmesh/data/collection.py`
- Modify: `src/quantmesh/data/catalog.py`
- Modify: `tests/test_quality_evidence.py`
- Modify: `tests/test_quality_policies.py`
- Modify: `tests/test_quality_publication.py`
- Modify: `tests/test_data_catalog.py`

**Interfaces:**
- Consumes: Task 2 `OverlapResolutionStore` and exact `OverlapConflict` values.
- Produces: `QualityEvaluationV2`, `QualityEvidence = QualityEvaluation | QualityEvaluationV2`.
- Produces: `QualityBaseline(manifest_id, evaluation_id, resolution_id)` and `CollectionCoordinator._quality_baseline()`.
- Produces catalog fields: `contract`, `original_status`, `resolution_id`, `qualification`, `use_policy`.

- [ ] **Step 1: Write RED natural-healing and catalog tests**

Create revision 5 PASS, revision 6 turnover-only FAIL and revision 7 byte-equal to revision 6. Assert revision 7 still compares with revision 5 and fails without a resolution. Record the exact Task 2 resolution for revision 6, publish revision 8 equal to revision 6, and assert its v2 evaluation records revision 6/evaluation/resolution IDs and passes.

Add a second correction at revision 9 and assert it fails with a new fingerprint. Add v1 object/report fixtures and assert byte-identical parsing and verification.

Catalog assertions:

```python
assert entry.quality.original_status is QualityStatus.FAIL
assert entry.quality.qualification == "qualified-with-resolution"
assert entry.quality.resolution_id == resolution.resolution_id
assert entry.trusted_for_research is True
assert catalog.require_research(entry.manifest_id, use="turnover") raises CatalogQualificationError
assert catalog.require_research(entry.manifest_id, use="ohlcv") == entry
```

- [ ] **Step 2: Run RED tests**

Run: `.venv\Scripts\python.exe -m pytest tests/test_quality_evidence.py tests/test_quality_policies.py tests/test_quality_publication.py tests/test_data_catalog.py -q`

Expected: failures for missing v2 contract, stable baseline and bounded use.

- [ ] **Step 3: Implement v1/v2 evidence loading**

Keep `QualityEvaluation` unchanged. Add `QualityEvaluationV2` with contract `quality-evaluation-v2` and fields:

```python
overlap_baseline_manifest_id: str | None
overlap_baseline_evaluation_id: str | None
overlap_resolution_id: str | None
```

Dispatch `load()` from stored `contract`; verify v1 by the old path. For v2, re-measure using the recorded baseline manifest, verify the resolution when present, and reject a PASS that lacks a valid resolution for a non-empty conflict set.

- [ ] **Step 4: Implement production baseline selection**

For each new real candidate manifest, inspect earlier committed manifests for the dataset and their checkpoint-bound quality evaluations. Select the latest ordinary PASS or exact resolved overlap-only FAIL. Never accept another hard issue. Pass the selected manifest explicitly to `QualityEvaluator.measure()` and record the three baseline proof IDs in v2.

- [ ] **Step 5: Implement bounded catalog projection**

Expose original evaluation status separately from qualification. Default `require_research()` to `use="ohlcv"` for existing bar/feature callers. Only `ohlcv` may use `OHLCV_DERIVATIVES_ONLY`; `turnover`, `liquidity`, `cost`, `capacity` and `slippage` must reject it. Fixture and missing resolution states remain untrusted.

- [ ] **Step 6: Run GREEN tests and broad data regression**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_quality_evidence.py tests/test_quality_policies.py tests/test_quality_publication.py tests/test_data_catalog.py tests/test_data_catalog_api.py tests/test_collection_recovery.py -q
.venv\Scripts\python.exe -m ruff check src/quantmesh/data/quality.py src/quantmesh/data/collection.py src/quantmesh/data/catalog.py tests/test_quality_evidence.py tests/test_quality_policies.py tests/test_quality_publication.py tests/test_data_catalog.py
git diff --check
```

- [ ] **Step 7: Commit and record role evidence**

Commit: `feat(data): enforce stable resolved overlap baselines`

Record Quant Researcher verdict on knowledge time/downstream use, plus Implementer and Reviewer evidence.

---

### Task 4: Typed Exact Collection Receipts

**Files:**
- Create: `src/quantmesh/data/collection_receipts.py`
- Modify: `src/quantmesh/data/cli.py`
- Modify: `tests/test_trusted_data_tool.py`
- Modify: `tests/test_hyperliquid_collection.py`
- Modify: `tests/test_moomoo_collection.py`

**Interfaces:**
- Produces: `TargetCollectionEvidence` and `CollectionCycleReceipt`.
- Produces CLI field: `collection_receipt` containing provider, commit, cycle, job ID, run ID, attempt, quality report ID and exact target/layer manifest map.

- [ ] **Step 1: Write RED receipt tests**

Assert Hyperliquid receipt contains exactly BTC/ETH/SOL and Moomoo exactly AAPL/NVDA, with raw/normalized/adjusted/feature IDs for each required bars target. Assert every ID belongs to one checkpoint with matching job/run/quality report, producing commit and collection cycle. Reject empty `{}`, stale manifests, mixed checkpoints, wrong target/layer, fixture provenance and manifest IDs not returned by the current collection.

- [ ] **Step 2: Run RED tests**

Run: `.venv\Scripts\python.exe -m pytest tests/test_trusted_data_tool.py tests/test_hyperliquid_collection.py tests/test_moomoo_collection.py -q`

- [ ] **Step 3: Implement receipt derivation**

After each collector returns, derive the receipt only from its returned manifest IDs. Open each manifest, obtain `CheckpointStore.checkpoints_for_manifests()`, require one exact owning checkpoint and build sorted target evidence. Do not consult catalog current pointers.

- [ ] **Step 4: Run GREEN tests**

Run the Task 4 tests, focused Ruff on touched files and `git diff --check`.

- [ ] **Step 5: Commit and record role evidence**

Commit: `feat(data): emit exact collection cycle receipts`

---

### Task 5: Crash-Safe Exact Daily Runner

**Files:**
- Create: `src/quantmesh/ops/immutable_runs.py`
- Create: `src/quantmesh/ops/processes.py`
- Create: `src/quantmesh/ops/source_contract.py`
- Create: `src/quantmesh/ops/soak_runner.py`
- Create: `tests/test_immutable_runs.py`
- Create: `tests/test_operational_processes.py`
- Create: `tests/test_source_contract.py`
- Modify: `tools/soak_daily.py`
- Modify: `tools/trusted_data_soak.py`
- Modify: `tests/test_soak_daily.py`
- Modify: `tests/test_trusted_data_soak.py`

**Interfaces:**
- Consumes: Task 1 packaged soak authority and Task 4 `CollectionCycleReceipt` for Hyperliquid and Moomoo.
- Produces: `DailyRunReceiptV1`, `DailyRunStatus`, `ImmutableRunStore`, `SlotLease`.
- Produces: `trusted_data_soak.py observe --cycle-receipt FILE` and v2 `SoakTargetEvidence` with job/run/quality-report IDs.
- CLI adds: `--run-root`, `--remote-ref` and per-stage deadline options.

- [ ] **Step 1: Write RED immutable-run tests**

Test create-once terminal receipts, exact retry, conflicting overwrite, atomic latest pointer, concurrent slot lease, stale lock recovery with owner proof, exception-finally receipt and reparse/hard-link rejection using the existing filesystem safety helpers.

- [ ] **Step 2: Write RED daily state-machine tests**

Use controlled subprocess results and assert:

- dirty or `git merge-base --is-ancestor HEAD REMOTE_REF` false stops before collection;
- malformed Hyperliquid/Moomoo output and stale/mixed receipts stop before observe;
- collection timeout kills the mocked tree and records `timed-out`;
- observation with critical issues runs verification and exits non-zero;
- verifier non-zero or invalid JSON propagates failure;
- duplicate UTC day reopens the existing report, reruns verification and preserves pass/fail;
- two processes for one slot produce one report and compatible terminal receipts;
- injected crash between report write and terminal receipt recovers only the exact report.

- [ ] **Step 3: Run RED tests**

Run: `.venv\Scripts\python.exe -m pytest tests/test_immutable_runs.py tests/test_soak_daily.py tests/test_trusted_data_soak.py -q`

- [ ] **Step 4: Implement immutable operational primitives**

Use content-derived receipt IDs, create-new atomic publication and an owner-token lock. Latest is a replaceable pointer containing slot, receipt ID and prior pointer digest; readers verify the target before accepting it.

- [ ] **Step 5: Implement exact v2 observation**

Pass two canonical collection receipts to observation. Build the report only from those exact manifest IDs and checkpoint proofs. Preserve v1 loading/verifying, while new evidence-v3 candidates use `quantmesh-trusted-data-soak-v2` and exact target job/run/quality-report fields. Make `SoakStore.append()` slot-locked and exact-retry idempotent.

- [ ] **Step 6: Implement deadline-bounded runner**

Implement `verify_source_contract(repo, remote_ref, dependency_digest, script_digest, config_digest)` and require clean HEAD plus `git merge-base --is-ancestor HEAD REMOTE_REF`. Use one `run_process(command, timeout_seconds, cwd)` boundary that accepts argv only, starts a new process group, waits with a finite monotonic timeout and terminates the complete Windows tree on expiry. Always record the terminal receipt in `finally`. After observe, call:

```text
trusted_data_soak.py verify --minimum-hours 0 --minimum-xnys-sessions 1
```

Parse `SoakVerification`; return zero only when `accepted` is true and the verifier proof is embedded in the terminal receipt.

- [ ] **Step 7: Run GREEN and concurrency tests**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_immutable_runs.py tests/test_operational_processes.py tests/test_source_contract.py tests/test_soak_daily.py tests/test_trusted_data_soak.py -q
.venv\Scripts\python.exe -m ruff check src/quantmesh/ops/immutable_runs.py src/quantmesh/ops/processes.py src/quantmesh/ops/source_contract.py src/quantmesh/ops/soak_runner.py tools/soak_daily.py tools/trusted_data_soak.py tests/test_immutable_runs.py tests/test_operational_processes.py tests/test_source_contract.py tests/test_soak_daily.py tests/test_trusted_data_soak.py
git diff --check
```

- [ ] **Step 8: Commit and record role evidence**

Commit: `fix(ops): make formal daily soak fully fail closed`

---

### Task 6: Deadline-Bounded Connection Witness

**Files:**
- Create: `src/quantmesh/ops/connection_witness.py`
- Create: `tools/connection_witness.py`
- Create: `tools/connection_witness.ps1`
- Create: `tests/test_connection_witness.py`

**Interfaces:**
- Consumes: Task 5 `ImmutableRunStore` and formal `DailyRunReceiptV1`.
- Produces: `ConnectionWitnessReceiptV1`, `FormalTaskState` and `interpret_formal_task()`.

- [ ] **Step 1: Write RED state-table tests**

Cover recent `Running/0x41301 -> in-progress`, overdue running -> failure, `0x41306 -> failure`, completed zero with matching verified terminal receipt -> pass, completed zero without receipt -> failure, missing/stale task -> failure. Assert no Moomoo SDK child is started while formal state is in-progress.

- [ ] **Step 2: Write RED deadline and persistence tests**

Inject TCP, scheduler and subprocess exceptions/timeouts. Assert each attempt writes a fresh immutable terminal receipt in `finally`, kills descendants, preserves both a failed scheduled slot and later supplemental success, and never overwrites concurrent run files.

- [ ] **Step 3: Run RED tests**

Run: `.venv\Scripts\python.exe -m pytest tests/test_connection_witness.py -q`

- [ ] **Step 4: Implement probe and thin wrappers**

Probe Python, loopback TCP 11111, Scheduler state and matching daily receipt under independent finite deadlines. Keep PowerShell limited to locating the pinned interpreter and invoking the Python command with explicit roots/task name.

- [ ] **Step 5: Run GREEN tests**

Run Task 6 pytest, focused Ruff and `git diff --check`.

- [ ] **Step 6: Commit and record role evidence**

Commit: `fix(ops): persist deadline-bounded connection witnesses`

---

### Task 7: Verified Staggered Windows Scheduling

**Files:**
- Modify: `tools/soak_schedule.ps1`
- Create: `tests/test_soak_schedule.py`
- Create: `docs/runbooks/trusted-data-soak.md`

**Interfaces:**
- Consumes: Task 5 daily and Task 6 connection wrappers.
- Produces: installer defaults daily 08:00, connection every two hours at minute 10; JSON verification output containing normalized actions/triggers/settings.

- [ ] **Step 1: Write RED command-construction and drift tests**

Mock Scheduler cmdlets and assert absolute pinned paths, explicit roots, wake/start-when-available, battery execution, IgnoreNew, three 15-minute daily retries, one-hour daily limit, 15-minute connection limit and minute-10 trigger. Feed altered settings back and assert installer verification exits non-zero with exact drift fields.

- [ ] **Step 2: Run RED tests**

Run: `.venv\Scripts\python.exe -m pytest tests/test_soak_schedule.py -q`

- [ ] **Step 3: Refactor registration and round-trip verification**

Use `Register-ScheduledTask` objects for both tasks, immediately read them with `Get-ScheduledTask`/`Get-ScheduledTaskInfo`, normalize the owned fields and compare against the expected contract. Emit one JSON result and fail on any mismatch.

- [ ] **Step 4: Run GREEN tests and PowerShell parse check**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_soak_schedule.py -q
$null = [scriptblock]::Create((Get-Content tools/soak_schedule.ps1 -Raw))
$null = [scriptblock]::Create((Get-Content tools/connection_witness.ps1 -Raw))
git diff --check
```

- [ ] **Step 5: Commit and record role evidence**

Commit: `fix(ops): install and verify staggered soak tasks`

---

### Task 8: Single-Authority Witness Outbox

**Files:**
- Create: `src/quantmesh/ops/witness_outbox.py`
- Create: `tools/soak_witness_outbox.py`
- Create: `tests/test_witness_outbox.py`
- Modify: `src/quantmesh/ops/soak_runner.py`
- Modify: `src/quantmesh/ops/connection_witness.py`

**Interfaces:**
- Produces: `WitnessIntentV1`, `WitnessPublicationReceiptV1`, `WitnessOutbox.enqueue()`, `.pending()`, `.record_publication()`.
- Idempotency key: SHA-256 over issue number, witness kind and exact local run/report ID.
- Publisher protocol: list pending -> remote exact-key read -> POST if absent -> remote read-back -> record receipt.

- [ ] **Step 1: Write RED outbox tests**

Assert exact enqueue retry, conflicting intent rejection, single publisher lease, deterministic pending order, ambiguous POST recovery by remote re-query, duplicate remote-match failure, receipt URL/read-back digest validation, restart idempotence and inability to enqueue #124 success without a passing full-verifier proof.

- [ ] **Step 2: Run RED tests**

Run: `.venv\Scripts\python.exe -m pytest tests/test_witness_outbox.py -q`

- [ ] **Step 3: Implement local outbox authority**

Use Task 5 immutable primitives. The local CLI exposes canonical `list`, `show` and `record-publication`; it never contains GitHub credentials or performs network I/O. Daily and connection terminal paths enqueue exact intents only after their local state is durable.

- [ ] **Step 4: Run GREEN tests**

Run Task 8 pytest, focused Ruff and `git diff --check`.

- [ ] **Step 5: Commit and record role evidence**

Commit: `feat(ops): add single-authority witness outbox`

---

### Task 9: ADR, Full Verification and Real-Host Migration

**Files:**
- Create: `docs/adr/0019-overlap-resolution-and-operational-evidence.md`
- Modify: `docs/iterations/0021-trusted-data-fabric.md`
- Modify: `docs/goals/ACTIVE.md`
- Modify: `docs/runbooks/trusted-data-soak.md`
- Modify host task definitions through `tools/soak_schedule.ps1` only after all local gates pass.
- Update heartbeat automation through the Codex automation API only after the local outbox is green.

**Interfaces:**
- Consumes: all prior tasks.
- Produces: remotely reachable integration commit, exact NVDA resolution, fresh evidence-v3 candidate, verified scheduled tasks and updated single-authority heartbeat.

- [ ] **Step 1: Write ADR and close documentation tests**

Record why resolution is additive, why v2 baseline IDs are required, why operational receipts are outside provider evidence, and why remote publication uses a local outbox. Update the runbook with `blocked-user-auth`, no-backfill and candidate-reset rules.

- [ ] **Step 2: Run complete automated verification**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_overlap_resolutions.py tests/test_quality_evidence.py tests/test_quality_policies.py tests/test_quality_publication.py tests/test_data_catalog.py tests/test_data_catalog_api.py tests/test_trusted_data_tool.py tests/test_hyperliquid_collection.py tests/test_moomoo_collection.py tests/test_immutable_runs.py tests/test_operational_processes.py tests/test_source_contract.py tests/test_soak_daily.py tests/test_trusted_data_soak.py tests/test_connection_witness.py tests/test_soak_schedule.py tests/test_witness_outbox.py -q
.venv\Scripts\python.exe -m ruff check src tests tools
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\python.exe -m pip check
.venv\Scripts\python.exe tools/license_review.py
git diff --check
```

Record exact counts, durations and expected skips. Run the `verification-before-completion` skill before any passing claim.

- [ ] **Step 3: Final whole-branch review**

Generate a review package from the `origin/main` merge base through HEAD. Obtain one independent Standards/Spec/Safety verdict. Fix every Critical/Important finding through the bounded review loop and record deferred Minor findings explicitly.

- [ ] **Step 4: Make the runner remotely reproducible**

Push the green integration branch without force. Verify:

```powershell
git status --porcelain --untracked-files=all
git merge-base --is-ancestor HEAD origin/HEAD-OF-INTEGRATION-BRANCH
```

Both must succeed before host mutation.

- [ ] **Step 5: Record the exact NVDA resolution**

Run `quantmesh-data overlap inspect` against the rejected trusted-data root. Compare the emitted evaluation/report/policy/dataset/manifests/fingerprint/diff with issue #124. Run `overlap resolve` using `operator-acknowledged`, `ohlcv-derivatives-only`, current UTC review time and the approved reason. Read back and verify; do not edit the failed report.

- [ ] **Step 6: Run clean-host simulations and failure drills**

From the pinned branch environment, inject provider outage, verifier rejection, new overlap, child timeout, scheduler running/terminated states, concurrent daily invocations and ambiguous publisher result. Each must produce the expected non-zero/typed receipt without altering real provider evidence.

- [ ] **Step 7: Start the new real candidate**

Create empty `C:\QuantMesh\evidence-v3` and its separate run/outbox roots only after resolving and printing their exact absolute paths. Run one fresh five-target daily cycle, reopen every recorded manifest/evaluation/checkpoint/receipt and require `minimum-hours=0`, `minimum-xnys-sessions=1` PASS.

- [ ] **Step 8: Register and verify the host schedule**

Install the daily 08:00 and two-hour minute-10 connection tasks from the pinned branch. Round-trip verify settings, run each once, and record their immutable local receipts. Treat absent/logged-out OpenD as `blocked-user-auth`; do not fabricate evidence.

- [ ] **Step 9: Update the heartbeat publisher**

Update the existing `quantmesh-daily-witness` heartbeat to minute 20. Its prompt must consume only pending outbox intents, acquire the publisher lease, query the exact idempotency key before posting, re-query after ambiguity, read back the comment and record the local publication receipt. Preserve notification settings.

- [ ] **Step 10: Publish repair/restart witnesses**

After local read-back succeeds, publish one repair/restart witness to #124 and one scheduler/probe repair witness to #127 through the outbox. Record the exact comment URLs and receipts in the iteration ledger.

- [ ] **Step 11: Commit the operational checkpoint**

Commit: `docs(iteration): start repaired trusted-data soak candidate`

Do not claim the 168-hour gate complete. The heartbeat monitors real elapsed evidence; completion requires 168 hours and a final full verifier PASS.
