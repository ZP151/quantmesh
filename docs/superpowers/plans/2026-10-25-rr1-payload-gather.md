# RR1 payload gather: sparse-key predicate

Issue218 continuation. New explicit root leaf ACK2026-10-24T19:29:53Z,
cause checkpoint19:44:53Z, implementation checkpoint20:09:53Z, hard20:29:53Z.
Base actual merged9d8b33075e5f2a31d7e67b02f9715c83f19a9c0c/tree
d71ded3dbf52d248b02d00ea4968fecd8e91aa36. Previous449 branch/artifacts remain.

RR1 trace1132 is complete-row batch execute, not1123 key selection. Failure is
OPEN/archive-default-temp/READ_ONLY_FILESYSTEM, errno30 inferred from public
text. Unknown batch index/key count/C++ operator remain unknown. No host retry.

- [x] Read exact source and RR1 corrected trace; inspect LOCAL DuckDB1.5.5 plans.
  Sparse128-key IN rewrites to HASH_JOIN; dense IN can become a direct range,
  an important limitation of the previous all-matching generated-view model.
- [x] Select one direction: exact bound scalar equality disjunction within the
  same128-key batch plus its min/max range for scan pruning. No IN/hash rewrite,
  no smaller batch, changed projection, snapshot or key-selection semantics.
  LOCAL generated-view20MiB/0B old sparse IN refuses and selected predicate
  returns128 exact full17 rows. This is a tighter owned model, not native proof.
- [x] TDD: new sparse full10000/raw17tuple oracle, plan difference, sparse bounds,
  absent/duplicate keys, caller snapshot/transaction and errors. Use only existing
  legal view/in-memory data; no new persistent DB or source copy.
- [x] Minimal payload-gather predicate change only and focused relevant checks.
- [x] One independent delta review: R1 READY, Standards0/Spec0; independent
  focused18pass/1deselected3.14s. No repeated232suite/old model/old CI/browser.
- [x] Freeze reviewed source and prepare immutable publisher/root handoff before
  the original new hard time; final documentation does not change runtime/tests/ADR.

Freeze key query, forward/public API, transaction/lock handling and17-column
projection. Keep production128MiB/threads1/temp0/RO. Retained old data150353373B
and existing2MiB incremental metadata cap; no deletes/compression/new large data.
No SSH/SDK/secrets/provider/new environment/dependency/paid or shared board edits.

TDD actual3RED/2pass before implementation, including the current helper's
payload execute refusing20MiB after key selection. Single selected predicate
change plus two bound parameters; no batch shrink or transaction/key changes.
Final focused18pass/1explicit old-wide-model deselection2.99s. New independent
Python formula oracle compares every raw field/byte for10000 sparse events;
new public-decoder limits and sparse caller/concurrent snapshot tests included.
Existing error/duplicate/missing/lock/ownership cases run in the focused boundary.
No232suite or old full model/CI/browser/native replay.

LOCAL metadata on the immutable partial DB confirms its PRIMARY KEY/old indexes:
old sparse IN has HASH_JOIN over17-column SEQ_SCAN; selected scalar form has
no join and a range filter on its scan. No payload SELECT, schema DDL or data
change in this metadata case; original DB hash verified unchanged. All RR1
packet30members/hash/source pins verified without extracting or rerunning host.

Reviewed577b3b3318bd292974463ca769615a1d2457bc52/tree0565854de7d2cd42824c9c2633cbc503fb641379;
source SHA3cd08da4f04eb7bbbf2482a62e991de5641576a0b1f6ff10ae7975eeb4b5c690.
R1 report and raw output hashes are in the own iteration and final ignored
HANDOFF.json. No corrections required. Commit-hook bypass follows explicit scoped
checks and is disclosed. New exact-head CI/normal merge remain publisher gates;
native acceptance needs root's separate complete release forecast/decision under
the corrected carry197988352B/HWM9353, normal other remaining1241088B. Neither
software READY nor future merge approves native staging or completes research.
