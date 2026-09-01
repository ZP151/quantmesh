# ADR-0019 — Overlap resolution and operational soak evidence

- Status: accepted for Iteration 0021 reliability repair Tasks 2–9A
- Date: 2026-09-01
- Extends: ADR-0018 derived quality evidence and checkpoint binding

## Context

The rejected evidence-v2 soak exposed two different classes of fact. Provider
objects, quality evaluations and daily reports describe market-data evidence.
Scheduler observations, bounded process outcomes and publication attempts
describe whether one workstation operated the evidence pipeline reliably.
Combining their clocks would let a late task, retry or GitHub comment manufacture
market-evidence duration.

The NVDA correction also cannot be handled by rewriting a failed evaluation or
by accepting a loose tolerance. Its exact conflict must remain visible, its
operator review has a knowledge time, and downstream use must remain narrower
than the original data contract. Later publications need a deterministic
accepted baseline so an omitted resolution cannot appear to heal naturally.

Finally, durable local success and remote witness publication fail at different
boundaries. A network timeout after POST is ambiguous, while a local terminal or
acceptance object is already immutable. Directly coupling them would either
rewrite local truth or risk duplicate remote claims.

## Decision

Overlap correction is additive. The original v1 evaluation, report, conflict
fingerprint and provider objects remain unchanged. A create-once resolution
binds the exact candidate and immediate predecessor manifests, checkpoint-bound
report/evaluation/policy closure, re-derived field differences, winner anchor,
reviewer decision and `reviewed_at`. The accepted
`operator-acknowledged`/`ohlcv-derivatives-only` policy permits only unchanged
canonical OHLCV descendants. Turnover remains visible but cannot qualify
liquidity, cost, capacity or slippage use. Resolution knowledge never applies
before `reviewed_at`.

Quality v2 records both `overlap_baseline_manifest_id` and
`overlap_baseline_evaluation_id`, plus the exact inherited resolution ID when
one exists. The baseline is derived from committed checkpoint-bound history.
Omitting, forging or replacing these IDs fails verification. A later distinct
conflict has a new identity and requires a new decision; a PASS cannot erase or
broaden an earlier resolution. V1 bytes and dispatch remain supported.

Operational receipts are a separate evidence domain. Daily terminals bind one
exact provider report and complete-verifier proof. Connection receipts bind an
explicit scheduled slot, source contract, process deadline and typed outcome.
Their timestamps demonstrate cadence and host behavior only; they never start,
extend or backfill the provider soak clock.

Final completion is therefore a separate versioned composition. The
operational verifier re-runs the provider verifier with at least 168 hours and
four XNYS sessions, derives `evidence_as_of` only from the last accepted
provider report, reopens every report and exact daily recovery chain, validates
the complete two-hour connection-slot cadence, and requires the exact local
outbox intent for every admitted terminal. It reads six absolute, pairwise
disjoint roots and publishes a create-once `OperationalSoakAcceptanceV1` to a
seventh operational-acceptance root. It exposes no caller `as_of` and has no
provider, Scheduler, credential, GitHub, release or trading mutation authority.

Remote publication is mediated by a local create-once outbox. Daily,
connection-state and final `operational-accepted` witnesses have distinct
idempotency keys and authorities. The final kind is fixed to issue #124 and can
be enqueued only after reopening an immutable `accepted=true` operational
result. Only the leased publisher may query, POST, re-query after ambiguity,
read back the exact body and record a publication receipt. Publication time is
never evidence time.

## Consequences

- Rejected provider evidence and the exact NVDA conflict remain byte-verifiable;
  no tolerance, wildcard or synthetic repair is introduced.
- A missing baseline proof, late daily gap, failed scheduled attempt, missing
  terminal, source mismatch, cadence gap or outbox mismatch rejects final
  acceptance without changing provider objects.
- Same-day daily recovery is accepted only as a linked all-PASS chain whose last
  terminal is canonical. Supplemental connection attempts remain auditable but
  cannot fill a missed slot or heal a failed scheduled attempt.
- A local acceptance may exist while remote publication is pending or failed.
  Recovery retries the exact outbox intent instead of rewriting evidence.
- Acceptance grants neither release promotion nor execution authority. Paper
  mode and the structurally separate live-trading approval remain unchanged.

## Rollback

New code may stop producing v2 quality evidence, operational receipts or final
acceptances, but existing content-addressed objects and create-once bindings
remain readable and verifiable. Removing or rewriting a resolution, baseline,
terminal, intent, publication receipt or acceptance is corruption. A rejected
candidate is replaced by a fresh candidate in new empty roots; its clock is
never resumed or backfilled.
