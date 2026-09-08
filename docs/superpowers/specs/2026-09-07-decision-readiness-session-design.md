# Decision Readiness Session — Design

- Status: approved by operator on 2026-09-08
- Date: 2026-09-07
- Iteration: 0029
- Issue: [#131](https://github.com/ZP151/quantmesh/issues/131)
- Baseline: `origin/main@4fb810e1268f5f0e13599d7198aee4fa78cc4717`

## 1. Problem and outcome

Iterations 0027 and 0028 prove the instrument DecisionPacket loop and the
cross-watchlist Decision Inbox, but the operator still has to infer whether the
underlying evidence is usable and open packets one at a time to refresh local
watch conditions. Iteration 0021 also has a "daily" cycle, but it is an
operational data-plane process: Scheduler invokes Provider/OpenD collection,
validates immutable evidence and publishes an independent witness.

Iteration 0029 does not merge those authorities. It adds one product-plane
**Decision Readiness Session** inside the existing Decision Inbox. The
successful user action is:

> Open Decision Inbox, understand data readiness, explicitly refresh every
> registered local watch, and open one exact triggered, blocked or review-due
> DecisionPacket in no more than two minutes.

The root correction is composition through a narrow read-only contract. A
trusted-data catalog already attached to the application may qualify exact
manifest/evaluation bindings. The session cannot discover, collect, repair,
schedule, migrate, backfill or publish trusted-data state.

## 2. Product shape

```text
0021 trusted-data fabric
  immutable manifest + quality + checkpoint evidence
                  |
                  | exact-ID, read-only qualification
                  v
Decision Readiness Session
  readiness + explicit local watch refresh
                  |
                  v
Decision Inbox
  Triggered / Blocked / Review due / No action
                  |
                  v exact packet_id
Instrument Workspace
```

The Watchlist route remains the Decision Inbox; no second dashboard or ops
console is added. Its session header reports when the view was generated, when
registered watches were last checked, whether exact evidence is usable, and
one explicit **Refresh session** action. Each row keeps one primary exact-packet
link and shows concise, textual readiness and attention reasons.

## 3. Authority boundaries

### 3.1 Iteration 0021 data plane

Iteration 0021 continues independently under issues #124 and #127. It owns:

- Windows Scheduler and host cadence;
- Provider/OpenD and network collection;
- trusted-data roots, manifests, quality evaluations and checkpoints;
- soak candidates, immutable daily reports, outbox and GitHub witness state.

Iteration 0029 owns none of these. Absence or corruption is returned as
`unavailable`; the product must not search alternate roots or reconstruct
evidence.

### 3.2 Iteration 0029 product plane

Iteration 0029 may:

- read watchlist, packet, forecast, monitoring, review and account state
  already attached to the local workstation;
- qualify a packet's exact manifest/evaluation references through an optional
  read-only catalog port;
- render a current workspace observation through existing local services;
- append a normal `DecisionWatchEvaluation` after an explicit same-origin
  operator request;
- return and display a deterministic attention projection.

It may not call Provider/OpenD, run data collection, invoke or change a
scheduled task, write trusted-data evidence, publish externally, create an
order, confirm a proposal, or change risk authority. Reading readiness never
becomes execution authority.

## 4. Readiness contracts

Add strict instruments-owned read contracts rather than exposing catalog
objects directly:

```text
DecisionReadiness
  status: ready | demo | blocked | unavailable
  checked_at
  limiting_evidence_at | null
  reason_code
  reason
  history { manifest_id, evaluation_id, report_id, evaluated_at } | null
  forecast { manifest_id, evaluation_id, report_id, evaluated_at } | null

DecisionSessionSummary
  generated_at
  last_checked_at | null
  registered_count
  triggered_count
  blocked_count

DecisionSessionRefreshResult
  started_at
  completed_at
  status: complete | partial | no_registered_watches
  registered_count
  evaluated_count
  items[] { packet_id, registration_id, evaluation_id | null, status, reason }
```

Each `DecisionInboxEntry` gains its `readiness` and the last monitoring
evaluation time/reason needed to understand the row without expanding the full
packet. Exact packet and evaluation identifiers remain visible through the
existing disclosure.

The read model remains a projection. No mutable Inbox aggregate is introduced.
`last_checked_at` is the maximum replay-validated evaluation time among the
registrations that participate in the current Inbox. `limiting_evidence_at` is
the oldest generation/evaluation time among the exact evidence required by the
selected packet, so the UI never hides an older binding behind a newer one.
`complete` and `partial` exist only on the immediate refresh response; after a
restart the durable per-row evaluations are authoritative and the summary does
not claim that an earlier subset was a complete session.

## 5. Exact evidence qualification

Readiness begins from the exact selected DecisionPacket and never performs a
catalog-wide scan.

1. Reopen and validate the packet through `DecisionPacketStore`.
2. If the packet is deterministic demo evidence, return `demo` only when the
   existing demo exception and packet invariants hold. The UI labels it as demo;
   it is never reported as trusted real data.
3. For real evidence, require the packet's paired history manifest and quality
   evaluation IDs. Forecast evidence, when present, requires its paired IDs.
4. For each exact manifest, call the read-only catalog port by ID, revalidate
   immutable lineage and checkpoint/report binding, and require the returned
   evaluation ID to equal the packet binding.
5. A failed quality status, missing binding, mismatched identity, unknown
   source rights, corrupt closure or unavailable catalog returns `blocked` or
   `unavailable` with a stable code. It never falls back to another manifest,
   current pointer, evidence root or a PASS ID from another packet.
6. Packet freshness and current observation freshness remain distinct. A valid
   historical packet can be replayed, while the current watch evaluation may
   still be non-comparable because its local quote or forecast is stale or
   absent.

The port is optional so the deterministic demo and historical review surfaces
still open when no 0021 root is configured. Real evidence is not silently
qualified in that state.

`ready` means every real evidence binding actually present on the packet has a
valid exact closure. It is not a Paper recommendation and does not imply that a
current price or newer forecast exists. An absent optional forecast is handled
by the existing packet and Paper-capability semantics; an advertised forecast
whose exact closure fails is `blocked`. `blocked` means the exact closure was
found but fails qualification; `unavailable` means the reader or required
closure cannot be opened or validated.

## 6. Explicit session refresh

Add one same-origin endpoint, likely `POST /api/decision-session/refresh`. The
request has no provider, root, symbol, price, forecast or time parameters. The
server owns all facts.

The service takes one injected UTC time, one replay-validated watchlist
snapshot and the registrations associated with the exact packets selected by
the Inbox rules. For each registration it:

1. reopens the exact packet and its immutable registration;
2. computes readiness from exact evidence IDs;
3. renders the existing local Instrument Workspace for that packet's
   venue/symbol/range;
4. builds `DecisionWatchObservation` using the same server-owned construction
   as the single-packet watch endpoint;
5. records through `DecisionWatchService.check`, preserving its canonical ID,
   continuity, terminal-event and idempotent replay rules;
6. returns the exact evaluation/result IDs or a typed per-item failure.

The existing observation construction should be extracted into one shared
unit so single-packet activation and session refresh cannot diverge. The
session never registers new conditions; a packet without a registration is
reported as not participating.

Readiness is not a blanket switch that suppresses all watch logic. A stale-data
condition may truthfully evaluate from the packet's pinned timestamps even
when current data is unavailable. Price and drift conditions receive only the
facts already admitted by the existing workspace/quote/forecast checks and
therefore become `not_comparable` when those facts are absent or invalid.
Readiness can block Paper capability but cannot manufacture a watch fact.

One item failing does not erase independent successful evaluations or turn the
failed item into success. The response is `complete`, `partial`, or
`no_registered_watches` with bounded per-item results. Store corruption or an
identity disagreement remains a fail-closed response. Concurrent identical
requests rely on the existing watch-store transaction and observation
idempotency rather than inventing a second lock or cursor.

## 7. Attention semantics

After refresh, `DecisionInboxService` recomposes from durable stores. The
existing priority and exact-packet selection remain authoritative. The UI
groups or filters the same entries into:

- `triggered`: a terminal local watch event exists;
- `blocked`: exact evidence or paper/risk linkage is unusable;
- `review due`: the bounded outcome horizon is complete and no exact review is
  saved;
- `no action`: watching, reviewed, rejected, draft or not started.

These labels describe state, not recommendations. AI output cannot determine
readiness, priority or refresh results. The exact packet link remains stable
across background GET refetches, browser history and a clean restart.

## 8. Error and degraded behavior

- No trusted-data catalog: demo remains explicitly usable; real evidence is
  `unavailable`.
- Missing required packet binding or an opened closure that fails qualification:
  affected item is `blocked`. A referenced closure or reader that cannot be
  opened or verified is `unavailable`. No alternate-root search occurs.
- No fresh local quote: price conditions return existing `not_comparable`
  facts; the service does not call a provider.
- No newer compatible forecast: drift remains `not_comparable`.
- Corrupt packet/watch/review ledger: return a stable 409-style typed error;
  do not skip the record.
- Partial refresh: retain exact successful evaluations and list failed items;
  summary says `partial`.
- Application restart: recompute summary and Inbox from existing immutable
  stores; do not depend on in-memory session state.

## 9. Vertical slices

### Slice 1 — Readiness truth in Decision Inbox

Add the strict readiness projection and optional exact-ID catalog adapter.
Show source/evidence time, reason and last checked alongside current mark
timestamp/reason. Stop when NVDA/AAPL and evidence-blocked BTC/SOL render
truthfully from existing local state after restart. Do not add the refresh
write path.

### Slice 2 — Explicit local session refresh

Extract the server-owned observation builder and add the one refresh command.
Evaluate all and only existing registrations, return complete/partial/no-watch
results, and recompose the Inbox. Stop when one user action refreshes the
deterministic NVDA/AAPL registrations without Provider/OpenD or order calls.

### Slice 3 — Action queue and exact navigation

Expose compact Triggered, Blocked, Review due and No action group/filter
semantics, including last check and stable reason text. Stop when keyboard and
390 px paths open the exact packet for each actionable category. Do not add
notifications, background polling or portfolio analytics.

### Slice 4 — Restart and two-minute acceptance

Prove NVDA/AAPL session refresh, exact navigation and durable evaluation/review
identity across a clean application reconstruction. Prove missing catalog,
stale observation, corrupt exact binding and BTC/SOL evidence-blocked states.
Stop when the complete deterministic daily session is under two minutes and
the final branch boundary is green.

## 10. Verification strategy

Use TDD and targeted contract/service/API/component checks while developing.
Each demonstrable slice gets at most two review rounds and a bounded slice
gate. Full repository and release checks run only at slice commit boundaries
where risk warrants them and once on the final exact PR head; test count and
ledger length are not product progress measures.

The default final boundary remains an exact-head release gate. After review,
the operator may explicitly approve a bounded correction exception when the
change does not expand product or trading authority, focused RED/GREEN and
static/build checks cover the correction, the earlier release-gate result is
kept only as historical evidence, and both the corrected PR head and merged
`main` pass protected CI. PR #133 received that explicit exception on
2026-09-09 for four review corrections; no exact-head release certification is
claimed for its final `3e239c6` head.

Required final evidence includes:

- exact-ID readiness qualification and mismatch/corruption refusals;
- refresh idempotency, partial result, chronology and restart tests;
- no calls to Provider/OpenD/Scheduler/order/confirmation collaborators;
- NVDA/AAPL completed session and BTC/SOL honest degradation;
- English/zh-CN, keyboard and compact browser acceptance;
- API schema/client freshness, Ruff, TypeScript/lint/build, dependency/license
  closure, `git diff --check`, full pytest and exact-head CI, subject only to
  the explicit bounded-correction exception above.

## 11. Explicit non-goals

- merging iteration 0021 into the product Goal or changing #124/#127;
- Scheduler installation, update, enablement or execution;
- Provider/OpenD, network collection or alternate evidence-root discovery;
- trusted-data writes, overlap resolution, soak candidates or witness publish;
- background refresh, operating-system notifications or external alerts;
- order creation, proposal confirmation, testnet/live trading or AI authority;
- new symbols beyond NVDA, AAPL, BTC and SOL;
- new forecasting models, Qlib/Darts expansion or model ranking;
- mobile/extension work, social features or broad portfolio performance views;
- unrelated refactors, sidecar maintenance or 0021 repairs.

## 12. Architecture consequence

The operator receives one daily product entry without collapsing two failure
domains. Iteration 0021 can repair and prove ingestion independently; iteration
0029 can ship a useful local decision session against already attached data.
When trusted evidence is available, the narrow port makes it visible. When it
is not, the session remains inspectable and fails closed rather than acquiring
operational authority.

Because this is a durable interface between the trusted-data and instruments
modules, Slice 1 records the accepted boundary in a focused ADR before adding
the public contract. The ADR does not reopen iteration 0021 behavior.
