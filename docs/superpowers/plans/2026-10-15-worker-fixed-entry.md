# Fixed standalone Worker entry and source-bound preflight

Issue #172, kernel dependency985f8a3. This is the next implementation part of
the approved full Worker/parent chain, not a narrower final acceptance. Preserve
all full numerical/report/recovery/PG/Agent/server-source requirements.

The stopped a718900-line object-graph proposal is not revived. Implement only
the missing canonical entry and externally sealed source/binding association
now; no new cache exception, image certificate, native permission or saved-bool
provider. Existing `_child_main` retains all actual runtime/Reader/report guards.
The full creation/current-state/native-load observer remains a required later
integration into the same entry, before numerical image admission.

Canonical layout: /opt/quantmesh/worker_entry.py,
/opt/quantmesh/quantmesh/research/worker_provenance.py,
/opt/quantmesh/quantmesh/research/worker_build.py,
/opt/quantmesh/manifest.json and inventory.json. Package root is /opt/quantmesh;
the actual Python installation is /usr/local CPython3.12.15, exactly81 frozen
distributions. No site/.pth/pyc, venv-prefix adjustment or alternate argv.

Entry only accepts the fixed binding/manifest/inventory paths plus the expected
binding SHA appended by the trusted bootstrap go channel. Require actual Linux
x86_64, -B -I -S, /usr/local prefix and /usr/local/bin/python3, version3.12.15
before project/numerical/job imports. Read <=16KiB binding with component-wise
no-follow directory handles, regular/single-link/unchanged named/held identity;
verify the externally received SHA before parsing any binding fields. The entry
and observer bytes must match its entry/observer digests. Load only verified
observer bytes at its actual fixed filename; never rewrite sys metadata or read
expected SHA back from a file. Errors are one fixed sanitized rejection/exit2.

Source observer validates bounded, duplicate-free binding/manifest/inventory
JSON and exact current sealed source associations. Reuse ParentBindingContract
only after worker_build bytes and all package source bytes are bound to the
externally pinned manifest/inventory. Exact ordinary membership and every source
digest remain required; canonical metadata exclusion uses the integrated fix.
Only then append the actual verified package and site-package search roots,
without importing site or arbitrary caller paths. No public session setter,
qualification boolean or exception for originless native code is introduced.
Revalidate binding, entry, observer and metadata/source bytes immediately before
calling existing `_child_main('/inputs', output_directory='/output',
build_manifest=<fixed>, manifest_sha256=<independent>)` and after it returns.
Output files on a refused child cannot be published by the unchanged parent.

Files: new deploy/research_worker/worker_entry.py,
src/quantmesh/research/worker_provenance.py and tests/test_worker_entry.py.
Do not change worker_build, job_runner, baselines, store/schema, locks, OCI
ownership/bootstrap, services, GUI/helper/tunnel or shared docs in this part.
Expose only a source-preflight observation if needed; explicitly no native or
Engine/CID certificate. A valid synthetic source binding does not qualify a
real parent or permit opaque caches.

Root software reservation:8MB new source/fixtures/evidence phase, cumulative
123MB from prior115MB allocation; carry actual110,709,736B/all prior failures
and pending whole-C attribution forward. Existing WSL Python only, fresh
/var/tmp/quantmesh-entry-* basetemp, no C-mounted/global-temp fixtures, cache
disabled, bounded120s/log64KiB and free>=50GB. No image/build/clone/install/AWS
or CI repeat in this software part. Root owns eventual exact source-image
materialization under original AWS5GB/free50GB limits and scoped recipe review.

- [ ] TDD actual subprocess entry refuses unsupported real host flags/prefix
  before project/job imports; malformed/duplicate/noncanonical/wrong-SHA binding,
  missing/mutated/shadowed/link/ancestor-swap entry/observer/source/metadata,
  altered fixed paths and unsealed extra files reject. No caller hooks/descriptors
  or arbitrary decoder are invoked before source admission.
- [ ] Minimal fixed entry and source observer, reusing existing contract/math.
  Test valid bounded source preflight separately from image/kernel permission;
  preflight failure prevents the child callback, and a post-call mutation rejects
  child success. Do not make fake native admission to get a green numerical test.
- [ ] Focused fresh native-Windows-platform-neutral and real Linux source tests,
  raw RED/GREEN/exit/resource receipts, Ruff/format/diff and one scoped review.
- [ ] Root commits coherent source checkpoint, then builds a reviewed immutable
  source-derived image, adds actual kernel/parent/creation provenance, and runs
  the full registered baseline/report/two-job-reclaim/service acceptance.

Checkpoint: final root combined49pass/18.53s and Ruff/format/diff pass.
See the mirrored iteration for review correction, retained REDs and resources.
Complete positive fixed source preflight, actual different-UID container access,
source-derived image/current-loader/parent/native admission and full numerical
reports/recovery remain required; no source-only test is an image certificate.
