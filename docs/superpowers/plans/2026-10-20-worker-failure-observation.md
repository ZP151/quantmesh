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

Private interfaces: `_observe_worker_call(stage, call, *args, **kwargs)` returns
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
reviewable diff/checkpoint for issue198, with no local commit until root authorizes.
