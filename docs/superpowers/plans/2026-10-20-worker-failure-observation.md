# Worker failure observation implementation plan

> For agentic workers: execute inline with TDD and fresh verification; root owns
> independent review, commit and PR gates. Do not spawn additional implementers.

Goal: issue [202](https://github.com/ZP151/quantmesh/issues/202), under parent198, retains a bounded,
sanitized first escaping Worker failure for source-level operator diagnosis.
The historical exit3 category is irrecoverable; this is not its causal fix or a
90-second recovery fix. Start: 2026-10-20 14:12:48 UTC; budget: 1–3 hours.

Architecture: add private scalar-only per-slot observation next to the existing
worker execution ContextVars. Existing calls are observed without added store or
Engine operations. Freeze the first escaping failure across slots; preserve an
active primary separately from a later cleanup failure. Bootstrap reconstructs
one bounded stderr JSON record from typed allowlisted fields; ordinary stop is
silent. Current production stderr=null remains unchanged.

Tech: Python3.12, standard library, existing pytest/WSL runtime; no dependencies.
Spec: root's bounded R leaf handoff plus the prior OBSERVATION-PROPOSAL.md;
durable scope and acceptance are frozen in the iteration named below.

## Scope and interfaces

Only four source files are owned:

- `src/quantmesh/research/worker_execution.py`: private diagnostic scope,
  scalar frozen failure/stage/slot/observation records, safe operation observer.
- `src/quantmesh/research/job_runner.py`: existing operation stage markers,
  validated opaque job/attempt binding, primary-versus-cleanup snapshot.
- `src/quantmesh/research/worker_daemon.py`: slot admission/start/join evidence,
  first-wins shared capture, optional private observation on WorkerDaemonError.
- `services/research_agent/src/qm_research_agent/worker_runtime.py`: bounded,
  allowlisted JSON rendering; unchanged worker_daemon_failed string and exit3.

Tests: new `tests/test_worker_failure_observation.py` exercises real daemon,
runner and stop token with fake child/store/numerical seams; service renderer
cases in the same file use the actual bootstrap main with config/runtime seams.
Existing tests may be updated only if necessary for these owned interfaces.

Private interfaces: `_observe_worker_call(stage, deferred_call)` returns
the exact call result or bare-reraises its original exception; observation errors
are suppressed. `_worker_diagnostic_scope(slot_state)` resets its ContextVar.
`_bind_worker_job(job)` accepts validated32-hex ID/positive bounded attempt only.
`_worker_unwinding()` captures current exception category before cleanup.
The daemon-local `capture(slot)` freezes `_WorkerSlotDiagnostics.escaping()`
after the original failed.set then stop_event.set; it never delays that order.
`WorkerDaemonError.observation` contains immutable scalar snapshots only.

## Invariants and review focus

- Preserve all return/raise behavior, exception chaining, cleanup ordering,
  first-cause stop, lease/timeout/heartbeat/handoff predicates and hashes/protocol.
- Never retain an exception instance, message, cause, traceback, locals, paths,
  configuration, provider payload or arbitrary class name in observation state.
- Explicit unknown-error category; fixed stages/outcomes; integers and validated
  opaque IDs only. Fixed stage cells and two slots bound memory and stderr16KiB.
- Handled failures/new attempts cannot contaminate subsequent escaping failures.
- Cleanup secondary never replaces an escaping primary. Concurrent slot failures
  freeze one first capture. Observation and renderer failures are non-authoritative.
- No unit change, SSH, remote action, new pair/job/provider, credentials,
  deployment, commit or push. Root owns separate sink proposal and broad gates.

## Tasks

- [x] Write real-chain RED tests for post-receipt second-validation failure and
  primary-plus-cleanup preservation, asserting fixed stage/category/monotonic,
  synthetic attempt metadata and unchanged shared stop/cleanup/no-handoff.
- [x] Export the Windows worktree sources/tests to local scratch (Windows Git
  archive for base plus explicitly copied changed files); run existing WSL Python
  with scratch src/tests/service PYTHONPATH. Preserve expected pytest assertion
  failures under `output/0038-worker-failure-observation/red.txt` before source.
- [x] Implement the four owned source differences, smallest change matching RED.
- [x] Extend and observe targeted RED/GREEN for ten mechanism/control outcomes,
  sibling next admission, handled-failure reset, concurrency, thread failures,
  ordinary-stop silence, telemetry errors and sentinel redaction/bounded renderer.
- [x] Run focused new tests plus existing daemon/controlled-stop/runtime affected
  checks (not the original123 suite); record commands, counts and limitations.
- [x] Run changed-source/test Ruff/format and whitespace checks. Stop at reviewable
  focused GREEN. Full repository lint/tests and source pins are root's normal
  coherent-commit/final-PR gates, not duplicated during development.
- [x] Update `docs/iterations/0038-worker-failure-observation.md` with Planner,
  Quant Researcher, Implementer, Verifier outputs and actual phase timestamps.
  Root adds independent Reviewer output, capped at two rounds, before integration.

Execution rulings: no new private capture API was needed; capture is local to
one daemon and its lock. `thread_join` exceptions retain their original type and
propagation and are not converted into WorkerDaemonError for observation.
Transient store failure handling is unchanged. No extra lease-time sampling was
added. These are narrower implementations of the approved observation leaf.

Verification command (from the exported scratch root, with existing runtime):
`PYTHONPATH=<scratch>/src:<scratch>/tests:<scratch>/services/research_agent/src
/var/tmp/quantmesh-backup-final-xvcv1u9k/venv/bin/python -m pytest -q
tests/test_worker_failure_observation.py`.

Acceptance: expected RED observed; focused GREEN; same ten behavioral outcomes;
safe bounded stderr capture; no operational visibility/90-second claim. One
reviewable diff/checkpoint for issue202, with no local commit until root authorizes.

## Review correction: argument evaluation belongs to its operation

The user's independent AI-assisted review identifies eager argument evaluation
before the observation boundary (human review remains incomplete). Reproduce
through the real daemon/runner with job serialization and claim-clock failures;
retain canonical serialization as a control. Defer each already observed call's
callable resolution and argument evaluation inside a synchronous zero-argument
callable. Preserve evaluation order, exactly-once invocation, all execution
predicates and exception identity; no new operation, stage or public API.

- [x] Capture actual failing regression before source edits (2failed/1controlpass).
- [x] Correct only existing observation call boundaries; verify unwrapped call
      ASTs remain identical and failures now identify the intended fixed stage.
- [x] Run focused affected checks (85passed), full Ruff/changed format/whitespace.
- [x] Independent round2 READY: P2 resolved, five frozen hashes match, all56
      deferred expressions preserve the original unwrapped operations/control flow.
- [x] Prepare ordinary follow-up commit/push; normal new-head CI remains a merge
      gate. Record its new head and superseded old-head CI in the root handoff.
- [x] Record explicit user fact: AI-assisted review only; human review incomplete.

## CI integration correction — root-checkout service import

Main workbench's bounded2026-10-21 instruction authorizes only this test-local
integration repair, not a third structural/source change. Actual fab35ac release
CI39444763986 failed7observation bootstrap/renderer cases on missing
qm_research_agent after5446passes. Existing root pytest config provides src and
repo root, while the independent service gate explicitly supplies its own src.
Earlier local affected commands inherited service src and masked this boundary.

Exclusive files: tests/test_worker_failure_observation.py and this plan/own
iteration. Four product source files must remain byte-identical to fab35ac;
no dependency install, assertion weakening, product import path, workflow,
pyproject, broad local suite, service/remote action or merge is in scope.

- [x] Preserve actual failed CI log and reproduce the7import failures from
      checkout root with PYTHONPATH unset, using the existing local Linux runtime.
- [x] Add one function-scoped monkeypatch.syspath_prepend service-source fixture,
      requested only by the five test functions/seven parameterized cases.
      Assert the imported Worker bootstrap file is the checkout's actual service
      source. Existing test bodies/assertions remain unchanged.
- [x] Run the affected root tests with the same import environment, no inherited
      service path, and record loaded module/source pins. Run relevant targeted
      daemon/stop tests and static/whitespace checks; no full-suite replay.
- [ ] Verify original assertions and all four source bytes unchanged, update
      tracked evidence, commit/push one follow-up head to the existing PR, and
      hand the sole normal new-head CI run to the unique release owner.

Commit checkpoint: all original test function bodies/assertions and the complete
bootstrap helper AST match fab35ac; four product file bytes match exactly.
Final root targeted GREEN is54passed/1existing warning/17.13s with PYTHONPATH
unset; full Ruff, changed-file format and whitespace pass. First format refusal
was only the new fixture comparison layout and is retained separately; final
exact-file GREEN follows formatting. Independent limited CI integration review
READY checks the final hashes and evidence without rerunning tests. Commit/push
and new-head normal CI/human hold remain the root/release handoff boundary.

This test import correction does not satisfy the independent human review or
remove the named203/204 no-merge hold. Runtime sink/90s/live gates remain open.
