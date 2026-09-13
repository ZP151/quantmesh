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
- [ ] Required exact-head CI before merge/deploy. Preserve localmain and existing
  private deployment boundaries; merge under standing user authorization.

## Task3 — actual operator acceptance

- [ ] Deploy exact merged source using reviewed existing private release helper.
  Keep the original lake, all four old quarantines and rollback releases.
- [ ] On retained production-sized lake, paired API/browser witness: six
  Markets/Watchlist entry paths; real source/time/age<=30s; at least two active
  candle changes and one next-minute append; reload retains covered points.
  Health/state/workspace response times must be recorded, with no20s timeouts.
- [ ] Check existing stale/disconnect/gap controls separately; papertrue/livefalse
  and orders/risk unchanged. Observe response/ingestion under actual browser
  load, then record user-facing acceptance steps and limits in iteration/issue.
  Do not infer durable health merely from a brief fresh restart.
