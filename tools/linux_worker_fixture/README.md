# Task1 standard-library OCI fixture

This recipe contains the fixed offline controller and standard-library test
fixtures. It is not the numerical Worker image or a service deployment.

The pinned official Python Linux amd64 manifest is
`sha256:9ce5a4e59b833c002e1c4196c60ec0b38977e3235d626298ba7ffe2e64f5a30c`.
Official packaging Git is `2a3b794c223ab067d122719541cdd54a068732a5`,
`3.12/alpine3.23`, CPython3.12.15 source tar SHA256
`c2c4321961fab0fb999d66e0cecf521c2ab3994c7992873ea99e306c1094fd5a`.
Public immutable source metadata/SPDX/provenance were verified before root
admission. Docker Engine29's containerd store exposes manifest-based Image IDs;
registry config digests are recorded separately and never substituted for IDs.

Run `PYTHONDONTWRITEBYTECODE=1 python -B tools/linux_worker_fixture/prepare.py
--output <new-absolute-owned-context>`, recording the printed file hashes.
It adds the exact current repository bootstrap bytes to the nine-file context.
Preparation never pulls/builds/runs or modifies Docker/global state. The source
stage copies reviewed immutable bytes using offline RUN; final `FROM scratch`
does not inherit GPG_KEY, volumes, pip, shell, package manager or optional GNU
extension libraries. The constant amd64 FROM is intentional and can cause a
nonblocking Docker lint warning; other platforms remain outside qualification.

Final native dependencies are CPython, musl and libcrypto; curation checks ELF
DT_NEEDED and records every selected byte in `/opt/quantmesh/runtime-files.json`.
Pure stdlib/ext module hashes missing in upstream SPDX are pinned by complete
base layer digests, then measured after materialization. All selected actual
files, dependency edges, notices, controller SHA, image config and smoke imports
must pass before native witnesses. Source/image admission alone is insufficient
to certify cgroup, owner-loss or namespace behavior.

`licenses/` preserves CPython PSF/historical/embedded third-party notices, musl
MIT, OpenSSL Apache-2.0 and QuantMesh Apache-2.0 texts. The full transient base
SBOM includes additional GPL/LGPL/pip/meta packages; this remains disclosed
build material, with root acceptance for this qualification use. Those extra
components are excluded from final fixture runtime. Optional stdlib features
requiring excluded modules are unsupported. No package was added to core locks.

The October13 local witness used owned labels/IDs/nonces, five-billion-byte new
temporary total ceiling, fifty-billion-byte C free floor, and no global prune.
Default BuildKit leftovers are measured and retained when per-build deletion
cannot be safely proven. Exact raw immutable evidence/source/context/image and
cleanup identities are listed in the runbook and handoff. This temporary local
evidence does not deliver the long-term AWS service or admit Task2.

`evidence/index.json` binds the immutable compressed evidence archive, including
the exact executed context bytes and the four tested source files. Checkout
line-ending policies may change text serialization; prepare and seal a fresh
context and admit its actual image before any subsequent native qualification.
The October13 native15/15 result passed. The post-cleanup conservative whole-volume
disk-delta gate failed despite stable attributable files/cache; its unresolved
attribution is retained separately and is not reported as storage acceptance.
