# Sustained live chart recovery implementation plan

Goal: restore the existing BTC/ETH/SOL full chart after the live lake has grown,
with responsive HTTP and real fresh source observations on the private AWS host.
Spec: iteration0035 / reopened issue144; existing ADR0023/0024 semantics apply.
Architecture: retain DuckDB, append-only evidence, exact four-field identities
and the existing feed. Add a selective physical access path and express the
scope as row equality so DuckDB1.5.5 uses it. No event-loop/authority redesign.

## Evidence and constraints

Actual855594-row AWS copy: original lookup1.101s Sequential Scan; row-scoped
lookup3.628ms Index Scan with equal result. Merely adding the single-column
index leaves the original query sequential. Independent200004-row local
experiment agrees. The CPU profile is dominated by DuckDB string scans.
MAX(local_seq) is~1ms and remains unchanged. Four old quarantines are retained.
CPU steal73–79% is observed; credit exhaustion is not independently established.

No new provider/dependency, live trading, paid AWS capacity change, ledger
rewrite/deletion, widened time tolerance, identity weakening or unrelated0021/
0030 work. Root owns docs/integration/benchmarks; implementer owns only files
below. Full-scope equality and composite uniqueness must remain authoritative.

## Task1 — selective exact-identity admission

Files: `src/quantmesh/live/buffer.py`, new
`tests/test_live_buffer_lookup.py` (existing tests are read-only unless a directly
required regression belongs there). No other production file.

- [x] RED: shared Python `-m pytest -q tests/test_live_buffer_lookup.py` with
  worktree PYTHONPATH and unique OS-temp basetemp. Seed retained rows through
  valid replay fixtures; capture the actual append identity SELECT via a thin
  delegating connection probe. EXPLAIN ANALYZE that captured statement on a
  checkpointed/reopened database must use Index Scan, not a wall-clock threshold.
  Cover hit, plausible hash miss, same ID across venue/instrument/kind and true
  same-key conflict. Preserve returned receipt sequence/dedup and quarantine.
- [x] Implement lookup SQL:
  `SELECT local_seq, content_digest FROM market_updates WHERE source_event_id = ?
  AND row(venue, instrument, kind) = row(?, ?, ?)` with parameters
  `[key[3], key[0], key[1], key[2]]`.
- [x] In the second migration transaction, after column/backfill validation,
  create non-unique `idx_updates_source_event_lookup` on
  `market_updates(source_event_id)`. Keep composite UNIQUE and version semantics.
  Initial `_SCHEMA` must not reference a missing legacy source_event_id column.
- [x] Test legacy upgrade, prior-schema reopen, idempotent re-open, atomic
  paired-book rollback and source-status retry through existing focused tests.
  GREEN: new lookup tests plus buffer/feed/candle/observation/supervisor tests;
  Ruff and format check changed Python. Report actual RED/GREEN before review.

## Task2 — root benchmark and review

- [x] On owned copies only, compare full append_many batches at retained sizes,
  hit/miss/scope controls, reopen, rows/quarantine preservation and query plan.
  Record batch size, latency/throughput and CPU/memory limits. Query-only speed
  is not complete feed acceptance. Leave primary AWS DB unchanged at this gate.
- [x] Independent bounded spec/standards review, maximum two rounds. Resolve
  findings, run relevant combined gate, then commit and publish one PR.
- [x] Required exact-head CI before merge/deploy. Preserve localmain and existing
  private deployment boundaries; merge under standing user authorization.

## Task3 — actual operator acceptance

- [x] Deploy exact merged source using reviewed existing private release helper.
  Keep the original lake, all four old quarantines and rollback releases.
- [ ] On retained production-sized lake, paired API/browser witness: six
  Markets/Watchlist entry paths; real source/time/age<=30s; at least two active
  candle changes and one next-minute append; reload retains covered points.
  Health/state/workspace response times must be recorded, with no20s timeouts.
- [ ] Check existing stale/disconnect/gap controls separately; papertrue/livefalse
  and orders/risk unchanged. Observe response/ingestion under actual browser
  load, then record user-facing acceptance steps and limits in iteration/issue.
  Do not infer durable health merely from a brief fresh restart.


## Task3a — bounded live chart refresh after failed AWS load acceptance

Planner/quant checkpoint2026-09-13 10:03UTC: actual deployed sources remain
fresh, but initial SOL chart failed20s. A single diagnostic trace localized
ETH/SOL delays to workspace TTFB13.15/13.21s; lazy chunks15/34ms. Whole-workspace
invalidations on each matching update every500ms can produce back-to-back
retained reads. Local copied855594-row replay costs377–409ms, of which236–259ms
is conversion/validation of10000rows. AlternativeTOP-N query has no consistent
improvement. This slice bounds read frequency; it does not weaken validation,
replace replay or presume complete server-side attribution.

User action/outcome remains the six real-chart entry paths above, with no20s
loading timeouts under three chart pages and sustained real revisions/appends.
Keep AWS source5332a19 running until the new exact reviewed merge passes CI.

Exact owned files: frontend/src/screens/InstrumentWorkspace.tsx,
frontend/src/screens/InstrumentWorkspace.test.tsx. Root owns generated assets
under src/quantmesh/api/static/app and documentation/build integration.
Only live Hyperliquid automatic workspace refresh changes; existing Moomoo/
other venue timings, user-driven refresh, packet mutations and UI copy stay.

- [x] RED component regressions using actual QueryClient and deferred responses:
  sustained matching quote/candle bursts never refresh while fetching and never
  start another request until5000ms after success/error settlement; eventual
  fallback refresh still occurs without another event. Wrong identities do
  not trigger refresh. Route/range/comparison changes and unmount leave no
  obsolete callback. Refreshed authoritative history visibly revises/appends.
- [x] Gate live Hyperliquid invalidation for the exact active query on idle
  fetchStatus and elapsed5000ms since max(dataUpdatedAt,errorUpdatedAt). Reuse
  existing QueryClient; no custom global cache or new state authority.
  Poll interval is false while fetching and5000ms when idle for this scope,
  verified against installed QueryObserver timers. Existing500ms callbacks may
  coalesce events but must not re-admit a request before this completion gate.
- [x] GREEN targeted workspace/live/chart frontend tests. Preserve aging and
  stale/degraded labels at existing thresholds. Response duration plus5s is
  the possible refresh spacing, not a promise of five-second ticks. No stale
  value becomes fresh just because WebSocket remains connected.
- [ ] Independent spec/standards review max2rounds; root full frontend suite,
  typecheck/lint/API freshness and production build plus packaged chart E2E.
  Commit/push one reviewed slice, required exact-head CI, squash merge.
- [ ] Exact AWS deployment; actual three-page trace shows bounded request
  rate and lower response times, then complete source/browser/reload gates.
  If response time still violates acceptance, record failure and return to
  Planner; do not increase timeouts or freshness tolerance to pass.
