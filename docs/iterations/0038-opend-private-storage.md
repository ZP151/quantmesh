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


## Final propagation repair — local software checkpoint, Refs #263

Planner: the operator still needs the original visible private OpenD login window
and persistent session. PR266 published17c82e1/tree0e72da7 after selected CI41196548212
success; its latest real full Source check refused storage_denied at
_mapping:262 -> _validate_mounts:271 (POOL/fs), after the mode predicate. Raw
optional tags and effective MountFlags remain UNKNOWN; this is not a captured
shared-tag value. The original ordinary start requests remain3; no fourth start,
accepted backend/window or SDK occurred. The earlier mode261 refusal and isolated
A readonly/synthetic-write proof remain distinct, with formal alias retained.

Select one complete-contract correction: final MountFlags=slave in the c8 drop-in,
exact effective c8 manager scalar and updated drop-in SHA. Namespace isolation and
final propagation are different; slave rejects shared peers while retaining
host-to-unit unmount propagation, unlike private. The storage spec now enumerates
all22 retained contract rows, including still-unreached predicates after POOL/fs.
No A/flag probe or extra observer precedes the later single full formal transaction.

Quant: no market data, SDK, costs/leakage, math/model/metric, order or paper/live
semantics change. No financial research evidence is inferred from these tests.

Implementer: reuse the isolated sparse checkout on new
codex/0038-opend-mount-propagation from fresh origin/main17c82; relevant drift is
zero. Old local main/branches/history remain. Before production edits, independent
merged-vector/config controls failed for missing MountFlags. The clean existing
manager lifecycle RED is6failed/13passed: five invalid modes were not denied by
the old gate, and the positive did not return the newly required queried field.
Earlier harness attempts omitted the admission machine-id seam and then supplied
an incomplete backend context; those retained errors are not product RED. The
final test uses the existing complete lifecycle, actual manager and real modeled
recovery lease/files. All invalid modes now deny before child creation/release,
marker creation, claim identity or prior/control bytes change.

Only two production files change: add MountFlags=slave (drop-in1337B
SHA8ba096a3557da9b0c6c9f39c67bf01276b677c4a7dc74a3b461e2cd8b9e652f4),
and add the exact c8 manager scalar plus mechanical drop-in pin in stage_console.
Guard d2add, recovery761f, baseb23d, fixturea462, all six bindings/writes, readonly
alias/physical claim, resource controls and observer remain frozen. Initial and
other-nonce admission modes gain no MountFlags exemption.

Verifier: targeted twofiles235passed; complete directly affected threefiles
(storage/recovery/software fixture)273passed/5.13s, not added together. New tests
cover all11 mapping targets with independent shared denial/master-only acceptance,
and preserve RO/RW, alias identity, claim readonly, hidden shared-stack selection
and visible writable-child denial through KernelWorld metadata capture. The
complete literal effective Service vector verifies base plus drop-in resets,
append rules, commands, groups/environment and all protection/resource/bind fields.
Scoped Ruff/format, Python3.12 in-memory syntax, whitespace/submodule and minimal
AST/byte delta evidence are recorded in the same ignored Source purpose. The
first Ruff line-length check failure is retained as a formatting error, not a
behavior failure. Root selects these directly affected gates; no unrelated
full-local/frontend suite, old native/CI or dependency/environment operation ran.

Reviewer: Parent will assign a fresh independent Spec/Quality review on the
coherent green commit, max R1/one known-fixR2; no READY is inferred here. Parent
owns push/PR Refs263, exact-head CI/normal merge/full-tree/catalog. Current software
hold12MiB includes retained old evidence, sparse checkout/admin/shared Git objects
and future review/CI/catalog margin, without recharging it. This implementer stops
before push/PR/host. Later runtime must rebind actual merge and use the existing
one full Source actor, normal closure/fresh gates, at most original fourth start,
then fresh backend/socket/private-window acceptance. Any real deny/partial/unknown
stops; cumulative transport exceptions USED2/remaining0 remain. Backend/window and
the user goal are still UNMET.

### Propagation slice independent review — 2026-10-31 13:43Z

Reviewer: fresh independent Spec/Quality R1 reviewed implementation
`d66ff31ba5e240838f14a3c2c03c90f544780376` against actual base17c82;
READY with zero actionable findings, no R2. Report10065B,
SHA256c67d6041d6d1918801384c13aacb5e44ba878d104d022906d689fe8a32905c30,
under `output/opend-visible-mount-nearest-ancestor-20261031/propagation-repair-01/review/R1.md`.
Parent matched27 source/evidence pins and the real235/273 overlapping results;
reviewer independently matched18 evidence members and nine changed Git blobs.
This checkpoint adds only the observed review fact; runtime/tests remain identical
to the reviewed implementation. Exact-final-head CI/publication/catalog and actual
Source/backend/window acceptance remain pending, not inferred from technical READY.


## R1 addendum: shared bind-list reset correction — 2026-10-31

The earlier full-vector/READY checkpoint is superseded by the immutable fresh
reviewer R1 addendum (7378B SHA b0c578264526b3248faccf7d45259f1be6343c86c48d55d9c6a061d908f64a6e).
The review missed an Important/P1 configuration ordering defect: in systemd255,
either empty BindPaths or empty BindReadOnlyPaths clears the same common bind
list. The old drop-in put the second reset after the six writable pairs, erasing
all six before appending the two readonly pairs. The test and public formal
property deriver modeled separate resets, falsely claiming original/transient
mapping equivalence. This static defect was found before any new native run; it
does not establish the exact cause/code of earlier runtime denials or a guard
bypass. Original starts remain3 and the backend/window goal remains UNMET.

Implementer/Verifier: correct the controlled test model first; both cross-reset
cases pass and the unchanged old configuration fails the literal required-six
vector (1failed/2passed, R1-BIND-RESET-RED). The order-only fix puts BOTH empty
resets before ANY nonempty bind, then appends the identical six writable and two
readonly source/destination pairs with unchanged flags. New drop-in1337B
SHAb3073bdc16fb65e7bd4a1c771bc84a00621140419a1d70051ddd419a8f64176e;
launcher changes only that pin relative to12ad1f5. MountFlags=slave, guard/recovery/
base/fixture/observer, six destinations, alias/claim identities and resources stay
unchanged. Reset-both-directions and alternating nonempty append controls are
independent literals, not expectations from a production builder. Targeted24
pass; complete affected threefiles276pass/5.13s, counts overlap.

The old derivers, model, source/test bytes, raw results and R1 READY are retained.
A new disabled candidate public deriver in propagation-repair-01 uses the shared
reset semantics, exact current public pins and all formal inputs, emits6RW+2RO
and no extra /etc/opt mirrors. It does not produce an operational grant or invent
a merged SHA. Future formal derivation must use this corrected revision; the old
separately keyed builder is superseded, never silently reused. No Source function,
observer, schema, host/auth/UI/SDK, native fixture or fourth start changed/ran.

Same fresh reviewer known-fix R2 is next, limited to this P1 boundary; no R3. Parent
owns the existing PR267/new exact-head CI and normal publication. The old CI run
and historical review remain retained; their outcomes do not release this new
candidate. No new ordinary approval or hash-by-hash Root gate is required.

### Bind-reset known-fix R2 — 2026-10-31

Same independent reviewer R2 reviewed `ca4acfc540f0c29f144d5de05def498232e6abc0`: READY,
the Important/P1 blocker closed, zero remaining actionable Spec/Quality findings.
Report9728B/SHA256fe87f3ef8934ab0bc60dfb295417cc30eebfe3ca8d71ec99b3545fc7064e15b7
is retained beside the unchanged originalR1 and its superseding addendum. No R3.
Parent matched28 current source/evidence pins and actual276-pass stdout; reviewer
independently matched20 evidence members and eight known-fix Git blobs. This
review-fact checkpoint changes no runtime/test bytes. PR267 needs new exact-head
CI and normal publication; old-head CI518 cannot qualify this candidate. Actual
formal Source, fourth start, backend/window and SDK acceptance remain separate.

## Complete private boundary — 2026-11-01 software slice

Refs [issue263](https://github.com/ZP151/quantmesh/issues/263);
[new spec](../superpowers/specs/2026-11-01-opend-private-boundary.md) and
[plan](../superpowers/plans/2026-11-01-opend-private-boundary.md) supersede the
earlier slave lifetime inference without replacing any historical outcome.

Planner: Root selected one complete private/off/fullRO contract after the entire
candidate proof, rather than another one-flag/CI/refusal loop. The single task's
only shared interface is drop-in bytes -> launcher exact SHA/properties -> tests;
these change atomically. No parallel task or guard/recovery/base edit is needed.
Fresh origin/main is0620cc97b9d382f1f226e2f336fef7cf8890efec, no relevant drift;
new branch codex/0038-opend-private-boundary preserves the old propagation branch
and divergent local main. Existing issue263 remains open/ready-for-agent; open PR
query returned none at slice start. One action remains the original private
login window, which is still UNMET.

Quant: no dataset, algorithm, confidence/math/order/SDK/capture change. IVV121,
once/eight-false/encryption and paper/live gates remain separate and unchanged.

Actual prerequisite: unchanged0620 Source check-window admitted once in the SAME
candidate process/namespace as whole kernel classification at16:40:01Z. Six
designated RW, zero noncanonical escapes, exact private/off/threeRO properties,
all eight flags false/forbidden[], physical ALIAS/claim retained and normal
actor/Ref/mount/loop/source rollback. Decoded28955B SHA256
0b9fe86310f9ed5bc7e65403a1cebdfa029498b1d02ebecfc472076e6d40ed00 and thin seal
are retained under candidate-private-boundary-01. No original start/window/SDK.
The original manager still reflects published slave until later deployment.

Implementer: runtime edits are only c8 private/off/RO append and the launcher c8
exact manager expectations/mechanical drop-in SHA. Shared-list resets stay before
all unchanged sixRW/twoRO pairs. Guard d2add, recovery761f, baseb23d, fixturea462,
observer, schema4/nonce/image/claim9/ALIAS/resources stay byte/behavior frozen.
The suspected nested cgroup defect was independently disproved: actual template
slice is beneath `/system.slice/`, accepted by the existing predicate. Only the
test positive now uses that actual hierarchy; no cgroup runtime change was made.

Verifier: test-only checkpoint on actual old runtime produced genuine RED
3failed/23passed/217deselected (old config, full vector, manager positive), then
the minimal runtime delta gave26passed. Independent KernelWorld metadata covers
RUN, hugepages and two synthetic opaque child classes, RO-parent/RW-child,
pressure on/off, hidden mounts, normalization and later slave incoming mounts;
historical opaque names remain UNKNOWN. Source is the admission oracle, not the
property model. Each missing/extra/wrong manager property refuses before child,
release or recovery marker while preserving claim/prior/control bytes. No new
Source/host/native/CI/auth/UI/SDK was executed for this software task.

Reviewer: fresh independent Spec/Quality R1 is pending on the coherent GREEN
commit, at most one known-fix R2; no self-READY claim. Parent owns push/PR Refs263,
normal exact-head selected/aggregate CI, merge/catalog and later formal gate.
Root selects targeted twofiles + affected software fixture/static checks; no
unrelated whole-local/frontend, old native or repeated prior CI. Exact commands,
raw RED/GREEN, failures, pins, allocation and unified diff live in ignored
private-boundary-repair-01. Source16MiB and N24MiB retain all old holds/evidence;
the one added4MiB source margin is consumed, never renewed per artifact. Generic
packing USED2/remaining0 and original starts3 remain unchanged. Private propagation
requires proven-owned stop/terminal+recursiveCGempty before host cleanup; unknown
live state must retain mappings. Backend/private-window/SDK acceptance stays open.

Verifier final software boundary: targeted256passed; final affected294passed/7.46s
(the affected count includes the targeted cases). Scoped Ruff check/three-file
format, Python3.12 syntax, whitespace and unchanged submodule pins pass. The first
E501 result remains INITIAL-RUFF-CHECK, corrected only by splitting a byte literal.
No product setup failure is conflated with the genuine3-case RED. Runtime delta
is drop-in1397B/SHA256c8a5b6517e2861cb5f20f6bc610f259a3d8964dcd62f7409d17d84a007f06c68
and its matching c8 manager/pin; immutable guard/recovery/base/fixture byte checks
and exact inverse proof accompany the unified review diff. This is review-ready
software, not independent review READY or production/backend/window completion.

### Complete-boundary independent R1 closure

Fresh independent whole-slice review on b88c6d0b332ad343dda7c26663a0c23aa056dfb0:
Spec PASS / Quality READY, zero Critical/Important/Minor findings; no R2 needed.
Report2269B SHA2569b4b25dafc3ef776a13752c463b43075f2ada5e87a75e84adfa0650528022fb7
is retained as private-boundary-repair-01/review/R1.md. Reviewer independently
read the41200B unified diff, runtime pins, ten raw receipts and complete actual
candidate; no tests or native operation were repeated. This docs closure leaves
runtime/tests/spec bytes exactly reviewed. Parent owns normal PR/selectedCI and
publication; original backend/window/SDK remain unaccepted.

The final Win32 accounting found17,646,848B actual against the historical16MiB
source hold, over869632B (+64KiB directory margin over935168B). All bytes remain,
not retroactively compliant. Root registered ONE8MiB supplement at16:49:25Z,
newsource24MiB, G10240999514/P4297298958, guardG10266837082/P4323136526.
Actual growth consumes a fixed remaining future envelope for R1/R2/CI/catalog
and known-fix evidence; it never renews the supplement. N24MiB/remote72/ops8
and all failures remain retained, no deletion/refund/borrowing or new test run.


## Invocation-bound diagnostic witness design — 2026-11-01

Refs #263; [design](../superpowers/specs/2026-11-01-opend-invocation-witness.md) and [plan](../superpowers/plans/2026-11-01-opend-invocation-witness.md), design review pending, no production changes. Planner: one invocation-bound last-stage/owned-child-exit diagnostic, not an inferred root-cause repair. Quant: no data/math/SDK/order/confidence change, eight qualification flags remain false. Implementer: fresh origin/main e2eab51/tree9e04 branch codex/0038-opend-invocation-witness, existing checkout; old branches/localmain retained. Reviewer: Parent's independent targeted design check precedes TDD; fresh softwareR1/maxknownfixR2 later, no self-review approval. Verifier: existing actual fourth-start/readonly postmortem only; two current complete ATTEMPTED marker views bind original control but do not prove release/exec, oldCG counters unavailable, current storage not exhausted. No new test/Source/host/CI/auth/UI/SDK executed. Existing schema4 fixednonce marker is spent: fresh control cannot authorize a fifth start; an independent protocol disposition is required and is not implemented here. Software32MiB forecast includes old checkout/history/admin/shared Git and fixed future; no hold recharge/refund/deletion.


### Diagnostic design ruling and implementation checkpoint

Planner: independent targeted design was NOT_READY on four concrete gaps;
Parent resolved c8/schema4 early binding, memory-only fork-to-ACK/reap, complete
existing-pipe child frames/inherited witness FD closure, and write-once bounded
slots/limited durability/primary-error cleanup. Original design/plan and ruling
remain in invocation-witness-01; current tracked design incorporates one final
contract. This is a diagnostic witness, not a fix for an identified runtime cause.

Quant: no dataset/math/provider/SDK/order/confidence effect; existing eight
qualification flags remain false. Original backend/login/financial loop is UNMET.

Implementer: fresh e2eab51 origin/main on codex/0038-opend-invocation-witness;
only launcher runtime changes, one focused test file and tracked design/plan/
ADR/iteration/roadmap. Recovery/guard/base/drop-in/fixture remain byte-frozen.
Header binds actual invocation/source/control; early failures never substitute
for normal admission. Writer and child protocol stay within existing c8 runtime
and pipe/FD/reap ownership. No new write destination or generation/marker change.

Verifier: old source actual RED14failed/9errors are absent new API definitions
(the9 fixtures could not construct the absent _Witness), not native/setup or
credential effects. Privacy integration RED1failed/28passed exposed checksum-valid
unknown-field acceptance; fixed closed projection. Outcome RED2failed exposed
incorrect gate-write-as-ACK and absent numeric error metadata; both fixed. Earlier
GREEN38/215 overlapping results and Windows POSIX skips are interim, not current
final verification; exact final commands/results are indexed in ignored evidence.
Initial Node orchestration missing process/W names and initial E501/static failures
are local harness/static issues, never product/runtime diagnoses. No original
Source CLI, native fixture/host/auth/UI/SDK/CI was run in this software phase.

Reviewer: fresh independent implementation Spec/Quality R1 follows coherent GREEN,
maximum one known-fixR2; Parent owns publication/CI/catalog. Target19:22Z first
software result is retained; no reset. A future diagnostic run is currently
BLOCKED by the existing consumed fixed-nonce marker; no fifth start is implied.
All old images/claims/controls/history and root holds remain retained.

Verifier coherent software boundary: COMMIT-AFFECTED234passed/42skipped in5.60s
(four directly affected files;48new witness passes/6new POSIX skips overlap).
All42 are platform-dependent skips on Windows, not Linux/native acceptance.
Scoped Ruff/format/Python3.12 syntax/diff/submodule pass on final code. Gate write
attempt/return/ACK, requested/sent cleanup signals, pre-fork no-child no-reap0,
registration-failure reap->nonblocking report drain->close, original prepare
cgroup denial before new file creation, close-attempt versus confirmed-close,
checksum-valid private extras and primary-error precedence have direct controls.
Every RED/harness/static failure remains retained. No unknown report/EOF/ACK is
promoted into exec; content/stream/durability remain separate. Fresh implementation
R1 remains pending; no production/root-cause/login completion follows.


### Witness R1 and one known-fix wave

Reviewer: fresh R1 on4859d8 is Spec FAIL/Quality NOT_READY, sole Important issue,
no Critical finding. Immutable report SHA256
1e61247fcdcc099f2f9c25493abfb669b5d4f8e875d591ab97a3ff441ca0c804.
Actual executable observation succeeded, then its event persistence failure was
caught as benign UNKNOWN. A released persistent child could continue despite
failed instrumentation. This is a diagnostic software defect, not evidence of
the earlier fourth-start exit cause.

Implementer: only that observation function changes: keep benign probe failures
UNKNOWN, emit the observed event outside its catch so real record errors reach
existing owned/backend cleanup. Never deny release already occurred. Verifier:
actual observation plus actual release/persistent main, with synthetic admission/
metadata, RED4failed/1passed for ENOSPC/EIO/shortwrite/guard, thenGREEN5passed;
assert released/ack/executable observation true, cleanup attempted, no success
receipt and no loop continuation. Benign unobserved probe is separately UNKNOWN.
The original failure, all interim results and ACL issue remain retained. Windows
Python-created temp directories had two explicit foreign grant classes; normal
DACL-only direct icacls removed them. The first PowerShell native-pipeline refusal
is preserved; no escalation or SACL change, final private check must be0bad.

Planner/Quant scope is unchanged: no root-cause fix, schema/marker/claim/gate or
resource change, no host/Source CLI/native/SDK/UI/fifth start. Same fresh reviewer
gets one scoped R2 after the known-fix commit; no self-READY/third round. Parent's
parallel future diagnostic proposal is a separate unapproved protocol disposition,
not implemented or executed by this software wave.

Known-fix final verification:174passed/6POSIXskipped/5.55s, witness+direct recovery
lifecycle only; scoped Ruff/format/Python3.12/diff/submodule pass. This overlaps
prior results and does not replace the original R1FAIL or claim Linux/native.
Same-reviewer scoped R2 remains pending; no push/CI or operational action.


### Invocation-witness scoped R2 closure — software only

The same fresh reviewer on bbb1df82707b0d830f01455633bf3e35c7fe664d reviewed the
single known-fix range: sole Important ADDRESSED; Spec PASS/Quality READY; zero
new Critical/Important. Immutable REVIEW-R2.md SHA256
41dc9c7dd8a441b581e0449c49963de58622daf6d89e7629396c282f8a5745e0;
original R1 FAIL is preserved, no R3 or fabricated human review. No tests/runtime
were rerun by reviewer. This closure changes plan/iteration only; source/tests
remain exactly bbb1df. Windows/synthetic evidence does not prove full protected
file/inode integration, actual owned-kernel cleanup, Linux/native qualification
or the earlier exit cause. Backend/window/SDK and a fifth start remain unapproved.
Parent's diagnostic-1 proposal is separate and unimplemented. Parent owns normal
exact-head publication/CI/catalog after this branch's ordinary push; no force,
new protocol or operational action follows from software READY.


## Fixed diagnostic-1 approved design checkpoint

Actual human approval call_667904a5ea5645c4b62f045ccb4782b6 is recorded in Root
resume-after-pr270-20261101.json; historical unapproved proposal remains unchanged.
[design](../superpowers/specs/2026-11-01-opend-diagnostic-1.md) and
[plan](../superpowers/plans/2026-11-01-opend-diagnostic-1.md) define strict schema5,
fixed diagnostic-1 consumption and heldRO original spent evidence, same unit/image/
claim/prior, source-enforced90s with no timing rebase. Source guard's only runtime
change will be explicit fixed5 eligibility, not a kernel exception. Old control
may be renamed only to fixed protected history with REAL post-rename stamps;
old consumed files/claim are never renamed/deleted/reset. Known runtime public
artifact collisions are pre-start STOP risks, not unapproved cleanup permission.
Planner scoped one task; Quant no data/math/SDK/trial; Implementer design only,
no fetch/branch/code/test/host; Reviewer Parent scan pending; Verifier fresh local
physical/authority pins only. Source40MiB was registered once; old holds/failures
and new8MiB finite envelope remain, N24/remote72/ops8 unchanged. Conditional fifth
is not executed; backend/window/SDK remain UNMET.

### 2026-11-01 fixed diagnostic-1 software checkpoint (Refs #263)

Planner: actual human approval and Parent design/conflict scan select exactly one schema5/diagnostic-1 authority, held old schema4-control/ATTEMPTED evidence and <=90s source-enforced lifetime; future fifth start remains unexecuted/conditional. Shared interfaces are strict recovery shape/name/lease, stage witness+deadline, storage eligibility and mechanical pins. No marker/claim reset or new manager/resources. Quant: no dataset, SDK, strategy, market/order or confidence-promotion work. Implementer: branch codex/0038-opend-diagnostic-1 from freshly fetched actual b8ce; old branches/localmain retained. Old c8 schema3/4 active grants stay spent; ordinary non-c8 legacy lifetime remains. Child remaining alarm and parent frozen monotonic deadline do not restart after consume.

Verifier: genuine old-source RED9failed/12passed; first protocol GREEN21; direct actual-spawn RED4failed then corrected signature; exhausted-deadline category RED2failed/1passed then distinct DEADLINE frame. Initial path harness21setup errors, duration expectation2fail, affected first30fail/118pass (synthetic digest/clock setup), and intermediate spawn error-expectation1fail/16pass all retained separately, not relabeled as successful TDD. Final current-code direct affected run:279passed/42Windows-POSIX-skipped, scoped Ruff/format/Python3.12 compile-only/diff/submodule checks pass. No staging-host/native qualification. Reviewer: fresh Parent-assigned R1 pending, at most one known-fixR2. Actual four starts/old ATTEMPTED/original claim persist; backend/window/cause/SDK remain unqualified.

Capacity: initial private-test4MiB next-run forecast stopped before execution; retained artifacts were not deleted. Actual Root net4MiB supplement after prior8MiB makes Source44MiB/newpurpose12MiB, fullforward46026680<46137344 with oldforward33443768 preserved. The private9MiB tmp envelope includes directory allocation, unique basetemp/-B/no cacheprovider and retained failures. No hold refund/borrowing or additional execution permission is inferred.
