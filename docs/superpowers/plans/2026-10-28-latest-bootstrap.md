# Bounded latest bootstrap implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans. One writer, one whole-slice reviewer, maximum two rounds.

**Goal:** Hydrate the existing ordinary saved-history workstation from its read-only lake without unnecessary wide query materialization, preserving every latest observation and refusal.
**Architecture:** In LiveBuffer.latest only, select the same MAX(local_seq) keys using disjoint kind groups so unrelated kinds do not project payload JSON; retrieve full rows via existing _tail_rows under the existing connection lock/snapshot. No feed/API/settings or engine changes.
**Tech Stack:** Existing DuckDB1.5.5, Python, pytest and existing bounded gather.
**Spec:** issue https://github.com/ZP151/quantmesh/issues/239; parent218/237 and ADR0034. Root explicitly authorizes this narrow product repair after the new staged native diagnostic.

## Global constraints

- Actual ACK00:38:32UTC2026-10-28. Cause/scope00:53:32; genuineRED/GREEN02:38:32; reviewed slice04:38:32. Old diagnosis/type-only/native failures retain their own facts and clocks.
- Actual fetched origin/main B6 b6fa35b/tree31d372. New codex/latest-bootstrap worktree; running18765/its source/helper/fixture and old239 branches untouched.
- Runtime implementation lock only src/quantmesh/live/buffer.py:latest; new tests/test_live_buffer_latest_bootstrap.py and own plan/ADR0037/iteration. No helper/feed/API/config/README/version/dependency/generated/permissions or real data/host changes.
- Original128MiB/one thread/temp0/read_only stays. No new LIMIT, fewer channels, silent fallback, partial success, cancellation suppression or caller-transaction commit/rollback. Full result/key memory may still be unbounded by stream cardinality; no total RSS/arbitrary payload/native-scale guarantee.

## Review focus

- Preserve original ELSE grouping for NULL/unknown kind; JSON null mid is distinct from missing SQL NULL; missing/invalid channel must not silently disappear.
- Kind/source/channel collisions and nullable identity fields must not change full17field winners or ascending local_seq output.
- Bind venue/instrument filters identically in all branches; all keys/results survive, including >10000 streams.
- New multi-query work must use one snapshot and retain caller lock/transaction ownership; cancellation/native resource error must not return partial results.
- Generated-view OOM vs stored/native filesystem failure are distinct; no claimed fix of an unobserved C++ operator.

## One vertical slice

- [x] Capture safe original native stage/type/frames and source/config. Finite owned controls: stored134MB model old/helper128PASS and stricter32..96bothrefuse; generated-view original CASE key selection/old latest/helper128OOM, kind-split selection+existing helper128 and32PASS1217. Preserve all controls and their limits.
- [x] Write failing actual persisted tiny DuckDB generated-view test invoking real LiveFeed(lake=realReadonlyLiveBuffer) at unchanged128MiB, no fake feed/connection; old public latest raises OOM. Assert all selected full rows against independent Python stream oracle, not only counts; inspect safe EXPLAIN/config and unchanged archive/no tmp artifacts.
- [x] Add full stored-row equivalence for venues/symbols, STATUS/quotes/trades/L2bidask/null/metrics mid/null/missing/other identities/revisions; filters and >10000 streams. NULL/unknown kind must keep old validation refusal. Add owned/caller transaction, concurrent writer, cancellation and real resource refusal cases.
- [x] Implement only latest: three disjoint scalar key branches (other/NULL kind, L2 side, metrics category), original per-branch filters/MAX/group semantics, UNION ALL; _tail_rows within original lock. Retain its snapshot/key completeness/128batch/Python ordering and error/cancel behavior. No truncation.
- [x] Run new targeted tests GREEN, only necessary affected small helper/default-latest checks, changed Ruff/format/diff. Commit green checkpoint. No old13core/24history/51math/fullWindows/native reruns.
- [ ] Independent R1; at most one aggregate important correction with actual RED/GREEN, then finalR2. Third structural finding returns toPlanner. Update own ADR/iteration with user impact, safe local plan/config/equivalence/error evidence and limitations.
- [ ] Freeze committed HEAD/tree/filemanifest and raw RED/GREEN/controls/reviews in output/latest-bootstrap/HANDOFF; root sends sole publisher for exact applicable CI/normal merge. Sole server alone then performs one necessary native/API reacceptance. Do not touch rc1.

Ruling: merely replacing payload gather was not discriminating and its failures are retained. Kind-splitting is selected only after the finite view control shows the original CASE projection allocates wide payload even for ordinary kinds. SQL grouping semantics, including invalid/NULL rows' fail-closed behavior, govern the oracle. Local generated layout is not a production-storage certificate.
