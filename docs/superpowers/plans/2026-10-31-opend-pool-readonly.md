# OpenD pool readonly implementation plan

Spec: ../specs/2026-10-31-opend-pool-readonly.md. Base actual merged559584b663c5868f7efc44334761d3dfa62218a5; old source branch preserved. Existing isolated checkout is reused on a new codex branch from origin/main.

## Contract and review focus

Only c8 recovery requires ReadOnlyPaths=/run/quantmesh-opend-storage-c8f0d0de4ca641a491fca6df24c66ceb. Six existing ReadWritePaths and all formal Bind(ReadOnly)Paths remain. _manager_contract(window)->dict adds that exact scalar; _manager(window) must refuse absent, empty, wrong, additional or duplicate readonly values. Private storage, recovery consume and initial/other-instance contracts are unchanged. No market data/model/fees/leakage semantics change.

## Single implementation checkpoint

Files: deploy/aws/opend/quantmesh-opend-console-c8-private-storage.conf; deploy/aws/opend/stage_console.py; tests/test_opend_private_storage.py; tests/test_opend_same_unit_recovery.py; this spec/plan and active private-storage iteration. Roadmap gets only a narrow actual-proof checkpoint.

- [x] Extend the existing parsed dropin contract with exact readonly POOL; extend the real manager boundary test with valid readonly value and missing/empty/wrong/additional/duplicate mutations. Expectations are literal, not computed from production contract.
- [x] Run these two test nodes using existing Python313 -B -m pytest -q -p no:cacheprovider with unique retained basetemp; observe old-config/old-manager failures, retain raw stdout/stderr/RC and commit tests/docs before production changes.
- [ ] Add the single dropin line, literal dropin SHA and exact c8 manager scalar. No guard or recovery algorithm edits.
- [ ] Run the two nodes GREEN, then affected private-storage/fixture and recovery tests; changed-file Ruff check/format, in-memory Python3.12 compile, whitespace and submodule metadata at checkpoint. No old native/Windows/frontend replay, dependency install or host operation.
- [ ] Update iteration with Planner/Quant/Implementer/Verifier evidence and commit coherent green delta. Independent fresh agent reviews exact base/head, proof limitations, drift tests and frozen guard/template/bind bytes. One known-fix R2 maximum.
- [ ] Normal PR Refs263; exact final-head repository-selected jobs and aggregate green, no substantive findings, then expected-head normal merge. Fetch full actual tree, compare complete candidate tree and freeze literal source catalog; preserve old failures, commits, holds and local main divergence.

Operator/backend acceptance remains pending. No original fourth start, Source main, SDK or private window is authorized by this software checkpoint alone. Parent owns later merged operational disposition.
