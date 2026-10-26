# ADR 0035: Bind the private SPY diagnostic exception to one consumed intent

Status: accepted for the bounded offline slice, 2026-10-26.
Issue: [#177](https://github.com/ZP151/quantmesh/issues/177).
Plan: [approved technical boundary](../superpowers/plans/2026-10-26-spy-private-policy-exception.md).

The human approved one internal private diagnostic exception. This is not proof
of external API storage permission. Preserve `provider_permission_verified=false`,
`external_api_storage_applicability=UNKNOWN`, `POLICY_EXCEPTION_ONCE` and
`diagnostic_only_under_policy_exception` throughout the immutable evidence chain.

Use explicit v3 authorization, capture, review, freeze, acceptance and descriptor
contracts, report3 and sample-evidence2. Existing v1/v2 meanings and saved object
bytes remain intact. Never coerce exception authorization into v2 ALLOW.

B0 binds exact original approval/policy refs, approval-derived scope, capture UUID,
window, output/authority roots and deterministic job UUID. A private operator
configuration `QUANTMESH_SPY_ONCE_AUTHORITY_ROOT` fixes the canonical authority
root independently of authorization input. Before constructing the SDK, create
the scope marker exclusively, flush and fsync it. Failure never refunds that
marker. B1 adds the consumed marker ref downstream without a self-hash cycle.

Reuse the existing job/idempotency store and immutable report CAS. A new exception
job must use its deterministic key; a retry reopens the same job, including failed
jobs. The public request still contains only snapshot/protocol digests. Thin
original proofs accompany the report so cold verification needs no current input
configuration. Frontend options supply no authority to historical reports.

Keep the upstream engine, strategy, normalization, costs, calendar, transport and
real-field gates unchanged. All original actual-data, time and resource gates
still apply. The original protocol exceeds16KiB; protocol/freeze use the existing
1MiB object ceiling. The remaining thin proofs retain16KiB caps, checked before
reading. This grants no acquisition or total-storage budget.

The consequence is a small exception branch rather than a new permission platform.
Operator policy, independent real-input review, publisher CI/deployment and actual
research acceptance remain separate gates. No strategy promotion or live trading
follows from this internal exception.
