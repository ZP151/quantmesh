# Beta research accounts implementation plan

> Execute inline using TDD; one independent whole-backend review and at most one located R2. Original UX remains the sole frontend writer.

**Goal:** Operator-controlled invitation, isolated user research and effective revocation through the ordinary API.

**Spec:** [approved-scope short design](../specs/2026-11-17-beta-research-accounts.md), [issue309](https://github.com/ZP151/quantmesh/issues/309). Base verified local and remote main `a99340195b27368772ef8d2d24242da79c1a85f5`.

**Architecture:** One opt-in hashed-credential registry with a WriterLease/SQLite, per-user existing NativeDailyService roots and one ASGI access boundary. Keep original Operator service and all artifact schemas unchanged. No frontend or running-instance changes.

**Files:** new `src/quantmesh/auth/{__init__,beta}.py`, `src/quantmesh/api/beta_access.py`; bounded edits in `api/native_daily_real.py` and `api/workstation.py`; new `tests/test_beta_access.py`, `tests/test_beta_research_isolation.py`; this plan/spec and `docs/iterations/0038-beta-research-accounts.md` only. ADR number is coordinated before final freeze.

## Constraints and review focus

- Per-user storage is selected only from a server principal, not UUID knowledge, headers, request owner fields or data grants. Legacy/unowned records never move.
- Do not let authenticated testers fall through to original raw/Operator APIs or WebSockets.
- Check revocation again inside each research operation, not only at initial middleware authentication.
- Credential exchange, errors and storage never echo or persist raw session/invitation/bootstrap credentials.
- Retain original personal mode, report/decision hashes, candidate input/grant/trial math, source provenance and actual service ownership.
- Full new128MiB forecast: source68/git4/testslogs24/review8/teststates16/temp8, net0 redistribution of the registered128MiB; preserve every old hold/failure/future. No new dependencies or environments.

## Task1 — actual account and cross-user RED

- [ ] Add account lifecycle and real Native app isolation tests before production code. Include invitation single use/expiry, Operator create/list/revoke, cookie/Bearer auth, exact-Origin cookie write checks, logout/revoke401, private credential storage and legacy mode.
- [ ] Real A/B tests create separate owned temporary Native stores and known IDs. Assert A cannot list/read/download B admission/report/decision or POST B decision, owner spoofing fails, Operator reads the retained old root, and existing original bytes stay identical.
- [ ] Run via purpose-owned home/temp, explicit source PYTHONPATH and `python -B -m pytest -q tests/test_beta_access.py tests/test_beta_research_isolation.py -p no:cacheprovider --basetemp=<unique owned REDdir>`; preserve raw output, exit, source/import SHA. Missing implementation is expected, collection/launcher errors are not functional RED.

## Task2 — minimal registry, API and scoped service GREEN

- [ ] Implement BetaAccess root/token validation, hashed one-time invitation/session records, transaction/lease discipline, public projection, guarded per-user Native service pool and close lifecycle.
- [ ] Implement the declared Operator/session API, strict models/error sanitation and whole-app ASGI HTTP/WS capability guard. Integrate via optional create_workstation_app parameter and Native authority only; no numerical service modification or frontend generation.
- [ ] Run new tests GREEN, fix substantive failures with targeted source-bound evidence, then existing Native API/collection and relevant workstation tests once coherent. No old matrix/full Windows/CI loop.
- [ ] Export exact API/schema/permission/cookie/error contract and safe examples for main coordinator to hand to original UX after charts freeze. Never include valid secrets in the handoff.

## Task3 — review/freeze

- [ ] Run changed Python Ruff/format/diff; relevant source-wide lint once at coherent commit. Verify source/test import hashes and full actual allocation+all future cap.
- [ ] Commit coherent backend slice. Fresh independent Spec/Standards review, one combined correction pass with actual RED/GREEN if needed; at most located R2. No third structural patch loop.
- [ ] Freeze actual commit/tree/source/schema/test/review/raw-log/resource references and iteration role checkpoint; hand off to main and sole Publisher for normal necessary integrated CI/PR, not each patch. No deployment or external invitation claim.

## Phase clock

Original Product ACK00:02:22SGT2026-11-17. First verifiable API increment target by02:02:22, reviewable bounded slice by04:02:22, not unknown global DDL promises. Existing single Operator authentication is not individual beta authentication; scope decisions above address that actual gap. Important new rights/public-exposure/service-disruption risks go to main once; ordinary implementation choices continue under the actual human authorization.

## Current checkpoint

Task1/2 implementation and acceptance tests exist;24 new and40 selected related tests pass. Actual behavioral RED/GREEN and prior launcher failures are distinguished in the [iteration](../../iterations/0038-beta-research-accounts.md). Additional reviewed files are the retained synthetic archive JSON/provenance and ADR0044, reserved by the coordinator. Production Native math/storage code is unchanged. Fresh whole-backend review remains the next gate. Human UX pause holds all frontend work and combined publication; no end-to-end beta acceptance is inferred.
