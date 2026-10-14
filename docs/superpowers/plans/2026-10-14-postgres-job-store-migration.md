# PostgreSQL Research Job Store Migration Plan

> **For agentic workers:** Follow the repository TDD and review lifecycle in `docs/agents/cross-agent-execution.md`.

**Goal:** Preserve deterministic FIFO claims and lease recovery when a PostgreSQL research job store is opened or upgraded from schema v1.

**Architecture:** Keep the existing `PostgresJobStore` and nine-method `JobStore` contract. Upgrade the schema transactionally to v2, assigning missing queue positions from persisted enqueue/completion timestamps and stable job IDs; add no new queue, service, dependency, or deployment path.

**Tech Stack:** Python 3.12+, pg8000 (synchronous DB-API), PostgreSQL, pytest.

**Spec:** `docs/adr/0026-research-job-publication-and-advisory-boundary.md`; operator-approved Option A in `docs/iterations/0038-research-foundation.md`.

## Global Constraints

- Preserve the nine-method `JobStore` protocol and SQLite behavior.
- Keep schema changes transactional and serialize migration with the existing schema advisory lock.
- Preserve FIFO using persisted timestamps and deterministic job-ID tie-breaking.
- Keep `paper=true` and `live=false`; do not configure model keys, deploy services, or change AWS resources.
- PostgreSQL 16 local integration verifies SQL behavior only; it does not qualify PostgreSQL 18.6 production TLS, backup, HA, or deployment.

## Review Focus

- Existing v1 databases without queue-position columns migrate atomically and retain FIFO.
- Reopening a migrated store does not add duplicate indexes or reorder jobs.
- Explicit legacy positions do not break future identity-generated positions.
- Expired analysis leases are reclaimable with a higher attempt while stale lease owners remain fenced.
- The Python closure admits the reviewed exact SPDX identifiers LGPL-2.0/2.1/3.0 (base, `-only`, `-or-later`), MPL-2.0, EPL-2.0 and CDDL-1.0. Maintainers may add another exact identifier without new operator approval only after official-text review confirms comparable weak/file-level copyleft and records package, version, notices, distribution and applicable source/relinking/network duties. GPL/AGPL, Commons Clause, proprietary and unknown licenses remain denied absent a separate decision.

---

### Task 1: Transactional v1-to-v2 queue ordering migration

**Files:**
- Modify: `src/quantmesh/research/job_store.py`
- Test: `tests/test_research_postgres_job_store.py`

**Interfaces:**
- Consumes and preserves `PostgresJobStore` and the existing `JobStore` protocol.
- Produces schema v2 with unique `queue_position` columns on jobs and analysis outbox.

- [x] Verify the populated legacy-v1 migration case fails before the implementation.
- [x] Migrate both tables under the existing transaction-scoped advisory lock; derive legacy order from persisted timestamps plus stable job IDs and keep identity sequences usable after explicit migrated positions.
- [x] Verify a populated v1 store claims analysis in FIFO order after migration, has one queue index per table, and assigns later new sequence positions.
- [x] Verify reopened jobs/reports/outbox and expired-lease recovery, including attempt increment and stale-owner fencing.
- [x] Run the focused PostgreSQL integration file against a disposable local PostgreSQL 16 instance: 3 passed, 1 dependency warning, exit 0.
- [x] Run Ruff and format checks on both changed Python files and `git diff --check`.

### Task 2: Historical classifier expansion and original driver admission

**Files:**
- Modify: `tools/license_review.py`, `tests/test_security.py`
- Modify: `requirements-audit.txt`, `docs/licenses.md`, `docs/REUSE_MATRIX.md`
- Add: `docs/adr/0027-lgpl-weak-copyleft-dependency-policy.md`

- [x] Add regression cases first and observe the LGPL acceptance and exact-text cases fail against the previous deny-all policy.
- [x] Permit the operator-approved exact LGPL-2.0/2.1/3.0 base / `-only` / `-or-later`, MPL-2.0, EPL-2.0 and CDDL-1.0 SPDX identifiers; retain explicit GPL, AGPL and Commons-Clause rejection. The operator's standing authorization allows maintainers to add future comparable weak/file-level identifiers only after exact-text and package/distribution review; it does not create a wildcard.
- [x] The earlier checkpoint pinned Psycopg based on exact metadata; that runtime choice is superseded by Task 3 below. Keep its review history and classifier tests, but remove those packages from the current runtime closure.
- [x] Run the focused license suite and gate on a clean release environment; inspect the exact closure rows and confirm no unknown/untracked packages (72 Windows closure packages reviewed, six Linux-only pins tolerated, all 78 locked rows classified, no untracked packages).
- [x] Run the focused PostgreSQL integration tests on disposable local PostgreSQL 16; retain paper-only and no-AWS scope (3 passed, 1 existing NumPy deprecation warning, 15.46s).
- [ ] Push a reviewed checkpoint and pass exact-head required CI; do not merge until the applicable PR review and release gates are satisfied.

Review follow-up: the first bounded review identified two parser escape paths
(`WITH GPL-3.0-only` and mixed-case Commons Clause). Both were reproduced by
focused RED tests, then fixed. The parser now allowlists only the currently
reviewed `LLVM-exception`; unknown SPDX qualifiers fail closed, and Commons
Clause matching casefolds free text. The reviewer verified the fixes and the
two focused tests pass. Windows security tests pass 24/24, the 78-package clean
release closure passes, `pip-audit` reports no known vulnerabilities, and Ruff,
format and diff checks pass. These changes still require an exact-head CI run.

### Task 3: Replace the root PostgreSQL driver with pg8000

**Files:**
- Modify: `pyproject.toml`, `src/quantmesh/research/job_store.py`
- Modify: `tests/test_postgres_connector.py`, `tests/test_research_postgres_job_store.py`, `tests/test_security.py`
- Modify: `requirements-audit.txt`, `docs/licenses.md`, `docs/REUSE_MATRIX.md`, this plan, ADR-0027
- Add: `docs/adr/0028-pg8000-postgresql-driver.md`

- [x] Add connector tests first for URI parsing, TLS defaults/loopback exception, cursor placeholder adaptation and DB/socket error mapping; observe them fail against the Psycopg-only implementation.
- [x] Preserve the synchronous nine-method store contract, explicit transactions, advisory migration lock, sanitized outage errors and PostgreSQL schema/FIFO/lease/report behavior.
- [x] Remove Psycopg from the root package and audit closure; admit pg8000 1.31.5 and its exact dependency metadata without changing the existing license classifier policy.
- [x] Run the affected unit/security/store/CI-workflow tests (57 passed, 2 skipped, 1 existing warning); the disposable PostgreSQL 16 integration file separately passed 3/3. Ruff and diff checks pass; the CI-workflow test was formatted and will be included in the final rerun.
- [x] Verify the constrained pip report has no resolved-only packages or mismatched pins; six Linux-only pins are absent on Windows. The clean Windows release closure classified every installable package with the existing no-unknown-license gate.
- [ ] Push this checkpoint and wait for exact-head required CI and applicable review before merge; no production database or AWS mutation is part of this driver-only slice.

## Acceptance Boundary

This local SQL slice is eligible for the existing PR's CI and review gates. Production PostgreSQL service startup/recovery, PostgreSQL 18.6/TLS, backup/restore, Agent/Eval user flow, Worker native admission, and server-owned market data remain separate unfinished gates.
