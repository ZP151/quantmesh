# ADR-0018 — Derived quality evidence and checkpoint binding

- Status: accepted for Iteration 0021 Task 10
- Date: 2026-08-14
- Extends: ADR-0017 atomic collection graph publication

## Context

ADR-0017 deliberately stopped at integrity preflight. Task 10 must add quality
without weakening content-addressed manifest identity or introducing a hash
cycle. A manifest cannot hash a report that hashes an evaluation that hashes
the same manifest. Quality also cannot be trustworthy when duplicate, gap,
coverage, rights, entitlement, pagination, freshness or latency values are
accepted as caller assertions.

The quality decision has four product states: `pass`, `fail`, `not-due` and
`unavailable`. A failed or unavailable report must remain immutable and visible;
it must not be rewritten by a later pass. Fixture, demo and synthetic lineage
must never qualify real-provider evidence.

## Decision

Quality policy identity includes venue, artifact layer, data kind, interval,
pinned calendar/session semantics, grace period and hard thresholds. Scheduled
bar completeness is always exact; the hard coverage ratio cannot be configured
below one. Raw and feature artifacts use layer-specific cardinality semantics,
while normalized and adjusted bars use exact calendar-derived candle opens.
XNYS daily identities are anchored to the venue-local session date, including
DST and early-close calendar behavior.

`QualityEvaluator` derives measurements from the immutable manifest closure,
object bytes and real raw envelopes. It reopens typed bar or feature objects,
derives row counts, exact gaps, ordering, pagination termination, rights,
entitlement, freshness and latency, and rejects any supplied observation that
does not equal those measurements. Every raw lineage leaf must contain a real
raw envelope. Every external parent must already be committed; candidate
parents are admitted only through the exact pending graph set.

Raw cardinality is reconciled against the exact ordered source-event identities
declared by its envelopes; it is never copied from the manifest under test.
Derived non-bar artifacts must decode through their bounded typed contract,
including canonical `EquitySplitAction` rows and the explicit no-split sentinel.
Historical/live overlap is measured by comparing content fingerprints for the
same row identities against the immediately preceding admitted revision. A
changed overlap is a hard failure until an explicit immutable amendment records
the exact same conflict-fingerprint set; one amendment cannot suppress a new or
unrelated correction.

Calendar due-state is based on exact window/session intersection, not merely on
whether a UTC date contains a session. Out-of-session rows fail instead of
hiding behind `not-due`. Inclusive provider terminal bar opens are converted to
one exact exclusive quality bound. Bar availability is candle close (or the
pinned XNYS session close for daily equity bars), so latency is not measured
from candle open. `log_return(window=2)` cardinality begins at the third parent
bar, matching the production transformation.

Policies, evaluations and reports are canonical SHA-256 objects. An evaluation
hashes the exact policy, manifest, time window, measured numerators and
denominators, state, issue codes and optional amendment pointer. Amendments
must provide a reason, advance evaluation time and retain the same policy,
dataset and window. They may point to a corrected immutable manifest; the
earlier evidence remains readable. Report bindings are one-to-one and sorted
canonically by manifest and evaluation identity.

The publication order is:

1. stage and verify the candidate graph;
2. persist the integrity preflight;
3. derive and persist every policy and evaluation;
4. persist one report for the exact graph;
5. atomically commit the graph and checkpoint.

The report hashes the checkpoint body projection with only the
`quality_report_id` back-reference omitted. The final checkpoint then records
the report ID. This one-way projection avoids the manifest/evaluation/report
identity cycle while binding job, run, attempt, preflight, graph members,
provider frontier and update time. Completed reads verify the complete
checkpoint → report → evaluation → policy → manifest/object closure.

Real provider graphs use the deterministic default quality builder. Fixture
graphs retain `quality_report_id = null` and cannot contribute qualifying
evidence. A custom builder must produce the same authoritative policy identity
for every graph member and the exact job window and checkpoint time; it cannot
relax pagination, freshness, latency, calendar or coverage rules. Hard
integrity failures take precedence over provider unavailability. A quality
failure does not erase captured raw evidence or make a partial graph visible;
downstream catalog and research gates decide whether a committed failed dataset
is usable. AI and execution authority are unaffected.

## Consequences

- A self-addressed but fabricated `pass` is rejected when its measurements do
  not match immutable evidence.
- Missing completed bars, shifted candle grids, incomplete pagination,
  synthetic lineage and checkpoint/report tampering fail closed.
- Normal manifest reads verify the stored report/evaluation/policy hash closure;
  publication and completed-job retry additionally remeasure semantic evidence.
- Completed reads scope quality verification to the requested job or owning
  dataset history, so unrelated corruption remains isolated and read cost does
  not grow with every independent graph.
- Weekends and holidays are `not-due`; grace cannot mask an already observed
  hard integrity failure or permit an early pass.
- A crash after report publication leaves inert content-addressed objects. A
  deterministic retry rebuilds the same report and commits at most one graph.
- Historical backfills may truthfully record freshness or latency failures;
  preserving raw data is separate from authorizing downstream use.
- Task 11 may expose quality through the catalog without inventing another
  mutable quality authority.

## Rollback

Code may stop producing new reports, but committed checkpoints with report IDs
must continue to verify and read their complete closure. Removing a report,
evaluation or policy object is corruption, not rollback. Returning real
provider publication to unqualified checkpoints requires a new migration ADR.
