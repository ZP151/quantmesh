# Worker failure observation — issue202

Issue: https://github.com/ZP151/quantmesh/issues/202
Parent recovery issue: https://github.com/ZP151/quantmesh/issues/198 (still open).
Plan: ../superpowers/plans/2026-10-20-worker-failure-observation.md
Branch: codex/198-worker-failure-observation from merged28221e1.

Planner: root authorized one observation-only leaf in an isolated worktree.
Operator action: inspect a future escaping Worker failure through captured
source stderr. Success metric: one bounded fixed stage/category/monotonic record
with validated attempt metadata, primary preservation and no changed Worker
execution behavior. Non-goals: historical category reconstruction, recovery
speed changes, retry, protocol/schema/hash changes, service unit/sink deployment,
new pair/jobs/provider, broader product work or commit/push before root review.

Quant researcher: operational synthetic fixture evidence only; no numerical
method, dataset, fee/cost/leakage assumptions, accounting or trading authority
change. AI remains advisory; paper/live defaults are unaffected.

Implementer: phase1 started2026-10-20 14:12:48UTC. Canonical guidance, exact
controlled-stop iteration and ADR0026 read; this tracked scope/plan precedes
source edits. Four source files and one focused test file are exclusively owned.
Prior diagnosis demonstrated historical category loss; no historical causal
claim is made. Production stderr=null remains an acknowledged sink gap.

Implementer checkpoint: the four source files add a private per-slot ContextVar,
immutable scalar snapshots, fixed stage/category allowlists and operation
observation. Runner cleanup observes the active unwind separately from secondary
cleanup failure. Daemon preserves original failed.set then stop_event.set before
first captured escaping failure selection; later sibling cleanup is secondary.
It does not assert which physical exception happened first. The monotonic field
is the captured boundary's observation time relative to this daemon start.
Job/attempt fields are32-lowercase-hex/positive bounded int orNone. One cell per
fixed stage and exactly two slots bound memory independently of poll count.

Bootstrap keeps existing worker_daemon_failed/exit3 and emits one additional
allowlisted JSON line only when a safe observation exists, bounded16KiB. No
observation keeps the original one-line stderr. Renderer/recording/diagnostic
Lock and ContextVar failures cannot replace original result/exception behavior.
No exception instance, message, cause, traceback, locals or raw payload is stored
in observation state. The original Python exception propagation is not changed.

Verifier: initial real daemon→runner RED observed2failed for missing observation,
then2passed. Renderer RED observed2failed/18passed, then20passed. A coordinated
later sibling-cleanup RED observed1failed/29passed, then30passed. Diagnostic
Lock/ContextVar fault-injection RED observed3failed/30passed before their guards.
The handled-stop-then-cleanup test passed when added: no source change was needed
for that control; the log named handled-cleanup-red is a passing control run.

Final focused affected run: **82passed**, one existing exchange_calendars/NumPy
deprecation warning,15.44seconds, existing WSL Python3.12.3. This includes33new
observation cases, existing daemon and controlled-stop tests, and service Worker
bootstrap tests. Ten mechanism/control outcomes remain unchanged: constructor,
poll, first/second exit validation, cleanup, persistent finish-store and next-loop
admission failures still fail the daemon; heartbeatFalse, finishFalse and handled
receiptValueError do not. Coordinated concurrent failures preserve first capture
and later sibling cleanup separately. Ordinary stop is silent. Thread-start stop
and join behavior is preserved; a thread-join exception keeps its original type.
The original123-test campaign and full repository suite were not repeated.

Changed four source files plus new test pass Ruff, formatter and git whitespace
checks. Nine uninitialized submodule pins remain unchanged. Source was exported
with Windows Git archive and changed files explicitly overlaid byte-for-byte;
WSL used explicit scratch src/tests/service paths and never parsed Windows .git.
Raw RED/GREEN evidence and exact commands are under local ignored
`output/0038-worker-failure-observation/`; source/test export pins and review
diff/checkpoint are included there for root's independent verification.

Phase evidence (UTC; overall budget10800seconds):

| Phase | Actual start | Actual end | Budget | Evidence |
| --- | --- | --- | --- | --- |
| Scope and tracked plan |14:12:48|14:14:48|900s|plan created before source/tests|
| Real-chain TDD and focused affected checks |14:14:48|14:26:37|7200s|red.txt,renderer-red.txt,sibling-cleanup-red.txt,telemetry-red.txt,focused-affected-green.txt|
| Freeze review package |14:26:37|14:28:24|2700s|byte-pins.json,source-review.diff,new-test-review.diff|

Reviewer: independent round1 READY, no blocking findings. Reviewer checked all
five frozen source/test SHA and Git blobs, WSL export equality, raw RED/GREEN,
original stop order, first capture/secondary cleanup, original exception/join
propagation and bounded allowlisted rendering. No test rerun or Engine/store
call was used for review. This automated review does not supply a human review.

Root's fresh full Ruff check (src/tests/tools plus the changed service module)
and whitespace check pass. A full local pytest check with explicit inherited
source/root/service PYTHONPATH and stop-at-first-failure is running at the draft
checkpoint. Broad test and normal PR/CI gates remain pending; the reviewed draft
commit/PR starts normal CI and does not certify a whole-repository pass. Class B
human implementation review remains a merge gate. No unit change, production
action, provider call or new pair/job occurred. The production null sink,
historical cause and90-second acceptance remain unresolved. The dedicated
observation issue202 separates this leaf from the still-open recovery issue198.

## PR204 review correction — argument evaluation

The user supplied an independent AI-assisted static review of exact156ad3a,
explicitly stating human review is incomplete and merge must remain held. P2:
argument evaluation before the observation wrapper may retain an earlier stage.
Real daemon/runner RED confirms job.model_dump_json failure was labelled deadline,
and claim-clock evaluation failure was labelled slot_admission. Actual result:
2failed/1passing canonical-serialization control, before source changes, retained
in argument-evaluation-red.txt.

The correction defers each existing observed operation's callable resolution and
arguments inside an immediately invoked zero-argument callable. The helper enters
the fixed stage before invoking that callable, then retains its original bare
raise and exact result. A mechanical AST comparison strips observation from
before/after and proves every underlying operation and control predicate equal:
55runner calls plus1daemon admission call. No new operation, stage, store/Engine
read, retry, lease/cleanup change or renderer change is introduced.

Final affected evidence is85passed/1existing warning/15.59s:36new observation cases
and49existing daemon/stop/service-bootstrap cases. New cases assert intended stage,
safe category/identity, cleanup, no handoff/publication, stopped state and redaction.
An initial affected launcher omitted tests/ from inherited PYTHONPATH and failed
conftest collection; that log is retained separately and is not a source-test
failure or pass. Corrected command supplies src/tests/root/service paths.
Full Ruff, changed format and whitespace pass; submodule pins remain unchanged.
argument-evaluation-byte-pins.json pins all five relevant source/test files and
the AST proof. Independent review round2 is READY with no remaining blocker;
the reviewer independently checked all56 deferred expressions, matching five
file hashes and actual RED/GREEN/static evidence without rerunning tests.
Normal new-head CI and genuine human review remain merge gates; old-head CI cannot
certify the corrected head. No local full-suite replay, merge or deployment.

## CI root-checkout import boundary — 2026-10-21

Planner: main workbench authorizes one bounded test/fixture import correction.
The exactfab35ac release CI39444763986 is FAILED:5446passed/7failed/143skipped,
all seven failures ModuleNotFoundError for qm_research_agent in this new root
test file. Full log is retained in output/0038-worker-failure-observation/
ci-import-integration/fab35ac-release-failed.log. It is real failure evidence,
not a green source checkpoint. Root pytest's src/root path does not include
the independently packaged service. Earlier local85pass command supplied the
service path explicitly and therefore did not verify root CI import behavior.

Implementer scope: only a test-local scoped source fixture for the affected
bootstrap/renderer functions, loading the actual checkout Worker service file.
No original test assertion, four product source byte, product runtime path,
CI workflow, dependency/environment, merge or remote host changes. This is a
separate finite CI integration repair, not another structural Worker patch.
Quant researcher: synthetic integration coverage only; no data/math/strategy,
cost/leakage or trading-authority changes. Named203/204 no-merge holds remain.

Verifier: actual root-CI-style RED is7failed/29passed/1existing warning/6.16s,
using checkout cwd and env -u PYTHONPATH with the existing WSL Python3.12.3/
pytest9.1.1. No dependency install or fresh environment. CI's normal Python3.13
gate remains responsible for that interpreter; local evidence does not claim
the complete CI gate. Root pyproject src/root paths are unchanged.

Implementer: one function-scoped worker_service_source fixture temporarily
prepends services/research_agent/src with monkeypatch and asserts the loaded
Worker runtime's __file__ resolves to that checkout's actual source. Only the
five bootstrap/renderer functions (seven parameterized cases) request it via
usefixtures. No autouse/global PYTHONPATH, package installation or runtime import
change. All original test function bodies/assertions and the bootstrap helper's
complete AST remain identical to fab35ac; the added assertion is source-origin
validation only. All four product source files remain byte-for-byte identical.

Final affected root command runs this36case file plus the existing18daemon/
controlled-stop cases with PYTHONPATH **unset**:54passed/1existing warning/17.13s.
Unlike the historical85affected run, this does not add the independently rooted
service test directory or inherit its src path. Real module path assertions run
in the seven corrected cases. Evidence and four-file/test SHA are in
ci-import-integration/affected-final-receipt.json and affected-final.txt.
Full Ruff(src/tests/tools plus the unchanged service runtime), changed-file
format and whitespace pass. An initial format refusal on the new fixture's
Path comparison layout is retained; the final exact test bytes were rerun after
formatting. No local full suite or old CI rerun.

Reviewer: independent limited CI import-integration verification READY. It
checked actual old CI/local RED/final54GREEN, final file/log hashes, fixture
scope, actual source-origin check, unchanged original bodies/helper AST and
four frozen product source bytes. Reviewer did not rerun tests and does not
re-certify observation behavior or supply human review. Root prepares one
follow-up commit/push; only its normal new-head CI is to be consumed by the
unique release owner. No merge, deploy, host action, new pair or R sink work.
