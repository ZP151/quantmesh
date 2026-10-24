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

## Later root direction and DX1 actual I/O observation

After the d8a1c6f checkpoint, root explicitly authorized the sole server operator
to run one different-evidence-target diagnostic. It keeps product SQL, read-only
archive,128MiB/threads1/0B, OS256M and original time bounds/default10000 semantics.
It adds safe exception metadata and pre-collection cgroup/exit observation only;
no SDK/login/restart/cache. This supersedes the earlier no-additional-diagnostic
decision for this one operator-owned run, not for a product-owner host retry.
No streaming-reader architecture is selected or presumed necessary. This
product task retains its original18:18:04Z deadline.

Product owner independently reviewed four frozen DX1 function-level runtime
pins, exact AST identity of run_child with sealed CB2, finite safe graph/error
mapping, trusted frame allowlist, exact-unit stop witness, unchanged query
properties, once claim, snapshots, allocation tracking and owned-child cleanup.
READY_FUNCTION_DELTA_ONLY, Standards0/Spec0 blocking findings. No test/model/host
action. Report in the operator's dx1/DX1-FUNCTION-REVIEW.json SHA256
3eef45b226e148aea9e3e7657528fea150db9ce38d73196caf6b502d7227d4af.
This is a function review, not native query acceptance.

Sole operator's one actual run17:17:31.824Z–17:17:35.961Z completed; no retry.
Product owner read its structured public DX1-START.stdout directly, local SHA256
fb1107c809d2479b551a1dec1687fa8cc1cd43752b973e4efa40593ae9bc11f0.
Its public record identifies root receipt SHA256
0b9c80cf371cf576ebdf00334be312d876430a2d6cf8fe98622112ef8f1ee197;
product owner did not independently access/hash that remote receipt.

New observed service result remains STOP_SHIPPED_FORMAL_SERVICE_SEMANTICS,
RESOURCE_TEMP, reader_closed=true,1.9596685911528766s. Complete two-node context
chain: VALUE_WRAPPER at live_history.py349 then DUCKDB_IO, with trusted frames
live_history.py347 and buffer.py1104. Finite public mapping:
action OPEN, public_error READ_ONLY_FILESYSTEM, path_category ARCHIVE_DEFAULT_TEMP.
The errno30/EROFS value is inferred from an exact known public error-text suffix,
not a directly captured C-layer errno attribute. No arbitrary message, original
temporary filename, SQL/data payload, source line or locals is exposed. This
locates a temporary-file OPEN refusal, not a CREATE_DIRECTORY failure. Exact
DuckDB C++ operator and preceding allocation trigger remain unobserved.

Actual stop witness before collection: service_result success, exit_code exited,
exit_status0; memory.events low/high/max/oom/oom_kill/oom_group_kill all0;
memory.peak225701888B/current6447104B/max268435456B; read_failures empty.
This peak covers the entire query cgroup including the stop helper. It is neither
production RSS nor a measurement of one SQL operator. No cgroup OOM/max event
is observed; DuckDB-internal pressure can still trigger attempted eviction.
Exit0 means the diagnostic captured its result, not that history succeeded.
Owned child terminal/runtime observation complete/canonical stat signatures and
vendor/private attach unchanged/no hot/no image are reported true.

The saved v1.5.5 source adds a compatible precise mechanism: in
TemporaryFileHandle::TryGetBlockIndex, CreateFileIfNotExists precedes allocating
the new block index; that allocation reaches IncreaseSizeOnDisk's0B capacity
guard. Thus a read-only file-open failure can precede that guard. This explains
why0B did not suppress the observed attempt, without proving which query
operator requested it.

Minimal-correction decision remains no product patch on this evidence alone.
Changing temp configuration or moving a guard earlier would merely replace
EROFS with a different refusal; it would not supply the requested history.
No actual operator or matching failing owned model supports selecting another
SQL or declaring a new reader necessary. Any later bounded implementation must
demonstrate the exact existing event/snapshot semantics and resource/latency
constraints, then separately earn actual-host acceptance. Current source stays
9cdf; original CB2 evidence, model and d8a STOP receipt remain immutable.

## Root-approved implementation after DX1/PM1

Root subsequently selected the existing-buffer two-stage materialization design
and explicitly authorized its implementation inside the original deadline.
This supersedes the preceding no-patch decision; historical evidence is retained.
PM1's sole metadata-only EXPLAIN reports SEMI HASH_JOIN, a17-column left probe
SEQ_SCAN estimated33402996 rows and right HASH_GROUP_BY/MAX selection. One
non-allowlisted operator remains UNKNOWN. These are estimates, not a profile
or certificate of the exact failing C++ operator. No additional EXPLAIN requested.
Plan: docs/superpowers/plans/2026-10-25-bounded-tail-materialization.md.

Planner/Implementer: buffer.py tail now selects keys with the unchanged rank/
max semantics, then fetches all17 columns in batches of128 keys under its existing
lock and one transaction. Two txid_current() probes distinguish autocommit from
an existing transaction, verified on real DuckDB1.5.5. Only owned transactions
are ended; caller-owned uncommitted data remains visible and caller-owned.
Each batch must match its selected keys exactly, including cardinality; missing
or duplicate rows raise. Original receive/data/asof predicates, STATUS, ordering,
forward SQL, zero/negative limits, unknown errors and decoding stay intact.
Default full10000 now uses79 payload/84 total statements in autocommit; this is
an explicit latency/index-scan tradeoff, not a claim of bounded overall RSS.
ADR0034 records the durable single-snapshot change from the earlier one-statement
implementation. Product settings128MiB/threads1/0B/RO remain unchanged.

Quant/Verifier: the attempted on-disk wide model hit its real post-batch budget
guard: total150323016B, new failed DB81014784B/5000 rows, old model69218304B.
This is an author construction failure, not query RED. Root narrowly accepted
that frozen raw retained total plus2MiB small metadata; no compression/deletion,
no further DB fill/checkpoint or new large DB. Exact failed-DB SHA256
2746b32461758e345fbe0ec486890f7152ad7ae32795e9f90597327c27f9511d.

A generated16000-row view writes no wide data: all17 columns, varying dual time,
valid candle JSON with8KiB padding or STATUS with8KiB note. Key-only selection
returns10000. The frozen9cdf whole-width query and original replay genuinely
refuse at declared test16MiB (wide-red.txt); the first batch implementation also
refuses16MiB because one generated vector needs8MiB. At still-stricter-than-product
32MiB/0B, the frozen old SQL still refuses while new replay returns exact10000,
all fields/order equal the independent complete-row oracle. No POSIX/7GB failure
reproduction is claimed. This discriminator is broader than the original narrow
PASS model and isolates a bounded-materialization improvement in owned data.

Initial semantic tests RED5/2pass preceded the helper. Final focused12pass5.71s
checks batch size/query count, all fields, concurrent writer DELETE/UPDATE between
batches, lock ownership, caller transactions, missing/duplicate rows, genuine
SQL error behavior, resource refusal and unchanged forward behavior. One test
incorrectly assumed DuckDB1.5.5 catalog errors abort caller transactions; actual
1.5.5 state remains usable and test expectation was corrected. Early parser,
16MiB candidate and test expectation failures remain retained.

Read-only production128MiB partial-model differential matches4905 complete raw
17-column rows with the frozen SQL, SHA256
6778e6e9227f89af5422f6f66ec2f593e42138894c521d5dd41e69b8dc753667;
all decode and the DB hash remains unchanged. First affected check had two child
import failures from another worktree's inherited PYTHONPATH and shared Windows
pytest cleanup denial. Corrected process-local source binding and fresh pytest
temporary base produce232pass/2explicit Windows native-fsync skips/6existing
warnings62.25s, exit0 (batch-affected-final.txt), across new batching, existing
tail/buffer/lookup/history/archive+hot tests. Initial failed runs remain retained.
Changed-file Ruff/format/whitespace pass. No full repository/old CI/native query.
Source freezes for one independent delta review; no native recovery claim yet.
