# Fixed c8 OpenD private storage implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans. Implement inline, then one fresh independent whole-slice reviewer; R1 plus one known-fix R2 maximum.

**Goal:** Admit the original c8 recovery only with six writes on one finite persistent disk image.

**Architecture:** A pinned stdlib private_storage helper separates closed public
profile/layout validation from live metadata capture. A c8-only drop-in and schema4
profile digest connect that guard to the existing recovery gate. A finite isolated
synthetic fixture proves the shared filesystem mechanics after publication.

**Tech Stack:** Existing Python/pytest/Linux ext4+OverlayFS/systemd/Git CI only.

**Spec:** ../specs/2026-10-31-opend-private-storage.md

## Global Constraints

- Fixed c8/UID997/GID987; original source/vendor/endpoint/base unit/initial behavior.
- One33554432B persistent image, six writable targets, readonly original lower and
  nine-field claim; no credential/image-payload/terminal reads, copied source or installs.
- Original1GiB/high768MiB/swap0/CPU50/tasks128/no restart/boot/live. Disk is not RAM.
- Existing16MiB local/72MiB remote fullholds; all old failures/images retained.
- No actual profile/control/start/SDK in software. Native fixture only after merge
  and sealed finite execution plan; production remains a later Root release.
- Base d9f12e0e83f3cac5489438f9885fd3f03e94afac, branch codex/0038-opend-private-storage.

## Review Focus

- An ancestor or nested foreign writable mount must not inherit a six-target exemption.
- First overlay copy-up and marker fsync must not change the original claim binding.
- Profile/image/loop/mount drift during a successful check must deny before vendor release.
- A legacy c8 recovery control or initial/other unit must not gain a drop-in exemption.
- Native fixture must preserve one image/marker and close only its owned namespaces/loops.

## Task1: closed finite layout and c8 drop-in

Files: create deploy/aws/opend/private_storage.py;
create deploy/aws/opend/quantmesh-opend-console-c8-private-storage.conf;
create tests/test_opend_private_storage.py.

Interfaces: parse_mountinfo(raw: bytes)->tuple[Mount,...];
validate_snapshot(profile: dict,snapshot: dict)->None raises StorageDenied;
capture_live(profile: dict)->dict reads fixed kernel/image metadata only;
validate_live(claims: dict)->None binds protected fixed production profile and live observations.
Constants own all destinations/pool/image/profile/alias names,33554432B and c8 identity.

- [x] RED valid six-target snapshot cannot be admitted by absent guard; run
  `python -B -m pytest -q tests/test_opend_private_storage.py` with retained RED log.
- [x] Implement strict profile/mount parser and finite layout checks, without native effects.
- [x] GREEN and negative vectors: missing/duplicate mounts, wrong lower/upper/work,
  differing loop device/root/fsid/geometry/image inode/size/owner, readonly writes,
  rw lower/claim/alias, extra nested/ancestor regular mount and writable tmpfs.
- [x] Add live capture tests proving fixed reads only, profile hash/live identity and
  mount snapshot recheck; source never reads original HOME/STATE or image bytes.
- [x] Record role/RED-GREEN evidence and commit one coherent guard checkpoint.

## Task2: recovery authority and exact manager/gate wiring

Files: modify deploy/aws/opend/same_unit_recovery.py and stage_console.py;
update tests/test_opend_same_unit_recovery.py only as needed;
add focused integration cases to test_opend_private_storage.py.

Interfaces: closed schema4 = schema3 fields + storage_profile_sha256, fixed c8/997/987.
RecoveryWindow c8 _admit invokes pinned helper.validate_live(claims); manager contract
adds exact c8 drop-in SHA/path and namespace properties. Existing final _admit call
reuses it; no new consume/backend/timeout/order mechanism.

- [x] RED schema4 c8 control with valid profile/layout reaches existing check, while
  missing digest/old schema3 c8/profile drift denies without marker/vendor release.
- [x] Implement strict schema4 and recovery-only manager/admission integration; update helper pins.
- [x] RED/GREEN manager wrong drop-in/SHA/PrivateMounts/PrivateTmp/StateDirectory/
  RuntimeDirectoryPreserve/ReadWritePaths, and guard drift after marker fsync.
- [x] Verify original nine-field claim/one O_EXCL/spent-failure regressions plus
  legacy initial/schema3 non-c8 unchanged. No real vendor, credential or SDK calls.
- [x] Run affected OpenD tests, focused Ruff/format/compile/whitespace and update iteration;
  commit tested recovery integration. Linux-only skips are not native passes.

## Task3: finite native fixture, review and normal publication

Files: create deploy/aws/opend/private_storage_fixture.py;
create tests/test_opend_private_storage_fixture.py;
create docs/iterations/0038-opend-private-storage.md;
update ADR0032, REUSE_MATRIX and ROADMAP narrowly.

Interface: fixed main()->JSON receipt, no arbitrary args; existing root-only entry
requires isolated preparation namespace, one retained fixture image, hard240s and
owned cleanup. Nested namespace runs common layout inspection as997/987; parent
verifies outside socket and controls remount of same image. No effective grant.

- [x] RED fixture rejects original mount namespace/foreign preexisting image before
  allocation, and failures close/join only owned child/mount/loop handles.
- [x] Implement finite construction/proof/cleanup and safe stage-specific diagnostics;
  no automatic retry, new image, shared path mutation or global remount.
- [x] Verify offline control flow with syscall/process adapters for failure cleanup,
  one-image identity, aggregate exhaustion, remount-spent and declared paths. Do not
  label these substitutes native evidence; actual native result remains pending.
- [x] One fresh spec+quality reviewer on exact whole slice; fix only confirmed
  blockers with RED/GREEN then known-fix R2. Third structural failure => Planner STOP.
- [ ] Run relevant broad affected/static gates at final boundary, normal push/PR,
  attach artifact, required exact-head CI green/ready/no unresolved threads, normal
  expected-head squash. No force/admin or fabricated human review.
- [ ] Verify complete merged-tree equality/source catalog and retained budget.
  Seal exact native240s plan/packet for original executor; native/provider remain separate.

## Completion checklist and self-review

- [ ] All spec requirements map to the above tasks; interfaces/types consistent.
- [x] Six writes share one geometry in the source contract; native proof remains pending.
- [x] Profile/control/helper/drop-in pins and base-template preservation agree.
- [x] Claim and spent-marker semantics unchanged; new guard runs at final admission.
- [x] Source/tests/docs/iteration evidence agree; actual native/login still honestly pending.
- [x] Plan proportion/step scan/review-focus coverage checked before implementation.

Verification: Python313 `-B -m pytest` focused new tests while iterating; affected
OpenD suite plus scoped Ruff check/format, in-memory compile, git diff --check and
submodule pin check at commit/final boundaries. Existing exact-main broader CI is
not rerun for baseline; final PR required release checks run normally. No installs.


## Propagation repair checkpoint — 2026-10-31, Refs #263

This supersedes pending-publication/native wording above only where actual
iteration evidence closes it: PR264 and its synthetic native fixture passed;
PR265/PR266 were normally published. Actual original backend/window remains UNMET.
Selected contract: the final namespace propagation amendment in the storage spec,
and ADR0032. Scope is one original operator action, not a new provider platform.

- [x] Reuse the sparse isolated checkout; fresh origin/main17c82e1 has no relevant
  drift. Branch codex/0038-opend-mount-propagation; preserve old branches/main.
- [x] Before production edits, add independent full base+drop-in effective vector,
  manager MountFlags missing/empty/shared/private/unknown controls through the
  real existing start/recovery gate, and KernelWorld per-mapping propagation
  plus unchanged safety predicates. Record genuine old-source RED separately
  from test seam failures; production hashes remain exact17c82 at RED checkpoint.
- [x] Add MountFlags=slave, c8-only exact manager scalar and mechanical drop-in SHA.
  Guard/recovery/base/fixture and all binds/alias/claim/resource settings frozen.
- [x] Run same targeted two files GREEN, then the directly affected three files
  including software fixture tests. Root explicitly selects this complete affected
  boundary instead of unrelated full-local/frontend/native suites. Run scoped
  Ruff/format, Python3.12 syntax, diff --check and submodule pins at final boundary.
- [x] Update iteration with Planner/Quant/Implementer/Verifier, complete contract,
  current user-loop limits, retained failure paths and finite Source12MiB forecast.
- [ ] Parent assigns a fresh independent Spec/Quality reviewer; max R1/known-fixR2.
  Third structural failure returns to Planner. No self-review substitutes for it.
- [ ] Parent owns push/PR Refs263 (not Closes), exact-head selected CI/aggregate,
  normal expected-head merge and complete actual merged tree/source catalog.
- [ ] Only after publication and Parent's bounded operational release use the
  existing single formal packet with matching propagation/source/readback pins.
  One full Source admission, normal actor closure, fresh gates then at most one
  original fourth start. All error/unknown results stop; no automatic retry.

Verification commands use existing Python313 -B -m pytest -q -p no:cacheprovider
with unique retained basetemp in propagation-repair-01, for
 tests/test_opend_private_storage.py tests/test_opend_same_unit_recovery.py
and at the final affected boundary also tests/test_opend_private_storage_fixture.py.
No environment/dependency, host/auth/UI/SDK, Source CLI/native fixture or CI run
is part of this local implementation checkpoint. Parent owns later CI once.


### Known-fix R1 addendum checkpoint

R1 READY on d66/12ad is superseded by R1-ADDENDUM.md: its full-vector model missed
the shared bind reset. The historical checked box above is not current acceptance.
- [x] Preserve old model/source/derivers and R1; correct test model first.
- [x] Observe actual old-config RED:1failed2passed, zero effective writable binds.
- [x] Move both empty resets before all nonempty pairs; mechanically refresh pin.
  No guard/helper/base/fixture/observer/resource or pair/flag changes.
- [x] Add reset-both-directions/mixed-append literals;24 targeted and276 affected
  tests pass. New disabled candidate formal deriver yields the exact6RW+2RO.
- [ ] Same fresh reviewer known-fix R2 only, then Parent-owned new-head CI and
  normal expected-head merge/catalog. No third structural review/host retries.
