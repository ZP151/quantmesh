# Linux research Worker containment — Task1

Issue [#172](https://github.com/ZP151/quantmesh/issues/172), approved
[plan](../superpowers/plans/2026-10-13-linux-worker-containment.md).
This removable adapter contains trusted offline attempts. `job_runner.py` still
refuses Linux execution; no report publication, baseline equivalence, lease
recovery, server readiness or advisory/model effects are certified here.

## Operator admission

Supply an already reviewed, immutable local Linux image ID and an already
running local Docker Engine with cgroup v2. The tool never starts an Engine,
installs anything, changes WSL, builds an image or pulls an image. Tags, remote
endpoints, ambient Docker contexts, host credentials and fractional CPU are
refused. Rootless limits must be delegated and effective; accepted CLI flags
alone are insufficient. See Docker's [resource constraints](https://docs.docker.com/engine/containers/resource_constraints/)
and [rootless requirements](https://docs.docker.com/engine/security/rootless/tips/#limiting-resources).

The reviewed image must contain `/usr/local/bin/python3` and the exact bytes of
`src/quantmesh/research/linux_bootstrap.py` at
`/opt/quantmesh/linux_bootstrap.py`. The host verifies the executing bootstrap's
SHA256 before `go`. Image source/dependency/Python provenance is a separate
operator review and Task2 gate; a matching controller file is insufficient to
qualify an entire research runtime. No image or digest is supplied by this slice.
Reject image-declared volumes and unexpected environment keys. Review the
image for baked credentials and network services. No user-uploaded Python is
admitted; trusted argv is construction-time configuration only.

Create a dedicated fixture root containing only test data and these new
attempt directories. Do not point it at HOME, production datasets or shared
artifacts. Existing inputs must be readable by the container UID/GID. Output
must be absent, its parent must exist, and mounts may not overlap. Symlinks,
junctions and mount-option delimiters are refused. On Linux the caller must
have permission to assign the configured UID/GID to output. Unqualified
rootless UID mappings may fail this admission; fix operator provisioning
separately, never relax permissions or install a daemon in this tool.

Profile JSON has exactly `endpoint`, `docker_cli`, `image_id`, `uid`, `gid`,
`fixture_root`. Paths are absolute. Allowed endpoints are
`unix:///var/run/docker.sock`, `unix:///run/user/<nonzero-uid>/docker.sock` and
`npipe:////./pipe/dockerDesktopLinuxEngine`. `docker_cli` is a trusted absolute
existing executable; `image_id` must be an actual `sha256:<64 lowercase hex>`
identity. UID/GID are numeric nonzero values. Profile/command never come from
job requests. No invented example digest represents a qualified image.

```text
python tools/qualify_linux_worker.py --profile <owned-profile.json> --output <new-directory>
python tools/qualify_linux_worker.py --profile <owned-profile.json> --output <new-directory-under-fixture-root> --native-fixtures
```

Default prerequisite-only checks always exit 2/pending. Native mode creates
only named test-owned attempts. Exit 0 requires every listed native check to
produce real passing evidence; missing Engine/image/permissions or incomplete
witnesses exit nonzero. `qualification.json` retains passed/failed checks,
actual limits, container exit/OOM status, elapsed times, Engine/kernel/image
identity and executing bootstrap SHA. No raw Docker stderr, credentials or
workload log text are printed in sanitized evidence. Workload stdout/stderr
remain in fixture directories; use only credential-free trusted fixtures.

## Lifetime and limits

An attempt has network none, read-only root/input, one unique writable output,
non-root UID/GID, all capabilities dropped, no-new-privileges, 128 processes,
one CPU and memory=memory-swap. `/tmp` is a 16 MiB noexec/nosuid tmpfs.
No Docker socket/HOME mount, port, restart policy or shared cleanup is used.
PID1 checks `memory.max`, `memory.swap.max`, `cpu.max`, `pids.max` itself before
ready. The owner verifies those values and the controller digest before go.
The child receives DEVNULL stdin and a minimal environment.

Call `pulse()` every second and `poll()` for actual container status. The
independent PID1 watchdog terminates after five seconds of owner silence;
EOF, invalid control, timeout, output overflow and child failure also fail.
PID1 exit closes the namespace including double-forked/reparented descendants.
Killing the Docker CLI is never treated as killing the container. `close()`
checks the exact full returned ID and random nonce before `rm --force`.
It never searches name prefixes or prunes containers. Missing identity or
nonce mismatch refuses cleanup. If creation loses its response before an ID
is returned, an unstarted residue can remain; operator inspection is required,
and no speculative/global cleanup is authorized. A failed cleanup closes the
attachment but retains retryable ID/nonce cleanup; call `close()` again after
the transient failure clears. Workload lifetime still has the PID1 deadline.
Each control write has a one-second deadline; a hung attachment is killed on
write failure without treating its CLI exit as workload success.

Output is an aggregate 16 MiB admission bound checked every 50 ms by PID1
and again by the host. It is an observed fail-closed bound, not a host filesystem
quota: burst writes can overshoot between samples. Symlink output fails.
Later report ingestion must independently verify contained paths, byte bounds,
digests and canonical report contents; Task1 never publishes child files.
Nonzero/OOM/timeout cannot be upgraded to success based on CLI exit alone.

Native fixtures cover normal/nonzero exit, aggregate descendant OOM, measured
one-CPU throttling, timeout, abrupt owner/CLI loss, cancellation/lease-loss
close, output overflow, detached descendants, input immutability, credential/
socket/network/capability isolation and an independent surviving sibling.
No Task2 two-job/reclaim/numerical-equivalence or paid model calls occur here.
Timeout and output witnesses inspect actual container exit before any host
rescue. The hung-attachment witness keeps stdin open, suspends only its owned
Docker CLI, stops pulses and requires actual PID1 exit near five seconds with
the sibling still alive. This witness requires a Linux/POSIX owner; Windows
native attempts remain nonzero/incomplete rather than skipping it to green.

## Evidence levels and current boundary

- Windows command tests mock the Docker control plane; they prove argv,
  admission, status interpretation and ID/nonce ownership decisions.
- Standalone WSL tests run the actual controller loop and process-group cleanup,
  with normal/nonzero/EOF/silence/timeout/output/reparented-child cases and a
  surviving sibling. They do not run PID1 in OCI or enforce actual cgroup limits.
- Native OCI qualification requires an admitted immutable image and an actual
  Engine run of every opt-in witness. Windows skips and mocked cgroup dictionaries
  cannot issue a native certificate. The bounded October13 witness below qualifies
  the local standard-library fixture only.

Coordinator mirrors exact SHA, tests, logs, review and remaining gates into
iteration0038. Keep issue#172 open until Task2/native/server acceptance. Preserve
the Windows Job Object, store/schema and report mathematics unchanged.

## October13 native Task1 checkpoint

Root reviewed the immutable source/metadata/license/context packet before the
one-time local materialization authorized by the user. Long-term services remain
AWS. `tools/linux_worker_fixture/` preserves the minimal pinned offline recipe,
selected binary hash inventory and upstream license notices. It installs no
packages, copies no research engine into the image and changes no core locks.
PID1, fixture/descendant/owner Python launches use `-B`; the clean child environment
explicitly preserves `PYTHONDONTWRITEBYTECODE=1`.

Actual Docker29.6.2/Linux x86_64/cgroupv2 Engine ID was
`d619836c-83fd-4b61-bccd-28f15d06069f`, kernel6.6.87.2-microsoft-standard-WSL2.
The admitted derived image ID was
`sha256:968595795332a9424a6b47591e79ff594b3048cb3161801156a5c782833de167`,
distinct from config digest
`sha256:2bbe620f62bed9f37df4cc76f65105cfdbbe90eefa4c7cb5a964c2dcc424d250`.
Docker29's containerd store reports manifest-based IDs; config digests must not
be substituted for returned image IDs. Controller byte SHA256 was
`e05ce046cd800ab801e4ceafb352c02de20774dc2f9bf92dc77ed3688f6de740`.

Image admission checked all636 manifest file/link entries and26 ELF files,
dependency edges and license/controller bytes. Selected ordinary files totalled
25,495,714B; exported rootfs tar26,125,312B. Engine-reported image Size8,066,465B
has different semantics and is not called unpacked filesystem allocation.
Docker-created empty init-layer placeholders were accounted for separately.
Smoke imports, child bytecode policy and actual128MiB/swap0/oneCPU/pids128
admission passed before the full opt-in tool ran.

All15 required native witnesses passed, tool exit0/native_qualified=true,
56.9649563s overall observation including host envelope/checkpoint work. Actual
aggregate descendant OOM at96MiB produced OOMKilled=true/exit137. Four competing
CPU descendants used4.086467 CPU seconds over4.060530 wall seconds with41
throttle periods. Native timeout exited124 in2.329014s. SIGSTOP of only the owned
Docker attachment, with stdin retained and pulses withheld, produced actual
PID1 exit124 after5.657946s from last pulse; host removal was not the witness.
CLI EOF/abrupt owner exit23, cancellation, lease-loss, output overflow,
setsid/double-fork namespace closure, immutable input and network/socket/
credential/capability isolation passed while the independent sibling remained
running. The tool then closed that owned sibling in its finally block.

Raw evidence remains in the managed a718 worktree's ignored
`output/172-native-qualified-20261013/` plus its exact owned WSL fixture root;
the new immutable handoff identifies source/context seals, archive SHA256,
phase-by-phase disk/image/cache/artifact observations and cleanup references.
The initial missing-image pending result and intermediate admission diagnostics
remain retained; none were overwritten as a green result. Per-attempt evidence's
conservative `qualification=unqualified/native=false` fields mean the adapter
itself grants no certificate; actual qualification is the separately measured
tool envelope and admitted image, not constructor success.

The ceiling was5,000,000,000B newly introduced temporary total with at least
50,000,000,000B C free. The1GiB planning reservation was never reported as a
measurement. Default BuildKit cache is retained and budgeted when exact safe
per-build deletion cannot be proven; no global prune or unrelated resource
cleanup is allowed. Raw evidence/archive and owned clone are retained for root
review. During the native run the conservative introduced-total observation was
547,016,704B with102,358,667,264B C free. Both new image IDs were subsequently
removed without force, all known owned containers were absent, and baseline
container states were preserved. Twelve new cache records remain, with a
CLI-display upper bound of83,875,867B.

The post-cleanup conservative disk gate failed: C free was89,973,710,848B,
12,931,973,120B below the starting observation, while attributable owned files
and retained cache totalled203,031,020B. The additional whole-volume change has
no proven attribution. The free-floor gate still passed; the conservative
five-billion-byte total gate did not. Its failure and the initial digest-tag
cleanup diagnostic are retained. Further image materialization stopped; do not
describe final storage acceptance as green. Native15/15 is the measured local
Task1 qualification for the exact fixture. Task2 numerical Worker
integration/image, <=90s two-job recovery,
provider/service/server/AWS delivery and final release gates remain pending.

## October13 Task2 software checkpoint1

This is a reviewed software checkpoint, not an admitted execution image. The
second bounded review originally stopped with loaded external dependency code
unbound to the inventory. Planner/root reproduced five shadow variants and
fixed that exact P2; a specific corrective review also identified measured
source-entry and base-stdlib compatibility cases, which were reproduced and
corrected. The final corrective review has no actionable P1/P2. The original
review stop and every intermediate failure remain retained as historical evidence.

The [numerical Worker plan](../superpowers/plans/2026-10-13-linux-numerical-worker.md)
separates read-only byte admission from later image construction and Linux
activation. `worker_build.measure_worker_runtime` requires an independently
SHA256-bound manifest and inventory, the frozen81-package Linux lock, actual
Python/source/distribution/library/notice bytes and the unchanged five runtime
fields. It refuses undeclared files, bytecode, special files, source aliases,
out-of-prefix distribution records and loaded QuantMesh modules outside the
admitted source tree. All other loaded file/spec origins must be in the measured
inventory; package search paths must be real directories within admitted roots.
Measured base stdlib outside the venv prefix and measured file/module main entries
are supported. Unmeasured inline/stdin main code is not an admitted image entry.
Rejections expose only `worker build rejected`. No Git
checkout or saved runtime tuple substitutes for those byte checks.

The manifest SHA must come from a later independent immutable-image admission.
This helper verifies the declared closure; it does not establish complete ELF
edges, actual OS notice eligibility, image identity or numerical containment.
The source commit is externally pinned metadata returned after actual source
verification. No image admission or Linux execution profile is activated by
this checkpoint. Four-argument `run_next_job` callers and the default host
fingerprint remain compatible; Linux without crash-safe admission still refuses.

The existing runner now launches Python with `-B` and
`PYTHONDONTWRITEBYTECODE=1`, obtains exit status through the owned child's actual
`poll()`, and validates contained, bounded, unchanged regular result/receipt
files, canonical contents and owner/attempt/runtime identity before the existing
publication fences. Windows keeps its suspended launch, Job Object assignment
and go gate. Its pulse method is a no-op; no background pulse thread is added.

Focused RED/GREEN uses synthetic manifest fixtures and existing small receipt
fixtures on a read-only borrowed81-package Python3.12.3 environment. Only the
four changed source/test files are overlaid onto the prior owned Task1 clone;
this is not a clean whole-integration checkout or a CPython3.12.15 image witness.
Final focused WSL checks pass49 with4 Windows-only skips and17 deselections in
3.62s. A separate actual Windows ownership/memory/affinity run passes5 with
zero skips in5.03s on the existing Python3.13.9 host environment; this is not an
81-package Linux or full Windows runtime admission. Initial harness errors and
corrected failing test attempts remain retained. The final software resource
observation is below10MB introduced logical bytes and at least50GB free C; it
does not waive the prior whole-C5GB attribution gate.

Construction-only ContextVar wiring, complete image producer/admission tooling,
actual image/ELF/notices, same-image numerical equality and <=90s two-job lease
recovery remain pending. The original whole-C five-billion-byte storage gate
also remains pending. Issue#172, server/AWS delivery and release acceptance
cannot be closed using this software checkpoint.

## Construction-context software sub-checkpoint

`WorkerRunner(execution=...)` supplies construction-only configuration around the
unchanged four-argument function, with private ContextVar reset in finally.
Default wrappers and independent threads inherit no configured executor. There
is no environment, request DTO or SDK configuration path and no background
pulse keeper. Linux execution uses the existing LinuxOwnedProcess interface;
its actual inspect/poll, pulse and exact CID/nonce close determine the adapter
status. The loop still checks the store live fence before1s pulse, heartbeat15s,
real60s lease and global2 store cap. Existing Windows construction is preserved.

The host prepares a distinct `bundle` mounted read-only at `/inputs` and an absent
`output` subsequently created by the owned adapter and mounted at `/output`.
The trusted command is fixed venv Python `-B -I` plus the baked worker entry.
The private numerical child accepts explicit input/output/manifest binding;
separate-output Linux execution cannot fall back to a host/Git fingerprint.
Admission is rechecked before launch and before publication. Parent receipt,
actual adapter terminal status/cgroup limits and existing heartbeat/finish fences
must agree before success.

`WorkerImageAdmission.verify(profile)` is a trusted typed provider boundary.
No concrete image admission implementation is shipped here; a caller-supplied
saved tuple or qualified boolean is not an implementation of the required
actual image/config/source/inventory/probe checks. The eventual operator entry
must use the reviewed immutable-image provider; current default Linux refusal
remains. Full producer/admission, baked entry, real numerical-container evidence
and <=90s recovery remain required before delivery.

Targeted software tests use the production owned adapter, SQLite and numerical
receipt/publication against a fake Engine and test-only admission provider.
The nonzero/OOM/cgroup scenarios are mocked control-plane checks, not actual
container witnesses. No new image/container/environment/download was created.
Original raw evidence and the original10MB cumulative budget remain preserved.
