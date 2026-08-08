# ADR-0006 — Broker/paper reconciliation identity and tolerance policy

- Status: accepted
- Date: 2026-08-08
- Deciders: solo delivery (iteration 0006, M4 Phase D, issue #28)
- Related: ADR-0004 (OpenD boundary and wire contracts), ADR-0005 (report
  identity discipline — the same "identity is derived from pinned state,
  never fabricated" principle), `docs/iterations/0006-m4-moomoo-equity-workflow.md`

## Context

M4 delivers a Moomoo **simulated-only** execution path: QuantMesh places
orders into the broker's simulated environment, and the broker's order/status/
fill state must be reconciled against QuantMesh's own order journal. The
broker is the market — its fills are facts — but its state arrives over a
network that can drop a placement ack, a status push, or a reconnect window.
The reconciliation service must therefore (a) decide, per order, whether the
two sides agree, disagree, or are only partially visible, and (b) never
silently accept drift, never fabricate an identity mapping, and never auto-apply
anything it could not verify.

Two identities exist per order: the broker's `order_id` and QuantMesh's
`order_id`. The broker also accepts a `remark` (≤ 64 UTF-8 bytes, echoed on
every order-list query) that QuantMesh fills with its own identifier, giving a
second correlation channel for exactly the "place ack lost" failure. Statuses,
quantities, prices, fees, timestamps, fills, and positions all have their own
comparison semantics and tolerance.

## Decisions

### 1. The journal is the single source of truth for the mapping

Broker `order_id` ↔ QuantMesh `order_id` is derived exclusively from the
order journal: an internal order carries `broker_order_id` when the broker
acknowledged placement, and `client_order_id` (echoed in the broker's
`remark`) when QuantMesh supplied one. Reconciliation reads the journal,
builds both channels, and:

- refuses a broker order whose two channels disagree (mapping finding,
  divergent);
- refuses two internal orders claiming one broker order, or one remark
  matching two internal orders (mapping finding, divergent);
- treats a remark-only match as a *recovered* mapping (the ack was lost) and
  records a mapping note, never silence.

Never inferred: an order whose identity cannot be established is reported
missing or divergent — there is no best-effort guess.

### 2. Status comparison goes through an explicit table

Broker status → domain status is a closed mapping derived from the vendored
SDK enum. Pre-submission states (`UNSUBMITTED`, `WAITING_SUBMIT`,
`SUBMITTING`) map to `PENDING`; `SUBMITTED` → `ACCEPTED`; `FILLED_PART` →
`PARTIALLY_FILLED`; `FILLED_ALL` → `FILLED`; `CANCELLING_PART/ALL` → their
fill-based equivalents; `CANCELLED_PART/ALL` → `CANCELED`; `SUBMIT_FAILED` /
`FAILED` → `REJECTED`. Broker statuses with no honest domain meaning
(`TIMEOUT`, `DISABLED`, `DELETED`, `FILL_CANCELLED`) are **unmappable** and
produce a typed status finding — the result is "unknown", and unknown is
reported, never equalized.

### 3. Tolerances are declared per run; the deterministic simulator defaults to exact

QuantMesh owns the comparison: quantity and price in bps of the order's
reference values, fee in absolute currency units, timestamps as wall-clock
skew in seconds, positions in bps of the position. Because the simulated
environment is deterministic, the default tolerance is **exact** (0 bps, 0
fee, 0 s) — any declared tolerance is an operator decision, and every
violation is a typed finding carrying the observed and expected values.

### 4. Fills are identified by broker `deal_id`

An adopted fill is stamped with `broker_fill_id` (= `deal_id`), so
fill-level reconciliation maps deals ↔ internal fill events by id. A deal
whose status is not `OK` (`CANCELLED`, `CHANGED` — a revoked or altered
fill) is never adopted and, when a previously adopted fill carries that
`deal_id`, produces a revoked-fill finding. Fees ride on the deal; when the
broker reports no fee for an order that has internal fees, the fee dimension
fails closed (missing-data finding) rather than comparing vacuously.

### 5. Adoption is a guarded write, only for clean pairs

`apply_reconciliation` appends broker-confirmed progress — new fills and the
resulting status transitions — to journal orders **only** for pairs the run
classified matched or pending, and only through `OrderStateMachine` (a
transition the state machine refuses is itself a status finding and blocks
that order). Divergent, missing, and ambiguous pairs are never adopted and
are returned as refusals. Adoption stamps broker data verbatim: fill qty,
price, fee, deal id, and broker timestamps (venue-local wall clock converted
to UTC by market-prefix zone, ADR-0004). There is no reconciliation-driven
cancel, modify, or reverse order — adoption only adds verified events.

### 6. The adapter is simulated-only by construction

The execution adapter is explicit-construction-only (no default path, no
registry entry, nothing reachable from a bare import), mirrors the
`MoomooOpenDClient` injected-transport boundary, and pins the SDK's trade
environment to `TrdEnv.SIMULATE`; a caller attempting `REAL` is refused with
a protocol error before anything reaches the wire. The vendored SDK is
reached only through a lazy `SdkTradeTransport` constructed by an explicit
operator command (Phase E gate); unit tests run entirely on the fixture
transport.

## Consequences

- Positive: reconciliation is deterministic and replayable — the same
  journal plus the same broker snapshot yields the same classifications and
  findings; the disconnect/reconnect case (lost ack) is a first-class,
  fixture-covered scenario instead of a silent hole.
- Positive: the journal (append-only, fail-closed reads, same discipline as
  the experiment and report registries) becomes the durable internal order
  state that M5+ execution surfaces build on.
- Negative: adoption is conservative by design — a broker order that drifts
  even once never re-syncs automatically; the operator must resolve it. For
  a guarded-trading workstation that is the point.
- Negative: zero default tolerance will flag simulated-market artifacts
  (e.g. a broker that rounds a fill price) until the operator declares a
  tolerance; findings make the drift visible instead of hiding it.
- Open: live `order_fee_query` aggregation is wired as an optional transport
  capability; fee comparison still requires deal-level fees in fixtures
  today. Execution granularity (execution detail per venue) remains a Phase
  D+ concern; the cost model of ADR-0005 stays separate from reconciliation.
