# ADR-0032 — Explicit single-operator persistent OpenD console

Date:2026-10-19. Status: accepted for the explicitly requested implementation;
actual release, private login, authentication and SDK evidence remain separate.
Issue:[#192](https://github.com/ZP151/quantmesh/issues/192).

The human clarified that earlier operator/reviewer/SafetyOwner roles were one
person, assigned the alias Operator, and explicitly requested changing the flow
to single-person approval and keeping the login process running. Do not encode
one person as two independent reviewers. This request overrides the historical
OpenD two-person and expiring-window approval scope only, not the advisory key
boundary or trading authority.

Add an explicit schema2 persistent permit and separate console unit to the
existing guarded launcher. A fresh one-shot900second permit admits initial
release only. Once admitted, this process remains owned until controlled stop
or exit, with no900second vendor alarm. Preserve schema1 stage semantics and
the separate production/source qualification flags. Root protects the permit;
actual merged-source checks and independent technical review precede deployment.

Reuse the existing pinned tmux, terminal checks, guarded child registration,
pidfds, parent-death protection and control-group cleanup. Bound the persistent
unit to1GiB memory, swap0, CPU50% and128tasks. Disable automatic restart and
boot enablement so no stored password or automatic login becomes necessary.
The human alone operates the private terminal. Credential/vendor state and
terminal bytes are never observed by the assistant, logged or copied.

The consequence is an explicitly trusted single human, not two-person control.
A persistent process can survive SSH-client detach but cannot guarantee vendor
session validity or reauthentication after process/host exit. Keep exact host,
source/vendor/unit/config pins, loopback11112, original11111 rollback route and
paper/live invariants. A launched login pane grants no SDK/market qualification
and does not switch application endpoints.

## Same-unit recovery amendment — 2026-10-31

Issue [261](https://github.com/ZP151/quantmesh/issues/261) adds one separate,
short-lived schema3 recovery control for the existing persistent unit. Preserve
the spent initial claim and prior public permit; bind their actual identities
along with source/vendor/host/service identity. Fixed check/prepare/pane commands
select a present recovery control and fail closed if it is invalid. One private
O_EXCL marker is consumed at the final owned-child gate; checks do not consume,
and any failure after consumption remains spent. No automatic restart, nonce
reset, new unit, credential transport or market qualification follows.

The existing operator repair/start/login and standard agent-review/normal-merge
authorization selects this bounded implementation. It is not a new independent
human review fact or a global change to repository review policy. Actual merged
deployment, resource/native/source/provider gates and login remain separate.
See the [specification](../superpowers/specs/2026-10-31-opend-same-unit-recovery.md)
and [checkpoint](../iterations/0038-opend-same-unit-recovery.md).

## Finite private storage amendment — 2026-10-31

Issue [263](https://github.com/ZP151/quantmesh/issues/263) closes the unbounded
original HOME/STATE growth gap for this same c8 instance. A single persistent
33554432-byte ext4 image supplies OverlayFS upper/work directories and all six
writable targets. Original lowers, spent initial claim and a metadata-only image
alias are readonly. A closed root-protected profile binds the image/loop/layout
and a new c8-only schema4 recovery digest; original claim and one-marker consume
semantics remain unchanged. Actual kernel metadata is checked again at the final
post-fsync vendor gate. Missing support or any drift denies release.

The c8-only disarmed drop-in retains the existing unit and resource limits; it
does not create a second unit, enable restart, increase RAM or confer SDK access.
An independent retained synthetic image must first prove aggregate ENOSPC,
same-image remount-spent behavior, unchanged synthetic lowers and an outside
private socket. A nested private mount namespace makes copied mounts readonly
while retaining the preparation namespace's upper mount references. Native
support must be observed, never inferred from offline adapters. Normal source
review/CI/merge, the synthetic native run and the later original-unit preparation
and login are separate gates. See the [checkpoint](../iterations/0038-opend-private-storage.md).


## Final mount propagation amendment — 2026-10-31

Issue263's c8 drop-in explicitly selects MountFlags=slave while retaining
PrivateMounts=yes, readonly POOL, six external writes and all formal alias/claim
binds. The c8 recovery manager must report exact slave and the pinned drop-in.
Namespace isolation alone does not specify the final propagation mode. Under the
reviewed systemd255 behavior, the final default shared conversion conflicts with
the unchanged guard's no-shared predicate; master-only slave tags remain valid.
Choose slave to retain host-to-service unmount propagation without propagation
back to the host. Private would also remove shared status but could retain stale
host mounts, so it is not selected. No host remount command or guard exception is
introduced. See [systemd255 MountFlags](https://www.freedesktop.org/software/systemd/man/255/systemd.exec.html#MountFlags=)
and [Linux shared-subtree semantics](https://docs.kernel.org/filesystems/sharedsubtree.html).

The latest actual Source refused at the shared_mount predicate for POOL/fs, but
raw tags/effective MountFlags were not observed; this is not a captured tag value
or proof of a future pass. Source/config tests and publication precede one full
formal transaction, conditional original fourth start and separate private window.
The single-operator/agent-review/normal-merge authorization above remains bounded
to this OpenD flow; no fabricated human review, SDK or trading authority follows.


The c8 bind declaration also places both empty bind resets before every nonempty
pair. systemd255 uses one bind list for BindPaths and BindReadOnlyPaths, so either
empty assignment clears both kinds; interleaving a reset after six writable pairs
erased them. Preserve all eight pairs/flags and the final slave contract. The
original separate-key test/derivation assumption is superseded; this order-only
correction neither relaxes the guard nor proves actual manager/backend acceptance.

## Complete private writable-boundary amendment — 2026-11-01

This supersedes the earlier slave lifetime choice, preserving its failed runs and
review history. Issue263 now selects final `MountFlags=private`, explicit
`MemoryPressureWatch=off`, and appends `/run /dev/hugepages` to the existing POOL
readonly list. Retain PrivateMounts, both common bind resets before all six RW/two
RO assignments, physical ALIAS/claim, source/identity/resource/control guards.
The c8 recovery manager requires exactly the new vector and pinned drop-in bytes;
initial and other recovery modes gain no exemption.

A readonly parent alone cannot exclude a later writable submount. Slave permits
incoming host topology events; private disconnects them, while ordinary writes
to the same filesystem/socket remain shared. The earlier preference for passive
host-unmount propagation is therefore superseded: proven-owned service stop and
terminal/recursive-cgroup-empty must precede normal host unmount/loop detach.
Unknown-live retains all required state. Pressure-off disables notification setup
only; memory.high/max/swap0, CPU50%, tasks128 and protected cgroups stay enforced.
See [systemd255 execution settings](https://www.freedesktop.org/software/systemd/man/255/systemd.exec.html),
[resource controls](https://www.freedesktop.org/software/systemd/man/255/systemd.resource-control.html#MemoryPressureWatch=)
and [Linux shared-subtree transitions](https://docs.kernel.org/filesystems/sharedsubtree.html).

The complete isolated candidate at2026-10-31T16:40:01Z used unchanged published0620
Source and the same process/namespace for full kernel classification: real
check-window admitted once, eight flags false, six designated writable targets,
zero noncanonical escapes, normal actor/Ref/mount/loop/source rollback. It retained
the complete ALIAS and physical-claim binds, with no diagnostic mirrors or omitted
inputs. POOL's redundant self-record disappeared under readonly RUN, so acceptance
uses effective protection and unchanged guard mappings, not historical IDs or
14 self-records. The two earlier opaque identities remain UNKNOWN. The bounded
candidate was not the original service start, backend, login or SDK qualification.

This amendment changes no storage-guard/recovery/base/observer algorithm or
resource limit. Fresh software review, exact-head CI/normal merge/catalog and a
separately bounded formal transaction still precede original-unit backend/socket
and visible-window acceptance. The original three starts remain historical;
Source/manager GREEN does not release a fourth start or a trading action.
