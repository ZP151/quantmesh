# Fixed c8 OpenD private storage

Issue [263](https://github.com/ZP151/quantmesh/issues/263). Root selected this bounded
engineering slice under the existing operator repair/login/long-session authority
(bb706220, with capability amendments bad4e29d/a69c5a83). It is not another human
approval or a global review-policy change. Native prerequisites actually passed
2026-10-31T03:04:40Z; this does not admit production mounts or a provider start.

## One action and outcome

Recover the original c8 persistent console with all new filesystem writes sharing
one retained 33,554,432-byte ext4 image. Success means a denied mapping cannot reach
the vendor gate, and a published implementation has a separate finite synthetic
native proof before production preparation. Login remains an operational outcome.

## Fixed architecture

- Original nonce c8f0d0de4ca641a491fca6df24c66ceb, UID997/GID987 and original unit.
  No new unit, target, tunnel, vendor, dependency or environment.
- Root-private storage root `/srv/quantmesh-opend-private-storage-20261031` holds
  distinct retained `fixture.ext4` and future `provider.ext4`; never reuse/reformat
  an attempted image. Each is root0600/single-link/preallocated33554432B.
- Pool `/run/quantmesh-opend-storage-c8f0d0de4ca641a491fca6df24c66ceb` contains
  `fs`, read-only `lower-home`/`lower-state` binds and `view-home`/`view-state`
  overlays. Separate home-upper/work and state-upper/work pairs share `fs`.
- HOME `/var/lib/quantmesh-opend`, STATE `/var/lib/quantmesh-opend-stage`, original
  c8 runtime directory, `/tmp`, `/var/tmp`, `/dev/shm` are the ONLY writable regular
  filesystem mounts. Runtime/tmp/vartmp/shm are distinct directories on `fs`.
- Original claim is separately read-only bound into STATE. All nine original
  fields remain exact; existing Recovery Lease still owns that verification and
  O_EXCL/full-write/file+directory-fsync consumption. Any post-create failure is
  SPENT. Persistent image and marker survive remount; no refund/new nonce.
- One exact c8-only drop-in binds these views, sets PrivateMounts=yes,
  PrivateTmp=no, clears StateDirectory, preserves RuntimeDirectory and resets the
  six ReadWritePaths. Base template bytes and initial/other-instance contracts
  remain unchanged. Original host runtime is separately bound to image/runtime
  during later preparation; namespace-only socket visibility is insufficient.
- A read-only file bind exposes image METADATA at
  `/etc/quantmesh/opend/private-storage-image` (root0600, never read/hash payload).
  This additional read-only alias lets UID997 verify the original image inode and
  size while the storage root remains0700. It grants no seventh writable target.

## Authority and live admission

Schema4 extends the existing closed recovery control only with
`storage_profile_sha256`, fixed c8/997/987. Schema3 remains valid for other existing
recovery instances. The original c8 recovery path requires schema4 and its storage
profile; an old schema3 c8 control cannot bypass the guard. Initial schema1/2 is
unchanged.

Fixed root0444/single-link `/etc/quantmesh/opend/private-storage.json` contains only
closed-schema public mount/image identity metadata, bound by the recovery digest.
Production requires the exact provider image path. Common layout inspection also
supports the fixed fixture image as synthetic evidence, never as production
admission. No arbitrary user path or Boolean qualification interface is added.

The pinned stdlib helper checks profile identity/hash before and after bounded
kernel observations; exact six mount points/roots, expected overlay lower/upper/
work paths, read-only lower/claim/image aliases, one loop-backed ext4 device,
actual loop backing path/offset/size, stable image inode metadata, runtime fsid and
finite geometry. Profile lower-root strings are expected kernel metadata, never
paths opened for credential reads. Malformed/ambiguous mount entries and
any unexpected writable regular filesystem (including tmpfs) deny. Fixed kernel
pseudo filesystems for devices/IPC/proc/sys/cgroups are not disk-cap certificates.
Normal overmount stacks resolve by mount-ID parent chains to the visible mount;
disconnected duplicate targets deny. Covered old-root children do not falsely
appear as writable escapes in the new namespace.

Recovery-only manager admission checks exact drop-in path/SHA and critical
namespace/state/runtime/write-path properties. It runs with the live namespace
guard at ordinary admission and the existing final post-persistence admission.
Bare-host --check-window is expected to deny; prepare proof before signing control
and use original unit ExecCondition. No expiring control while waiting for proof.

## Native proof and release

After normal publication, the original executor runs ONE <=240s synthetic fixture
with its own retained32MiB image, safe output<=32768B. A private preparation mount
namespace and its nested unit-like namespace model host preparation plus unit
read-only mounts without a new unit or host-global remount. All synthetic lower,
etc/run/varlib mount targets belong to its private purpose. The nested namespace
uses recursive mount attributes read-only, then opens only the six mounts; the
parent's overlay upper mount references stay private and writable, as in a real
systemd namespace. No original credential/lower/provider is read or used.

Prove common live layout, aggregate ENOSPC after writes through all six targets,
unchanged synthetic lowers, exact original-claim equivalent bind, persistent
O_EXCL-spent marker across remount of the SAME image, socket reachability from
the outside preparation namespace and normal owned child/FD/mount/loop cleanup.
This is filesystem/namespace evidence, not a real recovery grant or provider
acceptance. Keep image, failures and diagnostics. No fallback image or retries.

Root consumes published source, actual fixture and executable production mapping
before separately releasing production image/profile/control/start. SDK/capture,
encryption, one-shot trial and statistical gates remain separate. Never read,
copy or hash credentials, terminal contents, vendor state or image payload.

## Constraints and evidence

Original1GiB/high768MiB/swap0/CPU50/tasks128, no restart/boot, private loopback and
paper/live invariants remain. Disk32MiB is not a RAM cap; pagecache/slab/headroom
still need actual operational evidence. No copied upstream code: reuse Linux
ext4/OverlayFS, systemd binds, Python stdlib and existing recovery primitives.

Local16MiB/remote72MiB fullholds and all earlier failures remain; remote is
fixture32+provider32+operations8MiB. Latest G10126569562/P4297163790, caps10.5/4.5GB
and50GiB free floor. Source/Git/tests/docs/review/CI/catalog all count. Fresh source
review max2 rounds; a third structural failure returns to Planner, not patching.
Original first increment04:19:13Z/reviewable06:19:13Z targets are not reset.


## Final namespace propagation contract — issue263, 2026-10-31

The operator action remains the original private OpenD login window followed by
an explicitly persistent owned session. Software admission is a prerequisite;
local tests do not complete that user action. PR266 published17c82e1/tree0e72da7
with the readonly POOL configuration. Its latest real formal Source check
returned storage_denied at _mapping:262 via _validate_mounts:271 (POOL/fs), after
the preceding mode predicate. Raw optional propagation tags and effective
MountFlags were not captured, so their values remain UNKNOWN. No fourth original
start occurred; original requests total3, with no accepted backend/window/SDK.

Selected change: add only MountFlags=slave to the c8 drop-in, require that exact
effective manager scalar for c8 recovery, and refresh the drop-in pin. Preserve
PrivateMounts=yes and the complete base/reset/append vector, exact POOL readonly,
six external writes, formal IMAGE->ALIAS and physical original-claim readonly
binds. The guard, recovery helper, base template and observer remain unchanged.
Initial permits and other recovery nonces gain no new property exemption.

Namespace isolation and final propagation differ. The reviewed systemd255
contract selects final slave propagation rather than default shared: master tags
remain valid, shared tags deny. Slave retains host-to-unit unmount propagation
without reverse propagation; private is deliberately not selected. This does not
change per-mount RO/RW or the writable backing superblock. Reuse systemd/Linux
behavior; no upstream implementation, package or dependency is copied.
[systemd255 execution settings](https://www.freedesktop.org/software/systemd/man/255/systemd.exec.html#MountFlags=),
[Linux shared subtrees](https://docs.kernel.org/filesystems/sharedsubtree.html).

The complete contract below is retained, including predicates after the last
actual failure. A software positive is not an actual formal/backend pass.

| Contract | Preserved implementation and required evidence |
| --- | --- |
| Machine/c8/UID997/GID987/groups987/caps0/NNP | Original unit, NSS and fresh Source identity gates; no actor replacement. |
| Closed protected profile/held FD/digest | Existing profile validation and final reread; no new schema field. |
| Same finite image physical identity | Existing33554432-byte provider, root0600/single link; no payload read, format or replacement. |
| Loop backing/offset0/limit32MiB/sectors/read_only0 | Existing bounded metadata capture and repeat; no alternate loop. |
| Runtime device/fsid/inode/owner0700/geometry | Existing profile/runtime gates; disk cap is not a RAM guarantee. |
| Stable mountinfo/parent graph/visibility | Frozen nearest-visible-ancestor classifier, drift and ambiguity denial. |
| POOL/fs correct ext4/device/root/RO | Exact ReadOnlyPaths=POOL, writable backing superblock retained. |
| Each required mapping has no shared tag | New final slave setting; all11 mapping classes independently reject shared, accept master-only metadata. |
| Original readonly lower HOME/STATE | Same sources/devices/roots and readonly mounts. |
| HOME/STATE writable overlays | Same precise lower/upper/work, no volatile option or different backing. |
| Original spent claim | Exact physical readonly bind, original identity9 and prior history; no copy-up/reset. |
| Formal image alias | Exact original file/device/root/readonly identity; synthetic A omission never enters production. |
| Six external writable targets | HOME, STATE, RUNTIME, /tmp, /var/tmp, /dev/shm remain finite and exact. |
| No foreign visible writable escape | Frozen strict protection/pseudo-filesystem target/root rules and hidden-mount handling. |
| Exact manager source/base/drop-in/resources | Literal pin plus c8 effective MountFlags=slave, not merely configuration text. |
| Per-Exec namespace contract | Declarative original unit/drop-in, not an ExecStartPre remount or manual clone substitute. |
| Complete Source admission | Real unchanged main/admit/unclaimed, admitted and all8 qualification flags false before start. |
| One short-lived recovery authority | Existing schema4, fresh TTL299/max_seconds180, old claim/prior permit preserved; checking never consumes. |
| Resources/Slice/cgroup/same-sender Ref | Original1GiB/high768MiB/swap0/CPU50/tasks128/noRestart; actual ownership and durable facts. |
| Normal owned rollback and live retention | Terminal/cgroup-empty proof before normal cleanup; unknown-live retains source/mappings/loop/history. |
| Actual backend/outside socket/private window | Same host runtime and image socket identity, clean fresh backend before separately authorized visible-window step. |
| SDK/data/research/trading separation | SDK/market/math/order effects remain0; paper/live and qualification semantics unchanged. |

Test-first acceptance requires full literal merged Service vector with reset and
append semantics, manager missing/empty/shared/private/unknown denial through the
existing lifecycle before marker consumption or child release, per-mapping kernel
metadata controls and unchanged mode/identity/claim/hidden escape checks. Models
reuse KernelWorld and real recovery file/lease IO; they do not qualify systemd.

Normal independent Spec/Quality review (at most R1 and one known-fix R2), exact-head
selected CI, expected-head merge/full-tree/catalog precede any operational use.
Root's later single formal transaction must check the complete contract, then
conditionally one original fourth start and separate fresh private window. It
must stop on any denial/partial/unknown; cumulative remote packing exceptions
USED2/remaining0 do not reset. No extra observer or fifth start is implied.


### Shared bind-list reset rule — R1 correction

The previously assumed effective six-plus-two vector was not valid for the old
declaration order. systemd255 treats either empty bind directive as clearing BOTH
writable and readonly entries in its common list; nonempty entries append with
their readonly attribute. BOTH empty resets must precede ALL nonempty bindings.
Only order changes: retain exact six writable/two readonly pairs, flags, slave,
POOL RO, original alias/claim and all immutable source/resource contracts. Tests
must characterize cross-reset in both directions and nonempty mixed append, then
check the complete original base/drop-in vector. The public operational deriver
must use identical reset semantics before asserting original/actor equivalence.
Old separately keyed derivations/READY claims are superseded and retained.
[systemd255 BindPaths](https://www.freedesktop.org/software/systemd/man/255/systemd.exec.html#BindPaths=),
[versioned parser](https://github.com/systemd/systemd/blob/v255/src/core/load-fragment.c#L4801-L4806).
This static fix grants no actual Source/backend/window qualification.
