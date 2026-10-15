# Research Recovery Manifest Implementation Plan

> **For agentic workers:** Execute the single bounded task inline. Use TDD; files listed below are the full tracked scope.

**Goal:** Capture a read-only manifest of the formal qm_research PostgreSQL service schema and every referenced immutable artifact from one PostgreSQL repeatable-read snapshot.

**Architecture:** Use services/research_agent's direct SecretStr connection, explicit READ ONLY REPEATABLE READ transaction and one exported snapshot. Read all job/outbox/effect/portfolio rows on that connection and copy only exact same-job immutable refs, checking source and destination file identity and digests. Fingerprint private row contents without copying payloads/secrets into the manifest. No store/ledger constructors or writer advisory lock.

**Tech Stack:** Existing Python 3.12 Agent service environment, pg8000, Pydantic contracts, Python standard library.

**Spec:** Root-approved bounded handoff; formal contracts in services/research_agent/src/qm_research_agent/{store.py,budgets.py,accounting.py}; inventory precedent in tools/qualify_research_backup.py.

## Global Constraints

- Base: origin/main fb66ed29d374e7f63acd47a52a508904bcbbc5ca; branch codex/0038-recovery-manifest.
- Only new tracked files: services/research_agent/src/qm_research_agent/backup_capture.py, services/research_agent/tests/test_backup_capture.py, and this plan.
- Formal schema is qm_research, qm_schema version 1. Use qm_research_agent.store.connect(SecretStr) directly.
- Never call PostgresJobStore.__init__, PostgresJobStore._transaction, EffectLedger(store), accounting.initialize, or any core store/public protocol mutation.
- No writer advisory lock. Use one explicit READ ONLY REPEATABLE READ transaction and pg_export_snapshot(); MVCC supplies the table/row cut. Changed/missing immutable bytes fail closed.
- Capture jobs(sequence), analysis_outbox(sequence), model_effects, qm_portfolio_schema, qm_portfolio_policy and qm_portfolio_reservations when initialized. Either all four effect/accounting tables are absent (mark uninitialized) or all present; partial/orphan/unknown status/version/policy/budget invariants refuse.
- Empty store, no-analysis, pending analysis, reserved/unknown provider outcome and completed states are capturable. No completed model analysis is required.
- Analysis queue rows follow the formal job-store transitions: queued/running backtests may retain pending analysis without an outbox row; successful requested jobs in pending analysis have one outbox row with null lease and attempt 0; running analysis has one matching lease, including expired leases. Terminal and no-analysis jobs have no outbox row.
- Preserve exact effect identities and both sides of portfolio reservations, policy binding and high-water. Never call a provider or change ledger state.
- Sequence counters are outside MVCC. Record the maximum row.sequence observed per table. Do not claim atomic capture of last_value; later restore must require the restored counter >= captured maximum.
- Manifest/logs exclude DSN, password, raw jobs.payload, effect response/checkpoint, prompts, model inputs and credentials. Record canonical row hashes, necessary identities/status/price, and response/checkpoint hashes.
- No CLI/tools, DB dump, restic, restore, SSH, persistent service, model call, AWS/S3/IAM, new dependency, or cost in this slice.
- Optional native check may use only already audited PG18 binaries/environment, a fresh owned temporary WSL cluster, synthetic dummy credentials, verified free disk >=50GB and <=128MiB new evidence. If uncertain, record blocker and stop; never download/install a substitute or touch existing/production PG.
- Do not modify PR176, Worker files, core/formal store or ledger, accounting, runtime/advisory, old qualifier, runbook, shared ACTIVE/iteration/locks.

## Review Focus

1. Source or destination artifact is linked, foreign-owned, cross-job, missing, extra, unstable or hash/size substituted: refuse.
2. Concurrent source row advancement remains outside the captured MVCC cut; no writer lock or false sequence atomicity claim.
3. Empty/uninitialized/unconfigured, analysis-not-requested and pending states remain valid.
4. Reserved unknown-outcome effects retain their exact identity and portfolio reservation without recall or budget reset.
5. Partial tables, unsupported schema/status/policy and orphan effect/reservation state fail closed without DDL.

---

### Task 1: Read-only formal service manifest capture

**Files:**
- Create: services/research_agent/src/qm_research_agent/backup_capture.py
- Test: services/research_agent/tests/test_backup_capture.py
- Plan: docs/superpowers/plans/2026-10-15-research-recovery-manifest.md

**Interfaces:**
- Reuse qm_research_agent.store.connect, store._Connection only for read-only accounting.validate, JobRecord/AnalysisLease/AnalysisRecord/ArtifactRef and canonical digest contracts, PortfolioBudgetPolicy, schema_digest and protocol_digest. Validate report envelopes directly and use descriptor-relative no-follow reads to avoid path races; never instantiate the store.
- Export capture_manifest(dsn: SecretStr, *, schema: str, lake_root: Path, artifact_root: Path, output_root: Path, policy: PortfolioBudgetPolicy | None) -> dict and validate_manifest(root: Path, expected_digest: str) -> dict.
- Persist no snapshot token. Return snapshot_closed=true, manifest_only=true.

- [x] Step 1: Add tests for direct connect, explicit read-only repeatable-read transaction and pg_export_snapshot; no SQL writes; fixed schema/version; empty valid store; all-absent and all-present empty unconfigured ledger.
- [x] Step 2: Run focused tests and observe RED because the module is absent.
- [x] Step 3: Implement one concrete connection reader/capture and manifest validator. Read only explicit known tables and sequences on the same connection; use canonical per-row/table SHA-256; write an exclusive private manifest root and only referenced artifact bytes.
- [x] Step 4: Run focused tests to GREEN, including no SQL write and tampered manifest refusal.
- [x] Step 5: Add service-contract jobs for queued/running/succeeded/failed/cancelled plus not-requested, pending and running analysis states. Seed and verify a reserved effect with its matching policy/reservation and high-water. Reject partial schemas, effect/reservation pairs without a job, orphan outbox rows and inconsistent pending/running outbox states.
- [x] Step 6: Verify a succeeded report reference is copied with its digest, reject a cross-job ref, and refuse a source artifact changed between validation and copy while cleaning the incomplete output. The implementation applies descriptor-relative no-follow, owner/mode/link-count and exact output-tree checks.
- [x] Step 7: Run the focused suite and affected PostgreSQL/job-store regressions. Run Ruff, formatting, diff and submodule checks. Do not run the old 45/85 qualification.
- [x] Step 8: Preflight the existing PG18.6 and Python 3.12.3 environment and disk, then run a fresh owned WSL cluster for read-only write refusal, a repeatable-read concurrent-commit witness, real empty-store capture and manifest validation. The witness did not import the exported snapshot into a second connection or test artifact advancement; the later code fix was not re-certified natively. Evidence stayed below 128 MiB. Record the cluster PID and confirm stop/cleanup.
- [x] Step 9: Complete two bounded read-only review rounds. Root authorized one final, narrow correction for second-round state consistency and cleanup findings; no third review was run. Commit only the three files on codex/0038-recovery-manifest and push that branch; no PR/merge/deploy.

### Required checks

    python -m pytest services/research_agent/tests/test_backup_capture.py -q
    python -m pytest services/research_agent/tests/test_research_postgres_job_store.py services/research_agent/tests/test_research_job_store.py -q
    ruff check services/research_agent/src/qm_research_agent/backup_capture.py services/research_agent/tests/test_backup_capture.py
    ruff format --check services/research_agent/src/qm_research_agent/backup_capture.py services/research_agent/tests/test_backup_capture.py
    git diff --check
    git submodule status

Stop after reporting formal-service-snapshot-manifest-qualified. The manifest is not a database dump or recoverable encrypted backup. Root independently verifies before integration.

## Implementation and review evidence

- Focused capture plus affected PostgreSQL/job-store regressions: 56 passed, 2 skipped (optional PostgreSQL integration requires an external DSN). Ruff lint and format checks, `git diff --check`, and `git submodule status` completed; submodules remain at their existing uninitialized (`-`) state.
- Review round 1 found effect/reservation pairs could reference a missing job; fixed by binding every effect to a captured job and adding a refusal test.
- Review round 2 found successful pending analyses could omit their outbox row, running analyses could omit a lease, and cleanup errors could skip database close. Root's Planner ruling preserved the formal queued/running backtest pending-without-outbox state, required the success/pending/outbox and running/lease bindings, allowed expired leases to be captured, and required independent cleanup attempts with fixed public errors. Positive and negative tests cover these transitions and descriptor closure. No third review was run.
- Root's targeted acceptance check then found `analysis_state=running` could bypass the outbox checks on a non-succeeded backtest with no outbox row. A RED test reproduced it; a global state guard now rejects it. Paired existing tests confirm queued/running backtests with pending analysis and no outbox remain valid. This was a narrow completion of the same authorized correction, not a structural review; no new review or native run was performed.
- Native evidence: PostgreSQL 18.6, CPython 3.12.3, existing audited venv, 981,803,428 KiB available on `/var/tmp` at preflight, temporary cluster PID 75742, port 55439, capture manifest digest `066c06a22cd630099fd5eba231be98e5bf18a088d23d7e4724a25ef9421eb998`; readonly DDL was refused, a concurrent commit remained invisible to an already-read repeatable-read transaction, empty capture/manifest validation passed, and the temporary cluster was stopped and removed. The native run preceded final source changes; its implementation source hash was not recorded, so this evidence is not a native certification of the final file.
- This slice did not run pg_dump, restic, restore, off-host copy, or any provider/model call. It qualifies only the bounded formal snapshot-manifest capture path.
