# Fixed-entry image metadata without a self-hash cycle

Issue #172, kernel dependency branch0e27bd9; parent PR175370a745 unchanged.
Approved Option A fixed-entry/parent chain stays required, numerical algorithms,
costs, reports and source/81-dependency/native-cache gates remain unchanged.

Actual layout for the frozen command is source_root=/opt/quantmesh, package
/opt/quantmesh/quantmesh, and entry=/opt/quantmesh/worker_entry.py. Manifest and
inventory must be /opt/quantmesh/manifest.json and inventory.json. They share
the source root, so the present strict complete-file inventory would require
their own hashes inside themselves. This is an impossible self-hash cycle.
Do not invent prefixes, move the fixed argv or waive complete source coverage.

Planner: independently SHA-sealed metadata is checked separately from the
ordinary file inventory. In `_inventory`, accept ONLY the current inventory
path with its already expected digest and the caller's current manifest path
with its independently supplied digest. If either is inside an inventory root,
it must have the canonical JSON filename and is omitted only from ordinary-file
membership; validate bounded actual bytes and hash before and after inventory
verification. Neither may also appear in files/symlinks. No other JSON/file is
excluded. Existing external-metadata fixtures remain compatible. Preserve
three-key inventory, eleven-key manifest and five-field runtime schemas.
This is metadata association, not native cache or image/parent admission.

Implement only src/quantmesh/research/worker_build.py and tests/test_worker_build.py.
Root owns shared docs, entry/image tooling, actual SSH and release. Existing
interpreter-link late-mutation test wrappers must accept the internal manifest
keyword if necessary; keep their actual mutation and refusal assertions.

Initially reserve2MB new software phase/cumulative114MB from prior112MB allocation;
carry108,397,325B measured upper and every original failure forward. No new
environment/image/container/dataset or paid resource in this software slice;
fresh owned native WSL fixture directory, free>=50GB. Do not delete old roots.

- [x] RED canonical manifest/inventory inside source root with all ordinary
  files pinned must pass without metadata self-digests. Add refusal of changed
  manifest/inventory bytes, noncanonical covered metadata names, unsealed extra
  JSON/source files, metadata-listed-as-file/link, and late metadata changes.
- [x] Implement the two independently sealed metadata paths only. Preserve
  raw byte/order/duplicate/path/source/RECORD/native-helper refusals.
- [x] GREEN entire worker-build/binding suite on existing WSL Python with
  bounded120s/owned basetemp, retained raw logs/exits and fixture sizes;
  Ruff/format/diff, one bounded fresh review, coherent checkpoint/commit.
- [ ] Continue immutable fixed entry/source image, independent actual parent
  and complete numerical report/recovery; no Linux Worker default activation.

Root continuation: agent's C-mounted fixture GREEN attempt hit120s/exit124 and
one unflushed failure; preserve it and do not claim its cause. The same source
on fresh WSL-native fixtures passes71/7.17s. The prior interpreter late-link
wrapper omitted new keyword forwarding, so it could refuse on TypeError before
the mutation. Add a mutation marker RED, then forward kwargs and verify the real
mutation occurs. Before those extra focused/full checks, extend THIS software
phase to3MB/cumulative115MB, retaining the earlier2MB reservation, all bytes,
failures, no reset/cleanup and no paid resource. No unnecessary healthy rerun.

Root final71pass/6.81s plus added source-case1pass/4.32s; bounded review clear and Ruff/format/diff pass. C-mounted124/unknown unflushed failure, initial misplaced-marker result and true marker RED all retained. Canonical entry/derived source image/independent parent/full Worker remain pending.
