# ADR-0026 — Research job publication and advisory boundary

Status: accepted for Batch-B implementation; operator approved Option A
architecture. Two bounded independent review rounds and audited contract tests
freeze the local schema/protocol. This does not approve deployment or certify
the unfinished Worker, remote store or Agent service.
Date: 2026-10-12, Asia/Singapore.
Issues: #167/#168. Preserve ADR-0010/0015 and all order/risk authority boundaries.

## Context

The first iteration0038 job slice provides local submit/status persistence,
not a new backtest engine or real-source strategy evaluation. An interface that
merely accepts file names on success could mark the wrong run successful.
Conversely, numerical validation belongs to the deterministic Worker, not
the durable job store. Optional Agent outcomes must remain distinguishable
from deterministic results, including when no model call was made.

## Decision

One configured JobStore is authoritative per mode: local SQLite and later
isolated PostgreSQL implement the same versioned nine-method protocol. Request
identity includes validated strategy/data/version/cost/window/configuration;
same idempotency key/digest means one job and changed digest means conflict.
JobRecord also freezes an implementation_digest at submission for baseline and
report-engine source bytes. This limited digest is not a complete dependency,
image or environment fingerprint. Worker compares it before execution and binds
the actual full build/dependency fingerprint separately in durable evidence;
engine changes cannot silently execute an old queued job with different math.
Owner/attempt/lease fences protect state changes; no stale completion can
publish. Successful backtest publication and pending advisory outbox creation
are transactional. Advisory has its own lease and terminal state.

SQLiteJobStore path-only construction stays compatible. Optional lake_root,
artifact_root and clock injections provide isolated data/artifact/time tests
without using global temporary files or production datasets. They do not
escalate remote, credential or order capabilities.

Local successful publication requires exactly one report ArtifactRef. Each ref
has verified byte_size and SHA256, a job-owned relative key, and containment
without symlink/path traversal. The report JSON envelope's request_digest must
equal JobRecord.request_digest. The Worker validates numerical/schema content
before publishing; matching an input digest alone does not certify a backtest.
Other admitted artifact kinds are equity_curve, trades and analysis. The remote
artifact adapter must provide equivalent verified immutable bytes; it must not
skip validation because bytes live outside the SQLite host.

The Worker publishes an envelope with schema_version=1, request_digest,
the job's verified implementation_digest and
result (the parsed canonical numerical JSON). Its object key is
`<job_id>/<sha256-of-envelope>.json`; whole envelope byte_size/SHA256 identify
publication. canonical_result excludes wall-clock receipt fields and binds
numerical metrics/windows plus input/config/engine identity. Archived receipts
and retry timestamps are separate from deterministic result identity.

AnalysisRecord.state is succeeded/failed/unavailable/cancelled. Unmeasured usage
is None, not zero. A call that never occurred must not get invented provider,
model or prompt/output digest evidence; nullable unavailable metadata and
success-only validation are finalized before contract freeze. Successful
analysis needs actual schema-valid output, cited report evidence and no error;
failure never rewrites a valid backtest as failed or grants order authority.
Errors crossing CLI/API are fixed allowlisted codes, never vendor raw payloads.

Success additionally requires output_artifact (optional/None before a model
produces output) with kind=analysis and SHA256 equal to output_digest. Its
owned immutable bytes/size are verified; an isolated digest is not archived
output. Citations must resolve exactly to this job's published artifact refs
and bytes, not merely be a nonempty list. Output model/pipeline/schema validation
remains the Agent Worker's responsibility. First independent review exposed
this evidence-resolution gap; RED/GREEN and final contract freeze are pending.

## Admission scope and consequences

The first Task2 slice admits existing legacy-v1 fixture/test manifests only.
It validates manifest/export digest and chronological window/grid; no fixture
is called real-source, and no unsupported provider data falls back to fixtures.
Qualified immutable-v2/real-source admission is a later bounded adapter slice.
Initial registered baseline parameter schemas explicitly admit empty objects;
later strategy versions may extend their schemas. This avoids pretending the
foundation already supports arbitrary user strategies.

This record does not approve deployment, model calls, dependency admission,
real-data performance or final schema compatibility. Schema/protocol digests,
review results, final tests and actual user-loop evidence are recorded in
iteration0038 before changing this ADR's status to accepted.
