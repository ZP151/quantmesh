# Iteration0038 — fixed c8 OpenD private storage

Issue [263](https://github.com/ZP151/quantmesh/issues/263), directly blocking the
remaining original OpenD recovery/login path and later259 data gate.
[Spec](../superpowers/specs/2026-10-31-opend-private-storage.md),
[plan](../superpowers/plans/2026-10-31-opend-private-storage.md).

Planner: selected Root bb706 design under existing operator repair/login authority;
one33554432B persistent disk image, six fixed writable targets, original read-only
lower/claim and retained marker. Read-only root0600 image alias permits metadata
identity checks without opening credentials/image payload. No new paid resources,
dependencies, environments, units, source strategy/math or general storage platform.

Quant: no SDK/data/capture intent/trial/order. Existing IVV121-session scope/math,
once/encryption/actual input acceptance and financialINSUFFICIENT remain unchanged.

Implementer: branch codex/0038-opend-private-storage from actual d9f12e0; ignored
purpose output/opend-private-storage-20261031-0220/checkout, sparse shared Git
objects because native worktree tool cannot meet no-checkout/16MiB requirement.
Original W and prior recovery branch remain intact. Code/TDD starts after this plan.

Reviewer: fresh whole-source review pending, max R1/known-fixR2; operational packet
checks are not source approval. Existing single-operator agent-review/normal-merge
authorization is task-scoped, not a claim of two independent humans.

Verifier: native full capabilities actually AVAILABLE03:04:40Z; exact installed
package bytes/compathelp/heldFD overlay insertion passed, ext4/loop10:237 and root
capabilities ready, kerneltaint0. No mount/image/provider/control/start/SDK followed.
Operational collector verifier omission and CLI-dispatch omission are retained
harness failures, not module trust failures or continuous software-development time.
Native capability artifacts are sealed under capability/kernel-activation01/02/03;
old32MiB capture budget was not a human mandate for every UI start.

Budget: local16MiB/remote72MiB fullholds retained, remote fixture32/provider32/ops8.
Latest reported G10126569562/P4297163790, caps10.5/4.5GB/free50GiB, old positive
intervals61440/200704 already charged. No new charge/free probe/refund/history delete.
Original04:19:13Z first increment/06:19:13Z reviewable targets unchanged.
Source tests/publication, synthetic native proof and actual login remain pending.

## Guard checkpoint

Implementer: fixed public profile and live metadata capture now validate one loop
extent/image identity/runtime fsid, exact lower/overlay/claim/image alias and six
writable mounts; unexpected writable regular filesystems and volatile overlays
deny. Root public profile stays held through live capture and is reopened to reject
same-byte inode replacement; duplicate JSON keys and unsafe parents/file modes deny.
No image/HOME/STATE payload is opened. The disarmed c8 drop-in is present; existing
launcher/recovery code is not wired yet, so no production admission is claimed.

Verifier: RED01 missing guard, RED02 backing counterexamples, RED03-real mapping
counterexamples, RED04 covered-root/type regressions, RED05 missing drop-in and
RED06/07 absent live/profile gates were observed before implementation. GREEN
Task1 is64 passed with focused Ruff/format/in-memory compile/whitespace clean.
RED03's first attempt failed only the new snapshot-shape transition; it is retained
but is not the21 genuine mapping REDs in RED03-real. Initial style findings and all
RED logs remain in the ignored purpose/verification; Linux metadata is modeled,
not native qualification. No old full suites/CI/native preflights were repeated.

Ruling: resolve legitimate mount stacks through kernel parent chains rather than
reject all duplicate path strings. Original host runtime bind plus unit binding can
create a normal stack; ambiguous siblings/cycles still deny. Cost if wrong is a
hidden writable escape or a false denial, covered by regressions and later native proof.

Ruling: read-only root0600 image alias is metadata-only, permitting stable inode
checks with a0700 parent pool. It adds no writable destination; actual mapping and
no-payload-read semantics remain explicit native/review requirements.

Ruling: a nested fixture namespace models systemd's clone of prepared OverlayFS
mounts. Its recursive readonly flags must affect copied mounts, preserving the
preparation namespace's upper mount references. Unsupported native behavior stops
the retained fixture; it does not permit a new unit, image or host-global remount.

## Recovery integration checkpoint

Implementer: closed schema4 adds only the profile digest and fixes c8/997/987.
Other schema3 and initial controls retain their contracts. Original c8 recovery
requires pinned live storage admission, so old schema3 cannot bypass it. The exact
c8 drop-in path/SHA and manager namespace/state/runtime/write-path properties are
checked; original template SHA remains b23d91ec. The existing post-persistence
_admit call now also rechecks storage before its unchanged child gate. No backend,
consume ordering, timeout, SDK or vendor operation was changed. Safe storage_denied
was added to the fixed error categories after its regression exposed generic masking.

Verifier: actual CLI RED08c refused new schema4 but admitted old c8; after schema4
support, RED08d exposed missing profile enforcement. GREEN08 closes both with real
Control/Lease IO and modeled Linux/vendor facts. RED09b exposed the exact-drop-in
manager gap; all manager wrong-property/SHA vectors now deny. Final-gate simulation
has one release on valid layout, zero after fsync-time loop drift, retained spent
marker and normal owned handle closure. Affected11:263 passed/70 platform skips;
focused Ruff/format/compile/diff and unchanged submodule pins pass. This is software
evidence, not Linux native qualification or an opened login window.

Test setup failures are retained separately: default pytest temp cleanup encountered
an unrelated inaccessible old pytest-current path; one owned basetemp lacked its
parent, and one manager adapter used Windows backslashes for POSIX keys. None is
claimed as product RED. Subsequent runs use unique owned vector roots, preserving
all prior failures. The tiny first default-temp fixture footprint is additionally
covered by the original unknown/test margin; no foreign cleanup was performed.

Task3 remains: reviewed finite native fixture source, fresh whole-slice review,
exact-head normal CI/publication/catalog, then separate synthetic native execution.

## Synthetic fixture source checkpoint

Implementer: a fixed, existing-tool adapter creates one retained synthetic image
only inside an already verified preparation namespace. A nested namespace makes
all copied mounts readonly, opens exactly six writable leaves, drops to997/987,
clears groups and verifies CAPEff0/NNP. Its source embeds the exact pinned common
guard and the same tested create-only/fsync marker and aggregate writer functions.
The parent independently checks all six physical image backings before bulk writes
and connects to the child's owned AF_UNIX socket. First round primes the marker
and six4KiB files; normal unmount/remount of the same image precedes the spent-marker
check and real aggregate errno28 exhaustion. This order avoids requiring new
OverlayFS work metadata after filling the filesystem. Physical marker inode,
image identity, fsid and runtime inode persist; OverlayFS view inode is not used
as the physical remount identity. Only synthetic lower bytes are hashed.

Verifier: RED12–18 cover missing fixture/lifecycle/namespace/aggregate/marker/
embedded-code/owned cleanup behavior. RED20 adds controlled-stop cleanup; RED21b
exposes and closes raw machine-id byte-hash drift. AFFECTED22:299 passed/70 Windows
platform skips. Fixed proof deadline195s and cleanup reserve25s remain below the
separately imposed240s native packet limit; output is bounded. Busy normal unmount
retains its owned loop and returns failure, with no force/lazy or foreign cleanup.
All failed images, logs and partial markers are retained. An initial missing
Windows SIGCHLD adapter is setup failure, not product RED. Offline adapters do not
prove kernel mount_setattr/OverlayFS or actual provider readiness.

Ruling: explicitly bind the old claim readonly in the c8 drop-in as well as the
prepared view, so the broader STATE write rule cannot make claim protection depend
on recursive bind propagation. It changes no writable target or claim identity.
If the actual manager mapping differs, the common guard still denies release.

Reviewer: one fresh whole-source review is next. Native fixture, original-unit
preparation, control consumption, provider start, visible login and SDK remain
pending; no actual native/storage/provider operation occurred in these tests.

## Whole-slice R1 and one fix pass

Reviewer: fresh independent R1 on c9e4c01 found two Important admission defects:
writable pseudo-filesystem types were exempted at arbitrary targets, and loop
facts could drift during live capture without a repeat read. No Critical/Minor
finding was reported. The source remained blocked; offline adapters were not
called native evidence. The report is retained as review/R1.md in this purpose.

Implementer/Verifier: R1-RED23 reproduces four foreign/noncanonical pseudo mounts
and all five loop-field drift cases (nine failures). Writable kernel exceptions
now require their closed canonical target and root, and all five loop observations
are repeated around the remaining metadata reads. R1-GREEN23 passes; unchanged
canonical proc/dev/sys/cgroup positives remain accepted. Guard SHA is6e8177e51abb2b8381881ac6d2cac237c00d353efc734292f2730d2d68b3e518,
with launcher and fixture pins refreshed.

The author also confirmed that pre-READY child exceptions lost their safe cause
because stderr is discarded. R1-RED24 executes generated child code with a wrong
modeled identity, exposing the missing structured failure. The same single fix
pass adds bounded stage/type/fixed reason/errno events and a closed parent decoder;
no traceback, private values, arbitrary fields or paths enter the receipt.
R1-GREEN24 passes. Preexec failures still report their actual outer stage/type;
unobserved kernel errno remains UNKNOWN. AFFECTED25:313 passed/70 platform skips.
Native support and all original-provider operations remain pending.

Final: Ruling: actual mount_setattr/OverlayFS behavior and parent upper references
require the separate finite native gate; source tests cannot certify them. Cost
if unsupported is a retained failed fixture and no production release.

Final: Ruling: actual systemd bind serialization and original socket visibility
require the later original-unit check; the exact source guard denies mismatches.
Cost is a refused startup until the concrete mapping is corrected.

Final: Ruling: target persistence/aggregate ENOSPC require the one actual fixture;
source control flow is not filesystem evidence. Failure stops before production.

Final: Ruling: production profile/control/start/login/SDK/headroom remain later
gates; this source checkpoint confers none of them. Cost is remaining operator
work rather than an unsupported readiness claim.

Final: Ruling: unchanged PR262/base-unit implementation and global review-policy
redesign stay outside this bounded slice. New integration is reviewed; an unrelated
older defect would need separate triage rather than silent expansion.

Final: Ruling: snapshots establish observed admission stability, not immunity to
future privileged reconfiguration. A later root change requires a new live check;
the source does not certify indefinite layout integrity.

Final: Ruling: foreign/busy mount repair is excluded. Failed normal owned cleanup
retains evidence and reports remaining handles; the cost is manual disposition,
never force/lazy/global cleanup or a refunded retry.

Known-fix R2 closure and normal exact-head CI/publication are next. Issue263 stays
open for actual native/operator evidence; the login window has not been opened.
