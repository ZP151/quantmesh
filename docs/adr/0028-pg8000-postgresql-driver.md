# ADR-0028: Use pg8000 for the root PostgreSQL job store

- **Status:** Accepted
- **Date:** 2026-10-14
- **Decision owners:** QuantMesh operator and maintainers
- **Supersedes:** the earlier Psycopg root-driver implementation. The
  repository's existing license gate is unchanged.

## Context

The root `PostgresJobStore` was implemented against Psycopg 3.3.6. Its exact
runtime wheels declare `LGPL-3.0-only`, which the existing project license
gate refuses. The operator selected the BSD-licensed pg8000 driver and
explicitly required that the license policy remain unchanged.

The existing research-agent service already uses pg8000 synchronously through
its DB-API cursor facade. The root store's public contract and transaction
operations are synchronous; its API handlers invoke those operations from
synchronous service boundaries. No async driver or architecture change is
needed for this migration.

## Decision

Use `pg8000>=1.31.5,<2` in the root package. The audited release closure pins
pg8000 1.31.5 and its runtime dependencies. Upstream PyPI describes pg8000 as
a pure-Python DB-API 2.0 PostgreSQL driver under BSD 3-Clause; the exact wheel
SHA256 is recorded in the reuse matrix and release lock provenance.

Keep the `PostgresJobStore` and nine-method `JobStore` protocol synchronous.
Use cursors for parameterized statements, preserve explicit commit/rollback/
close behavior and transaction-scoped advisory locking, and keep the strict
PostgreSQL URI policy: verified TLS by default; `sslmode=disable` only for
literal loopback hosts; reject fragments, duplicate/unsupported query options,
and incomplete URIs. Map pg8000 DB-API and socket failures to the existing
generic `StoreUnavailable` response without exposing DSNs.

Keep all PostgreSQL schema, FIFO, lease, idempotency, report and analysis
outbox behavior unchanged. Integration tests use the same pg8000 connection
path and a disposable local PostgreSQL service.

## Consequences

- Psycopg is removed from the root runtime and its audited closure; no LGPL
  package is admitted by this driver migration.
- LGPL, EPL, CDDL, GPL/AGPL, Commons Clause, proprietary, ambiguous and
  unknown license declarations remain refused by the existing gate.
- pg8000's BSD notice and exact dependency versions remain in the inventory.
- This synchronous adapter and PostgreSQL 16 local integration do not qualify
  production PostgreSQL TLS/HA/backups, worker containment, or service recovery.
