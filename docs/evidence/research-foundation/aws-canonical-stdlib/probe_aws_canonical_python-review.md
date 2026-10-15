# Bounded canonical-probe pre-execution review

Actual reviewed SHA256: `821CDB7751510B2F470FA3499E3456D88231710157314F792FE0C93646A2F778` (`output/probe_aws_canonical_python.py`).

## Findings

1. **P2 — Distinguish requested start from observed start** (line 84). `container_started=True` is assigned before the start request is accepted or any started process is observed. If the daemon refuses start, the failure receipt still claims an actual start. Record `start_requested` separately; derive actual started status from a current inspected state/start timestamp or the successfully validated observation, retaining uncertainty if inspect fails.

2. **P2 — Preserve uncertainty for an incomplete create request** (lines 101–108,112–114). A failed/timed-out create with no captured CID may still finish in the daemon after the one nonce-label scan. Empty scan and an immediate zero-container Engine snapshot cannot prove cancellation or completion of that request. Currently `partial_create_quiescence=NOT_PROVEN` appears only when recovery observation throws. Track whether create was attempted and whether its completion is proven; for unknown completion, preserve NOT_PROVEN even when both snapshots are empty. Recovery must remain limited to the exact unique nonce/CID, with no creation retry or global cleanup.

## Other scoped conclusions

The tmpfs predicate is consistent with this pinned Engine. [GetMountPoints](https://raw.githubusercontent.com/moby/moby/a5b58c94d334674eae3a3207d4f05417643a90d0/daemon/container/container_unix.go) iterates MountPoints, while legacy `HostConfig.Tmpfs` is handled separately by TmpfsMounts. [Mount registration](https://raw.githubusercontent.com/moby/moby/a5b58c94d334674eae3a3207d4f05417643a90d0/daemon/volumes.go) does not add the legacy map to MountPoints. Thus an empty Mounts array alongside the exact requested Tmpfs map is not itself an overly strict refusal for this --tmpfs form.

The supplied create argv requests the immutable image without pull, isolated network, readonly rootfs, nonroot user, capped memory/pids/cpus, capability drop and no-new-privileges. CID cleanup re-inspects exact image/nonce labels, stops only that owned CID when running, checks stopped/Pid=0, and uses non-force removal. CLI timeouts are not daemon cancellation authority. No additional substantive P1/P2 found in these reviewed ownership/cleanup paths, subject to the two receipt findings above.

## Limits

Static source review plus pinned primary Engine source only. No remote execution, probe, tests, container create/start/import, or old architecture review performed. The recipe was unexecuted. The official base is the explicitly trusted TCB for this finite diagnostic; this review proves no source-to-binary equivalence, effective kernel profile, numerical/native permission, image/runtime certificate or completion of Option A.

## Two-observer correction closeout

Actual corrected source SHA256: `618F44A4A4125B46DD05901948E937253AE432125AA8C10791D2E1E2ACE6AB71`.

Clear within the two requested corrections: both original P2 findings are closed; no new substantive P1/P2 found in these changed boundaries. `start_requested` is recorded separately, and `container_started=True` is now set only from an owned inspected Running state or nonzero StartedAt. A refused start followed by a never-started owned state no longer claims a start. `create_requested` is set before create, and the no-acknowledged-CID recovery path preserves `partial_create_quiescence=NOT_PROVEN` independently of an empty nonce scan or the final zero-container snapshot. No recovery retry or global cleanup was added.

Inspected existing `0038-aws-numeric-canonical-observers-red.log/.exit` and `-green.log/.exit`: the controlled refused-start and uncertain-create cases changed from two failures/exit 1 to zero failures/exit 0. Both receipts explicitly state `actual_Docker=false`; the recipe itself remains refused (exit 1) in these negative cases. The original source is retained as `probe_aws_canonical_python-before-observer-fix.py`. These are software counterexamples only, not a remote probe or Docker/kernel certificate. This reviewer ran no tests or remote commands for the closeout.
