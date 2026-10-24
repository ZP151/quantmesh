# Equivalent read-only tail query plan

Issue218; specification is root's bounded B2 follow-up authorization. Actual
ACK2026-10-24T09:54:21Z,20min checkpoint10:14:21Z,40min freeze10:34:21Z,
hard stop10:54:21Z, no reset. Base actualorigin/main7a1fa218b807a581023e77e4e28985636241b3ee.

## User action and constraints

Read the original default BTC ONE_DAY history with candle+STATUS, inclusive
received/data time windows and asof, tail10000, without modifying the archive.
Runtime scope only buffer.py replay tail SQL and bounded returned-row ordering;
new focused tests and necessary iteration/ADR. No other runtime refactor.
Preserve all predicates before selection, full rows/identity/continuity, unique
local_seq ordering, limits/nonpositive legacy behavior, manifest/hot boundaries.
No real host/DB query,7GB copy/simulation, index DDL/migration, RAM/RW/spill
relaxation, dependency/environment/provider/Goal/mount/qualification changes.

## Evidence and candidate

Reuse B2's formal native RED:09:52:39.402692Z actual7a1fa218, DuckDB1.5.5,
2.027s HistoryUnavailableError/IOException while attempting read-only temporary
storage. Original128MiB/threads1/max_temp0B unchanged; probe256M cgroup is not a
demonstrated cause. Raw operator receipt SHA
1de9843615a1d305e67ea2b520c17bf5c9397e45dab3ebcb8a52a5ce608d5784.
No profile of that host call exists, so do not identify its exact operator.

Small owned60000row/512B payload model uses real DuckDB1.5.5/full17columns,
dual-time/default10000. Initial hypothesis of an always-wide historical WINDOW
is disproved: EXPLAIN shows the old optimizer already selects rowids via arg_max.
The old query still sorts full selected payload rows in SQL. Exact old query
fails at16MiB/no spill; a key-only membership query with Python ordering of only
the returned rows succeeds10000/50001..60000. At128MiB both succeed. Profiles
show lower reported peak for the candidate, but may exceed memory_limit because
that setting is not a process/RSS bound. This is a model, not host acceptance.

Candidate keeps the original ROW_NUMBER predicate inside a scalar local_seq
subquery, then reads complete rows by unique non-null primary key. It removes
the wide final SQL sort and sorts at most the returned limit in Python, inside
the existing connection lock. Same one SQL statement/snapshot, no query state
change, no premature candle-only or time trimming. Keeping the predicate also
preserves old zero/negative limit behavior without new LIMIT coercion.

## TDD and delivery

- [x] Read actual base/query/caller/schema, retain formal native RED; run owned
  small actual plans/profiles and record both disconfirmed and supporting models.
- [x] New tests/test_live_buffer_tail_query.py: actual legacy/new differential
  full rows across every predicate/boundary/STATUS/gap/empty/seq uniqueness;
  actual small32MB-logical data constrained16MiB/no spill regression RED.
- [x] Minimal buffer.py tail change; GREEN focused file and legacy live_buffer,
  live_history, market-history-hot-cache/lookup affected boundary, changed Ruff/
  format/diff. Preserve all initial errors and output; no full repository suite.
- [x] Freeze commit; one independent known-query and affected-boundary review,
  at most2rounds/one aggregate correction, then exact reviewed publisher handoff.
  If structural equivalence/memory issue persists, precise STOP, no expansion.

Output evidence directory output/market-history-hot-cache/. Root receives20min
cause/model/TDD checkpoint and final immutable handoff. Sole publisher owns new
exact-head CI/normal merge and delivers merged receipt directly to root/operator.
Original219/220/B2 STOP remain; original research blocked/capture0/financial0/
Phase2_NOT_STARTED/PRECISE_UNKNOWN unchanged. Native reacceptance remains separate.

Source freeze checkpoint:80RED2/73pass then81GREEN75pass4.94s. Final affected
83invocation220pass/2explicit Windows native-directory-fsync skips/6existing
warnings56.28s exit0 across new tail, live_buffer, lookup, live_history and
market-history-hot-cache.84Ruff/format/diff exit0. Runtime delta9+/3- only.
Local commit hooks bypassed after these explicit checks; publisher exactCI remains.
Independent review pending; no real-host query or qualification inferred.

Independent R1 finished PASS on dab1cf9/treeed1290e8 with Standards0/Spec0 and
no requested correction. One reviewer invocation220pass/2Windows native-fsync
skips/6existing warnings55.07s exit0; report/raw hashes in the iteration record.
Final candidate checkpoint edits only iteration/plan, retaining source/test/ADR
identities. Publisher exactCI/normal merge and sole operator's default-service
merged-source reacceptance are still outstanding, independent of author timebox.
