# Decision Inbox & Bounded Paper Shadow Portfolio — Design

- Status: approved by operator on 2026-09-05
- Date: 2026-09-05
- Iteration: 0028
- Issue: [#129](https://github.com/ZP151/quantmesh/issues/129)
- Baseline: `origin/main@324d51d82ab4eae5e6176f7f91ce0631c5e76c32`

## 1. Problem and outcome

Iteration 0027 proves one exact, evidence-backed decision loop inside
Instrument Workspace, but the operator still has to open instruments one at a
time to discover what needs attention. Iteration 0028 adds the smallest useful
cross-instrument layer: Watchlist becomes a Decision Inbox, then deep-links to
the exact DecisionPacket that owns the action.

The successful user action is: **from Watchlist, identify one next action and
open the exact packet in Instrument Workspace.** The supporting shadow
portfolio is deliberately bounded to the durable paper state already owned by
that packet. It is not a new execution engine or a performance dashboard.

## 2. Product shape

The approved route keeps one short path:

```text
Watchlist / Decision Inbox
        ↓ exact packet_id
Instrument Workspace
        ↓
Reject / Watch / Paper proposal
        ↓ existing IDs
Monitor / paper order state / review
```

The Watchlist screen gains a compact decision-status region and one primary
action per scoped symbol. Instrument Workspace remains the only screen that
shows or mutates a complete decision. This preserves the established calm,
separator-first visual system and avoids a second dashboard of decorative
cards.

## 3. Authority and identity rules

1. The Inbox is a read-only projection. It persists nothing and owns no order,
   risk, watch or review transitions.
2. Every actionable row carries the exact canonical `packet_id`. Instrument
   Workspace accepts an exact packet query parameter, loads that packet first,
   validates venue/symbol/range, and never replaces it with a context-wide
   latest packet during refresh.
3. A legacy unscoped watchlist record is never assigned a venue by inference.
   It reports `unavailable` and links only to venue selection.
4. Store replay remains fail-closed. Invalid DecisionPacket, watch, proposal,
   order or review data cannot be skipped to manufacture a partial success.
5. AI explanation never determines Inbox priority or paper capability.
6. Current marks or account positions are context only. They are not attributed
   to a packet unless the existing proposal/order binding proves the link.

## 4. Owned read model

Add an `instruments`-owned query service and strict public contracts. A likely
shape is:

```text
DecisionInbox
  generated_at
  entries[]

DecisionInboxEntry
  instrument { venue, symbol, instrument_type }
  mark_context { value, status, received_at, reason } | unavailable
  attention_state
  attention_reason
  packet_id | null
  parent_packet_id | null
  selected_range | null
  disposition | null
  evidence_status | null
  proposal { id, status, order_id } | null
  monitoring { registration_id, latest_evaluation_id, triggered } | null
  review { state, review_id } | null
```

The contract exposes identifiers and small status facts, not embedded full
packets or mutable domain objects. The exact packet endpoint remains the detail
source.

The query service composes only existing replay-validated stores:

- `WatchlistStore` for venue-scoped membership;
- `DecisionPacketStore` for immutable roots and terminal action children;
- `DecisionWatchStore` for exact registration/latest evaluation;
- `ProposalLedger` and `OrderJournal` for packet-bound paper lifecycle;
- `DecisionReviewStore` for an exact saved review;
- `DecisionOutcomeReviewService.preview(packet_id)` for bounded, read-only
  unsaved-review eligibility and evidence status;
- existing market snapshot state for a clearly labelled current mark.

No new Inbox file or aggregate JSONL is introduced.

## 5. Deterministic attention selection

There is one visible entry per scoped watchlist identity. Its focus packet is
chosen from durable packet lineages, not from render order:

1. Prefer a terminal action packet that still requires operator attention:
   risk/evidence blocked, triggered Watch, pending Paper confirmation, or an
   eligible unsaved review. Review eligibility exists only when the current
   `DecisionOutcomeReviewService.preview(packet_id)` returns the bounded
   outcome required by the review contract; absence of a saved review alone is
   never eligibility.
2. Otherwise prefer the most recent terminal action packet.
3. Only when no action packet exists, use the most recent persisted draft.
4. Break ties by `(as_of, created_at, version, packet_id)` in descending order.

Attention labels are evidence descriptions, not recommendations:

- `blocked`
- `watch_triggered`
- `paper_pending_confirmation`
- `review_available`
- `paper_open`
- `watching`
- `reviewed`
- `rejected`
- `draft`
- `not_started`
- `unavailable`

If a required linked record is missing or mismatched, the entry becomes
`unavailable` with the exact reason. It does not fall through to a more
favorable state. Priority and tie-breaking receive unit tests so refresh and
clean restart return the same result.

`paper_pending_confirmation` is deliberately neutral: it means a durable
pending proposal exists, not that confirmation will succeed. Confirmation
still rechecks forecast freshness, quote provenance and deterministic risk.
The Inbox either derives current freshness through the same clock-injected
`forecast_freshness_blocker` or states that these gates remain pending; it
never labels the proposal ready or approved.

Mark context reuses `WorkspaceMarkStatus` vocabulary (`available`, `stale`,
`unavailable`) and its `received_at`/reason semantics. The service's injected
clock determines status through the existing workspace/live freshness policy.
Marks are display context only: they never affect attention priority, packet
identity, evidence status or paper capability.

## 6. API and navigation

- Add `GET /api/decision-packets` alongside the existing POST route. It returns
  the read model and performs no writes.
- Preserve `GET /api/decision-packets/{packet_id}` as the authoritative detail
  read.
- The Inbox link uses
  `/instruments/{venue}/{symbol}?range={range}&packet={packet_id}`.
- Instrument Workspace treats `packet` as an exact selection request. An
  invalid ID, absent record or context mismatch renders a recoverable explicit
  error; it does not silently show another packet.
- Existing create/action/watch/confirm/review endpoints remain unchanged unless
  a targeted compatibility correction is required by a failing acceptance
  test.

## 7. Slice 1 — Decision Inbox

Implement the read model, GET route, typed frontend client and Watchlist
integration. The visible state includes mark freshness, decision state, a short
reason and the exact open action. Add URL-driven exact selection to Instrument
Workspace.

The responsive layout may retain the desktop table, but at 390px it must stack
or constrain content without document-level horizontal overflow. All status is
available as text; color is supplemental. Loading, empty, unavailable and
corrupt-ledger errors are explicit.

Stop when one saved NVDA packet appears in Watchlist and opens by exact ID after
a reload. Do not add multi-symbol fixtures or portfolio aggregation in this
slice.

## 8. Slice 2 — AAPL extension

Exercise the same deterministic composition/action path for AAPL as for NVDA.
No new model or provider is added. The built-in deterministic evidence may be
used only where it already satisfies the packet contract.

The proof ends with saved and reopened Reject and Watch actions plus a saved
pending Paper proposal. It does not confirm or place the order in this slice;
second confirmation and order-linked summary belong to Slice 4.

Stop when AAPL completes those exact saved/reopened actions through the same UI
and API contracts. Do not change crypto behavior or aggregate paper state.

## 9. Slice 3 — Honest BTC/SOL degradation

BTC and SOL remain in the Inbox but must not receive synthetic confidence or a
paper-capable forecast by convenience. When required forecast, manifest,
quality, freshness or leakage evidence is absent, Instrument Workspace still
supports an honest degraded decision:

- evidence status and blocker reason are visible;
- Reject and Watch can each be saved and reopened for both symbols using
  independent packet lineages;
- Paper is disabled before proposal creation;
- the UI never suggests that missing evidence is zero risk.

Stop when BTC and SOL acceptance tests prove both non-Paper dispositions and an
explicit Paper blocker without Provider/OpenD access. Do not broaden to a new
forecast, synthetic confidence or other symbol.

## 10. Slice 4 — Bounded paper shadow summary

Enrich each Inbox entry using exact existing links:

```text
DecisionPacket.proposal_id
  → ProposalLedger latest immutable-identity state
  → PaperProposal.order_id
  → OrderJournal replay-validated order/fills
  → packet watch evaluations
  → exact saved outcome review
```

The summary may report pending confirmation, risk/evidence blocked,
risk-rejected, accepted/unfilled, filled/open, Watch trigger and saved review.
It must reuse existing domain vocabulary where available. It must not compute
portfolio returns, allocate fills across unrelated packets, add exit orders or
claim closed-trade P&L that the current paper contracts cannot prove.

Stop when a bounded NVDA/AAPL Paper proposal is separately confirmed through
the existing quote/risk authority and can be reopened after a clean app restart
with the same packet/proposal/order/watch/review IDs and statuses.

## 11. Error handling and restart semantics

- Missing optional state yields a typed absent state.
- Missing required linked state, identity mismatch, invalid JSONL or illegal
  lifecycle transition yields an explicit unavailable/error response.
- API errors include a stable machine-readable code and a concise operator
  reason; raw filesystem paths and record contents are not exposed to the UI.
- Restart tests reconstruct services from the same local roots rather than
  reusing in-memory instances.
- Demo reset semantics stay deterministic and clear only the state already
  owned by the demo reset contract.

## 12. Verification strategy

Development uses targeted contract/service/API/frontend tests. Each slice ends
with its focused Python and Vitest suites, Ruff, TypeScript, relevant frontend
lint and `git diff --check`. Browser E2E covers exact deep-link identity,
390px overflow, keyboard reachability, degraded BTC/SOL Paper blocking and
clean-restart replay.

One final exact-head CI/release boundary runs the repository-required broad
checks and repairs the known license-closure maintenance item before PR. It is
not repeated during every micro-change.

## 13. Explicit non-goals

- Provider/OpenD or real market calls
- real or testnet execution authority
- external alerts or scheduled tasks
- new forecasting frameworks or model leaderboards
- a broad portfolio analytics/performance dashboard
- automatic recommendations based on AI confidence
- symbols beyond NVDA, AAPL, BTC and SOL
- 0021 soak repair or migration
- Impeccable sidecar refresh as an implementation side effect

## 14. Open implementation details resolved by the plan

The executable plan may choose exact module and component names, but it may not
change the authority model, attention semantics, symbol boundary or four slice
stops above. If existing contracts cannot honestly support one status, the plan
must narrow that status rather than invent a new ledger or inference.
