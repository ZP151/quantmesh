# Trusted Data Fabric Design

Status: approved by the Iteration 0021 activation objective

Date: 2026-08-14

Tracking issue: [#110](https://github.com/ZP151/quantmesh/issues/110)

Baseline: immutable `v0.1.1-rc1` at
`b6b05b96f232366dad31177e2e8e13ab23c08b97`

## Purpose

Iteration 0021 turns QuantMesh's separate fixture lake and read-only live
cockpit into one trustworthy data fabric. The bounded product slice covers
Moomoo AAPL/NVDA and Hyperliquid BTC/ETH/SOL. It does not add trading,
strategy, model, AI, credential-storage or release-promotion authority.

The fabric must preserve the provider's raw evidence, derive canonical data
through explicit transformations, survive retries and restarts without silent
duplicates, expose quality as product state and retain every historical
revision needed to reproduce a chart, experiment or forecast.

## Current-state findings

The accepted baseline contains valuable pieces, but they are not one trusted
chain:

- `ProviderRegistry` accepts one fixture provider per venue and rejects live
  providers.
- Moomoo and Hyperliquid already have canonical adapters, but real providers
  are explicit side paths outside scheduled ingestion.
- the Parquet lake stores bars; books, trades and raw responses are not covered
  by its manifest contract;
- the live DuckDB buffer is replayable, but uses local append sequence as its
  only identity and has no immutable dataset manifest;
- `manifest.json` is mutable and detects row-count/range changes, not
  same-count/same-range content changes;
- an opened v1 dataset reads mutable current shards rather than immutable
  bytes;
- Moomoo history drops the SDK pagination cursor after the first page;
- an adjusted history binding currently copies raw close into
  `adjusted_close` without applying a factor;
- XNYS is a label rather than a versioned session schedule;
- Hyperliquid `tid` is incorrectly treated as a consecutive sequence. The
  provider documents it as a hash-like trade identity; globally unique trade
  identity is `(block_time, coin, tid)`;
- current ingestion has neither a durable run identity nor a publication
  checkpoint.

These findings are acceptance blockers for this iteration, not deferred
enhancements.

## Approaches considered

### 1. Evolve the owned provider and lake contracts

Add capability resolution, content-addressed objects, immutable manifests,
collection checkpoints and catalog APIs around existing adapters. Retain a v1
reader while new v2 datasets become the only trusted-data write path.

This is the selected approach. It reuses working parsing, history, research,
live-feed and UI contracts while replacing the weak trust boundaries.

### 2. Add a parallel trusted-data subsystem

A separate registry and lake would reduce immediate regression risk, but would
leave two provider identities, two history paths and two quality definitions.
The iteration's goal is convergence, so permanent parallel ownership is
rejected. Temporary adapters may bridge v1 reads during migration.

### 3. Adopt OpenBB's provider runtime

OpenBB offers useful provider-registry patterns, but its application boundary
and AGPL licensing do not fit the permissive QuantMesh runtime. It remains an
architecture reference only. No OpenBB source or runtime dependency is added.

## Architectural boundaries

### Capability-aware provider registry

`ProviderDescriptor` is immutable metadata. It identifies a provider by
`provider_id`, venue, provider version and adapter schema version. It declares
one `ProviderCapability` per supported operation.

Each capability records:

- access class: `fixture`, `public-live`, `authenticated-read-only` or
  `paper-broker`;
- data kind: bars, quotes, books, trades, adjustment factors, splits or
  dividends;
- bounded instruments, intervals and history limits;
- entitlement state and last probe time;
- source-rights identifier and terms version;
- timezone, market calendar and latency class;
- rate-limit policy and cursor/pagination semantics.

Consumers resolve a `ProviderRequest` by provider ID, venue, data kind,
instrument and access class. Resolution never upgrades access. A public or
authenticated data capability cannot expose an execution method. Existing
fixture providers remain valid through a compatibility descriptor.

### Canonical instruments and calendars

The bounded canonical identities are:

- `moomoo:US:AAPL:XNAS` and `moomoo:US:NVDA:XNAS` for US equities;
- `hyperliquid:perp:BTC`, `hyperliquid:perp:ETH` and
  `hyperliquid:perp:SOL` for perps.

Provider symbols are effective-dated aliases. Historical and live-tail paths
must resolve the same canonical identity before data can join.

Equity observations carry both UTC event time and `session_date`. XNYS
expectations come from a pinned exchange-calendar package/version and include
holidays, early closes and DST. Regular and extended sessions are separate
policies. Crypto uses a versioned `24/7` UTC calendar.

### Bitemporal raw envelopes

Every real response or frame is persisted before normalization as a
`RawEnvelope`. It records:

- provider, endpoint, request/window identity and optional cursor;
- canonical instrument and provider symbol;
- data kind and source event identity;
- event/session time, provider-available time when supplied, received time and
  ingested time;
- raw content digest, content type and byte length;
- provider/adapter/schema versions;
- source-rights and entitlement snapshots;
- provenance, with `real` required for qualifying evidence.

Knowledge-time queries filter by the time QuantMesh could know the observation,
not only market time. A correction creates a new envelope and validity interval;
it never rewrites the earlier vintage.

### Content-addressed objects and immutable manifests

Fabric objects are stored under a SHA-256 object namespace. Canonical JSON is
used for envelopes, manifests, checkpoints and quality reports; Parquet object
bytes are hashed after deterministic creation. Existing v1 data remains
readable but cannot qualify as v2 immutable evidence. All v2 state lives below
`.trusted-data-v2`, a namespace impossible under the v1 dataset-name grammar,
so provider evidence cannot collide with a legal v1 dataset.

An `ArtifactManifest` records:

- `manifest_id`, the SHA-256 of its canonical body;
- dataset ID, monotonic compatibility revision and layer;
- canonical instrument, data kind, interval and calendar version;
- object digests, row identities, schema digest and adapter version;
- parent manifest IDs and transformation policy digest;
- source-rights and entitlement snapshots;
- event-time and knowledge-time coverage;
- adjustment policy and quality-report ID;
- creation time, code commit and collection-run ID.

Manifests live at `manifests/<manifest_id>.json` and are never replaced.
Objects referenced by an accepted manifest remain readable. A small mutable
`current.json` pointer may advance only with compare-and-swap from the expected
previous manifest. Revision reuse, rollback and deletion-reset fail closed.

An opened v2 dataset binds to exact object digests. Later publication cannot
change its reads.

### Layer model

The required lineage is:

`raw -> normalized -> adjusted -> feature`

- **Raw** preserves provider bytes and request/frame evidence.
- **Normalized** maps provider symbols, timestamps and payloads into owned
  canonical rows while retaining raw-object and source-event identities.
- **Adjusted** is never inferred from a label. For equities, immutable raw bars,
  adjustment factors, splits and dividends remain separate parents. A pinned
  policy produces a split-adjusted series; total-return data is unavailable
  until cash-dividend semantics are fully evidenced. For crypto, the adjusted
  layer is an explicit identity transform with policy
  `identity-no-corporate-actions-v1`.
- **Feature** reuses the existing deterministic bar-feature functions and pins
  the adjusted parent manifest. This iteration creates no new model, strategy
  or trading signal.

If an adjustment source or policy is unavailable, the adjusted and feature
layers are unavailable. Raw data is never relabeled as adjusted.

### Moomoo read-only collection

Moomoo collection uses local OpenD and official API surfaces only. It covers:

- AAPL/NVDA daily history and bounded intraday history;
- read-only stock quotes;
- official adjustment factors, stock splits and dividends.

Historical requests follow every `page_req_key` until completion. Repeated
cursors, page/row/window limits or nonterminal truncation fail the run.
Pagination evidence is persisted in raw envelopes and checkpoints.

Missing SDK, missing daemon, unavailable quote/history capability, account
permission and quote entitlement are distinct catalog states. QuantMesh does
not request, store or log credentials. Real Moomoo acceptance waits for the
operator's already configured local OpenD; implementation and unavailable-state
verification do not require credentials.

### Hyperliquid read-only collection

Public mainnet market data gets a dedicated info/stream transport that has no
exchange or signing surface. Existing testnet execution guards remain
unchanged.

The bounded universe is BTC/ETH/SOL. REST collects candles and book snapshots;
WebSocket collects candles, snapshots and trades. The official candle endpoint
retains at most 5,000 recent candles, so backfill windows are bounded and the
catalog exposes the attainable horizon.

Continuity semantics differ by kind:

- candles use interval timestamps and provisional/final state;
- trades deduplicate by `(block_time, coin, tid)` and never infer a missing
  count from `tid`;
- books are snapshot epochs. Because the documented snapshot has no sequence,
  completeness across disconnects is `unknown-after-disconnect` unless an
  authoritative recovery proves otherwise.

Gap state is one of `complete`, `known-gap`, `unknown-after-disconnect`,
`recovered` or `unrecoverable`. Disconnect evidence records affected channels,
last durable event, first recovered event and recovery source.

### Idempotent collection and publication

A collection job identity includes provider, endpoint, canonical instrument,
data kind, interval/session, requested window, adjustment mode and
schema/mapping version. The deterministic run ID derives from that identity;
attempt number is separate.

`CollectionCheckpoint` stores provider cursor, last complete source event or
session, raw-object digest, published manifest ID, quality-report ID, run ID
and attempt number.

Checkpoint advancement follows this order:

1. persist raw response or frame;
2. validate and persist normalized/adjusted objects;
3. publish immutable objects and manifest;
4. publish immutable quality evaluation;
5. atomically advance the checkpoint and current pointer.

Crash injection after every boundary must be retry-safe. Repeating the same
request produces the same object identities and no duplicate logical rows.
Conflicting content for the same source identity is quarantined as a correction
and does not overwrite accepted evidence. The local collector enforces one
writer and compare-and-swap publication.

### Quality SLA and catalog

Quality policies are versioned by venue, data kind, interval and calendar.
Every evaluation records exact manifest and policy IDs, evaluation window,
expected and observed counts, numerators, denominators, grace period and one
status: `pass`, `fail`, `not-due` or `unavailable`.

Hard integrity gates are:

- zero unexplained duplicate source identities;
- zero object-hash or schema mismatches;
- zero unacknowledged order/timestamp violations;
- zero unexplained missing completed candles or expected equity session bars
  after the grace period;
- terminal provider pagination or an explicit incomplete failure;
- known entitlement and source-rights state;
- zero synthetic rows in a real dataset;
- explicit historical/live overlap reconciliation;
- endpoint-specific freshness and latency thresholds.

Corrections and amended evaluations append evidence. A later pass never erases
an earlier failure.

The local data catalog exposes provider capabilities, datasets, layers,
manifest lineage, coverage, quality, rights, entitlement, collection status and
checkpoint state through a read-only API and one operations screen. Charts,
experiments and forecasts expose a resolvable manifest ID and quality status.
Critical quality failures block downstream use; warnings remain visible.

## Seven-day evidence protocol

Acceptance requires one frozen code/configuration baseline observed for at
least 168 continuous hours.

- Produce seven consecutive UTC crypto reports for BTC/ETH/SOL.
- Include every XNYS session inside the window. Weekends and holidays are
  `not-due`, not successes or gaps. Extend the window if fewer than four
  completed equity sessions occur.
- Produce each immutable daily report automatically by its configured deadline
  and link it to exact code, config, raw objects, manifests and checkpoints.
- Only real provenance qualifies. Fixture, demo and synthetic data contribute
  zero evidence.
- Run at least one controlled process restart and one reconnect drill.
- A missing report, unexplained gap, duplicate, silent truncation, manifest
  mismatch or hard-SLA failure invalidates the window.
- Code, schema, mapping, calendar or adjustment-policy changes restart the
  qualifying window.
- Retention must exceed the observation window; qualifying evidence is not
  stored only in the current seven-day live buffer.

## Tracer-bullet delivery sequence

1. **Immutable AAPL daily tracer:** compatibility registry, canonical identity,
   raw envelope, all four layers, immutable manifests and catalog contract.
2. **Moomoo AAPL/NVDA:** complete pagination, quotes, XNYS calendar,
   adjustment factors/splits/dividends and entitlement-aware collection.
3. **Hyperliquid BTC candles:** public-mainnet read-only REST/WS boundary,
   bounded backfill and canonical candle lineage.
4. **Hyperliquid BTC/ETH/SOL microstructure:** trade identities, book snapshot
   epochs, disconnect/gap evidence and multi-kind persistence.
5. **Recovery:** durable runs/checkpoints, compare-and-swap publication, crash,
   restart, redelivery and long-outage drills.
6. **Product lineage:** quality SLA, catalog UI/API and manifest/quality links
   from chart, feature, experiment and forecast artifacts.
7. **Soak:** clean installation, real collection/replay and the frozen 168-hour
   evidence window.

## Verification strategy

Every behavior change uses red/green/refactor. Adversarial coverage includes:

- bitemporal corrections and as-of knowledge-time filtering;
- same-range manifest tampering, rollback, revision reuse and open-reader
  publication races;
- Moomoo histories above 1,000 rows, repeated cursors, holidays, early closes,
  DST, splits and dividends;
- nonconsecutive Hyperliquid trade hashes, duplicate reconnect delivery,
  snapshot epochs and outages longer than five minutes;
- crash injection after each publication boundary;
- synthetic-row rejection and incomplete seven-day evidence rejection.

Focused tests precede full Python, frontend, golden-path, security, license and
clean-checkout gates. Real smoke tests are opt-in and write only to an isolated
acceptance root.

## Safety and stop conditions

- `v0.1.1-rc1` and every existing tag are immutable.
- No final `v0.1.1` tag is created or promoted.
- No production or mainnet execution URL is admitted.
- No algorithm, AI role, model promotion or order authority is added.
- No synthetic data repairs a real dataset.
- Credentials and paid services require explicit operator authorization.
- A new runtime, database engine, paid feed or other major architecture change
  requires a new ADR and explicit operator authorization.

## Completion criteria

The iteration is complete only when all issue #110 acceptance criteria are
proved from a clean install, every required downstream artifact resolves to an
immutable manifest and quality report, restart/disconnect drills show no silent
duplicate or hidden gap, and the qualifying seven-day evidence window passes.
