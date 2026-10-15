# Explicit Research Worker Runtime Bootstrap — Task 2

> Bounded continuation of the reviewed Task 1 daemon slice. Implement only this operator-started worker bootstrap; root owns shared iteration records and integration.

**Goal:** An operator can run the research worker module directly in safe preflight mode or explicitly with `--run`, which validates existing service and worker admission boundaries before opening PostgreSQL and starting the two-slot daemon. The service API and model/Agent runtime do not start.

**Architecture:** Add a strict private worker configuration loader and a separate `python -B -m qm_research_agent.worker_runtime` entry point. Reuse `qm_research_agent.runtime.load_runtime`, `LinuxExecutionProfile`, the registered fixture profile, `WorkerAdmissionPins`, `WorkerImageAdmission`, `LinuxWorkerExecution`, service `PostgresJobStore`, `WorkerRunner`, and `WorkerDaemon`. The worker module does not reuse `build_app`, core SQLite stores, receipts as authority, arbitrary profiles, or environment/ambient credential fallback.

**User action and outcome:** `python -B -m qm_research_agent.worker_runtime --config PRIVATE_CONFIG` completes sanitized source/runtime preflight without SQL, Engine, child, claim, model, provider, or listener activity. Adding `--run` performs ordered live admission, creates the service PostgreSQL store, and starts only the worker daemon.

## Global constraints

- Own only `services/research_agent/src/qm_research_agent/worker_runtime.py`, `services/research_agent/tests/test_worker_runtime.py`, `services/research_agent/deploy/quantmesh-research-worker.service`, and this plan. Do not change Task 1 files, service package metadata, shared root ledgers, `ACTIVE.md`, or iteration records.
- Worker JSON is bounded and read with the existing `runtime._read_private` no-follow reader and `runtime._unique_object`; schema version is exactly 1, duplicate keys and extra fields reject. All paths are absolute. The fixed profile has exactly eight fields: endpoint, docker CLI, image ID, UID, GID, fixture root, AppArmor profile, seccomp path. Pins are exactly the current 22 `WorkerAdmissionPins` fields.
- `profile.image_id == pins.image_id`; `pins.source_commit == service_runtime.actual_build`; source/dependency admission before and after worker live admission must return the same `(actual_build, lock_sha256)`. Reject all mismatches before PostgreSQL construction.
- Container UID/GID must match existing admission requirements (`10001`); the service unit runs as `ubuntu` without new groups or host policy changes. Existing `LinuxExecutionProfile` enforces its endpoint, path, AppArmor, and private seccomp rules. AppArmor and seccomp must both be configured; never admit the optional unconfined profile.
- The resolved fixture root must contain the service lake and artifact roots as distinct immediate child directories; the private snapshot must remain inside that fixture. Do not relax service-root, snapshot mode/ownership, or WorkerAdmission checks.
- The execution profile is exclusively `registered_fixture_profile()`; do not accept strategy, dataset, or execution policy from config or job request. WorkerAdmissionPins and live measurements remain authority; never infer identity from a receipt.
- Preflight parses strict worker config and calls existing `load_runtime` only. It prints sanitized actual build, paper=true, live=false, and worker activation pending. It performs no SQL, Engine command, child, claim, model/provider call, app construction, or listener startup.
- `--run` order: early SIGINT/SIGTERM Event handlers; stop check; strict worker config and `load_runtime` source admission; construct strict profile/pins/snapshot/registered-profile provider; stop check; `LinuxWorkerExecution.runtime_fingerprint()` live admission; stop check; repeat service source admission and require unchanged actual build/lock plus `pins.source_commit`; stop check; construct `qm_research_agent.store.PostgresJobStore` with schema `qm_research`; stop check; construct `WorkerRunner` and `WorkerDaemon`; run with the same Event. Check stop around each effect stage and restore prior signal handlers in `finally`.
- Only fixed sanitized categories may reach stderr. Never echo paths, DSNs, credentials, provider/Engine payloads, chained exceptions, or traceback. Do not add credential discovery, environment fallback, model keys, EffectLedger, model runner, or `build_app` calls.
- The unit is an uninstalled template only. It uses `User=ubuntu`, `Group=ubuntu`, literal approved ExecStart, WorkingDirectory and PYTHONPATH paths containing `REVIEWED_MERGED_SHA` placeholders, `PYTHONDONTWRITEBYTECODE=1` as required by existing runtime admission, `NoNewPrivileges=yes`, `KillMode=control-group`, `TimeoutStopSec=20`, `Restart=on-failure`, `RestartSec=5`, `StartLimitIntervalSec=60`, and `StartLimitBurst=3`. It grants no new groups or host permissions and contains no secrets. Source placeholders must be replaced only after a real reviewed merge; do not install or start it.
- No SSH, AWS, Windows, OCI launch, PostgreSQL connection/qualification, new dependency, model, secret discovery, Task 1 retest, PR, merge, or deployment. Report native PostgreSQL recovery and unit activation as remaining gates.

## Files and tests

- `services/research_agent/src/qm_research_agent/worker_runtime.py`: strict config model/loader, signal scope, ordered default preflight and explicit worker-only run, fixed error categories.
- `services/research_agent/tests/test_worker_runtime.py`: RED/GREEN for strict fields and duplicate keys, private-reader delegation, path/profile/pin identity, preflight no-effects, exact startup ordering and stop checks, source drift refusal before store, sanitized failures, and unit-template directives.
- `services/research_agent/deploy/quantmesh-research-worker.service`: inert systemd template only.
- `docs/superpowers/plans/2026-10-15-worker-runtime-bootstrap.md`: durable bounded plan and evidence checkboxes.

## Task steps

- [x] Write failing tests first with unique pytest basetemp; prove expected failures are assertions rather than collection/setup errors.
- [x] Implement strict worker JSON parsing with duplicate-key rejection, exact 22-field pins, exact eight-field profile, absolute paths, and private reader delegation.
- [x] Implement preflight default with existing `load_runtime`, sanitized output, and tests proving no execution effects.
- [x] Implement explicit `--run` using the prescribed ordered stop/admission/source/store/daemon stages; test order and failure boundaries with controlled fakes only.
- [x] Add the uninstalled unit template and assert its exact user, paths, restart throttling and shutdown controls.
- [x] Run new tests red/green, then one affected service test set; run Ruff, format, diff and submodule checks. Complete at most two Spec/Quality review rounds.
- [x] Commit and push the green checkpoint to `codex/0038-worker-daemon-loop`; do not PR, merge or deploy.
- [x] Save ignored `output/0038-worker-runtime-bootstrap/HANDOFF.md` and `checked-summary.json` with exact HEAD/files/commands/counts/startup order and remaining native PostgreSQL recovery/unit-activation gates.

## Acceptance and stop

Preflight is inert beyond existing source/dependency/private credential reads and reports paper mode, live disabled, and worker pending. Explicit run admits the same registered fixture profile through existing pinned Linux admission before service PostgreSQL construction, refuses any identity/source drift, then starts only the two-slot WorkerDaemon. Tests use fakes for effects and do not claim native OCI or PostgreSQL qualification. Stop after the reviewed commit is pushed and both ignored evidence files are saved.
