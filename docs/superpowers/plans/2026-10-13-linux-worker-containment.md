# Linux owned Worker containment implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Qualify a Linux process-tree boundary before enabling the existing pinned backtest Worker on the research server.

**Architecture:** Reuse the operator-managed Docker Engine's OCI/cgroup boundary for each trusted attempt. A fixed PID1 controller gates execution on verified resource limits and stops its namespace after losing controller pulses. The existing store, numerical engine, publication fences and Windows Job Object remain authoritative and unchanged.

**Tech Stack:** Python standard library, operator-provided Docker CLI/Engine, Linux cgroup v2; no new core package, daemon installation or commercial framework.

**Spec:** `docs/superpowers/specs/2026-10-12-research-foundation.md`, Worker Task1 of `2026-10-12-research-workers-workstation.md`, issue [#172](https://github.com/ZP151/quantmesh/issues/172).

Status: bounded implementation refinement of approved Option A. Task1 sourcef818a553c024169b2e3a61dcd6fa8941774cf43b is integrated by root as e743c93. Actual local Engine/image/controller admission and15/15 native Task1 checks pass, with48 focused regressions. Root verifies17 source paths/202 public phase hashes/301 archived members. Final storage envelope remains PENDING: native-run conservative547MB was inside5GB, but post-cleanup whole-volume delta12.93GB exceeds that gate; known logical retained files/cache are203MB, attribution unproven. Exact new images/containers are removed and unrelated baseline states preserved; no global prune. Do not repeat completed Task1 tests or call its stdlib fixture a numerical Worker image. Task2 numerical image/materialization stays gated on resource resolution and separate actual image/runtime qualification. Long-term resources remain AWS.

## Global constraints

- Preserve the nine-method JobStore, request/schema digests, numerical output and `run_next_job` interface.
- Initial concurrency 2 globally; default900 seconds/2048 MiB/1 CPU. Fractional CPU remains explicitly unsupported in this slice.
- Trusted allowlisted baseline only; this is not a sandbox for uploaded Python or generated code.
- No network, broker/model credentials, host HOME/config, Docker socket, public port, privileged container, global prune or other workload cleanup inside an attempt.
- No production/source/Windows/helper changes, paid resources, model calls, root lock changes, or automatic daemon/WSL configuration.
- Native qualification is separate from command/mocked tests. Missing Engine, unqualified image or ineffective memory/CPU/pids controls must fail before the baseline starts.
- A fixed local Engine and immutable image ID are construction-time operator configuration, never job-request fields. Remote daemon/context/environment redirection is refused.

## Review focus

1. Owner exits or its CLI connection hangs: a 5-second monotonic pulse deadline stops the namespace, including reparented descendants; unrelated sibling survives.
2. Rootless Engine silently ignores limit flags: verify actual cgroup values inside the container before releasing the workload.
3. Creation/start fails between receiving an ID and attaching: cleanup is bounded to the exact returned container ID and matching ownership nonce; never name-prefix/global cleanup.
4. Read-only inputs and clean environment: writable output cannot make original inputs mutable or leak host credentials/socket.
5. CLI exit is not workload success: observe the container's actual exit/OOM status, bounded output and digest-verified report before any later publication.

## Task1 — Owned OCI boundary and truthful qualification

Files: create `src/quantmesh/research/linux_owned.py`,
`src/quantmesh/research/linux_bootstrap.py`, `tests/test_linux_owned.py`,
`tools/qualify_linux_worker.py`, `docs/runbooks/linux-research-worker.md`.
Do not modify `job_runner.py` or advisory effect execution in Task1.

Interfaces:
- `LinuxExecutionProfile`: fixed local Engine endpoint, absolute Docker CLI,
  immutable image SHA256 ID, numeric non-root UID/GID, owned fixture root.
- `LinuxOwnedProcess(profile, command: list[str], budget: RunBudget,
  inputs: Path, output: Path)`: construction-time trusted command; expose
  `poll() -> int | None`, `pulse() -> None`, `close() -> None` and bounded
  sanitized execution evidence. No arbitrary command route or user configuration.
- `python tools/qualify_linux_worker.py --profile <owned-profile-json>
  --output <new-owned-directory>`: default checks prerequisites without modifying
  global state; native execution requires an explicit test-owned fixture mode.
  Nonzero until every required native check has real evidence.

- [ ] RED tests for missing Engine/immutable image, fractional CPU, unsafe mount
  paths/symlinks, inherited credentials/daemon redirection, ineffective cgroup
  values, creation/attach errors and cleanup ID/nonce mismatch.
  Run `python -m pytest tests/test_linux_owned.py -q` in the audited environment;
  retain assertions failing because the boundary does not yet exist.
- [ ] Implement argv-only bounded Docker invocation, `--pull=never`, no restart,
  network none, read-only root, drop all capabilities/no-new-privileges,
  pids128, bounded tmpfs, memory=memory-swap=budget MiB and exactly1 CPU.
  Only the provided existing input directory is mounted read-only and the
  unique attempt output writable. Do not create a missing host input mount.
- [ ] Implement the fixed PID1 bootstrap: verify actual memory.max,
  memory.swap.max, cpu.max and pids.max before sending ready; wait for go,
  receive monotonic1-second owner pulses, and exit after5 seconds without a
  pulse. Workload stdin is DEVNULL and cannot forge control pulses. Parent
  silence/EOF is failure. PID1 exits after child termination, closing its
  namespace. Do not assume Docker CLI death closes or kills the workload.
- [ ] GREEN the command/ownership tests and standalone controller tests. Test
  controller owner loss, failed admission, normal/nonzero workload and a
  reparented descendant without manufacturing cgroup evidence on Windows.
- [ ] Add native opt-in witnesses: aggregate descendant memory exhaustion,
  one-CPU quota, timeout, abrupt controller-owner loss, cancel/lease-loss close,
  an independent sibling surviving all cleanup, input immutability and absence
  of network/socket/credentials. Archive actual container status/cgroup limits,
  engine/kernel/image identity and elapsed times. No installed Engine means
  pending/nonzero qualification, never a green skipped native certificate.
- [ ] At the bounded Task1 boundary run focused checks/Ruff/diff and at most
  two fresh Spec/Standards rounds. Commit/push the coherent adapter with a
  handoff distinguishing unit/standalone/native evidence. Stop before Task2
  if image, Engine or crash/lifecycle evidence is unavailable.

## Task2 — Existing Worker integration after native admission

Files: minimal `src/quantmesh/research/job_runner.py` integration,
`tests/test_research_job_runner.py`, owned Linux image/build fixture under
`deploy/research_worker/`; coordinator owns locks/shared integration.

Interfaces: retain `run_next_job(store, owner, inputs_root, artifacts_root)`;
the deployment constructs a qualified local execution profile. No profile,
missing capability or changed identity retains explicit fail-closed behavior.
The precise configuration adapter/image build is frozen after Task1's measured
runtime, not inferred from a Windows lock or untested image tag.

- [ ] Pin the executing image/source/dependency/Python fingerprints, preserving
  the distinction from the controller's runtime and the two-file engine SHA.
  An image without `.git` needs measured source bytes and immutable build
  metadata; do not label a host fingerprint as container execution evidence.
- [ ] RED then GREEN the same pinned fixture's numerical equivalence, unchanged
  canonical envelope and receipt validation, cancellation/expired owner fences,
  no duplicate publication, platform refusal and Windows regression boundary.
- [ ] Run actual two-job owner-crash/reclaim≤90-second witness on native Linux;
  archive sibling survival and one authoritative report. No mocked platform
  branch, RLIMIT-only process or stored target substitutes for this proof.
- [ ] Run relevant slice gate and bounded review, then integrate through root.
  Final clean-checkout/core and separate-service certification, private host
  deployment and user submit/report/reload acceptance remain later gates.

## Reuse and qualification sources

Docker is an external operator-managed component behind a removable adapter;
no upstream implementation is copied. Docker runtime limits must be enabled
and checked, including rootless delegation: [resource constraints](https://docs.docker.com/engine/containers/resource_constraints/),
[run and mount options](https://docs.docker.com/reference/cli/docker/container/run/),
[rootless resource requirements](https://docs.docker.com/engine/security/rootless/tips/#limiting-resources).

## Completion boundary

Task1 software can be handed off with native qualification pending. Issue#172
and Linux/server delivery remain open until Task2 and native evidence pass.
Advisory provider effects need their own qualified aggregate Linux boundary and
approved egress/API metadata; this offline no-network Worker does not certify
real model calls. Formal168h is not required; A research host redundancy and
arbitrary Python uploads remain outside the approved scope.
