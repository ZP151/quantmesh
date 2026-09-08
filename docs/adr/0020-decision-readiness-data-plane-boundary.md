# ADR-0020 — Decision readiness exact-ID data-plane boundary

- Status: accepted
- Date: 2026-09-08
- Related: ADR-0018, ADR-0019

## Context

Decision Inbox must expose whether a persisted DecisionPacket's evidence is
usable without making the product an operator for the trusted-data fabric.
The packet owns its immutable history and (when real) forecast manifest and
quality-evaluation pins. Listing catalog heads, following another root, or
refreshing providers could silently substitute different evidence.

## Decision

Readiness reads only `DataCatalogReader.lineage(manifest_id)` for the exact
manifest ID named in the selected packet. It validates the returned manifest,
quality evaluation, report/checkpoint binding, research qualification, known
source rights, and timezone-aware evidence time. It never calls `entries()`,
walks catalog heads, makes provider/network calls, or infers an alternate ID.

Demo-synthetic history remains an explicit `demo` state without a catalog
read. Missing real bindings are `blocked`; unavailable readers, missing exact
manifests, and corrupt exact closures are `unavailable`. An advertised real
forecast receives the same independent exact-ID closure check. The Inbox
projects this state read-only and receives its catalog through a reset-safe
app-state provider.

## Consequences

- A favorable catalog head cannot replace packet-pinned evidence.
- Readiness failures cannot create data, mutate watches, refresh providers, or
  affect proposal, risk, order, Scheduler, Provider/OpenD, soak, witness or
  outbox authority.
- UI truth is compact and local: readiness, evidence time, mark context and
  last persisted local watch check appear in the existing inbox row.

## Rollback

Remove the Inbox projection and its endpoint schema fields only in a
compatible API revision. Existing DecisionPackets and trusted-data artifacts
remain immutable; no catalog or execution state requires rollback.
