# Existing tail: bounded complete-row materialization

Issue218 continuation. Root approved this short design directly after DX1's
actual OPEN/READ_ONLY_FILESYSTEM observation. Original ACK17:03:04Z and hard
deadline18:18:04Z remain; no new clock. Existing branch is isolated from222.

- [x] Establish meaningful full17-column/wide-JSON RED at a declared test-only
  tighter memory cap/no spill. Keep the existing69MB model immutable and total
  owned files128MiB/output2MiB. Model is not an exact POSIX/7GB reproduction.
- [x] Keep existing key rank/max selection; retrieve complete rows in fixed
  small key batches under the existing lock and one database snapshot. Sort
  returned rows exactly as before. Preserve forward path, every predicate,
  STATUS/identity/corruption/error propagation and zero/negative/default limits.
- [x] Detect a caller's existing transaction without BEGIN failure or commit/
  rollback of caller state. DuckDB Python1.5.5 exposes no autocommit property;
  two txid_current() statements differ in autocommit and match in a caller
  transaction. Check this with real connections, concurrent writer and fault
  injection. Own BEGIN/COMMIT/ROLLBACK only when no caller transaction exists.
- [x] Focused RED/GREEN tests: full-field equivalence, bounded query cardinality,
  exact extra query count, absent/duplicate keys fail closed, empty relations,
  concurrent mutation between batches and caller transaction retention.
- [ ] One independent delta review plus known correction, then frozen commit
  and exact publisher handoff for normal CI/merge. No host query/CI here.

No resource/temp/RAM/RO change, new engine/platform, lost fields/observations,
new dependency,222 source/preview, raw archive or trading authority change.
PM1 metadata-only actual plan is separately owned by the server operator.

Model-construction correction: the attempted wide on-disk fill exceeded its
post-batch128MiB guard, actual total150323016B/new failed DB81014784B at5000 rows.
Root explicitly froze that raw retention and narrowly accepted that actual
retained total plus at most2MiB later metadata. No compression/delete or further
DB fill; the old69218304B model and new failed DB remain byte-for-byte intact.
Generated-view tests write no wide data. This budget failure is not a query RED.

Semantic RED5/2pass preceded implementation. Wide generated-view RED16MiB
actually refused current replay after key10000 PASS. First batch implementation
also refused16MiB because one generated vector needed8MiB. Declared stricter
32MiB test now checks frozen old SQL still refuses, while new10000 full rows
match the independent batched oracle,79payload/84total statements. Product
memory128MiB/threads1/0B unchanged. Final focused12pass5.71s. A mistaken test
expectation that1.5.5 catalog errors abort a caller transaction was corrected
to its actual behavior, preserving caller state. Early errors/logs retained.

Partial frozen DB differential under production128MiB/RO verifies4905 complete
17-column tuples exactly equal the frozen old SQL, with unchanged file SHA.
First affected invocation inherited another worktree's PYTHONPATH in child
processes and pytest's shared Windows temp cleanup denied access; rerun uses
this source explicitly and a fresh task-owned pytest temporary base. No runtime
environment or dependency installation; initial failures are retained.
