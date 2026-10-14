# PostgreSQL Research Job Store Migration Plan

> **For agentic workers:** Follow the repository TDD and review lifecycle in `docs/agents/cross-agent-execution.md`.

**Goal:** Preserve deterministic FIFO claims and lease recovery when a PostgreSQL research job store is opened or upgraded from schema v1.

**Architecture:** Keep the existing `PostgresJobStore` and nine-method `JobStore` contract. Upgrade the schema transactionally to v2, assigning missing queue positions from persisted enqueue/completion timestamps and stable job IDs; add no new queue, service, dependency, or deployment path.

**Tech Stack:** Python 3.12+, psycopg, PostgreSQL, pytest.

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

## Acceptance Boundary

This local SQL slice is eligible for the existing PR's CI and review gates. Production PostgreSQL service startup/recovery, PostgreSQL 18.6/TLS, backup/restore, Agent/Eval user flow, Worker native admission, and server-owned market data remain separate unfinished gates.
