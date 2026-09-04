# Packet Outcome Review Design

## Slice boundary

Iteration 0027 Slice 4 has one user action: reopen an exact persisted NVDA
action packet in Instrument Workspace, compare its frozen decision with the
locally available outcome evidence, choose one review classification, add an
optional note, and save the review.

The slice succeeds when the saved review and every referenced snapshot reopen
with identical identities after application reconstruction. It does not add an
exit-order lifecycle, performance dashboard, AI review, provider collection,
notification, another instrument, real trading, or 0021 work.

## Authority and persistence

`DecisionPacket` remains unchanged. Outcome/review state is a separate reverse-
binding record under `decisions/reviews/`, keyed to an exact non-draft action
packet. The record embeds the deterministic outcome snapshot shown to the
operator plus the classification and normalized note. One atomic append creates
the entire closure; no order, proposal, packet, monitoring, account, or Copilot
record is mutated.

One action packet accepts one review in this slice. Repeating the same request is
idempotent. A different request for the same packet is a conflict, not an edit.
Revision and deletion workflows are intentionally deferred.

## Outcome snapshot

The outcome snapshot freezes:

- the exact action packet and its root analysis packet;
- the 30-session forecast horizon target when the exact referenced forecast
  artifact provides one;
- local daily outcome bars strictly after the root analysis `as_of` and no later
  than `min(evaluated_at, target_at)`, including their dataset provenance and a
  canonical path digest;
- transparent Bull/Base/Bear threshold observations derived from numeric packet
  levels, without parsing narrative trigger text or inventing probabilities;
- exact proposal, risk-refusal, order and fill snapshots when they are bound to
  the action packet;
- existing monitoring registration/evaluation/event references, read without
  running a check.

Missing, stale, gapped, future, mismatched or unverifiable evidence produces a
typed `partial` or `unavailable` section. It never becomes zero performance or a
successful verdict.

## Quantitative semantics

The calendar is pinned to the forecast artifact's exact calendar and 30-session
target. There is no weekday fallback. A horizon not yet reached is `pending`.
Bars must be complete, strictly ordered, instrument-compatible and available by
the review clock; future knowledge is rejected.

Scenario attribution uses a versioned, disclosed close-based policy:

- Bull: first completed close strictly above resistance;
- Base: first completed close strictly above support;
- Bear: first completed close strictly below support;
- Bull/Base invalidation: first completed close strictly below the packet's
  numeric invalidation;
- Bear invalidation remains unavailable because the current long-only packet
  field has no direction-correct Bear invalidation meaning.

These states may overlap and are observations, not a winning scenario, signal,
confidence, probability, or calibration result. Equality does not cross a
threshold. If a target and stop both lie inside one daily OHLC bar without finer
evidence, ordering is `ambiguous_same_bar`.

The panel distinguishes:

- packet `planned_reward_to_risk`;
- gross path R at the available terminal close, explicitly not a trade result;
- entry-fill deviation in R units when exact fills exist, explicitly combining
  market movement and execution effects;
- mark-to-market paper R only when exact entry fills and a valid mark exist;
- realized paper R only when proposal-bound entry and exit fills, attributable
  quantity and complete fees exist.

The current system has no proposal-bound exit closure, so realized paper R is
expected to be unavailable. Aggregate account P&L or fees must never be allocated
to a packet.

## Action states

- Operator Reject: paper outcome is `not_applicable`.
- Watch: path attribution remains available; monitoring is `not_monitored`,
  `coverage_incomplete`, `no_trigger_recorded`, or a list of exact triggers.
- Pending/blocked proposal: `pending_no_order` or the exact blocker.
- Risk refusal: `risk_rejected`, with exact reason and zero fills but no invented
  P&L/R result.
- Resting paper order: `accepted_unfilled`.
- Filled paper entry without bound exit: `filled_open`; realized R unavailable.

Absence of a watch event never proves the condition was not triggered across the
whole horizon because Slice 3 evaluation is operator-invoked, not continuous.

## Review contract

Classifications are `supported`, `challenged`, `mixed`, and `inconclusive`.
They are operator judgments, never model probabilities. Partial or unavailable
outcome evidence permits only `inconclusive`.

Canonical IDs cover all semantic fields. Replay validates packet lineage,
proposal/order/watch bindings, path digest, outcome identity, review identity,
one-review-per-packet, and chronological ordering. Store corruption fails closed
with record attribution.

## API and workspace

`GET /api/decision-packets/{packet_id}/outcome-review` is read-only and returns
the current deterministic preview plus any exact saved record. `POST` on the
same route accepts only `expected_outcome_id`, classification and note. It
recomposes under the same clock, rejects outcome drift, and atomically appends
the record. Browser writes use the existing exact same-origin policy; non-
browser clients retain the documented absent-Origin exception.

The generated client powers a compact `PacketOutcomeReview` disclosure below
local monitoring in the Instrument Workspace evidence rail. Fresh drafts show a
save-first state. A saved review is read-only. Loading, error and late responses
are isolated by venue, symbol, range, exact packet and outcome identity. English,
Simplified Chinese, keyboard use, reduced motion and 390 px wrapping remain.

## Demonstration and stop condition

Targeted coverage must prove operator Reject/Watch semantics plus two paper
paths: a confirmed/filled-open entry and a deterministic risk refusal. The NVDA
browser path saves a review, reconstructs the application on the same root, and
reopens the same review/outcome/packet identity without leaving Instrument
Workspace.

If a claim requires provider data, continuous watch coverage, bound exit fills,
complete per-fill costs, or a new order lifecycle, the UI displays unavailable
and the slice stops rather than expanding authority.
