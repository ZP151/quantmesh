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
- Native OCI qualification is pending until an operator-supplied qualified
  image and Engine run every opt-in witness. Windows skips and mocked cgroup
  dictionaries cannot issue a native certificate.

Coordinator mirrors exact SHA, tests, logs, review and remaining gates into
iteration0038. Keep issue#172 open until Task2/native/server acceptance. Preserve
the Windows Job Object, store/schema and report mathematics unchanged.
