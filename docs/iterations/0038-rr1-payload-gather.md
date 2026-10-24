# RR1 sparse payload gather — issue218

Issue: https://github.com/ZP151/quantmesh/issues/218.

Planner: root explicitly authorizes a new60min payload-gather-only leaf after
the completed earlier leaf. ACK19:29:53Z,15min19:44:53Z,40min20:09:53Z,
hard20:29:53Z on2026-10-24UTC. Base actual merged9d8b33075e5f2a31d7e67b02f9715c83f19a9c0c,
treed71ded3dbf52d248b02d00ea4968fecd8e91aa36; branch codex/rr1-payload-gather.
Plan docs/superpowers/plans/2026-10-25-rr1-payload-gather.md. Original449 branch,
all prior failed/accepted software and native evidence remain unchanged.

Quant/Verifier: RR1 native regression failed again. The operator initially
misattributed trace1132 to key selection; author repeated that report before
checking, then immediately corrected it publicly and to root. Actual source
SHA7021d165 has key selection at1123 and full17-column batch execute at1132.
The actual failure is therefore in a complete-row batch, not key selection.
Which batch, how many keys and which C++ operator were not observed. OPEN of
archive-default temp is denied read-only; errno30 is public-text mapping, not
a directly captured C-layer attribute. No native retry or changed admission.

Investigation: LOCAL existing partial model metadata shows dense contiguous IN
can rewrite to a range, while sparse128-key IN uses HASH_JOIN. The original
generated-view discriminator selected contiguous keys; that did not establish
sparse-batch behavior. New legal-view control retains full17 fields,8KiB candle
JSON/STATUS notes and128 sparse keys. At16MiB both IN and OR refuse; avoiding
HASH_JOIN alone is not sufficient proof. At32MiB both pass. These controls and
their limitations are retained in old output/readonly-resource-diagnosis/
RR1-sparse-controls.json; no old large model rerun or source mutation.

Selected single direction is exact scalar equality disjunction plus min/max
range for pruning, with unchanged batch cardinality. A new LOCAL20MiB/threads1/
temp0 generated-view control shows old sparse IN HASH_JOIN refuses, whereas the
selected predicate has no HASH_JOIN and returns128 exact full17 rows. It does
not prove RR1's native C++ operator. Current physical archive/index/latency and
native resource effects remain acceptance limits. No parameter/config relaxation.
Evidence output/rr1-payload-gather/selected-direction-control.json.

Initial implementer scope: only _tail_rows payload gather and related tests/small
ADR. Key selection, lock, transaction ownership and snapshot,
forward/API, all filtering/STATUS/order/full fields stay frozen. A range bounds
the key interval, not bytes or guaranteed physical I/O; no RSS guarantee.

Budget: original retained150353373B and earlier2MiB metadata allowance stay in
force. New work is small metadata and in-memory generated rows only, no new
persistent DB/fill/delete/compression. Original research remains unfinished;
source rights/PIT/financial qualification/trading authority are unchanged.

## Implementer and verifier checkpoint

Actual TDD RED3/2pass (payload-red.txt) precedes source change: the current helper
fails at its complete-row execute under20MiB, while boundary tests also detect
the missing explicit bound predicate. Minimal source delta changes only that
batch predicate/parameters and adds explanatory comments. It retains128 exact
keys, projection/order, complete-key validation, key selection and all lock/
transaction/error handling. Parameter count becomes batch size+2, at most130.
The original first batching test now checks keys separately from these bounds.

Final focused18pass/1deselected2.99s, exit0 (payload-final-focused.txt): the old
dense wide model is explicitly not rerun. The new legal sparse view returns
10000 raw rows, all17 fields exactly equal an independent Python formula oracle,
including payload_json bytes/STATUS notes/dual timestamps/identity/null fields.
Local plan checks frozen sparse IN HASH_JOIN/real resource refusal versus the
new no-join predicate,79 payload/84 total SQL statements. Additional cases cover
zero/negative/one/partial final batch/public decoding and sparse concurrent
DELETE/UPDATE with owned or caller-owned transactions. Existing relevant small
tests cover missing/duplicate rows, lock, unknown/resource/SQL failures and
forward path. Source settings remain128MiB/threads1/0B/RO;20MiB is test-only.

LOCAL stored-model metadata additionally verifies PRIMARY KEY and original
indexes. Old sparse IN plan has a17-column scan below HASH_JOIN without a range;
the selected form has a17-column scan with a range filter and no hash join.
No payload SELECT or data/schema mutation in this metadata case; frozen model
SHA unchanged. This is not an actual-host batch plan or a C++ cause certificate.

RR1 sealed packet SHA3dc7c32ef5bd1fa9703674eab4a548669401002ba6329d3b34dcac4fa2ac6890,
manifest SHA94ce1e40bf1ef1a8712179994d6502223f9a250fc11924037cc19aa69dcdf64f;
all30 listed members verified in memory without extraction/host operations.
Corrected host carry197988352B/HWM9353 is separate from this software work.
Any future release/native probe needs a complete new forecast and root decision;
no inherited RR1 host window or automatic staging/activation follows a merge.

## Independent reviewer and final software handoff

One independent R1 delta review returns READY, Standards0/Spec0 findings, with
no correction or second round. Reviewed source commit
577b3b3318bd292974463ca769615a1d2457bc52/tree
0565854de7d2cd42824c9c2633cbc503fb641379; buffer SHA256
3cd08da4f04eb7bbbf2482a62e991de5641576a0b1f6ff10ae7975eeb4b5c690.
The reviewer independently verifies import identity, exact predicate equivalence,
unchanged other methods with explicit UTF-8 AST input, and runs the permitted
focused checks once:18passed/1deselected3.14s, exit0. Report
output/rr1-payload-gather/review-r1.md SHA256
628b13c5fa73dba208a03a359c919d9ffab5fc40edb732c76588b07533dff352;
raw review-r1-tests.log SHA256
ca4b556a3c4df0542dc90493f29941ddad6aaec2b1a2a3f10115dbd482532614.
Earlier author locale-default AST attempts falsely compared non-ASCII docstrings
and failed; they are not passing evidence or unrelated source changes.

Final handoff metadata is output/rr1-payload-gather/HANDOFF.json. This documentation
checkpoint leaves reviewed runtime/tests/ADR bytes unchanged. Local commit hooks
are bypassed after explicit scoped Ruff/format/whitespace checks; repository-wide
hooks and release acceptance are not claimed. Publisher owns new exact-head CI
and normal merge. Root owns any separate new native forecast/decision: corrected
host carry197988352B/HWM9353 and normal other headroom1241088B must include every
future source/helper/receipt. No inherited host window or automatic staging.

Software delta READY is not native PASS or completion of the original independent
research goal. No broader suite, old model acceptance, PR223/224 CI/browser,
provider/SDK/host action, Goal or automation change is performed by this leaf.
