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

## 2026-10-27 amendment: same-capture offline event representation

The actual consumed capture has English-month dates and a compact Cash Dividend
USD representation. Its two in-window amounts exactly cross-match same-ex original
get_rehab per_cash_div values; dates and pay fields are present. An explicitly
selected, closed-cohort v3 profile derives the established ISO/per-share event
representation offline, reusing unchanged original normalization and cash math.
This is not recapture, refund, new permission, an additional data gate or acceptance.
The original warmup rule permitting absent pay is preserved; the two actual pay
dates remain recorded. Window selection precedes cash syntax interpretation.

Raw schema3 has no embedded normalizer/source hash. Preserve original raw/auth/
intent and PR232 capture/source identities. Add a small named normalization block
only to a profiled v3 protocol, and let its existing normalizer_sha256 honestly
record the new offline tool. Derive expected cold lineage from the independently
validated PostReview profile and fixed cohort, never from protocol self-assertion.
Existing protocol/post-review CAS proofs bind this distinction without a new
permission service, ninth proof, raw-history copy or broad schema version.
Legacy v1/v2 and unprofiled v3 objects retain their prior fields and meanings.
Actual field qualification and all numerical/budget gates remain independent.
