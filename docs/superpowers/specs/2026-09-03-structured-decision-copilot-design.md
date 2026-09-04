# Structured Decision Copilot Design

**Iteration:** 0027 — Evidence-backed Decision Copilot  
**Slice:** 2 — Structured Copilot  
**Status:** approved direction, durable design record  
**Date:** 2026-09-03

## Product boundary

The Slice 2 user performs one action on an already persisted DecisionPacket:
request an explanation and challenge of that exact packet. QuantMesh returns a
schema-valid, cited Copilot report in the existing Instrument Workspace evidence
rail, or an explicit Copilot-only degraded state.

Success means that the operator can inspect a Base explanation, Bull and Bear
challenges, evidence gaps or contradictions, limitations, and operator questions
without leaving the workspace. Every displayed item resolves to one or more exact
facts in the persisted packet. The packet, its evidence blockers, suggested paper
inputs, deterministic risk result, and Reject/Watch/Paper controls are byte-for-byte
and semantically unchanged whether the model succeeds or fails.

This slice does not add Copilot to a fresh draft. It does not implement monitoring,
outcomes, reviews, document search, confidence or probability estimation, another
model framework, Provider/OpenD access, real trading, another instrument, or any
0021 soak work.

## Authority model

`DecisionPacket` remains the sole analysis snapshot and paper-capability authority.
Copilot output is a separately stored advisory record linked to the exact
`packet_id`; it never creates a child packet and never adds a Copilot field to the
packet identity. This deliberately realizes the iteration design's optional
Copilot linkage as a reverse packet binding, so later or unavailable AI cannot
change the immutable packet selected by the action rail.

Only a packet already present in `DecisionPacketStore` may be submitted. The service
reloads that exact record; it does not accept client-supplied packet content, the
current draft, a latest-packet alias, or post-`as_of` facts. The canonical packet
JSON is the only model context in Slice 2.

The structured output has no fields for direction, confidence, probability, side,
entry, price, quantity, size, notional, approval, blocker override, disposition,
confirmation, execution, fill, position, or provider routing. Unknown fields are
forbidden at every model schema boundary. Commentary may explain packet-owned risk
facts but cannot create or replace them. A critic pass must accept every item before
any report is displayed or stored.

## Contracts

`PacketCopilotDraft` is the analyst-stage model contract:

```text
packet_id
base_explanation: cited item
bull_challenge: cited item
bear_challenge: cited item
evidence_gaps_or_contradictions: cited item[]
limitations: cited item[]
operator_questions: cited item[]
```

A cited item contains only bounded `text` and a non-empty list of packet citations.
The critic returns only an exact `packet_id`, an allow/refuse verdict, and flagged
item paths with bounded reasons. A partial report is never returned: any flagged
item refuses the entire draft.

The existing `Citation` contract gains one source kind, `packet`. A packet citation
uses:

```text
source_kind = "packet"
source_id = exact packet_id
json_pointer = restricted RFC 6901 pointer to a scalar or scalar-list leaf
value_digest = sha256(canonical JSON of that selected value)
span = null
```

Legacy document, experiment, and audit citations retain their existing shape and
optional character span; they cannot carry a JSON pointer or value digest. Packet
citations require both and cannot carry a span. The packet source reloads the exact
record, resolves the pointer without attribute or array ambiguity, refuses
containers or missing values, canonicalizes the selected value, and recomputes the
digest. Cross-packet, bad-pointer, bad-digest, and unsupported-source citations
fail closed.

`PacketCopilotRecord` is immutable and content-addressed. Its identity includes the
exact packet ID, accepted report, analyst and critic DecisionLog IDs, schema version,
model metadata, and canonical request kind; only its append timestamp is excluded.
It is stored in a narrow JSONL ledger under the decisions root. `latest(packet_id)`
revalidates record identity and returns the most recent accepted record for that
exact packet. An identical request after a successful record is idempotent and
returns the existing record without another model call.

## Processing flow

```text
POST exact packet ID
  -> reload persisted DecisionPacket
  -> canonical packet JSON
  -> redact before transport
  -> structured analyst completion
  -> strict schema and exact packet-citation resolution
  -> structured critic completion over redacted packet + draft
  -> strict critic gate and second citation resolution
  -> append analyst/critic DecisionLog records
  -> append immutable PacketCopilotRecord
  -> return ready state
```

The service uses the existing `ModelGateway.complete_structured`, redaction, model
transport, citation-resolution, and `DecisionLog` boundaries. It does not reuse
`ResearchPipeline`: that pipeline requires directional confidence and adds risk and
portfolio roles whose authority-shaped outputs conflict with this slice.

Redaction happens before every model request. DecisionLog entries remain analyst and
critic role records distinguished by explicit Copilot schema IDs. Duplicate audit
records caused by a retry are accepted only when the existing content-addressed
record is exactly equal; any mismatch fails closed.

## API and failure semantics

The instrument router adds:

```text
GET  /api/decision-packets/{packet_id}/copilot
POST /api/decision-packets/{packet_id}/copilot
```

POST has no analysis payload: the path identifies the only allowed packet and the
single action always requests the complete explanation-and-challenge report. It is
protected by the existing loopback same-origin guard. GET returns the latest valid
record when one exists.

Both endpoints return a strict `PacketCopilotState` with `status` equal to `idle`,
`ready`, or `degraded`, the exact packet ID, an optional record, and a stable optional
reason code. A nonexistent or corrupt packet remains an exact packet 404/409 rather
than being mislabeled as a model failure. No configured Copilot service, transport
unavailability/timeout, invalid JSON, invalid schema, citation failure, critic
refusal, redaction refusal, audit failure, or record-write failure returns partial
commentary. It returns a typed degraded state and performs no packet, proposal,
risk, order, or position write.

Only accepted reports are durable. A prior accepted report remains reopenable after
a later transient failure; the failed POST response is degraded but does not erase
or replace the prior immutable record.

## Instrument Workspace

The existing three-column workspace remains intact. A compact, collapsible
`PacketCopilot` section is placed in the evidence rail, below the packet/scenario
evidence and before fresh forecast details. It has four visible states:

- Fresh packet: disabled explanation that the decision must be saved first.
- Persisted, no record: one “Explain & challenge” action.
- Loading: localized progress in the panel only; the rest of the workspace remains
  interactive.
- Ready or degraded: cited sections with disclosure of packet field and digest, or
  a localized unavailable reason plus retry.

The query and mutation keys include the exact packet ID. Changing instrument,
range, fresh/persisted selection, or saved child packet cannot leak commentary from
another packet. The panel never calls or disables DecisionRail actions. It preserves
English and Simplified Chinese copy, keyboard operation, reduced-motion behavior,
and 390 px wrapping; no new route, modal, dashboard shell, gradient, or decorative
visual system is introduced.

## Verification boundary

Deterministic scripted transports prove the valid analyst/critic path without a
model key or network call. Focused backend tests cover redaction, strict schemas,
exact packet/pointer/digest resolution, critic gating, timeout/unavailable/invalid
outputs, idempotency, restart recovery, and zero changes to packet/proposal/order
authority. Focused UI tests cover fresh, idle, loading, ready, degraded, packet
switching, localized copy, keyboard use, and compact wrapping. Existing stale and
paper-confirmation tests are retained as authority regressions.

One coherent Slice 2 boundary review is expected and may have at most one correction
round. Broad Python/frontend/OpenAPI/build checks run once after that review, at the
slice commit boundary. The inherited Python release-license lock drift remains a
tracked final-PR gate and is not repaired inside Slice 2.
