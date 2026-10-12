# Linux Research Service Qualification Plan

**Issue:** [#171](https://github.com/ZP151/quantmesh/issues/171), approved A
iteration0038; this refines the unfinished Linux environment gate in Task2 of
`2026-10-12-research-workers-workstation.md`.

**Goal:** Make the independent service's actual Linux dependency environment
reproducible without treating the existing Windows lock as Linux evidence.

**Architecture:** Keep the existing service/JobStore/advisory boundary. Resolve
the existing core dev and service dev requirements on an owned WSL
Ubuntu CPython3.12.3 x86_64 environment, under the existing audited constraints.
Capture the resolver's exact public-registry wheel hashes in a distinct Linux
lock. The separate gate binds lock selection to measured platform/Python/arch;
no unqualified runtime silently falls back to the Windows certificate.

**User outcome:** An operator can reproduce the service dependency/API checks
on the declared Linux target and see which native/DB/deployment proofs are absent.
Success is a hash-enforced fresh install, matched frozen schema/protocol,
complete license inventory and actual Linux offline service tests.

## Ownership and non-goals

- Root owns `services/research_agent/requirements.linux-cp312.lock`,
  `tools/research_service_gate.py`, `tests/test_research_service_runtime.py`,
  the service README and shared iteration/ACTIVE checkpoints.
- #173 continues in its independent worktree; do not edit its leaf screen,
  facade/client/options or browser witness. At most two current implementers.
- No system Python/apt, Docker Engine configuration, production/AWS/OpenD,
  credential, model call, paid resource, core lock or workflow change.
- No new SDK/strategy framework or upstream code copying. Reuse the existing
  package closure. Public installer tools stay in the owned development venv.
- WSL package/API tests do not certify the immutable OCI image, aggregate model
  process-tree limits, Linux Worker publication/recovery, real PostgreSQL,
  off-host backups, actual model or production source independence.
- Docker Engine activation, real disposable PG and original human source
  recovery/provider questions remain pending; do not repeat requests.

## Environment intake

Observed2026-10-13 Singapore: Docker Linux Engine pipe is absent. WSL Ubuntu
has CPython3.12.3/linux-x86_64, but no pip/ensurepip. A venv is created with
`with_pip=False` under ignored `output/175-linux-service/venv`; official
get-pip bytes and the exact pip26.2.1/setuptools84.0.0/wheel0.48.0 installer
receipts are retained there. No system package/configuration changes.
The initially requested versioned pip zipapp returned404 before execution;
the empty owned venv was resumed with the documented supported bootstrap.

## Steps and checks

- [ ] Resolve only existing `.[dev]` and
  `services/research_agent[dev]`, with `audit-constraints.txt`, public PyPI,
  binary wheels and no ambient pip configuration. Archive actual platform,
  selected artifacts/hashes, metadata and source commit. Exclude editable
  QuantMesh packages from the external dependency lock.
- [ ] Write runtime selection tests: Windows CPython3.13 x86_64 selects the
  unchanged Windows lock; Linux CPython3.12 x86_64 selects the separate Linux
  lock; wrong Python/platform/arch refuses, never substitutes a known profile.
  RED: audited Python runs `pytest tests/test_research_service_runtime.py -q`
  with a unique workspace-owned basetemp, retaining the missing-behavior failure.
- [ ] Add the minimal runtime/lock selection helper and measured runtime
  metadata to the service gate. Preserve license exceptions, schema/protocol,
  real-PostgreSQL admission and offline labelling. GREEN the same tests.
- [ ] Install the Linux lock with `--require-hashes` in the owned venv; install
  the two owned projects with `--no-deps --no-build-isolation`. Run pip check,
  full independent service license/gate in `--offline` mode and archived real
  Linux test output. Default gate remains nonzero until its actual disposable
  PostgreSQL evidence exists; no skip is called a native/DB pass.
- [ ] At the coherent checkpoint run relevant core runtime/gate checks,
  Ruff/format/diff, inspect actual Linux source imports, and preserve the
  original Windows lock/hash. Review the new qualification delta at most two
  rounds; never redispatch the completed #171 architecture review.
- [ ] Record measured environment versus missing OCI/DB/model/server proofs in
  README/iteration/ACTIVE. Final milestone release still needs clean-checkout,
  human/CI gates and approved private deployment/user-loop acceptance.

**Stop:** A platform package/closure/license conflict is a recorded qualification
failure, not permission to loosen constraints or claim readiness. Prepare a
bounded ruling before changing an existing admitted version. No image/runner
integration before #172's genuine native qualification.

Preflight ruling: an initial dry-run with core research extras selected94
external packages (the75 shared versions were unchanged). Those optional
ML/statistics packages are not in the existing service's77-package Windows
closure or required by the registered baseline/report API. Resolve core dev
plus service dev instead, retaining all existing admitted version constraints;
do not expand the advisory service with unrelated research extras. The first
resolver receipt remains an unadmitted diagnostic, not a shipping lock.

Observed boundary2026-10-13: clean9d5b3fa/native Linux filesystem passes81-wheel
hash installation/license audit,8 runtime tests and25 offline service checks
with5 actual-PG skips. Default gate exits1 only for real-PG absence. Original
mounted-drive capture/Git-pointer failure and300s expiry remain unaccepted;
owned persistent native filesystem fixes the environment, not test assertions
or admission limits. Imports and raw receipts are archived before WSL exit.
New delta Spec/Standards R1 clear; actual OCI/aggregate effects/Worker/PG/model/
private deployment remain the unfinished boundaries in the parent plans.
