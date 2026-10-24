# Read-only RESOURCE_TEMP diagnosis — issue218 continuation

Issue: https://github.com/ZP151/quantmesh/issues/218.

## Planner: bounded decision

Root ACK 2026-10-24T17:03:04Z; mechanism checkpoint17:23:04Z; hard stop18:18:04Z.
Branch codex/readonly-resource-diagnosis starts at actual origin/main
9cdf3217fd7a7a556f05d7a425f1a0102ca26ec5. Issue222 is independently handed off
at d719ef5; its worktree, UI and preview are not part of this investigation.

One user action remains the original default BTC ONE_DAY read-only archive+hot
history, candle+STATUS, inclusive received/data/asof filters and tail10000. The
success criterion is a verifiable mechanism/correction decision, not another
speculative SQL variant. No host/query/SDK/auth/provider, resource configuration,
archive copy/migration, dependency/environment, Goal or automation changes.
Owned model files are capped at128MiB total; non-model output at2MiB.

## Quant researcher: acceptance remains separate

No change to source rights, PIT/finality, identity, continuity or financial
qualification. Original independent research stays blocked/unknown, capture0,
financial0, Phase2_NOT_STARTED. A small model PASS cannot admit the real archive
or turn a failed native query into success.

## Verifier: sealed evidence and current source

The sole operator's CB2 packet SHA256 is
f3b9dca90a7b55d2203065b12e5204564e9f15b4eabcacfbc5851c4e86f51ee7.
Its MANIFEST SHA256 is
446a59e481ff5bb30a359cfc100b8492d0064c3ddae28af200e2e09b77e2552e.
All25 listed members match byte counts and hashes. All four enclosed product
files match this checkout byte-for-byte; current tree is
b605ec99e94ecaddbd3449ccfffd8a87e8b8e994. No extraction or canonical data access.

The actual default service query ran once16:54:06.480826Z through
16:54:08.666450Z (2.185362596064806s), DuckDB1.5.5, read-only archive,
memory128MiB/threads1/max_temp_directory_size0B. It returned
STOP_SHIPPED_FORMAL_SERVICE_SEMANTICS, category RESOURCE_TEMP, chain_complete=true.
Reader closed, child terminal, runtime observation complete, canonical DB/WAL
stat signatures unchanged and no hot root created are reported true in the
operator receipt. The signatures cover device/inode/size/mtime/allocated bytes,
not a fresh full-file content hash. SDK/auth and typed
baseline passed; downstream cache/native/RW/HTTP/live activation were NOT_RUN.
Probe MemoryMax256M is not a demonstrated cause.

The sealed classifier (sources/vb2_query.py:55–73) categorizes native
OutOfMemoryException as RESOURCE_MEMORY. RESOURCE_TEMP requires a DuckDB
IOException whose text contains duckdb_temp, max_temp_directory_size or temporary
directory. Complete singleton classification therefore establishes at least one
recognized temporary-related IOException and no recognized competing resource
category in that traversed chain. It does not preserve the matched token,
errno, exact operation, raw message or failing SQL operator. Those details are
not recoverable from this packet. Memory pressure could precede an I/O attempt;
the category alone neither proves nor rules out such a trigger.

Three synthetic native-exception classifier checks pass. They execute the exact
AST-extracted sealed function, not the host harness. Their exceptions are
constructed controls, not reproductions of CB2.

## Mechanism research: upstream and owned model

Version-pinned upstream code was read without installing or changing DuckDB:

- [standard_buffer_manager.cpp](https://github.com/duckdb/duckdb/blob/v1.5.5/src/storage/standard_buffer_manager.cpp):
  temporary-buffer writes first require a temporary directory.
- [temporary_file_manager.cpp](https://github.com/duckdb/duckdb/blob/v1.5.5/src/storage/temporary_file_manager.cpp):
  directory initialization can create its directory before setting the swap cap;
  the capacity-overflow guard itself throws OutOfMemoryException.

Consequently0B is a storage-cap setting, not evidence that every filesystem
operation is suppressed before a capacity check. A temporary-file I/O refusal
is compatible with the engine path, but exact CB2 cause remains UNKNOWN. Changing
the cap/path would change controls, and only changing the displayed exception
would not restore history. Neither is a corrective implementation here.

One new owned model uses actual DuckDB1.5.5, the complete17-column schema and
existing index definitions,1600000 highly compressible rows, candle+STATUS and
the unchanged current tail SQL. It retains read-only128MiB/threads1/0B during
the query. Result:10000 complete17-column SQL rows, keys1590001..1600000 exactly,
5.975617700023577s. It does not exercise MarketUpdate decoding/service coverage.
Its narrow repetitive payload, constant timestamps and Windows writable owned
directory are material differences from the real archive/POSIX namespace.
Constant time predicates are pruned by the optimizer in this model.

Actual EXPLAIN shows scalar max(local_seq,10000) aggregation plus SEMI HASH_JOIN
and a17-column sequential payload scan; no WINDOW or final ORDER_BY. This again
disproves an unconditional full-WINDOW-sort explanation for current SQL. It
does not prove bounded RSS, absence of all temporary I/O at production scale,
or the real failing operator. No third SQL variant was written or benchmarked.

Retained ignored output: output/readonly-resource-diagnosis/ contains model.py,
model.duckdb, model-result.json, plan.txt, classifier_probe.py/classifier-result.json
and version-pinned upstream files with hashes in model-result.json. Observed
total after model execution69289348B (<128MiB); final accounting follows in the
immutable handoff. All earlier artifacts/failures remain untouched.

## Implementer: STOP rather than speculative runtime change

No product/test/engine source change is justified by the available evidence.
The current default archive service remains unavailable. Root's permitted
single host regression requires new corrective evidence; this investigation
does not provide it and does not authorize a query retry for omitted diagnostics.

Actionable choices for the next product decision:

1. Continue the independently delivered local CSV snapshot import/inspection
   loop. It preserves the existing archive and controls and needs no host retry.
   Structural PASS still has research eligibility blocked until rights/PIT/
   finality and numerical acceptance are satisfied; it is not archive recovery.
2. Define a separate bounded streaming/archive-reader slice using the original
   read-only archive and the existing history contract. A candidate would have
   to prove all predicates, STATUS/identity/continuity, one consistent snapshot,
   inclusive times and exact tail10000, plus runtime/RSS/time bounds. Multiple
   statements require an explicit snapshot guarantee; scanning the entire
   archive has a latency cost. No implementation or feasibility claim here.
3. If later authorized corrective work earns an actual-host acceptance attempt,
   its pre-reviewed diagnostic receipt should retain a bounded allowlisted
   operation/token/errno and engine operator evidence. It must preserve current
   safety/resource controls and never log raw data/credentials. Existing omitted
   details are not grounds for an additional probe. An upstream engine report
   needs a matching sanitized reproducer; this PASS model is not one.

Resource/cap/RW/temp relaxation, a7GB copy or blind query retries are outside
this leaf.

## Reviewer and final handoff

Independent reasoning R1 READY, Standards0/Spec0 blocking findings. The reviewer
checked all25 packet members, four exact product sources, classifier inference,
version-pinned upstream mechanism and actual owned execution plan. No test,
experiment, host action or tracked change by the reviewer; no second round needed.
Report output/readonly-resource-diagnosis/reasoning-review-r1.md SHA256
99314dac67936e95c58396854a495342e7bc5a94b788da482b23fd95a362d12e.

Final decision is STOP for this resource investigation, with the three concrete
next choices above. No product/tests/ADR change or new-host acceptance claim.
Only this iteration record is committed; hooks are bypassed because this is an
evidence-only checkpoint, after explicit whitespace/source-identity/file-budget
checks. No old or broad suite/CI was repeated. Root receives immutable commit,
artifact hashes and final accounting. Original research Goal is not completed
or resumed by this checkpoint; root remains its owner. The75min allowance is a
maximum, not a reason to spend it after evidence reaches this decision.
