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

## Execution Amendment — 2026-09-01 Preflight

This amendment is normative for the remaining work. It preserves the approved
design while closing execution ambiguities found when the remote branch was
reconstructed on the current host.

- Execute the remaining slices in dependency order `Task 6 -> Task 8 -> Task 7
  -> Task 9A -> Task 9B`. Task 8 precedes Task 7 so registered command lines can
  include the final outbox roots and publisher contract instead of requiring a
  second scheduler rewrite.
- Keep the main thread as the sole source writer. Planner, quant-research,
  reviewer and verifier agents are read-only and their verdicts are recorded in
  the iteration ledger.
- The current host has an enabled legacy `\QuantMesh Daily Soak` task. Two
  reversible disable attempts on 2026-09-01 were denied by Windows access
  control and left the task unchanged. Until an administrator disables that
  task and a replacement Windows host is explicitly designated, Tasks 6-8 and
  Task 9A are local-only: no provider call, scheduler mutation, evidence-root
  creation, overlap resolution, automation update or remote publication is
  authorized.
- Use disjoint absolute roots for trusted data, soak reports, daily receipts,
  connection receipts and publication outbox. Never infer one root from
  another, and never use the rejected evidence-v2 root as a writable repair
  target.
- Task 9 is split at the authority boundary. Task 9A closes code, tests,
  documentation, review, clean-push ancestry and simulations. Task 9B performs
  real-host migration only after the scheduler/host gate above is satisfied.

### Task 6 state and deadline contract

- Normalize Scheduler timestamps to UTC before comparison. The formal daily
  deadline is 3,600 seconds. Completed task evidence becomes stale after
  93,600 seconds (26 hours), providing the daily cadence a two-hour grace.
  These values are explicit validated inputs whose production defaults are
  pinned by tests and scheduler command construction.
- Treat Scheduler result codes numerically: `0x00041301` is `in-progress` only
  while `now - LastRunTime <= 3,600 seconds`; a longer-running task is failed.
  `0x00041306` is failed. Missing, disabled, never-run, unparsable, future-dated
  or stale task evidence is failed.
- For a completed zero result, enumerate every immutable terminal for the UTC
  date of `LastRunTime` and filter on `started_at` within
  `[-120 seconds, +900 seconds]` of that Scheduler start. Pass only if there is
  exactly one match, it is the maximum attempt for that date and the target of
  the daily latest pointer, its `code_commit` and `source_contract_id` equal the
  explicit expected values, and its terminal state is `passed`. Reopen its
  exact `soak_report_id` from the configured report root and prove report ID,
  commit, source contract and accepted complete-verifier proof all agree.
  Ambiguity, a non-passing newer attempt, mismatched roots/source or any
  immutable-read failure fails closed. A connection attempt is keyed by an
  explicit scheduled UTC slot plus positive attempt and is persisted in its own
  connection-receipt namespace; supplemental execution must receive the slot
  being supplemented and never infer it from wall-clock time.
- `ConnectionWitnessStore(root)` owns `terminal_path(slot, attempt)`,
  `terminals(slot)`, `load_terminal(slot, attempt)`, `latest()` and
  `publish_terminal(receipt)`. Slots use canonical UTC `YYYY-MM-DDTHH:MMZ`
  schedule boundaries and positive attempts allocated under a per-slot lease.
  Publication writes the immutable terminal before atomically advancing a
  validated latest pointer; conflicts, stale-owner recovery and concurrent
  supplemental attempts are covered by tests.
- `ConnectionWitnessConfig` and the Python CLI require absolute repo,
  report-root, daily-run-root and connection-run-root paths; formal-task and
  connection-task names; expected commit and source-contract ID; execution kind
  (`scheduled` or `supplemental`); and all finite threshold/probe budgets. A
  scheduled execution derives its canonical slot from the connection task's own
  Scheduler `LastRunTime`. A supplemental execution instead requires
  `--scheduled-slot YYYY-MM-DDTHH:MMZ`; supplying or omitting a slot in the
  wrong mode is invalid. The store allocates the next positive attempt under
  the slot lease and records execution kind in the receipt.
- Give Python/import, loopback TCP 11111, Scheduler, exact daily-receipt,
  read-only Moomoo capability and public Hyperliquid API probes independent
  finite monotonic deadlines. Suppress only the Moomoo SDK capability child
  while the formal task is `in-progress`; all other probes and receipt
  persistence still run. Every attempt publishes one immutable terminal from a
  `finally` boundary and terminates timed-out descendant process trees.
- A missing/unreachable OpenD daemon or logged-out/read-capability denial is
  `blocked-user-auth`, persists a typed connection terminal and exits non-zero;
  it never synthesizes provider evidence. A legitimate formal `in-progress`
  state suppresses the Moomoo child and persists `in-progress` as an operational
  cadence result, not as a completed daily PASS or positive provider witness.

### Task 8 recovery and authority contract

- Keep the local CLI credential-free and network-free. Put remote list, POST and
  read-back behind an injected publisher coordinator so ambiguous POST,
  duplicate match and digest-mismatch behavior is executable under tests.
- Use a cross-process publisher lease. After a crash or restart, terminal paths
  call `ensure_intent(terminal)` idempotently before process success can be
  returned. If the terminal is already durable but enqueue fails, persist a
  separate immutable outbox-failure receipt and exit non-zero; never rewrite
  the terminal. Startup recovery scans exact unpaired eligible terminals and
  retries `ensure_intent`, rejecting ambiguity or conflict. Daily-success and
  connection-state witness kinds remain distinct.
- Publication timestamps and operational receipts never create or extend soak
  duration. Final 168-hour acceptance must reopen accepted daily reports and
  their exact immutable daily terminals, then validate connection-receipt
  cadence against the same source contract.

### Final operational-acceptance contract

- Keep provider-soak verification unchanged. Task 9A adds a separate versioned
  operational-acceptance verifier and immutable output. It consumes the
  provider verifier result, report root, daily-run root, connection-run root and
  expected source contract; it never writes provider objects or treats
  operational timestamps as market-evidence time.
- Final acceptance reopens every qualifying report and exactly matching daily
  terminal, then verifies the required connection slots/cadence. Missing,
  duplicate, stale, mismatched or non-terminal evidence rejects. A daily
  `minimum-hours=0` witness cannot satisfy the final-completion witness kind.
- Generate expected connection slots in `Asia/Singapore` every two hours at
  minute 10, from the first boundary on/after candidate start through the last
  boundary on/before verifier `as_of`, then normalize to UTC. Each scheduled
  receipt must start from 120 seconds before through 900 seconds after its slot,
  match the expected source and be `passed` or `in-progress`. Every expected
  slot needs scheduled evidence. Multiple chronological scheduled attempts are
  valid only when every attempt is immutable, non-overlapping and zero-outcome;
  any `failed`, `timed-out`, `blocked-user-auth` or `interrupted` scheduled
  attempt permanently rejects that candidate. Supplemental attempts are
  retained recovery evidence but neither satisfy a missing slot nor repair a
  failed scheduled attempt. Conflicting attempt identity, pointer or source
  evidence rejects.

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

- [x] **Step 1: Write RED contract tests**

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

- [x] **Step 2: Run RED tests**

Run: `.venv\Scripts\python.exe -m pytest tests/test_overlap_resolutions.py -q`

Expected: collection failure because `quantmesh.data.overlap_resolutions` and the public conflict API do not exist.

- [x] **Step 3: Implement conflict details and immutable store**

Define strict frozen Pydantic contracts. `OverlapConflict` must hash canonical JSON containing `identity`, prior/current row fingerprints and sorted `OverlapFieldDiff` items. Persist the resolution body through `ObjectStore`; persist the evaluation binding at:

```python
root / FABRIC_NAMESPACE / "quality" / "overlap-resolutions" / f"{failed_evaluation_id}.json"
```

Create the binding with a temporary file, `os.link(temp, target)` and exact-byte retry comparison. Verify both manifests, the failed evaluation/report binding, exact re-derived conflict set and every knowledge-time relation before accepting it.

- [x] **Step 4: Add exact inspect/resolve CLI**

Nest an `overlap` command with `inspect` and `resolve`. `resolve` requires all IDs, every repeated `--fingerprint`, UTC `--reviewed-at`, `--operator`, `--reason`, `--attestation` and fixed `--use-policy ohlcv-derivatives-only`. Print canonical resolution JSON only after a read-back verification.

- [x] **Step 5: Run GREEN tests and compatibility selection**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_overlap_resolutions.py tests/test_quality_evidence.py tests/test_quality_policies.py tests/test_trusted_data_tool.py -q
.venv\Scripts\python.exe -m ruff check src/quantmesh/data/overlap_resolutions.py src/quantmesh/data/quality.py src/quantmesh/data/cli.py tests/test_overlap_resolutions.py tests/test_trusted_data_tool.py
git diff --check
```

Expected: all pass; old amendment tests remain unchanged.

- [x] **Step 6: Commit and record role evidence**

Commit: `feat(data): add exact overlap resolution evidence`

Append Task 2 RED/GREEN commands, Implementer summary and Reviewer verdict to the Iteration 0021 ledger.

---

### Task 3: V2 Stable Quality Baseline and Bounded Catalog Qualification

**Files:**
- Modify: `src/quantmesh/data/quality.py`
- Modify: `src/quantmesh/data/collection.py`
- Modify: `src/quantmesh/data/catalog.py`
- Modify: `src/quantmesh/data/overlap_resolutions.py`
- Modify: `tests/test_quality_evidence.py`
- Modify: `tests/test_quality_policies.py`
- Modify: `tests/test_quality_publication.py`
- Modify: `tests/test_data_catalog.py`

**Interfaces:**
- Consumes: Task 2 `OverlapResolutionStore` and exact `OverlapConflict` values.
- Produces: `QualityEvaluationV2`, `QualityEvidence = QualityEvaluation | QualityEvaluationV2`.
- Produces: `QualityBaseline(manifest_id, evaluation_id, resolution_id)` and `CollectionCoordinator._quality_baseline()`.
- Produces catalog fields: `contract`, `original_status`, `resolution_id`, `qualification`, `use_policy`.

- [x] **Step 1: Write RED natural-healing and catalog tests**

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

- [x] **Step 2: Run RED tests**

Run: `.venv\Scripts\python.exe -m pytest tests/test_quality_evidence.py tests/test_quality_policies.py tests/test_quality_publication.py tests/test_data_catalog.py -q`

Expected: failures for missing v2 contract, stable baseline and bounded use.

- [x] **Step 3: Implement v1/v2 evidence loading**

Keep `QualityEvaluation` unchanged. Add `QualityEvaluationV2` with contract `quality-evaluation-v2` and fields:

```python
overlap_baseline_manifest_id: str | None
overlap_baseline_evaluation_id: str | None
overlap_resolution_id: str | None
```

Dispatch `load()` from stored `contract`; verify v1 by the old path. For v2, re-measure using the recorded baseline manifest, verify the resolution when present, and reject a PASS that lacks a valid resolution for a non-empty conflict set.

- [x] **Step 4: Implement production baseline selection**

For each new real candidate manifest, inspect earlier committed manifests for the dataset and their checkpoint-bound quality evaluations. Select the latest ordinary PASS or exact resolved overlap-only FAIL. Never accept another hard issue. Pass the selected manifest explicitly to `QualityEvaluator.measure()` and record the three baseline proof IDs in v2.

- [x] **Step 5: Implement bounded catalog projection**

Expose original evaluation status separately from qualification. Default `require_research()` to `use="ohlcv"` for existing bar/feature callers. Only `ohlcv` may use `OHLCV_DERIVATIVES_ONLY`; `turnover`, `liquidity`, `cost`, `capacity` and `slippage` must reject it. Fixture and missing resolution states remain untrusted.

- [x] **Step 6: Run GREEN tests and broad data regression**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_quality_evidence.py tests/test_quality_policies.py tests/test_quality_publication.py tests/test_data_catalog.py tests/test_data_catalog_api.py tests/test_collection_recovery.py -q
.venv\Scripts\python.exe -m ruff check src/quantmesh/data/quality.py src/quantmesh/data/collection.py src/quantmesh/data/catalog.py tests/test_quality_evidence.py tests/test_quality_policies.py tests/test_quality_publication.py tests/test_data_catalog.py
git diff --check
```

- [x] **Step 7: Commit and record role evidence**

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

- [x] **Step 1: Write RED receipt tests**

Assert Hyperliquid receipt contains exactly BTC/ETH/SOL and Moomoo exactly AAPL/NVDA, with raw/normalized/adjusted/feature IDs for each required bars target. Assert every ID belongs to one checkpoint with matching job/run/quality report, producing commit and collection cycle. Reject empty `{}`, stale manifests, mixed checkpoints, wrong target/layer, fixture provenance and manifest IDs not returned by the current collection.

- [x] **Step 2: Run RED tests**

Run: `.venv\Scripts\python.exe -m pytest tests/test_trusted_data_tool.py tests/test_hyperliquid_collection.py tests/test_moomoo_collection.py -q`

- [x] **Step 3: Implement receipt derivation**

After each collector returns, derive the receipt only from its returned manifest IDs. Open each manifest, obtain `CheckpointStore.checkpoints_for_manifests()`, require one exact owning checkpoint and build sorted target evidence. Do not consult catalog current pointers.

- [x] **Step 4: Run GREEN tests**

Run the Task 4 tests, focused Ruff on touched files and `git diff --check`.

- [x] **Step 5: Commit and record role evidence**

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

- [x] **Step 1: Write RED immutable-run tests**

Test create-once terminal receipts, exact retry, conflicting overwrite, atomic latest pointer, concurrent slot lease, stale lock recovery with owner proof, exception-finally receipt and reparse/hard-link rejection using the existing filesystem safety helpers.

- [x] **Step 2: Write RED daily state-machine tests**

Use controlled subprocess results and assert:

- dirty or `git merge-base --is-ancestor HEAD REMOTE_REF` false stops before collection;
- malformed Hyperliquid/Moomoo output and stale/mixed receipts stop before observe;
- collection timeout kills the mocked tree and records `timed-out`;
- observation with critical issues runs verification and exits non-zero;
- verifier non-zero or invalid JSON propagates failure;
- duplicate UTC day reopens the existing report, reruns verification and preserves pass/fail;
- two processes for one slot produce one report and compatible terminal receipts;
- injected crash between report write and terminal receipt recovers only the exact report.

- [x] **Step 3: Run RED tests**

Run: `.venv\Scripts\python.exe -m pytest tests/test_immutable_runs.py tests/test_soak_daily.py tests/test_trusted_data_soak.py -q`

- [x] **Step 4: Implement immutable operational primitives**

Use content-derived receipt IDs, create-new atomic publication and an owner-token lock. Latest is a replaceable pointer containing slot, receipt ID and prior pointer digest; readers verify the target before accepting it.

- [x] **Step 5: Implement exact v2 observation**

Pass two canonical collection receipts to observation. Build the report only from those exact manifest IDs and checkpoint proofs. Preserve v1 loading/verifying, while new evidence-v3 candidates use `quantmesh-trusted-data-soak-v2` and exact target job/run/quality-report fields. Make `SoakStore.append()` slot-locked and exact-retry idempotent.

- [x] **Step 6: Implement deadline-bounded runner**

Implement `verify_source_contract(repo, remote_ref, dependency_digest, script_digest, config_digest)` and require clean HEAD plus `git merge-base --is-ancestor HEAD REMOTE_REF`. Use one `run_process(command, timeout_seconds, cwd)` boundary that accepts argv only, starts a new process group, waits with a finite monotonic timeout and terminates the complete Windows tree on expiry. Always record the terminal receipt in `finally`. After observe, call:

```text
trusted_data_soak.py verify --minimum-hours 0 --minimum-xnys-sessions 1
```

Parse `SoakVerification`; return zero only when `accepted` is true and the verifier proof is embedded in the terminal receipt.

- [x] **Step 7: Run GREEN and concurrency tests**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_immutable_runs.py tests/test_operational_processes.py tests/test_source_contract.py tests/test_soak_daily.py tests/test_trusted_data_soak.py -q
.venv\Scripts\python.exe -m ruff check src/quantmesh/ops/immutable_runs.py src/quantmesh/ops/processes.py src/quantmesh/ops/source_contract.py src/quantmesh/ops/soak_runner.py tools/soak_daily.py tools/trusted_data_soak.py tests/test_immutable_runs.py tests/test_operational_processes.py tests/test_source_contract.py tests/test_soak_daily.py tests/test_trusted_data_soak.py
git diff --check
```

- [x] **Step 8: Commit and record role evidence**

Commit: `fix(ops): make formal daily soak fully fail closed`

---

### Task 6: Deadline-Bounded Connection Witness

**Files:**
- Create: `src/quantmesh/ops/connection_witness.py`
- Create: `tools/connection_witness.py`
- Create: `tools/connection_witness.ps1`
- Create: `tests/test_connection_witness.py`

**Interfaces:**
- Consumes: Task 5 immutable publication/safe-read primitives, formal
  `DailyRunReceiptV1` and its dedicated daily `ImmutableRunStore` namespace.
- Produces: `ConnectionWitnessReceiptV1`, a separate connection receipt store,
  `FormalTaskState` and `interpret_formal_task()`.
- Connection terminal statuses include `passed`, `in-progress`, `failed`,
  `timed-out`, `blocked-user-auth` and `interrupted`; only `passed` and
  `in-progress` are zero-exit operational outcomes.

- [x] **Step 1: Write RED state-table tests**

Cover the amended UTC/time-window/result-code table: recent
`Running/0x41301 -> in-progress`, overdue running -> failure,
`0x41306 -> failure`, completed zero with exactly matching verified terminal
receipt -> pass, completed zero without receipt -> failure, ambiguous/newer
non-passing attempts -> failure, and missing/disabled/never-run/future/stale task
evidence -> failure. Assert no Moomoo SDK child is started while formal state is
in-progress. Cover missing/logged-out OpenD as `blocked-user-auth` without a
provider-evidence mutation.

- [x] **Step 2: Write RED deadline and persistence tests**

Inject TCP, scheduler and subprocess exceptions/timeouts. Assert each attempt writes a fresh immutable terminal receipt in `finally`, kills descendants, preserves both a failed scheduled slot and later supplemental success, and never overwrites concurrent run files.

- [x] **Step 3: Run RED tests**

Run: `.venv\Scripts\python.exe -m pytest tests/test_connection_witness.py -q`

- [x] **Step 4: Implement probe and thin wrappers**

Probe Python/import, loopback TCP 11111, Scheduler state, matching daily receipt,
read-only Moomoo capability and the public Hyperliquid API under independent
finite deadlines. Keep PowerShell limited to locating the pinned interpreter
and invoking the Python command with explicit disjoint roots, task name and
deadline/staleness inputs.

- [x] **Step 5: Run GREEN tests**

Run Task 6 pytest, focused Ruff and `git diff --check`.

- [x] **Step 6: Commit and record role evidence**

Commit: `fix(ops): persist deadline-bounded connection witnesses`

---

### Task 7: Verified Staggered Windows Scheduling

**Execution dependency:** Task 7 is historically numbered before Task 8 in
this plan, but it is blocked until Task 8 is checked complete and commit
`feat(ops): add single-authority witness outbox` is recorded. A first-incomplete
scan must skip this section until that dependency is satisfied.

**Files:**
- Modify: `tools/soak_schedule.ps1`
- Modify: `src/quantmesh/ops/source_contract.py`
- Modify: `src/quantmesh/ops/soak_runner.py`
- Modify: `tools/license_review.py`
- Create: `tests/test_soak_schedule.py`
- Modify: `tests/test_source_contract.py`
- Modify: `tests/test_soak_daily.py`
- Modify: `tests/test_security.py`
- Create: `requirements-build.txt`
- Modify: `docs/licenses.md`
- Modify: `docs/release-process.md`
- Create: `docs/runbooks/trusted-data-soak.md`

**Interfaces:**
- Consumes: Task 5 daily wrapper, Task 6 connection wrapper and Task 8 outbox
  roots/contracts.
- Produces: installer defaults daily 08:00, connection every two hours at minute 10; JSON verification output containing normalized actions/triggers/settings.
- Scope boundary: this task installs and round-trip verifies the two Windows
  tasks only. Task 9B separately reads back the Codex publisher heartbeat and
  requires its two-hour minute-20 cadence before any candidate clock starts.

- [x] **Step 1: Write RED command-construction and drift tests**

Mock Scheduler cmdlets and assert the clean remotely reachable commit, absolute
pinned paths, remote integration ref, frozen script/config/dependency digests,
explicit trusted/report/daily-run/connection/outbox roots, timezone and
principal, wake/start-when-available, battery execution, IgnoreNew, three
15-minute daily retries, one-hour daily limit, 15-minute connection limit and
minute-10 trigger. Feed every owned altered action, trigger or setting back and
assert installer verification exits non-zero with exact drift fields.
Assert the runtime recomputes rather than trusts the three supplied digests.
The dependency digest covers the canonical relative-path/byte-digest manifest
for `pyproject.toml` and `requirements-audit.txt` plus the normalized Python
implementation/version, interpreter-file digest and sorted installed
distribution name/version inventory from `importlib.metadata` (including
editable QuantMesh identity). Retain the full lock-file byte digest, but derive
the host-applicable expected inventory by excluding only absent members of the
existing canonical `PLATFORM_TOLERATED` contract. Move that canonical set to the
shared source-contract module and have `tools/license_review.py` reuse it so the
runtime and release gate cannot drift. Require every other pinned
`requirements-audit.txt` name/version in the installed inventory and reject
missing/version drift. The script digest covers the tracked daily/connection
Python and PowerShell entrypoints; the config digest covers canonical normalized
runner/scheduler configuration with digest fields excluded. Changed/missing
files, installed environment drift or configuration drift must fail before
collection.

The installer writes one canonical `ScheduleContractV1` manifest under an
explicit absolute manifest root using `<config-digest>.json`. The daily action
pins that exact manifest path. Runtime source verification reopens the manifest,
recomputes its normalized config digest and rejects filename/content drift;
Scheduler object read-back remains an independent comparison boundary.

Cover three explicit script modes: `InstallDisabled` creates/replaces both tasks
disabled and verifies them; `Verify` performs read-only round-trip comparison;
`GuardedEnable` first re-runs `Verify` and the configured preflight command, then
enables both tasks and reads them back. Any drift, preflight nonzero, partial
enable or post-enable mismatch triggers best-effort disable of both tasks and a
mandatory read-back. If either remains enabled, return `unsafe-partial-enable`
with the exact enabled task names and keep candidate-clock admission denied.
`Verify` itself is strictly read-only: drift returns non-zero plus
`unsafe_enabled_tasks` but performs no Register/Enable/Disable call. Pin zero
automatic retries for the connection task; supplemental
recovery is explicit and cannot backfill cadence.

- [x] **Step 2: Run RED tests**

Run: `.venv\Scripts\python.exe -m pytest tests/test_source_contract.py tests/test_soak_daily.py tests/test_soak_schedule.py tests/test_security.py -q`

- [x] **Step 3: Refactor registration and round-trip verification**

Use `Register-ScheduledTask` objects for both tasks and implement
`InstallDisabled`, read-only `Verify` and fail-closed `GuardedEnable`. Read with
`Get-ScheduledTask`/`Get-ScheduledTaskInfo`, normalize the owned fields and
compare against the expected contract. Emit one JSON result and fail on any
mismatch. Recompute actual runtime/script/config digests in the Python source
contract before collection rather than accepting caller assertions.

- [x] **Step 4: Run GREEN tests and PowerShell parse check**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_source_contract.py tests/test_soak_daily.py tests/test_soak_schedule.py tests/test_security.py -q
$null = [scriptblock]::Create((Get-Content tools/soak_schedule.ps1 -Raw))
$null = [scriptblock]::Create((Get-Content tools/connection_witness.ps1 -Raw))
git diff --check
```

- [x] **Step 5: Commit and record role evidence**

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
- Runtime boundary: a pure coordinator receives an injected remote client;
  `tools/soak_witness_outbox.py` remains local-only and performs no network I/O.
- Integration boundary: daily and connection runners invoke
  `ensure_intent(terminal)` after terminal durability but before a zero process
  exit; outbox failures are recorded separately and cannot mutate terminal
  receipts.
- Produces: `WitnessPublisher` with an injected remote client,
  `WitnessReconciler.reconcile_daily()`/`.reconcile_connection()`,
  `OutboxReconciliationFailureV1`, and a local `reconcile` CLI accepting exact
  daily/connection/report/outbox roots plus expected source identity.

- [x] **Step 1: Write RED outbox tests**

Assert exact enqueue retry, conflicting intent rejection, a cross-process single
publisher lease, deterministic pending order, ambiguous POST recovery by remote
re-query, duplicate remote-match failure, receipt URL/read-back digest
validation, restart idempotence, terminal-before-enqueue crash recovery and
inability to enqueue #124 success without a passing full-verifier proof.

- [x] **Step 2: Run RED tests**

Run: `.venv\Scripts\python.exe -m pytest tests/test_witness_outbox.py -q`

- [x] **Step 3: Implement local outbox authority**

Use Task 5 immutable primitives. The local CLI exposes canonical `list`, `show`
and `reconcile`; it never contains GitHub credentials, performs network I/O or
offers a publication-receipt write path. Daily and connection runners call
deterministic `ensure_intent` after terminal durability and return non-zero
until the exact intent exists. Reconciliation scans explicitly configured
stores for eligible unpaired terminals, reopens their report/source proof, persists a typed
create-once failure receipt on conflict/error and remains non-zero until all
eligible terminals are paired. `WitnessPublisher` alone owns the injected
remote list/POST/read-back protocol and receipt write under the publisher lease;
the remote URL must identify the expected `ZP151/quantmesh` issue comment.

- [x] **Step 4: Run GREEN tests**

Run Task 8 pytest, focused Ruff and `git diff --check`.

- [x] **Step 5: Commit and record role evidence**

Commit: `feat(ops): add single-authority witness outbox`

---

### Task 9A: Operational Acceptance, ADR and Reproducible Pre-Host Closure

**Files:**
- Create: `src/quantmesh/ops/soak_acceptance.py`
- Create: `tools/trusted_data_soak_acceptance.py`
- Create: `tests/test_trusted_data_soak_acceptance.py`
- Modify: `src/quantmesh/ops/witness_outbox.py`
- Modify: `src/quantmesh/ops/source_contract.py`
- Modify: `tests/test_witness_outbox.py`
- Modify: `tests/test_source_contract.py`
- Modify: `tests/test_soak_schedule.py`
- Modify: `tools/release_gate.py`
- Modify: `tools/license_review.py`
- Modify: `tests/test_release_gate.py`
- Modify: `tests/test_security.py`
- Create: `docs/adr/0019-overlap-resolution-and-operational-evidence.md`
- Modify: `docs/iterations/0021-trusted-data-fabric.md`
- Modify: `docs/goals/ACTIVE.md`
- Modify: `docs/runbooks/trusted-data-soak.md`

**Interfaces:**
- Consumes: the provider-only verifier plus immutable daily, connection and
  outbox contracts from all prior tasks.
- Produces: `OperationalSoakAcceptanceV1`, its create-once store, a local
  verifier CLI, an `operational-accepted` local outbox intent authority,
  independently reviewed simulation evidence and one exact clean integration
  SHA. It does not mutate a real host or provider evidence.

- [x] **Step 1: Write RED operational-acceptance tests**

Assert rejection of a manual/unpaired report, daily terminal/report/source
mismatch, missing/non-terminal/conflicting or overlapping connection slot, cadence gap,
publication time used as clock evidence and `minimum-hours=0` used for final
completion. Assert acceptance reopens every exact report/daily terminal,
requires 168 market-evidence hours plus configured sessions, validates the
connection cadence separately and publishes a content-derived immutable result.

Add the operational composition gate missing from the provider-only v2
verifier: candidate-to-first-report and every report-to-report interval must be
non-negative/positive as applicable and at most 26 hours, so one late report
cannot manufacture 168 hours. The evidence end is always the final accepted
provider report timestamp; no caller-provided `as_of`, terminal, intent,
publication or current-wall-clock timestamp may move it.

Accept an ordered same-day daily recovery chain only when every terminal is
passing, source-identical and linked by `recovery_of_run_id`; the last exact
terminal is canonical. For each required connection slot, every scheduled
reservation must have an immutable terminal. Multiple attempts are permitted
only when attempts increase, all are `passed` or typed `in-progress`, and their
execution intervals do not overlap. A failed/timed-out/auth-blocked/interrupted
scheduled attempt permanently fails the slot; supplemental evidence remains
auditable but never fills or heals it. Require the exact local outbox intent for
every admitted daily/connection terminal, but do not require remote publication
or use its timestamp as evidence.

- [x] **Step 2: Implement the separate verifier and thin CLI**

Do not modify provider-soak evidence semantics. The operational verifier reads
configured roots with safe immutable APIs, composes the accepted provider result
and emits one versioned acceptance object. Require explicit absolute, pairwise
disjoint data, report, daily-run, connection-run, outbox and operational-
acceptance roots. The final thresholds are at least 168 hours and four XNYS
sessions; the CLI exposes no free `as_of`. It has no provider, Scheduler,
GitHub, credential or trading authority.

Extend the local outbox contract with a distinct `operational-accepted` kind
fixed to issue #124. Its local evidence ID is the acceptance ID and it binds the
last report, canonical daily terminal, source contract and commit. It can be
created only by reopening an `accepted=true` object from the operational store;
the existing leased Publisher remains the sole remote writer, and Task 9A
performs no network call.

- [x] **Step 3: Write ADR and close documentation**

Record why resolution is additive, why v2 baseline IDs are required, why
operational receipts remain outside provider evidence, why final acceptance is
a separate composition and why remote publication uses a local outbox. Update
the runbook with `blocked-user-auth`, no-backfill, authority inventory and
candidate-reset rules.

- [x] **Step 4: Run complete automated verification**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_overlap_resolutions.py tests/test_quality_evidence.py tests/test_quality_policies.py tests/test_quality_publication.py tests/test_data_catalog.py tests/test_data_catalog_api.py tests/test_trusted_data_tool.py tests/test_hyperliquid_collection.py tests/test_moomoo_collection.py tests/test_immutable_runs.py tests/test_operational_processes.py tests/test_source_contract.py tests/test_soak_daily.py tests/test_trusted_data_soak.py tests/test_connection_witness.py tests/test_witness_outbox.py tests/test_soak_schedule.py tests/test_trusted_data_soak_acceptance.py -q
.venv\Scripts\python.exe -m ruff check src tests tools
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\python.exe -m pip check
.venv\Scripts\python.exe tools/license_review.py
git diff --check
```

Record exact commands, exit codes, counts, durations and expected skips. Run the
`verification-before-completion` skill before any passing claim.

- [x] **Step 5: Run and record clean-host simulations and failure drills**

From the pinned branch environment and temporary disjoint roots, inject provider
outage, verifier rejection, new overlap, child timeout, scheduler
running/terminated states, concurrent daily invocations, orphan-terminal outbox
reconciliation and ambiguous publisher result. Each must produce the expected
non-zero/typed receipt without altering real provider evidence. Record the
results in the iteration ledger, then rerun affected automated gates.

- [x] **Step 6: Commit the complete pre-host checkpoint**

Commit code, documentation and recorded simulation evidence together:

```text
docs(iteration): close reliability repair pre-host gates
```

Require the committed checkout to remain clean and rerun the focused acceptance
selection. Any later source/documentation correction returns to Steps 4-6 and
creates a new reviewed candidate SHA.

- [ ] **Step 7: Final whole-branch review**

Generate a review package from the `origin/main` merge base through the exact
candidate HEAD. Obtain one independent Standards/Spec/Safety verdict. Fix every
Critical/Important finding through the bounded review loop; commit fixes, rerun
verification and regenerate the review package until the verdict is clean.
Record deferred Minor findings explicitly.

- [ ] **Step 8: Push and pin the pre-host SHA**

Push `codex/0021-soak-reliability-goal` to the concrete integration ref
`origin/codex/0021-soak-reliability-goal` without force, record
`git rev-parse HEAD` as `PRE_HOST_SHA`, and verify:

```powershell
$PreHostSha = (git rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0 -or $PreHostSha -notmatch '^[0-9a-f]{40}$') { throw "invalid pre-host SHA" }
$RemoteIntegrationRef = "origin/codex/0021-soak-reliability-goal"
$Dirty = @(git status --porcelain --untracked-files=all)
if ($LASTEXITCODE -ne 0 -or $Dirty.Count -ne 0) { throw "pre-host checkout is dirty" }
git merge-base --is-ancestor $PreHostSha $RemoteIntegrationRef
if ($LASTEXITCODE -ne 0) { throw "pre-host SHA is not reachable from the integration ref" }
```

Both must succeed. Task 9B uses a dedicated clean execution checkout detached at
this exact SHA; iteration evidence is written from a separate documentation
worktree so the runner HEAD cannot drift.

### Task 9B: Authorized Real-Host Migration

**Files/state:**
- Modify host task definitions through `tools/soak_schedule.ps1` only.
- Update the `quantmesh-daily-witness` heartbeat through the Codex automation
  API only after local outbox verification.
- Modify the iteration ledger only from the separate documentation worktree;
  push its operational checkpoint without force after review.

**Interfaces:**
- Consumes: exact `PRE_HOST_SHA`, designated Windows host identity, complete
  legacy-authority inventory and seven resolved sibling roots.
- Produces: disabled-then-enabled round-trip-verified Windows tasks, verified
  minute-20 publisher heartbeat, one fresh accepted daily cycle and immutable
  outbox/publication receipts. It does not close the 168-hour gate.

**Authority gate:** The operator designates the replacement Windows host and an
administrator proves every prior authority is stopped. At minimum, inventory
the observed `ZHOULAPTOP` `\QuantMesh Daily Soak` task and its
`C:\Users\15492\Develop\qm-soak-168h\run-soak.ps1` action plus every other
QuantMesh Scheduler task and publisher automation; record host, TaskPath/name,
action digest, enabled/running state and last result. All legacy schedulers must
be disabled and not running, and all prior publisher automations paused or
superseded by the one named authority. The dedicated execution checkout must be
clean, detached at `PRE_HOST_SHA` and reachable from the configured remote ref.

**Pre-mutation verification:** From the dedicated execution checkout, set
`$PreHostSha` to the recorded 40-hex `PRE_HOST_SHA` and `$RemoteRef` to the
configured integration ref, then require:

```powershell
$Dirty = @(git status --porcelain --untracked-files=all)
if ($LASTEXITCODE -ne 0 -or $Dirty.Count -ne 0) { throw "runner checkout is dirty" }
$ActualSha = (git rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0 -or $ActualSha -ne $PreHostSha) { throw "runner SHA drift" }
git merge-base --is-ancestor $PreHostSha $RemoteRef
if ($LASTEXITCODE -ne 0) { throw "runner SHA is not reachable from the configured ref" }
.venv\Scripts\python.exe -m pytest tests/test_connection_witness.py tests/test_witness_outbox.py tests/test_soak_schedule.py tests/test_trusted_data_soak_acceptance.py -q
if ($LASTEXITCODE -ne 0) { throw "focused pre-mutation pytest failed" }
.venv\Scripts\python.exe -m ruff check src/quantmesh/ops tools tests/test_connection_witness.py tests/test_witness_outbox.py tests/test_soak_schedule.py tests/test_trusted_data_soak_acceptance.py
if ($LASTEXITCODE -ne 0) { throw "focused pre-mutation Ruff failed" }
git diff --check
if ($LASTEXITCODE -ne 0) { throw "pre-mutation diff check failed" }
```

Any non-zero command stops Task 9B before host mutation.

- [ ] **Step 9: Perform read-only preflight and optional separately authorized resolution**

Run `quantmesh-data overlap inspect` read-only against the rejected trusted-data
root and compare the exact evaluation/report/policy/dataset/manifests/fingerprint/diff
with issue #124. Do not write into evidence-v2 or the old trusted-data root.
The real resolution is omitted from migration unless the operator separately
authorizes an additive write to that original trusted-data root; if authorized,
record the decision and exact backup/read-back procedure before acting. An
overlay or copied resolution store is not part of this plan.

- [ ] **Step 10: Prepare roots and install the Windows tasks disabled**

Create the empty sibling roots `C:\QuantMesh\trusted-data-v3`,
`C:\QuantMesh\evidence-v3`, `C:\QuantMesh\daily-runs-v3`,
`C:\QuantMesh\connection-runs-v3`, `C:\QuantMesh\witness-outbox-v3`,
`C:\QuantMesh\schedule-contracts-v3` and
`C:\QuantMesh\operational-acceptance-v3` only after resolving and printing
their exact absolute paths and proving no two are equal or have a parent/child
relationship. Install the daily 08:00 and two-hour minute-10 tasks from the
dedicated checkout in disabled state, round-trip every owned
action/trigger/principal/setting/root/ref/digest field, and keep them disabled.
Run the connection command manually as preflight; absent/logged-out OpenD is
`blocked-user-auth` and cannot start a clock.

Incident override, 2026-09-02: the first disabled v3 installation failed closed
after publishing its immutable schedule manifest. The v4 retry installed and
verified both tasks disabled, but its supplemental preflight exposed an invalid
path-qualified Scheduler task identity and an OpenD-absent timeout-precedence
bug; no task ran and no candidate clock started. Preserve all v3 and v4 roots
as negative evidence. The reviewed retry uses the same seven exact basenames
with suffix `-v5`, after the same absolute/disjoint/empty/non-reparse checks;
no earlier artifact is copied, linked or admitted into v5.

- [ ] **Step 11: Update and read back the heartbeat publisher**

Update the existing `quantmesh-daily-witness` heartbeat to minute 20. Its prompt
consumes only pending outbox intents, acquires the publisher lease, queries the
exact idempotency key before posting, re-queries after ambiguity, reads back the
comment and records the local publication receipt. Preserve notification
settings. Read the automation back and require the exact two-hour minute-20
cadence and single-authority identity.

- [ ] **Step 12: Start the fresh candidate and enable verified cadence**

Run one fresh five-target daily cycle from `PRE_HOST_SHA`, reopen every recorded
manifest/evaluation/checkpoint/daily terminal and require `minimum-hours=0`,
`minimum-xnys-sessions=1` PASS. This proves one daily cycle, not final
completion. Enable the already verified Windows tasks only after this local
read-back succeeds, immediately read their enabled/not-running state back and
record their immutable local receipts. Any pre-enable failure leaves them
disabled and invalidates the candidate.

- [ ] **Step 13: Publish repair/restart witnesses through the outbox**

After local read-back succeeds, publish one repair/restart witness to #124 and
one scheduler/probe repair witness to #127 through the outbox. Record the exact
comment URLs, read-back digests and local publication receipts in the iteration
ledger.

- [ ] **Step 14: Review, commit and push the operational checkpoint**

From the documentation worktree, record exact host/root/SHA/schedule/automation
and publication evidence. Obtain a read-only review, commit
`docs(iteration): start repaired trusted-data soak candidate`, rerun documentation
checks and push without force. The dedicated runner checkout remains detached at
`PRE_HOST_SHA`.

Post-mutation verification must re-read both Windows tasks, the automation, all
seven roots, the accepted daily terminal/report/source proof, pending/publication
outbox state and the pinned runner SHA. Record every command/API result and exit
code in the iteration ledger; any mismatch disables the new Windows tasks,
leaves immutable failure evidence and invalidates the candidate without
backfill.

Do not claim the 168-hour gate complete. The heartbeat monitors real elapsed
evidence; completion requires 168 hours and a final operational-acceptance PASS.

- [ ] **Step 15: Verify final 168-hour evidence without extending its clock**

After 168 real hours, run the separate Task 9A operational verifier. It reopens
every accepted daily report and its exact immutable daily terminal, requires the
same source contract/report identity and accepted provider-verifier proof, and
validates connection-receipt cadence. Operational or publication timestamps
cannot create or extend elapsed evidence. Only this immutable acceptance result
may create the local `operational-accepted` intent; the leased Publisher still
must perform exact-key remote query/post/read-back before recording a final-
completion publication receipt. It grants no trading authority.
