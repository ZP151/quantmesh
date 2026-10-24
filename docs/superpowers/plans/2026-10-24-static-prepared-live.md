# Static prepared-live initialization leaf

Issue218 follow-up to mergedPR219/6612f50; original CI40061381811 and B1 STOP
remain unchanged. Root's narrowed authorization2026-10-24, actualACK08:33:55UTC/
16:33:55SGT; hard17:33:55SGT60min, first10min16:43:55, freeze target17:13:55.

## User action / measurable outcome / non-goals

One real first startup on the sole operator's explicitly prepared, still-empty
fixed16MiB live mount can write its own real intent/header/session and DB.
Ordinary existing directories, missing/mismatched trust facts and partial
admission remain refused. No new privileged launcher, per-PID receipt, inherited
FD protocol, setting/API/service/dependency/Goal/provider or actual mount work.
Runtime files only live/buffer.py and new live/prepared_mount.py. New focused
tests; necessary ADR/iteration. Existing feed/history/settings unchanged.

## Static trust and bounded operator assumptions

Optional budget field prepared_live_receipt_sha256 pins one static root-issued
JSON at /run/quantmesh-live-prepared/<SHA256(canonical_root_utf8)>.json. None is
excluded from header serialization, preserving exact old legacy header bytes.
Receipt binds core budget SHA excluding that new pin (avoids cycles), root and
live dev/inode, fixed loop/backing16MiB identity/UUID/fsid/geometry, protected
lost+found identity and root's actual empty listing, boot/deployment/unit cgroup,
source/runtime facts and finite expiry. No bool passed, no invented peak hash.
Root-only regular0444/single-link/<=16KiB, root-owned non-writable parent chain,
no-follow open and before/after fstat. Solehostoperator issues it using actual
existing release/runtime/physical/earmark receipts; no per-process signing.

App opens its own root/live FDs, reads actual proc mountinfo/fdinfo/ns/cgroup and
sysfs loop mapping, checks stat/fstatvfs, expected source module hashes/Python
identity/version/DuckDB version, current UID/GID and boot. Held descriptors and
current named mount identity are checked again at write/close boundaries.
UUID/backing inode are root-attested facts mapped to the actual kernel device;
app receives no raw-device/backing authority. Root's existing controlled unit
owns namespace isolation, no CAP_SYS_ADMIN/rawloop/resize and no concurrent
remount. Its bounded acceptance profile must be single-start Restart=no, as the
existing no-second-start window requires; receipt binds actual unit cgroup and
that property, app has no restart loop. This closes pre-intent all-write-failure
auto-restart without inventing a privileged startup protocol. No automated root
reissue/restart after failure is authorized.

Fresh directories only: root:existing app GID01770 for budgetroot and mounted
root; root:root0555 underlying live, preserved root0700 lost+found. Sticky parent
protects root-owned live from rename after loss; native fallback cannot write
the0555 underlying directory. No existing owner/mode/ACL/link checks relaxed.
Root's protected empty lost+found witness plus current matching inode/mode and
only-that-name root listing is required; nonempty/foreign content is never removed.

## Exact new-mode initialization

__init__ validates optional receipt and all facts. Header absent permits only
root entries {live}, zero intents/session/stop/partials, verified first-live
empty state. Defer new-mode header write; keep pending-first on this instance.
start_session rechecks identity/emptiness, then calls genuine reserve for intent1,
fsyncs it, writes genuine header, fsyncs, writes genuine open-session1, fsyncs;
only then existing LiveBuffer opens DuckDB on fixed live. No record is preseeded.
Header already present/zero intent and all partial states remain refused.
Legacy without the field keeps its original order and guards.

Every new-mode availability/reserve and successful DB-close-to-clean-publication
boundary rechecks the same mount. Failure poisons before terminal bookkeeping;
original open-session/no-auto-rearm remains. Partial files are never repaired or
removed. Static receipt is neither peak proof nor write authority without facts.

## TDD / bounded handoff

- [x] Actual controlled RED on merged behavior: valid modeled static prepared
  mount with real tiny files cannot pass constructor/nonempty/start_session;
  legacy header bytes and refusal are pinned. Models explicitly not real mounts.
- [x] Minimal helper/branch GREEN with root receipt and kernel observations
  modeled on Windows; actual metadata/intent/header/session/DuckDB effects remain
  real. Verify no fake records before start_session.
- [x] Reject missing/foreign receipt, permissions/link/type, nonempty/lost+found,
  fake/mismatched mount/device/sysfs/boot/unit, partial header/intent/session,
  failure/crash and mount loss; preserve source/history boundaries.
- [x] Targeted checks/changed Ruff/format/diff, coherent freeze commit.
- [ ] One independent known-scope/affected boundary review, <=2rounds/one
  aggregate correction. Third structural issue/time expiry => precise STOP.
- [ ] Exact reviewed handoff to sole publisher for new exactCI/normal merge.

No old full suite/CI rerun, runtime environment, host/real DB/provider/physical
receipt/earmark manufacture. Static R and changed header allocation must be
included in operator's actual outside1MiB coverage; not proven by unit GREEN.

Actual checkpoints:60RED1/61GREEN24;62RED2/63GREEN45;65RED1 root-group gate;
68affected170pass/2Windows native-fsync skips/6warnings49.22s. Lost+found on
foreign FS69RED1 then final70GREEN59/2warnings5.17s. Changed checks71 pass.
All initial failures/format issues retained. Freeze for independent review;
no whole/native suite or actual static credential/mount qualification occurred.
