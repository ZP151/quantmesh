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

## Source review closure

Reviewer: known-fix R2 on e8a986643935cb9b5ef2ed8c8eb92fbd310b2cb7 is READY for
normal source publication only. Both admission findings and the safe diagnostic
gap are closed; no Critical/Important/Minor remains in that delta. No test rerun or
native operation occurred in review. R1/R2 original reports remain retained.

Final: Ruling: the preexec boundary does not expose a kernel errno through the
post-exec wrapper. Preserve actual outer stage/type and UNKNOWN errno rather than
infer success or a cause. The cost of a preexec failure is retained evidence and
a stopped native gate, never an automatic retry or production release.

PR [264](https://github.com/ZP151/quantmesh/pull/264) carries this source slice;
required exact-head CI is pending. This final documentation checkpoint changes
no reviewed runtime/test bytes. Original complete-tree/catalog publication,
synthetic native proof and the original login window remain pending.

## Nearest visible pathname ancestor follow-up —2026-10-31

Planner: issue263 remains the original console recovery/login action. Root cee66f50 selects only the visibility invariant, direct tests and two mechanical guard pins. New isolated sparse branch codex/opend-visible-mount-nearest-ancestor starts from actual origin/main5ce6d458; prior checkout/head66 and all native/failed evidence stay unchanged. Dedicated ignored purpose output/opend-visible-mount-nearest-ancestor-20261031 has a complete8MiB hold; no host effects or new environment. [Follow-up spec](../superpowers/specs/2026-10-31-opend-visible-mount-nearest-ancestor.md) and [plan](../superpowers/plans/2026-10-31-opend-visible-mount-nearest-ancestor.md).

Quant: this is namespace admission only; data lineage, strategy/math, fees/leakage, SDK permissions and paper/live invariants remain unchanged. Kernel graph evidence identifies two candidate leaves beneath visible PROC/PROC_SYS parents; the actual private target is UNKNOWN and the original-unit cause is not established. Tests use /proc/sys/opaque-fixture.

Implementer/Verifier RED checkpoint: unchanged guard6e8177e5 with new independently expected topology controls gives9 failed/83 passed (pytest0.86s). Six captured-topology ID/order variants expose mount_ambiguity, hidden-only old child remains incorrectly visible, and two missing-parent cases incorrectly admit. True sibling ambiguity, valid stacks, path-component boundary, cycle/invalid ancestor, root outside-parent and visible writable-child refusal controls pass. Raw RED-OLD-SOURCE.{stdout,stderr,json} retained under the ignored purpose. Source behavior has not changed at this checkpoint; tests/docs are committed before implementation.

Reviewer: fresh Parent-assigned Spec/Quality review is pending, capped at R1/known-fixR2. Parent owns later exact-head CI/normal publication; implementation stops before push/PR. Native fixed Source/backend/window are not claimed.

## Nearest-ancestor software correction checkpoint

Existing PR264 is merged as5ce6d458/tree159feb54 with exact CI41166733317 success (5pass/2skip); its separate synthetic native fixture was subsequently accepted. Those historical checkpoints are not pending again. Actual original-unit start requests total3, most recent held-Ref transaction recorded ExecCondition exit2 before prepare. A later real nonstarting systemd Source check returned storage_denied; kernel-only metadata then found two candidate leaves with different visible PROC/PROC_SYS ancestors. The precise private target remains UNKNOWN; the same original-unit cause is not yet proved. No new start/native/SDK/UI occurred in this software follow-up.

Implementer: `_visible_mounts` now finds the deepest already-selected proper pathname prefix once per target group and excludes candidate chains attached to another ancestor. Same-target stacks, cycle and sibling-ambiguity checks remain; unknown nonroot parent or missing namespace root denies, while an unlisted outside parent for namespace root remains valid. Only this function changes behavior. Launcher PRIVATE_STORAGE_SHA and fixture GUARD_SHA mechanically bind new guard d2addaa991a5b22eff531ccb5891add5c4849ca1357f1c7ba83455b4dc907e30; other source functions/template/profile/claim/resource contracts are unchanged.

Verifier: test-first checkpoints98acd167 and24f29ec retain unchanged old guard with9 genuine failures/83passes. The first post-change attempt exposed15 failures because old synthetic layout attached /dev/shm and added /dev/pts to ROOT despite a visible /dev. Correcting only those direct test parent IDs gives92passed. Six existing positive tests with the corrected fixture also pass the unchanged old guard, so this fixture correction does not weaken acceptance. Final directly affected storage+fixture130passed and recovery-pin22passed (152distinct selected cases); direct92 is included in130 and is not added twice. Changed4-file Ruff/format and diff checks pass. Raw commands/RC/stdout/stderr are retained in output/opend-visible-mount-nearest-ancestor-20261031. Initial test-style errors, sparse test-helper import failures and failed first GREEN remain recorded separately from product RED; no dependencies or environment were added.

Quant: no data/model/fees/math/financial evidence changed. Reviewer: fresh Parent-assigned R1 is pending; implementation is committed for review only and stops before push/PR. Later publication should use Refs issue263, not close the issue: actual merged/native/original backend/private login remain separate unresolved endpoints.

## Nearest-ancestor R1 test-only correction

Fresh independent R1 on90e552b found one P2 coverage blocker, no runtime defect: the foreign-root /dev replacement removed mount23 but left /dev/shm parent23, so mount_parent masked the intended canonical-root rejection. R1 report SHA84f7ea2979256cfcf240819f6ba846902de4466a38e16e1527768918f96b6648 is retained in the dedicated purpose/review/R1.md.

Implementer/Verifier: adding exact writable_escape assertions first produced the expected1failed/6passed RED (mount_parent versus writable_escape). The minimal fixture reparent20:23→40 then passes all7 selected cases. A bounded RAM-only removal of canonical_kernel_mount's root==/ predicate makes the actual final foreign-root test fail with pytest's DID NOT RAISE outcome, proving the intended safety check is reached. The real guard still rejects writable_escape. Runtime guard/launcher/fixture remain byte-identical to90e552b (d2addaa9/3b7666b3/a46265e7). Changed test Ruff/format and diff checks pass; no broader152 replay, host/native/Source/SDK/UI or push/PR. Exact raw R1-REASON-RED, R1-REPARENT-GREEN and R1-ACTUAL-TEST-MUTATION evidence is retained.

Only this direct test and plan/iteration status changed. Same fresh reviewer known-fix R2 is pending; this is not an independent READY or a third structural review. Earlier HANDOFF.json/90e evidence stays immutable; HANDOFF-R2.json carries the new exact candidate.

## Source-review closure — awaiting normal publication

Same fresh reviewer R2 is READY on5c12344254e5137dfd5af10ad8878fa2adffc1f3; report4467B SHA945b726d0de433cb4a43a1d324ede3445f91cde551ad535cbcc689128aa68576 under output/opend-visible-mount-nearest-ancestor-20261031/review/R2.md. R1's sole P2 test coverage blocker is closed; no remaining Critical/Important/Minor findings. The two-round source review stops, no R3. This final closure changes only this iteration and the tracked plan; runtime guard/launcher/fixture and direct test bytes remain exactly the reviewed5c123442 version.

The implementation handoff is now for Parent-owned push/Draft PR, required exact-final-head CI, normal merge and merged tree/catalog. These outcomes are pending and not inferred from local software checks or review READY. Use Refs #263; original-unit cause, fixed-source native/systemd admission, real backend/private login and financial Goal remain unresolved. No new tests, Source behavior, host/main/start, SDK/UI or control/image operations occurred in this documentation closure.

## Declarative pool readonly repair: planner and genuine RED

Refs issue263. Published PR265 merged559584b/tree59ce153 with exact selected CI41188309198 success; those source/CI checks are closed. Its actual manager-owned original sandbox Source check ran once and refused storage_denied at _mapping mount_mode for POOL/fs; no fourth original start. Original ordinary start requests remain3.

Planner: select one ReadOnlyPaths=exactPOOL c8 dropin addition plus pinned bytes/effective manager scalar, preserving six writes/all formal binds and all guard/claim/consume/resource contracts. A single subsequent isolated configuration probe on installed systemd255 proves six internal mounts readonly and six external own synthetic write11B/fsync/close operations. Full wire7541B/b1ea1c1d1d0dd7e5cd0975920b8dacf95b654b7acfcf243e08eec0c83e41ee84 and decoded23824B/0a1a77096c68745844f01c81eaaf2ac82446925b75ad7d04c638a8cd70c81897 are retained under output/opend-private-storage-20261031-0220/pool-readonly-probe-01. Parent independently decoded/asserted the complete actual record. Actor/cgroup, Ref/bus/libraryFD, matching mounts/loop closure and global-unchanged checks pass; no Source/main/vendor/SDK/UI/original start was performed by this trial.

Probe-only Root-authorized input omission: IMAGE->ALIAS readonly bind was omitted to avoid creating an absent formal global target. Formal software retains that binding. The trial is not full Source/backend admission. Direct POOL errno13 is traversal EACCES under unchanged0700, not EROFS; readonly evidence is the independent actual kernel mount flags.

Quant: no market data/model/fees/metric/leakage or trading authority changes. Implementer/Verifier: tests first on unchanged production files now give6failed/9passed, including absent dropin readonly and five actual manager drift controls. Raw RED-OLD-CONFIG-COMPLETE evidence is under output/opend-visible-mount-nearest-ancestor-20261031/pool-readonly-config-01. The earlier runner omitted the basetemp parent and yielded1failure/14setup errors; that failed invocation is retained and is not counted as the complete RED.

Existing isolated checkout is reused on codex/0038-opend-pool-readonly from fresh origin/main559; old b5 source branch, all failures and local main divergence are preserved. Fresh complete software forecast5556208B<existing8388608B hold; no new charge. Tracked spec/plan: 2026-10-31-opend-pool-readonly.md. Minimal production change, GREEN, fresh independent review and normal exact-head CI/publication remain pending.

## Declarative pool readonly software GREEN

Implementer: c8 dropin adds only the exact POOL ReadOnlyPaths line; resulting1320B SHA325cdfbf8424ac95b9d21a1a6929a886e1572c524078f785f462cf28438e83b9. Launcher updates that literal pin and adds the c8 recovery-only exact effective ReadOnlyPaths scalar. Formal IMAGE->ALIAS/claim binds and six writes/binds are unchanged. The private-storage guard, recovery helper, fixture and base template remain byte-identical to merged559; every other launcher definition is AST-identical. Test-first checkpoint e7673bf preserves old production bytes.

Verifier: genuine complete RED6failed/9passed becomes GREEN15passed/0.73s. The directly affected storage/fixture/recovery files pass238tests/6.16s; the15 targeted cases are included, not added twice. Changed3-file Ruff check/format, Python3.12 syntax plus in-memory compile, whitespace and submodule metadata checks pass. An initial Ruff line-length failure was corrected by formatting only. Raw commands, RC/stdout/stderr and minimal AST/byte delta proof are retained under the software purpose. No package/environment, old native qualification or host operation occurred in this software phase. An initial documentation writer used the Windows default decoding and stopped before updating this ledger; the corrected writer explicitly uses UTF8. Production tested checkpoint2e8daab is unchanged.

Reviewer: independent fresh dual Spec/Quality review remains pending, capped at R1/known-fix R2; this is not a third review of PR265. Normal exact-final-head CI, publication and later merged Source/runtime/backend/private window remain pending.

## Declarative pool readonly fresh review closure

Fresh independent agent R1 is READY on exact19fa9173305b30d2ac638aa1aade904d660ee8c4, zero actionable Spec/Quality findings. Report8598B SHA12b7965d69500dda9e16a297d8145ea479425b256371c85e14e88de2665e8b74 is retained in the software purpose/review/R1.md. Reviewer independently checked the actual diff, pins, tests-first production freeze, raw software evidence and actual limited native probe; no tests or host operations were repeated. It is agent technical review, not a fabricated human-review fact. No fix or R2 is required.

This closure changes only the plan/iteration/roadmap status; reviewed runtime and tests remain exact19fa917 bytes. Parent now owns normal PR, exact-final-head selected CI plus aggregate success and expected-head merge/full actual catalog. These are still pending. Issue263 remains open for full merged Source/runtime/original backend/private login; no fourth start or SDK/UI claim follows from software READY.
