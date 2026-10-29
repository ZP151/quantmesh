# Readonly complete-row batch resource repair — issue249

Planner: https://github.com/ZP151/quantmesh/issues/249. One user action is saved
history inspection; one leaf outcome is complete selected records under the
unchanged resource contract. Plan: ../superpowers/plans/2026-10-29-readonly-batch-compat.md.
ACK2026-10-28T22:13:46Z (Oct29 06:13:46Singapore). No new Goal/environment.

Quant researcher: infrastructure materialization only, no changes to selected
keys, all17 fields, bothUTC/scope/kinds/tail10000, temporal ordering, fees/math,
rights/confidence or paper/live authority. Native source facts are111 first-batch
keys/EXECUTE/default-temp lexical text; exact throwing syscall remains unknown.

Investigator: small owned plans and pinned DuckDB1.5.5 sources show scalar OR
leaves residual membership above wide scan. Stored1776-row ZSTD model with111
selected64KiB records refuses current query's128MiB allocation under128MiB/0B;
point UNION returns exact111x17, SHA4dcc2629d2b68166ff70d38337ff2e64893a577d7c1a6091012e7efd9845add1.
Same logical bytes split into4 smaller vectors pass both forms; this is a precise
allocation-amplification discriminator, not proof of native spill/I/O cause.
Evidence: output/readonly-batch-compat-20261029/continuation-221346/.

Implementer RED: new tracked regression directly invoked on the retained owned
stored model, using the real current LiveBuffer._tail_rows and an independent
17-field Python formula oracle. Actual10-source-red.log fails at buffer1134
with OOM128MiB allocation before production changes; no fake connection/error.
Direct test invocation deliberately reuses fixture; it is not a pytest count or
a claim that fixture creation was rerun. All old failures and19:59seal retained.

Resource: current owned fixture allocation57,737,216B including failed DB/WALs;
64MiB fixture component remains fully charged. Single-vector build forecast
66,625,536B, four-vector66,375,680B were checked before writes. Complete96MiB
cohort/16MiB external-crash UNKNOWN retained, no physical continuous-peak claim.
No host/real archive/source deployment/provider action; previews remain untouched.

Reviewer/Verifier: pending actual source GREEN and bounded fresh review. Parent
Goal remains incomplete; original native I/O must be reassessed only after normal
merge by sole operator. No implementation or native success is claimed yet.

## Implementer and targeted verifier checkpoint

The only runtime delta constructs each <=128-key payload statement as UNION ALL
of independently key-filtered complete-row scans, with bound inclusive point
ranges and exact equality. One statement still handles each original batch;
three bound parameters per key replace the previous batch bounds plusOR list.
All other method statements, transactions, validation and final sorting remain.
This supersedes the historical RR1 predicate detail; no schema/config change.

11-source-green.log directly invokes the exact tracked regression on the retained
model and verifies every field/string against the independent Python oracle.
12-pytest-stored.log: actual portable fixture creation plus regression,1passed/
9.83s. Fixture compression is ZSTD only for the engineering model, file/parent/
privateHOME readonly onPOSIX and DB bytes unchanged after the read.
13-pytest-normal.log:1passed/9.21s; exact10000 full rows of10037 originals,79
statements (78x128 +16 keys), STATUS/nullable fields/order/twoUTC/scope preserved.
14-pytest-affected.log:19passed/2deselected/7.76s, covering complete rows, partial/
zero/negative tails, public decoding, duplicates/missing, concurrent snapshot,
owned/caller SQL failure and real resource refusal propagation, cancellation and
connection lock. Two old wide generated models explicitly were not rerun.

Each actual Linux run used the existing exact-native C extension, query128MiB/
one thread/temp0,512MiB/swap0/CPU50% user cgroup, independent35s timeout andCPU35s.
Targeted four-file Ruff and format pass. Current cumulative owned fixture/control
files59,109,376B; all previous failed/UNKNOWN holds persist. Independent source
review and final freeze remain pending. Local GREEN proves the engineering OOM
repair, not resolution of the native default-temp IOException or full Goal.

## Independent review and final author freeze

R1 fresh whole-leaf SOURCE review is READY with no actionable correctness,
architecture, licensing or trading-safety defect; all six manifest hashes match.
Runtime remains d2103a747f60a92d86ec12728f7231b1ad1c0e71175652ce9aea18e87a622662.
No runtime/test change follows R1. Only these own records add actual verification.
Review transcript: output/readonly-batch-compat-20261029/continuation-221346/review-r1.md.

Two isolated private-RAM mutants (omit payload field / skip selected key) each
fail the exact regression assertion; production file bytes stay unchanged.
AST comparison proves only the two payload-query construction assignments differ
from base0a; the remaining entire module AST, including transaction/key-selection/
completeness/sort/decoder/configuration, is identical.

R1's portable-fixture geometry caveat is closed: the exact immutable base0a
helper was compiled in private RAM and the already retained portable32-row-build
fixture really throws OOM in the same tracked regression. This is a later
differential control, not a claim that portable RED preceded implementation.
The first WSL Git attempt failed before any DB query because of the Windows
worktree metadata path; that failure remains. Windows exported immutable base
bytes (58525B/SHAedec4...a0), then the valid baseline control ran without writing
product source or creating another fixture.

R1's affected CI coverage caveat is also closed: active20MiB sparse model1pass/
22.36s and32MiB generated model1pass/24.63s, each once under the same35s/512MiB
external profile. Total targeted pytest evidence is23passing cases across the
five stated invocations; publisher must not inherit prior local deselections.
Current rooted files59,142,144B before final metadata; all old failed fixtures,
19:59seal and external-crash UNKNOWN/full96MiB hold remain retained.

The tested local commit and final exact file hashes/review receipts are handed
to root/sole publisher under continuation-221346/. Local hooks are bypassed only
after explicit targeted Ruff/format/whitespace checks; no broad-suite claim.
Sole publisher owns new exact-head applicable CI and normal merge; only then may
sole operator reaccept the original API, with fresh source pins (payload execute
now buffer.py1138), unchanged resource/safety contracts and normal reader/server
closure. Real default-temp IOException, archive latency, financial qualification
and the complete research Goal remain unresolved until their actual acceptance.

## Follow-up acquisition work bound — issue 251

Planner: [issue 251](https://github.com/ZP151/quantmesh/issues/251) follows the
merged issue-249 repair. The user action remains saved-history inspection. The
measurable engineering outcome is complete selected records with at most four
source-sized scans for 128 sparse keys in the new 1,048,576-row model, while a
stored wide readonly model still succeeds at 128 MiB/one thread/zero temp.
The tracked follow-up plan is
../superpowers/plans/2026-10-29-payload-selectivity.md. No native or financial
acceptance is inferred.

Quant researcher: preserve every selected key, all 17 fields, both inclusive
UTC endpoints, scope/kinds, NULL/STATUS handling, one snapshot, caller-owned
transactions, owned rollback, duplicate/missing refusal and final ordering.
The earlier per-key point UNION scanned 134,217,728 rows for 128 selected keys
over 1,048,576 generated rows. A 128-key join reduces that model's work but
fails a separate stored ZSTD readonly resource case. The chosen bound is 32
keys per exact VALUES join with an inclusive min/max range. A normal 10,000-row
tail uses 313 payload statements and five owned control/key statements (318
total); this is a measured statement budget, not a latency guarantee.

Implementer: frozen source commit 5de5fc09af685b19029c7c4fe74369fa870ee41f
on base 38c1fce4ecc6e0716a0769367decba707b67b2c9 changes only
`src/quantmesh/live/buffer.py` and five focused test files. The runtime SHA-256
is 1a6de08f5576b25c2decd8d88f9cd946ef66f727cab02135bb50fd15b76a7b57.
AST comparison isolates the acquisition loop bound/slice and query/parameter
assignments; key selection, transactions, validation, sorting and decoding
remain the merged implementation.

Verifier: the new real-engine scan-work test first failed at 134,217,728 >
4,194,304 scanned rows, then passed under the 32-key relation. A new stored
8,192-row/128-selected/64 KiB ZSTD model returned all 128 complete records;
14 new boundary cases also passed, for 16 new passing cases total. Three
isolated mutants were killed. The initial new fixture build timed out before
query entry and remains recorded; its optimized build and query passed. Six
changed Python files passed Ruff, format and whitespace checks. Full applicable
CI is the publisher's pending gate; prior suites were not rerun. Evidence and
sealed hashes are in `output/payload-acquisition-20261029-031519/`.

Reviewer: fresh R1 and final R2 independently marked the frozen whole source
READY with no actionable findings. Both matched the six source pins; there is
no third source review. Publisher owns exact-head CI and normal merge. Sole
Server owns the later original API, independent reference and normal-close
acceptance on merged source. Host, real archive, SDK, model and trading work
remain outside this leaf.
