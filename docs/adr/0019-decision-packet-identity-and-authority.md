# ADR-0019 — DecisionPacket identity and authority

- Status: accepted
- Date: 2026-09-02
- Deciders: iteration 0027 Slice 1
- Related: ADR-0002, ADR-0015, ADR-0016, ADR-0018

## Context

Instrument Workspace needs a durable, replayable decision record without
creating a parallel paper-risk or execution authority.  A packet must retain
the exact evidence and analysis used at its as-of time, including a later
operator disposition, while allowing restart-safe replay.

## Decisions

1. Packet identity is `packet-` plus the first 24 lowercase hexadecimal
   characters of SHA-256 over canonical JSON.  The canonical payload excludes
   only `packet_id` and `created_at`.
2. `as_of`, version, parent, disposition, operator reason, proposal reference,
   every analysis value, typed blocker, evidence ID, metric, and cost
   assumption remain identity-bearing.  No other field is a bookkeeping
   exclusion.
3. Version 1 has no parent and disposition `draft`.  Every child names its
   parent and increments its version by exactly one.  Historical versions are
   immutable and replay validates this continuity.
4. Scenario probabilities are never populated from price quantiles.  In the
   absence of calibrated probability evidence, scenario confidence is explicitly
   qualitative.
5. Demo lineage is an explicit exception and is not trusted evidence.  Real
   history requires its paired manifest and quality binding before it can
   qualify a paper proposal.
6. The account fee schedule and matcher slippage are pinned in packet cost
   evidence.  Spread is deferred to confirmation and labelled unavailable,
   rather than represented as zero.
7. Existing deterministic paper risk evaluation and second confirmation remain
   authoritative.  A packet supplies proposal inputs and evidence; it cannot
   place or approve an order.
8. Structured Copilot output is a separate immutable advisory record that
   reverse-binds to one exact persisted `packet_id`.  It is not a packet field,
   packet version, evidence override, risk verdict or execution authority, and
   its availability cannot change packet identity or action capability.
9. A packet Copilot citation binds the exact packet ID to a restricted JSON
   pointer and SHA-256 digest of the canonical JSON value selected at that
   pointer.  Resolution reloads the packet from `DecisionPacketStore`, refuses
   missing, escaped, ambiguous or container paths, permits only scalar or
   scalar-list leaves, and recomputes the value digest.  Existing document,
   experiment and audit citation shapes and serialization remain unchanged.

10. Local monitoring is a separate immutable reverse binding from one exact
    persisted packet to one fixed condition set. Each evaluation atomically
    persists its complete local observation and typed results; it never mutates
    packet, Copilot, proposal, risk, confirmation, order or position authority.
    Browser requests select only fixed condition kinds. Price and forecast facts
    are constructed by the local workspace/runtime, and trigger identities are
    content-addressed so terminal conditions replay at most once.

11. Outcome review is a separate immutable reverse binding from one exact
    non-draft action packet. A deterministic preview reads only the packet's
    pinned 30-session forecast horizon, compatible local daily history, exact
    proposal/order records, and existing monitoring records. One atomic
    operator review binds the complete content-addressed outcome snapshot;
    missing horizon, continuous monitoring, exit fills, or attributable fees
    stays typed unavailable and never becomes zero performance. Outcome review
    cannot mutate packet, monitoring, proposal, risk, order, or position state.

## Consequences

DecisionPacket replay is content-addressed and fails closed if a persisted
record's identity or lineage drifts.  Reject and Watch can preserve useful
research under evidence blockers, but Paper remains governed by the existing
proposal, quote-fence, risk, and confirmation boundaries.

An accepted Copilot report can be reopened independently after restart, while
an unavailable model, invalid structured output, unresolved citation, critic
refusal or Copilot-ledger failure degrades only that advisory surface.  No such
failure writes or rewrites a packet, proposal, risk decision, order or position.
