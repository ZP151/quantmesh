# Held snapshot UID and read-only permissions before container creation

Issue #172, approved complete Linux Worker chain. Canonical fixed-entry software
is independently owned by worker_fixed_entry_implement on three NEW files.
Root owns this nonoverlapping bundle handoff and existing Worker integration.

The parent copies a sealed snapshot into a private attempt bundle, but snapshot
directories are0700 under the parent's UID. The actual container UID may differ;
read-only bind alone does not give it access. Handoff must change only this
fresh private bundle's metadata before creation, never the source lake/shared
files, decode data or grant broader file access.

Files: new src/quantmesh/research/worker_bundle.py and tests/test_worker_bundle.py;
bounded call in worker_execution.py after runtime/current admission and parent
binding-provider presence, before LinuxOwnedProcess. Existing math/store/Reader,
schema, OCI ownership and frozen command remain. Relevant affected test module
test_worker_execution.py uses independent tiny queues; adjust only covering
integration evidence if needed, not its admission/exit/fence assertions.

Exact dependency exception: job_runner.py's Linux-only `bundle.mkdir()` must
use mode0700 because its current default0755 would violate this private handoff
precondition. Change this one mkdir argument only; no runner protocol/math/lease
or output changes. Root owns it, with existing affected Worker cases as coverage.

Use existing DirectoryHandles: component-wise no-follow acquisition, relative
held opens and stable named/held file association. Enumerate <=4096 entries,
<=257MiB regular single-link bytes, no special/link/hardlink/mixed-owner files;
roots must be nonoverlapping trusted attempt bundle with actor-owned private
directories. Preflight collects all nodes/descriptors/metadata before any change.
Allow only root or the identical caller UID/GID target; unsupported privilege
refuses before mutation. Files become0400 and nested dirs0500 for the configured child.
The bundle root stays0700 for the same UID/root parent to create its exclusive
binding after controller readiness, before go. Its child bind remains read-only;
0700 is not child write authority. No shared/group/world permission is granted.
Never chown/chmod ancestors outside the actual bundle. Planned owner/mode updates
are accepted only after unchanged dev/inode/type/size/mtime/nlink association;
verify current namespace membership after updates. Do not claim timestamps
detect every transient namespace edit. No file content/decoder/model/job parsing.
Any failure before start leaves the owned attempt failed/retained; no unrelated
rollback, cleanup, restart or container. No metadata token grants admission.

Reservation uses the current8MB source-entry/handoff software phase and123MB
cumulative ceiling; previous110,709,736B/all failures retained. Existing WSL
runtime only, fresh native /var/tmp fixtures, no C-mounted/global tmp; free C and
WSL>=50GB. No sudo/credential/permission policy change, AWS/container/image/new
environment/install or full-suite repeat in this software part.

- [x] RED genuine same-UID Linux handoff validates exact modes and unchanged
  bytes, no content reads, sibling untouched and no ancestor metadata changes.
  Reject links/FIFO/hardlinks/foreign owner/unsupported target/bounds before
  mutation; cover renamed/replaced association through actual held descriptors.
- [x] Implement bounded held metadata-only traversal and integrate before create.
- [x] GREEN own module plus existing worker_execution affected cases on fresh
  native roots; retain failures/resources, Ruff/diff and one scoped review.
- [ ] Later real different-UID AWS/container source access and complete numerical
  report/reclaim remain actual acceptance gates, not certified by these fixtures.

Checkpoint: final root combined49pass/18.53s and Ruff/format/diff pass.
See the mirrored iteration for review correction, retained REDs and resources.
Complete positive fixed source preflight, actual different-UID container access,
source-derived image/current-loader/parent/native admission and full numerical
reports/recovery remain required; no source-only test is an image certificate.
