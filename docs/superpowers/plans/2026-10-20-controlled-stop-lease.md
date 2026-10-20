# Controlled-stop owned lease handoff — issue198

Operator approved the exact design on2026-10-20: “同意上述受控停止设计”.
Implementation is inline with one fresh independent review; no repeated design
question. Base: origin/main a2d9598; branch codex/198-controlled-stop-lease.

User action: controlled restart during two fixture jobs. Source acceptance:
after successful owned Linux child cleanup, a first-cause SIGTERM/SIGINT permits
one fenced transaction to shorten that attempt's still-valid lease to now.
Production acceptance remains a later merged-source/image/native bounded pair
within the unchanged90-second target. Original failed jobs remain immutable.

Architecture: an internal stop token records the first cause and provides the
existing is_set/wait/set interface. Ordinary set means uncontrolled stop; the
bootstrap signal handler alone records SIGTERM/SIGINT. A reentrant condition
permits main-thread signal reentry without a nonreentrant signal-handler lock.
The runner cleans its returned owned Linux child before the optional store
extension. Constructor interruption, any attempt exception, cleanup failure,
unknown stop and ordinary Event retain leases. No compute, pulse, heartbeat or
publication begins after stop. An in-flight operation may finish as before.

Reuse SQLiteJobStore's existing _transaction/_fenced/_replace operations;
both PostgreSQL adapters inherit the identical extension. The frozen nine-method
JobStore protocol and digest stay unchanged; no API endpoint or schema change.
Only lease_expires_at changes, including leaving updated_at untouched. No new
packages or copied upstream source; no license or data-lineage change. Fixture
timings do not establish research validity, entitlement or trading authority.

- [x] Store RED/GREEN: add tests in tests/test_research_job_store.py for immediate
  same-ID reclaim, unchanged payload except expiry and all transactional fences.
  Add _expire_owned_lease to src/quantmesh/research/job_store.py only after RED.
- [x] Runner/stop RED/GREEN: add tests in tests/test_worker_controlled_stop.py using
  the existing real LinuxOwnedProcess/fake-Engine fixture; prove successful
  cleanup precedes handoff, failed cleanup/no child/attempt error preserve the
  lease, generic Event preserves old behavior, and stop causes remain first-wins.
  Implement src/quantmesh/research/worker_stop.py, worker_daemon.py,
  job_runner.py and services/research_agent/src/qm_research_agent/worker_runtime.py.
- [x] Bootstrap signal regression in services/research_agent/tests/test_worker_runtime.py:
  signal handler records the actual signal, failure-first cannot be upgraded.
- [x] Run WSL existing Python3.12 with absolute source/root/service PYTHONPATH:
  pytest -q tests/test_research_job_store.py tests/test_research_postgres_job_store.py
  tests/test_worker_execution.py tests/test_worker_daemon.py
  tests/test_worker_launch_deadline.py tests/test_worker_snapshot_serialization.py
  tests/test_worker_controlled_stop.py services/research_agent/tests/test_worker_runtime.py
  services/research_agent/tests/test_store.py. Preserve RED/GREEN logs
  under output/0038-controlled-stop/. PostgreSQL integration needs the existing
  owned fixture gate; never use the production database for testing.
- [x] Independent Reviewer checks complete diff and stop/cleanup/transaction
  invariants, max two rounds; third structural failure returns to Planner.
- [x] Verifier: full Ruff src/tests/tools plus service source/tests, changed-file
  formatting, git diff --check, submodule pins. Required full Linux/research
  service CI belongs to the release owner; do not repeat the previously stopped
  local full suite. Record actual counts, failures, warnings and unrun gates.
- [ ] Update docs/iterations/0038-controlled-stop-lease.md, ADR0026 and roadmap;
  commit, push and create a reviewable PR referencing issue198. New ClassB
  exact-diff independent human review and green CI precede merge/deployment.

Forbidden: changing job state/attempt/reports/accounting; lease extension,
changed60-second crash expiry, changed90-second target, inventory optimization
from unmerged PR199, operational release overrides, new production jobs,
provider calls, credentials, OpenD/Windows/tunnel/Demo or live-data changes.
