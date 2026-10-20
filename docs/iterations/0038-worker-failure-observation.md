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
