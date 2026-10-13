# Isolated advisory-service CI integration

Goal: make the approved Workers Task2 isolated-service CI obligation executable
in the single milestone PR175, without enlarging the core dependency closure.
Current authoritative gap: only ci.yml/security.yml exist; release_gate certifies
the core checkout but never runs services/research_agent tests. A green core CI
therefore cannot establish service compatibility. Native owned PG proof remains
separate; do not replace that requirement with an offline job.

Scope: add one Linux CPython3.12 job to .github/workflows/ci.yml, include it in
the required python aggregation, and document its precise evidence scope in
services/research_agent/README.md and iteration0038. No service/core code, schema,
protocol, lock, provider, model, source, host or trading behavior changes.

Reuse: existing81-package requirements.linux-cp312.lock and
tools/research_service_gate.py --offline. Ubuntu24.04x86_64 runner, fresh private
RUNNER_TEMP venv, --require-hashes/--only-binary=:all: install from the admitted
lock. No unpinned build tool/editable package install; gate and pytest config
already insert explicit source paths. No global environment/package changes,
Docker, PostgreSQL daemon, AWS, secrets, paid calls or production operation.

- [x] Inspect actual workflow/release-gate/service lock and confirm missing
  independent coverage. Record terminal CI38328514078 (context fixed, frontend
  date assertions/bundle stale) before changes; never rerun that old head.
- [x] Add separate research_service job: runner3.12/private venv/hash-lock,
  existing offline gate, owned evidence upload with always(). Add that job to
  python.needs and its required-success tuple; no existing gate/selector weakened.
- [x] Validate YAML contexts and exact preserved old jobs; one bounded read-only
  CI wiring review. No third structural review of completed service architecture.
- [ ] Push tested integration to PR175, inspect the exact new-head service job
  and selected core gates. Remote logs/JUnit/license/lock/schema/protocol evidence
  prove only OFFLINE_SCRIPTED_ONLY compatibility. Actual SQL/model/aggregate
  containment/host deployment and final operator acceptance remain open.
- [ ] Mirror actual outcomes and retain RED/GREEN raw evidence. No PR merge,
  release, source flag change or full-goal completion from this CI job.

Acceptance: required CI/python cannot succeed if research_service fails/skips;
its own venv/81 hash-locked versions and scope-labelled service-gate receipt are
retained. Real owned PostgreSQL/native/Worker/model gates retain their independent
acceptance semantics. Unknown CI outcomes remain pending, not fixture success.
