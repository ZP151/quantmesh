# Local Packet Monitoring Design

**Iteration:** 0027 — Evidence-backed Decision Copilot  
**Slice:** 3 — Local monitoring  
**Status:** approved direction, durable design record  
**Date:** 2026-09-03

## Product boundary

On an exact persisted NVDA `DecisionPacket`, the operator selects one or more
fixed local watch conditions and activates **Save & check local conditions** in
Instrument Workspace. QuantMesh shows the frozen condition definitions and the
latest typed result in place. A later **Check now** action evaluates the same
registration against a new local observation. Registration, evaluation history,
and trigger identity survive a clean restart.

Success means deterministic trigger and non-trigger replay for entry, invalidation,
stale-data, and forecast-drift conditions without leaving Instrument Workspace.
This slice adds no background scheduler, provider call, external notification,
AI judgment, proposal/risk/order authority, packet mutation, outcome review,
other instrument, 0021 soak work, or license maintenance.

## Authority and persistence

`DecisionPacketStore.get(exact_packet_id)` is the only rule source. A draft,
`latest` alias, client-supplied packet body, or recomposed workspace packet is never
accepted. Monitoring is a separate reverse binding and cannot change a packet,
child lineage, blocker, disposition, proposal, risk verdict, confirmation, order,
position, or Copilot record.

One immutable `DecisionWatchRegistration` is permitted per exact packet. It holds
one to four content-addressed `DecisionWatchCondition` records. A registration is
idempotent only when its exact condition set agrees; a conflicting second set is
refused rather than silently replacing monitoring history.

Each check writes one atomic `DecisionWatchEvaluation` containing the complete
observation plus one typed result per registered condition. This single-record
boundary is also the durable cursor for price crossings: replay can recover the
last accepted price observation and terminal triggers without a second mutable
cursor file. The store uses the existing fail-closed JSONL persistence pattern and
a monitoring-root transaction lock. A byte-identical observation returns the
existing evaluation. Corrupt, duplicate-conflicting, reversed, future, or
cross-instrument evidence is refused.

## Fixed condition semantics

The UI offers exactly four kinds. Thresholds are packet-derived and not editable in
Slice 3.

### Entry zone entered

The current packet schema has a single `risk_plan.entry_price`, not an explicit
zone. To avoid changing old packet identities, the monitoring condition freezes a
transparent pullback zone from two exact packet facts:

```text
lower = min(market_state.support, risk_plan.entry_price)
upper = max(market_state.support, risk_plan.entry_price)
```

The UI labels this literally as the **support → entry zone** and displays both
bounds. It is not represented as an operator-defined or statistically estimated
band. A trigger requires a prior accepted price strictly outside the closed band
and a current accepted price inside it. The first observation only arms the
condition; an initially in-band value never backfills a historical trigger.

### Invalidation crossed

Iteration 0027 packets describe a long-only risk plan (`stop < entry < target`).
The condition therefore supports only a downward crossing of exact
`market_state.invalidation`: previous price greater than or equal to the level and
current price strictly below it. Equality is not a break. The risk-plan stop is a
different fact and is not substituted.

### Data stale

The condition pins packet history generation time and, when present, forecast
generation time. It also pins the canonical calendar identity/version/policy
derived from the packet's declared market: XNYS regular for NVDA/Moomoo and
continuous UTC only for a declared `24/7` instrument. The maximum is one completed
session, matching existing forecast admission semantics but using the repository's
versioned `CalendarService`, not a weekday approximation.

Stale triggers only when the number of sessions whose close is after the evidence
reference and at or before evaluation is greater than one. Weekends, holidays, and
an open XNYS session do not increment the count; an early close uses the pinned
calendar close; 24/7 advances at UTC day close. Missing evidence, unavailable
calendar/version, or a future reference is a typed unavailable result, never a
fabricated stale event.

### Forecast drift

The baseline is the exact packet `forecast_artifact_id` and its 30-session path.
The condition freezes the terminal target timestamp, its baseline p50, the packet
model/config/target/calendar compatibility fields, and one packet risk unit as the
absolute drift threshold. A candidate must be a later-generated, validated local
artifact for the same instrument and contain p50 for the same absolute target.

```text
distance = abs(candidate_p50 - baseline_p50)
triggered iff distance > risk_plan.risk_per_unit
```

Equality does not trigger. A missing candidate, no shared target, incompatible
model/config/target/calendar, corrupt artifact, or artifact generated after the
evaluation clock produces `not_comparable`, not a zero-distance or probability.
Quantiles, coverage, and drift thresholds never become scenario probabilities or
confidence.

## Observation and event semantics

A `DecisionWatchObservation` contains one evaluation time and optional current
price and forecast facts. Price evidence preserves value, instrument, source,
provenance, data time, received time, sequence, and sequence-gap state. It is
eligible for crossing only when it matches the packet instrument, both evidence
times are strictly after `packet.as_of`, received time is no later than the
evaluation clock, sequence is continuous, and the observation advances the prior
accepted price cursor. Exact replay is a no-op; reversed or conflicting sequence
identity fails closed.

The API constructs this observation from the current local Instrument Workspace
snapshot and exact local forecast registry. It does not accept an arbitrary price
or packet body from the browser and does not contact a provider. The service keeps
an injected-observation seam for deterministic tests and future local scheduling,
but Slice 3 installs no scheduler or polling loop.

Each condition result is `armed`, `not_triggered`, `triggered`, or
`not_comparable`, with its exact observed values and reason. A triggered condition
is terminal in this slice; later evaluations replay it without emitting another
trigger occurrence. Identifiers are canonical hashes:

```text
condition_id = condition- + sha256(schema, packet, kind, definition)[:24]
registration_id = registration- + sha256(packet, ordered conditions)[:24]
evaluation_id = evaluation- + sha256(registration, complete observation)[:24]
event_id = watch-event- + sha256(condition, evaluation, outcome, facts)[:24]
```

Only append timestamps are excluded. Replay revalidates all hashes, exact packet
binding, registration contents, evaluation ordering, price cursor continuity, and
at-most-once trigger history.

## API and Instrument Workspace

The instrument router adds:

```text
GET  /api/decision-packets/{packet_id}/watch-conditions
POST /api/decision-packets/{packet_id}/watch-conditions
```

GET is read-only. POST carries only the selected fixed condition kinds. On first
use it stores the registration and performs the initial local check; on an existing
identical registration it performs a new check. Both are protected by the existing
loopback same-origin guard. Missing packet/service is 404, corrupt/conflicting
state or unusable evaluation evidence is 409, and no write is partially presented
as success.

A compact `PacketMonitoring` disclosure sits below Copilot in the evidence rail.
Fresh packets say “save first.” Persisted packets show four checkboxes, the exact
derived levels/evidence, and one save/check action. Registered packets show all
conditions, current typed state, latest event time, and **Check now**. Query and
mutation identity includes workspace context and exact packet ID, so range,
instrument, fresh/persisted, or child-packet changes cannot leak state. English and
Simplified Chinese, keyboard operation, reduced motion, and 390 px wrapping remain
part of the existing workspace contract.

## Verification boundary

Focused RED→GREEN tests prove all four definitions, strict time/sequence gates,
initial arming, exact crossing boundaries, XNYS holiday/early-close and 24/7 UTC
session behavior, drift comparable/unavailable cases, duplicate and concurrent
replay, corruption refusal, restart/reset recovery, and byte-for-byte unchanged
packet/proposal/order ledgers. Component and one NVDA browser path prove the
single in-workspace action, typed results, packet switching, localization, and
compact layout.

One combined boundary review may use one correction round. Broad Python/frontend
gates run once after review at the slice checkpoint. The known Python license-lock
drift remains deferred to the final PR as explicitly authorized.
