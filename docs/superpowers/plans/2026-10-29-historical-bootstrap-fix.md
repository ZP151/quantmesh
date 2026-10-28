# Saved-history feed profile â€” issue246

## Approved outcome and narrow design

Root authorized this faithful dependency repair under existing saved-history
approval: one explicit historical date reads the real saved source or returns
precise unavailable. ACK2026-10-28T16:34:40UTC (Oct29 00:34:40Singapore), short
design16:54:40UTC, first actual increment18:34:40UTC, reviewed slice20:34:40UTC.
Reuse existing clean WT, new codex/historical-bootstrap-fix from actual origin/main
1b6cf75ea4908a4d739a071618619a9eb231a5e3/tree58e6cbbd. Preserve old refs/evidence.

Static dependency is proved, timeout inner cause is UNKNOWN: LiveFeed.__init__
calls global latest before API construction, while LiveHistoryService.inspect
only needs replay_buffer and existing bounded per-request replay. Both native
failed composite ctor phases and their close/exception UNKNOWNs remain unchanged.

Add explicit keyword history_only=False to real LiveFeed. True requires an actual
readable read-only lake; the same reader stays attached. That profile does not
construct the current live cache and cannot provide current snapshots/status/
session state, subscribe, attach providers, run a pump, ingest/publish or prune.
It retains real replay access. Default False retains full original latest warm-
start, all channels/winners and live lifecycle semantics. This is no dummy feed,
bootstrap subset or fake cache readiness; unsupported live use fails explicitly.

LiveHistoryService.inspect remains the original manifest-first/bounded replay
implementation. History-only service refuses current history/compare before data
access, so an intentionally absent current cache cannot masquerade as live.
Normal create_workstation_app(history=real_history_service) mounts the existing
inspection route, as it already does dynamically; widen that annotation to match.
Reject a history-only feed passed as live_feed before starting/mounting live
surfaces. No new URL/DTO/query privilege/CLI/profile environment/frontend change.

Actual composition:
LiveBuffer(real_archive,read_only=True) -> LiveFeed(lake=reader,history_only=True)
-> LiveHistoryService(manifest_or_None,feed) -> normal create_workstation_app(
history=service,live_feed=None) -> existing GET history-inspection?at=aware_time.
No separate prewarm/query, clock rollback, synthetic substitution or skipped feed.

## Full source semantics and negatives

Keep every existing venue/symbol/kind/received/market UTC/window filter, STATUS/
gap/identity/digest/conflict/interval/last-contiguous-segment rule. Per-store10000,
final10000 and128-key batches,128MiB/one thread/zero spill/readonly unchanged.
Original source/receipt/coverage/stale metadata and actual observed_at persist.
No extrapolation from tiny synthetic software fixtures to7.4GB performance,
native IOException/OOM/deadlock, source qualification or Paper/live authority.

Negative tests: invalid profile/writable/unavailable lake; future/naive/extra query
before replay; wrong venue/symbol and missing window; corrupt/resource refusal;
STATUS boundary/identity conflict preserve unavailable; current-cache/provider/
writer calls refuse before effects; misuse via factory live_feed rejects. Default
profile must still call complete latest and expose its real cached state.

## File locks and delivery

Runtime only live/feed.py, instruments/live_history.py, api/workstation.py.
Dedicated tests/test_historical_feed_profile.py; own iteration
0038-historical-bootstrap-fix.md, this plan and relevant ADR0036 append. Do not
touch quantity/research/protocol, CLI/policy/frontend/version/locks/README,
old18765/18843, host/data/SDK/providers/permissions/math, source buffer SQL or
resource settings. No package/env/install/site-packages mixing. Two writers
remain disjoint; parent alone implements this slice. Independent review<=2 rounds.

## TDD and observable delivery

- [x] Restore docs/history and verify fresh base/clean WT; create issue246 and
  report actual ACK/dependency graph/design to root within20minutes. No native.
- [x] New module-scoped tiny real DB shared across cases: actual readonly reader,
  real feed/history/ordinary factory/TestClient. Instrument latest to refuse if
  called for explicit history profile (no fake returned data). RED against old
  code must fail at missing profile; full explicit past200/source/receipt/
  coverage/actualclock and exact replay filters are the core assertion.
  Command: python -m pytest -q tests/test_historical_feed_profile.py.
- [x] Implement the above three-file dependency correction. Same command GREEN;
  include default real warm-start, readonly misuse/live operations, range/gap/
  conflict/malformed/resource negatives and no clock/account mutation. Keep real
  read-only file hash unchanged. No assertion-only or reject-all shell.
- [x] Changed Ruff/format/diff, actual results/commands in own iteration. Commit a
  coherent GREEN checkpoint within60minutes. No old19/69/wide/full suite reruns.
- [x] Fresh independent R1, at most one aggregate necessary correction then R2;
  a third structural issue returnsPlanner. Seal exacthead/tree/source+evidence
  manifest for sole publisher to run applicable CI and normally merge. No author
  duplicate CI/source hotpatch; root alone admits a later necessary native phase.

##8MiB cohort

HISTORICAL-BOOTSTRAP-FIX includes all new/failed small DB fixtures, output, tracked
file and new Git deltas in this existing WT. Root baseline7974752346+8388608=
7983140954, only16859046 global headroom; parent unchanged, hard8GB/4GB/free50GiB.
No new checkout or large fixture. Keep one module DB per test run, log bytes and
fixture allocations before any further run. Stop before exceeding the8MiB hold;
do not delete failures, borrow old native64, or claim future native allocation.
Existing Python3.13.9/DuckDB1.5.5/FastAPI0.141.1/NumPy2.5.2/pg8000 1.31.5 are
observed local runtime versions, not a new environment or release certification.

Author source/test freeze: c0209e6, R1 READY/no findings. Final docs-only exacthead
R2 receipt accompanies output handoff. Sole publisher still owns applicable CI/
normal merge; native is unadmitted and pending. No further database rerun.
