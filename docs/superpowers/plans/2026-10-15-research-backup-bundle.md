# Same-Snapshot PostgreSQL Backup Bundle Implementation Plan

> **For agentic workers:** Execute this single bounded task inline with TDD. Files listed here are the complete source scope. The frozen backup qualifier and shared iteration/locks are outside scope.

**Goal:** Add a backward-compatible bundle API that pairs the existing formal-service manifest and exact referenced artifacts with a real custom-format pg_dump imported from the same live exported PostgreSQL snapshot.

**Architecture:** Preserve `capture_manifest()` and `validate_manifest()` as manifest-only version-1 operations. Add `capture_backup_bundle()` and `validate_backup_bundle()` that share the existing validated state/artifact logic, hold the exporting read-only repeatable-read connection open through child completion, pin and execute an already-open `pg_dump` inode by file descriptor, and write a separate canonical bundle receipt without changing manifest-v1 bytes.

**Tech Stack:** Existing Python 3.12 Agent-service venv, pg8000, Pydantic and standard library; audited PostgreSQL 18.6 `pg_dump` SHA256 `137cf7c068b3459f5205f97f27cd206b537228e031d721f52535daf29c0ab6f8`.

**Spec:** Root-approved Task 1 authorization for Issue #171 / iteration 0038; `docs/superpowers/plans/2026-10-15-research-recovery-manifest.md`; `docs/adr/0026-research-job-publication-and-advisory-boundary.md`; `output/0038-production-backup-next/PLAN.md`.

## Global Constraints

- Base and branch: `e11a57bb8d95d4fcce5a1a0824da04d035fcde8f`, `codex/0038-recovery-manifest`; do not touch PR176.
- Only tracked files: modify `services/research_agent/src/qm_research_agent/backup_capture.py`, modify `services/research_agent/tests/test_backup_capture.py`, create this plan.
- Preserve `capture_manifest(dsn, *, schema, lake_root, artifact_root, output_root, policy) -> dict`, `validate_manifest(root, expected_digest) -> dict`, manifest v1 canonical bytes, exact-tree rules and no-write/readonly behavior.
- New API has no caller-provided digest/pin: `capture_backup_bundle(dsn: SecretStr, *, schema: str, lake_root: Path, artifact_root: Path, output_root: Path, pg_dump_path: Path, policy: PortfolioBudgetPolicy | None) -> dict`; it admits only the in-code audited SHA above. `validate_backup_bundle(root: Path, expected_digest: str) -> dict` verifies the canonical bundle receipt, nested v1 manifest, exact tree, dump and artifact references.
- Strictly validate schema, DSN shape, policy, all roots, output absence/ownership and the tool file before calling `connect()`. Open the tool with no-follow descriptor-relative traversal; require current-user ownership, regular executable, single link, no group/world write; hash the opened descriptor against the fixed pin and execute `/proc/self/fd/<fd>` with `pass_fds` so path replacement cannot change the executable.
- The only source DB queries remain read-only. No writer advisory lock, schema bootstrap, DDL or ledger mutation. No store/ledger API changes, CLI, service changes or Task 2 recovery tool.
- Export one `pg_export_snapshot()` in `READ ONLY REPEATABLE READ`; invoke `pg_dump --snapshot=<token>` while that exporter transaction remains active, await success, then finish manifest/bundle validation before its rollback/close. Never retain the snapshot ID in returned data, files, exceptions, output streams or logs.
- No shell, caller-selected command/args, user-supplied hash, DSN/password in argv/logs. Construct private libpq service/credential files with mode 0600, pass only their descriptor-backed paths to the child, and unlink only when the same opened file identity remains at that directory entry.
- Bound the one child to 60 seconds, stderr diagnostics to 2 MiB and custom archive stdout/dump bytes to 32 MiB. Use `pg_dump --file=-` and stream stdout into an exclusive parent-owned dump file so the exact byte cap is enforceable; never echo either stream. On failure/timeout/limit, terminate then kill only the exact spawned child as needed and always wait for it before rollback/connection/file-descriptor cleanup. Cleanup errors cannot bypass DB rollback/close.
- Do not alter the frozen qualifier, its tests/runbook, baseline/build/schema/protocol/tool/restic/PG pins, service store, ledger, accounting, CLI, shared ACTIVE/iteration/lock/root docs. Do not start PostgreSQL/restic or run native qualification in this task.
- Preserve reserved/unknown effects and portfolio identities as current capture does. This API has no provider/external-effect behavior. Record unit/affected checks and source/plan hashes under ignored `output/0038-backup-bundle/`.

## Review Focus

1. Snapshot lifetime: `test_capture_backup_bundle_runs_pg_dump_before_exporter_close` and `test_capture_backup_bundle_never_returns_or_persists_snapshot_token`.
2. Tool admission/path replacement: `test_capture_backup_bundle_refuses_unpinned_tool_before_connect` and `test_capture_backup_bundle_executes_opened_inode_after_path_replacement`.
3. Child timeout, output/dump ceilings and cleanup: `test_capture_backup_bundle_timeout_reaps_child_and_closes_database` and `test_capture_backup_bundle_refuses_dump_failure_and_cleans_private_files`.
4. Bundle exact-tree/ref substitution: `test_validate_backup_bundle_rejects_extra_dump_and_artifact_substitution`.
5. Existing API compatibility: all pre-existing `test_backup_capture.py` cases remain unchanged and pass; manifest-only outputs keep their v1 shape and flags.

---

### Task 1: Snapshot-scoped bundle capture and validation

**Files:**
- Modify: `services/research_agent/src/qm_research_agent/backup_capture.py`
- Test: `services/research_agent/tests/test_backup_capture.py`
- Create: `docs/superpowers/plans/2026-10-15-research-backup-bundle.md`

**Interfaces:**
- New `capture_backup_bundle(...) -> dict` as defined above; success includes only `bundle_sha256`, `manifest_sha256`, `dump_sha256`, `dump_size`, `snapshot_closed=True`, and `manifest_only=False` plus non-secret checked manifest metadata. The token never escapes.
- New `validate_backup_bundle(root: Path, expected_digest: str) -> dict`; accepted exact root tree is `capture/manifest.json`, `capture/artifacts/<exact manifest refs>`, `research.dump`, and canonical `bundle.json`.
- `bundle.json` exact fields: integer `bundle_version=1`, `schema="qm_research"`, `manifest_sha256`, `dump_sha256`, and positive integer `dump_size <= 32 MiB`; no snapshot token.

- [x] **Step 1: Add RED tests before production edits.** Covered invalid tool/path refusal before DB connect; opened-inode path-swap resistance; the exported token passed to a test child while the fake exporter remains open; token absence; dump failure/timeout/output/dump ceilings; exact child reaping and database cleanup; identity-safe service-file cleanup; round-trip bundle validation; dump, artifact, and extra-path substitution; and all existing manifest-only cases.
- [x] **Step 2: Run the focused suite and record RED.** In the audited WSL venv, the new API selection produced 9 expected `AttributeError` failures and 27 deselected tests before implementation.
- [x] **Step 3: Implement the minimum bundle lifecycle.** Added fixed tool pin and limits, descriptor-backed executable and service configuration, private output layout, one exported snapshot shared by manifest and pg_dump, bounded stdout streaming, canonical bundle receipt, and exact validation. Kept manifest-only APIs and v1 format intact.
- [x] **Step 4: Implement bounded child and independent cleanup.** The child uses fixed argv/no shell, a 60-second deadline, a 2 MiB stderr cap, and a 32 MiB archive cap. Timeout/failure paths terminate or kill and reap the exact child before exporter rollback/close. Cleanup attempts rollback, close, identity-checked service cleanup, output cleanup and each descriptor close independently. A reviewer-found substituted service-file cleanup case is covered by a regression test; the replacement entry is preserved while other private bundle files are removed.
- [x] **Step 5: Implement bundle verification.** Bundle validation uses no-follow private-directory/file reads, canonical JSON and expected digest checks, dump size/hash verification, and nested manifest-v1/artifact validation. The standalone manifest validator is unchanged.
- [x] **Step 6: Run RED-to-GREEN and affected checks.** Evidence is recorded below; no PostgreSQL, restic, or native qualification commands were run.
- [x] **Step 7: Complete review and checkpoint.** Two bounded review rounds found credential cleanup and service-file serialization issues. Each was fixed test-first, with the second verified through the audited libpq `PQconndefaults()` parser only. The corrective checkpoint is committed and pushed below; no PR or merge was created.

### Task 2: Correct custom-format pg_dump stdout transport

**Trigger:** Native attempt a08 created a 20,278-byte PostgreSQL custom archive named `-` in the checkout (SHA-256 `1d1cb1edac0142864d62299f7bb9a296cb775bb5eabe531d7958edc74eae6d2c`) and `capture_backup_bundle` later refused the zero-sized bundle dump. PostgreSQL 18's custom writer treats every nonempty `--file` value as a filename; only an omitted filename selects stdout. The artifact is preserved under ignored qualification history.

**Scope:** Modify only `services/research_agent/src/qm_research_agent/backup_capture.py`, `services/research_agent/tests/test_backup_capture.py`, and this plan. Qualification/handoff artifacts may be updated under ignored `output/0038-formal-backup-recovery-native/`. Do not change API, manifest/schema, pinned tool hash, credentials, lease handling, child timeout/output limits, failure cleanup, service store, CLI, frozen qualifier, active iteration, ADR, or production deployment. Do not start PostgreSQL, invoke native capture, or run restic/restore in this slice.

**Implementation:** Remove `--file=-` from the fixed `pg_dump` argv so custom archive bytes reach the existing bounded stdout pipe. After a zero child exit and before returning dump metadata, refuse when `stdout_bytes == 0`; this prevents an empty dump from reaching bundle creation. Do not relax bundle validation.

**Acceptance:**

1. Add a focused `_run_pg_dump` regression whose real test child exits zero with empty stdout; observe the expected failure before production changes, then pass after the fix.
2. Adapt the existing fake pg_dump body to assert that `--file=-` is absent while nonempty archive bytes still round-trip through capture and bundle validation.
3. Run the focused tests, affected service checks, Ruff check/format, and `git diff --check`; record exact commands and exits in ignored evidence. No native service qualification is part of this slice.
4. Perform one narrow review of the argv/stdout transport and zero-byte guard. Commit and push the original branch only after green verification; do not create or alter a PR, merge, touch CI branch 178, or rerun PostgreSQL/restic. Stop for root to review/cherry-pick the new head and run CI.

**Evidence boundary:** The a08 raw record does not contain pg_dump's exit code, the private pipe's byte count, or its dump hash. Preserve these as unrecorded fields; the literal `PGDMP` file/hash and PostgreSQL 18 source semantics are the direct root-cause evidence.

## Completion Record

**Verification:** RED: `python -m pytest services/research_agent/tests/test_backup_capture.py -q -k 'capture_backup_bundle or validate_backup_bundle'` → 9 expected failures, 27 deselected, before API implementation. Service-parser RED → 4 expected failures and 3 passes, including the real parser mismatch, trailing-space preservation, overlong-line admission, and late rather than pre-connect rejection. Parser GREEN: 7 passed using the audited libpq parser-only witness. Final affected check `python -m pytest services/research_agent/tests/test_backup_capture.py tests/test_research_job_store.py tests/test_accounting.py -q` → 99 passed. Ruff check and format check passed for the two Python files; `git diff --check` passed; `git submodule status` showed the configured submodules uninitialized and unchanged. Test runs report one pre-existing NumPy/exchange-calendars deprecation warning.

**Compatibility and safety evidence:** Existing `test_backup_capture.py` manifest-only cases pass unchanged. Bundle round-trip, exact tree, dump/ref tamper, token redaction, snapshot lifetime, opened-inode execution, timeout/reaping, output caps and substituted-service-file preservation tests pass. The service-file serializer writes literal libpq values and refuses control characters, trailing whitespace and overlong lines before database connect; an opt-in test confirms byte-for-byte host, port, user, password, dbname and sslmode values through audited libpq `PQconndefaults()` without calling any connection API. Limits are 60 seconds, 2 MiB stderr, and 32 MiB dump. No PostgreSQL service, restic, native qualification, provider, or Task 2 recovery activity occurred. Round 1 reproduced and fixed the substituted-path cleanup gap. Round 2 reproduced and fixed conninfo-style quoting with the real parser, then added refusal tests for unrepresentable values.

**Checkpoint:** Commit and source/plan hashes are recorded in ignored `output/0038-backup-bundle/HANDOFF.md` and `checked-summary.json`.

**Task 2 completion evidence:**

- TDD RED: the new empty-stdout child test failed before the guard (`DID NOT RAISE ValueError`); GREEN: the focused test passed. The RED result was observed before the production edit; no raw RED log was retained. The focused GREEN output is `output/0038-formal-backup-recovery-native/raw/tdd-green-focus.log`.
- Final affected verification from the project Linux virtualenv: `PYTHONPATH=src:services/research_agent/src QM_LIBPQ_LIBRARY=/var/tmp/quantmesh-backup-final-xvcv1u9k/prefix/lib/libpq.so.5 /var/tmp/quantmesh-backup-final-xvcv1u9k/venv/bin/python -m pytest services/research_agent/tests/test_backup_capture.py -q` → 45 passed; `PYTHONPATH=src:services/research_agent/src QM_LIBPQ_LIBRARY=/var/tmp/quantmesh-backup-final-xvcv1u9k/prefix/lib/libpq.so.5 /var/tmp/quantmesh-backup-final-xvcv1u9k/venv/bin/python -m pytest tests/test_research_job_store.py tests/test_accounting.py -q` → 55 passed. One pre-existing NumPy/exchange-calendars deprecation warning in each run. Logs: `raw/bugfix-backup-capture-final.log` and `raw/bugfix-jobstore-accounting-final.log`.
- Ruff check → all checks passed; Ruff format check → both files already formatted; Windows `git diff --check` → exit 0. No production behavior beyond removal of the `--file=-` argument and refusal on empty stdout was changed.
- One narrow transport review confirmed the existing pipe, byte cap, child exit handling, metadata checks, and cleanup remain in place. Only the three scoped tracked files are changed. No PostgreSQL, native capture, restic, or restore was run for this bugfix.
- Source SHA-256 after the fix: `a0bc61080dc33035c0f161b2cc33be4117e22a058b1d07dee0000d314fd5fa12`. Commit and push evidence will be added after checkpointing this original branch.
