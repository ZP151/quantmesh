# #208 whole-append owned I/O functional implementation

Root accepted the functional contract in NEXT-DELIVERY-PLAN.md on2026-10-22.
Inline implementation, one source writer, then fresh independent complete-diff
review (maximum2 rounds). This does not accept the old50ms experiments.

Base actual fetched origin/main aa62faeddd84c31887e43bf0dae532e649a4ecbe;
managed branch codex/0038-live-owned-persistence. Start08:12SGT, RED by08:27,
implementation by08:57, boundary evidence by09:27, immutable checkpoint or one
specific STOP by09:42. No push, CI, host/SSH, original DB, pair or dependency work.

Owned files: src/quantmesh/live/feed.py, tests/test_live_feed_owned_persistence.py,
this plan and docs/iterations/0038-live-owned-persistence.md. Buffer/SQL/schema/
retention/startup/supervisor/REST/chart/routes/dependencies remain untouched.
After R1, root additionally authorized only completion-wait corrections in
tests/test_live_candle_revisions.py and tests/test_live_observation_identity.py;
all original stream, identity, revision, dedup, count, content and order checks
remain. No tests/test_live_router.py write permission was added.

- [x] Fetch/ACK exact base, managed WT and paths; consume accepted contract.
- [x] Freeze original and calibrated test FULL texts in ignored history with
  SHA matches51c3e39a... and da1424f7..., plus all original raw/receipt/input
  generator rules. Realized old absolute timestamps were never recorded; say
  so rather than invent them. Preserve two failures and no third latency pair.
- [x] New real DuckDB+Hyperliquid pump event-order RED: accepted COMMIT pending,
  observer requests loop cache read/stop before finite release. Original loop
  observes after release/commit and sees new cache; expected old cache/pre-
  release observation fails.33 quotes persist; no timeout/collection substitute.
- [x] Single asynchronous sequence gate for supported live pump, tick, async
  and external thread-safe producers. Only complete append/prune I/O off-loop;
  retain and join the actual worker. Commit then short loop cache/ack/delivery.
- [x] Exact same first test GREEN, then real transaction failure, ordering/
  dedup, stop/join and active/offline producer completion/error tests.
- [x] Check actual synchronous caller compatibility; a required active owner-
  loop blocking API conflict is a STOP, not rejection/bypass/new platform.
- [x] Freeze source, fresh independent spec/standards review≤2 rounds, focused
  affected checks, Ruff/format/whitespace; no root-suite retry. Exact hashes and
  immutable local commit/handoff; runtime qualification remains NOT PROVEN.

Review focus: cancel at admission and entered I/O, cancelled await versus real
thread, external waiting producers during stop, dedup/no partial book publish,
restart generation and every supported live writer's commit/application order.

Completed bounded checkpoint: independent R2 READY, both R1 P2 findings closed;
127affected tests pass, full Ruff/changed-file format/whitespace pass, unchanged
uninitialized submodule pins inspected. The immutable local commit contains
exactly the six authorized source/test/record paths. No push/CI/merge/deployment
or retained-scale performance qualification is included.
