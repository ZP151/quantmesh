# Linux numerical Worker implementation plan

> For agentic workers: use executing-plans inline, TDD, one bounded fresh Spec/Standards reviewer and verification-before-completion. Steps below govern separate coherent checkpoints; no image/native execution is authorized by this plan alone.

**Goal:** Run the unchanged pinned numerical Worker on Linux with actual immutable-image runtime identity and measured two-job recovery.

**Architecture:** A construction-only WorkerRunner context preserves the public four-argument function. A pinned glibc image holds the unchanged81-wheel closure and trusted source. Read-only manifest/inventory validation supplies actual container fingerprints; existing OCI ownership, store fences and report mathematics remain authoritative.

**Tech stack:** Python standard library, existing Docker/cgroup boundary, frozen Linuxcp312 wheels. No new package, lock, environment or daemon.

**Spec:** Existing `2026-10-13-linux-worker-containment.md` Task2, issue#172, the accepted immutable proposal archive SHA256 `8770d945f510aa1854f07d612d7bfb010d4ff81896d1680e3aa72e973d228a01`, and root-task2-interface-freeze.json recorded2026-10-13. Inspected implementation base042fb0b491c13f4535bddbb61290b191d29b1790.

## Global constraints

Preserve run_next_job(store,owner,inputs_root,artifacts_root), nine JobStore methods,
schema/protocol/report envelope, CostModel/WalkForward, request/dataset/export/engine
pins, Windows Job Object ownership, suspended go gate and publication fences.
No edits to jobs/store/artifacts/baselines/reports/registry/linux_owned/bootstrap,
locks/API/service/SDK/CI/ACTIVE/shared iteration. Source changes outside these
authorized leaf paths need concrete dependency/RED/root decision.

DefaultLinux without admission/profile refuses. Context must be construction-only
private ContextVar set/reset/finally, never env/DTO/SDK/global setter. Actual Worker
poll/pulse/close differs from Docker CLI status. Pulse1s follows live-fence check;
heartbeat15s/lease60s/global2 remain, with no background pulse keeper.
RO bundle/RW output never overlap, snapshot256MiB, output16MiB, stdinDEVNULL;
all Python launch paths use -B/PYTHONDONTWRITEBYTECODE=1.

Current permission: source and small focused RED/GREEN on existing owned checkout/
read-only81 environment. Total new source/fixtures/evidence<=10MB; inspect before/
after each test. No clone/env/download/layer/wheel/pull/build/container/native/
bulk pytest/global scan or cleanup. Original5GB whole-C attribution gate and disk
question remain pending. Use a718 branch codex/0038-linux-worker-jobs; root owns
integration/current exactCI and final PR. Never use mocked qualification to close172.

## Review focus

1. Missing.git must not cause a fabricated HEAD or host runtime substitution.
2. Pinned metadata alone is insufficient: actual source/dependency/Python/library
   files and complete executable inventory must match, with no extra pyc/shadows.
3. Child receipt owner/attempt/runtime and bounded contained regular bytes must
   agree before publication; cancellation/stale leases retain store authority.
4. OCI controller and receipt status must report actual cgroup/Worker exit; CLI0
   and saved qualified booleans grant no authority.
5. Windows launch must retain suspended-before-assignment/go, ownership and clean
   environment while gaining -B; four-argument callers remain compatible.

## Checkpoint1: Read-only runtime identity and runner verification boundary

**Files:** new src/quantmesh/research/worker_build.py, tests/test_worker_build.py;
bounded job_runner.py fingerprint/owned-child/receipt guards, focused runner tests,
this plan and runbook evidence. No Linux activation, image producer or stubs.

**Interfaces:** measure_worker_runtime(manifest_path,*,manifest_sha256)->existing
five-field runtime dict. runtime_fingerprint optional explicit manifest binding
delegates there; no-argument host path stays. Common owned child poll/pulse/close
uses actual Popen on Windows. Public run_next_job signature unchanged.

- [x] RED: absent/mismatched/escaping/duplicate/incomplete manifest or inventory,
  modified source/RECORD/Python/library bytes, wrong81 lock/distributions,
  executable shadow/pyc/unadmitted symlink and injected saved runtime refuse.
- [x] Implement bounded strict JSON/path/byte inventory and actual in-process
  fingerprint measurement without Git. Source commit is returned only after
  externally SHA-bound manifest and actual source inventory verification.
- [x] RED/GREEN existing runtime shape/source/dependency distinction and no-Git
  branch; preserve host behavior. Test uses small synthetic RO fixtures, with
  measured metadata bindings; no new environment or image certificate.
- [x] RED/GREEN -B/common actual-child poll and
  contained bounded receipt owner/attempt checks; no numerical or store changes.
  Windows suspended-launch ownership tests remain skipped on WSL; native Windows
  evidence has not been renewed by this checkpoint.
- [x] Fresh bounded Spec/Standards review (one reviewer, at most two rounds),
  focused checks and source/fixture/evidence byte accounting; commit/push own
  coherent checkpoint. No native/fullTask2 claim.

**Review stop, October13:** final focused checks pass40/skip4/deselect17, but
round2 retains a P2: loaded dependency modules can come from external shadow
paths while admitted distribution metadata/RECORD stays inside the prefix.
QuantMesh origins and distribution records alone cannot prove the actual loaded
dependency code. The two-round review budget is exhausted. Stop patching and
return this uncommitted checkpoint to Planner/root for scope reduction; no
commit/push or runtime certificate. Earlier review findings and corrected RED
fixtures remain retained in the ignored software-checkpoint evidence.

**Planner/root corrective resolution, October13:** the complete Task2 scope
remains required. Root took over only the residual loaded-code P2 rather than
restarting whole architecture reviews. Five external-module shapes produced
RED5; measured source-main and out-of-venv base-stdlib cases each produced RED1.
Every active non-QuantMesh file/spec now binds to the admitted byte inventory,
and package paths to real contained inventory roots; distribution RECORDs still
bind to the venv prefix. Unmeasured inline/stdin main code refuses by design;
the future image uses a trusted baked file entry, while default host behavior
remains unchanged. Specific corrective review is clear of P1/P2. Final focused
checks pass49/skip4/deselect17 in3.62s; separate actual Windows Job Object,
memory/affinity and setup-failure ownership checks pass5/skip0 in5.03s.
Ruff/format/diff pass. The initial correction's undefined-root implementation
failure is retained, not relabeled as a harness failure. Commit/integration of
this coherent software checkpoint does not qualify an image or activate Linux.

Ruling: implement this independently verifiable checkpoint before the image-bound
construction/deployment loop. Full image admission needs actual notices/ELF/probe
bytes unavailable under the current materialization ban. Do not ship saved-bool
activation, fake image proof or unverified producer/qualifier stubs to appear done.

## Checkpoint2: Construction context and complete numerical image tooling

**Files:** new worker_execution.py; job_runner private Linux path; fixed
deploy/research_worker worker_entry/Dockerfile/prepare/admission source; dedicated
tests and opt-in tools/qualify_linux_worker_jobs.py. These are later implementations,
not placeholders in checkpoint1. Root may continue source-only work after the
first checkpoint when the producer interfaces can be independently tested.

- [ ] Add validated immutable image admission and WorkerRunner construction-only
  private ContextVar. Independent host bindings include Engine/Image/config,
  manifest/inventory/source/81-lock/controller/entry and actual probe hashes;
  no final-image-ID/self-hash cycle. Profile/image changes refuse.
- [ ] Separate RO job/runtime/snapshot bundle and RW output, fixed trusted
  venv Python -B -I entry (DEVNULL), BLAS/OMP1 before imports. LinuxOwnedProcess
  supplies actual poll/pulse/close/cgroup status, not transport Popen.
- [ ] Add live-fence1s pulse and existing15s store heartbeat, parent actual
  runtime/owner/attempt/status/cgroup validation and unchanged publication fences.
- [ ] Implement finite Git/blob/lock/wheel context producer and offline full-base
  retention Dockerfile. No borrowed env repack/cleaning; no new dependencies.
  Preserve full GNU/pip/CPython/81-wheel notices and nine unresolved SPDX rows as
  explicit actual-notice gates, not scanner metadata green certificates.
- [ ] Implement independently tested opt-in qualifier/default refusal. Actual
  image/materialization/native execution still requires separate root permission.

## Later measured-image/native gates — all pending

Official candidate Linuxamd64 base manifest2ed6491b93cd49272ee6de2b5a38440c3448360322c089fc23e370722d74179d,
CPython3.12.15/glibc2.36, frozen81-wheel Linux lock07f4e7ec64805a375e0bdc707d0158fbdb08bd07d02aa569e2d119496b32592a.
Metadata compatibility does not prove actual ELF/notices/imports, new Image ID,
physical storage or numerical process containment. Task1 musl image is insufficient.

- [ ] Resolve source/image/storage authorization and9NULL actual Debian notice
  mappings; materialize only precisely owned resources, measure every selected
  executable/stdlib/library/notice byte, full ELF edges and container runtime.
- [ ] Same-image all3 baselines match direct engine exactly; repeated identical
  request/image canonical report/envelope bytes equal with separate receipts.
  Cross-env test-only complete projection excludes created_at/two runtime digests;
  exact nonfloats/counts/chronology/costs, floats rel1e-9/abs1e-12/None agreement.
  Positive fee1+halfspread2+slippage3bps and production canonical math unchanged.
- [ ] Actual two-job owner os._exit23, independent live sibling, real60s lease
  reclaim/attempt2 finish/report reopen<=90s from confirmed owner exit. No fake
  clock. Crash after upload/beforefinish yields one authoritative ref; cancelled/
  stale/reclaimed attempt cannot publish success. Actual cgroups/bytecode/inputs/
  credentials/network/exit/cleanup evidence, no global/prefix cleanup.
- [ ] Exact root integration/release CI, server-owned source/private PG/TLS/
  offhost report/user loop/provider/AWS acceptance remain separate later gates.

Whole Task2, issue172 and fullA remain open until all required measured evidence
agrees. The first software checkpoint is useful source admission progress, not a
replacement for the numerical Worker/user action or a server certificate.
