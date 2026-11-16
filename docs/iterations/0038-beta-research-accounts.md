# Iteration0038 — minimal beta research accounts

Issue [309](https://github.com/ZP151/quantmesh/issues/309). [Spec](../superpowers/specs/2026-11-17-beta-research-accounts.md), [plan](../superpowers/plans/2026-11-17-beta-research-accounts.md). Actual human parallel account/chart scope recorded2026-11-17, source authority SHA8b0e81425f882157327dcbb8032295ca3c9ee709224e69d6efcbe90c0952a709.

Planner: one Operator invitation → authenticated tester → only owned Native archive → revoke blocks subsequent access. Original Product ACK00:02:22SGT; source base actual main a9934019, isolated managed beta-accounts-backend. Original UX owns all frontend/generated-client work. No duplicate runtime or CI owner.

Quant researcher: access ownership is not data entitlement, real-input admission, trial approval or financial qualification. No raw input redistribution, actual recipient, real study, provider/model/SDK or trading action in this engineering scope.

Implementer: existing desktop is single-person loopback; private service has fixed Operator Bearer only. New opt-in registry reuses stdlib credentials/SQLite, existing WriterLease and separate NativeDailyService roots, preserving the original Operator legacy store. Short spec and plan define exact files, capabilities and revoke/cookie behavior before code.

Reviewer: fresh whole-backend Spec/Standards review at coherent boundary, maxR1 plus locatedR2. No review result is claimed yet.

Verifier: targeted TDD source/import/error/exit/resource evidence will be retained in output/beta-accounts-20261117. New registered128MiB covers full source/git/tests/review/teststates/temp; complete category refinement68/4/24/8/16/8MiB has no net growth. No new dependency/environment, source frontend edit, public exposure or existing service interruption.

## Backend increment — 2026-11-17, before independent review

Implementer: hashed single-use invitations, bounded persistent sessions, Operator create/list/revoke, current-user/logout and the whole-app HTTP/WS boundary are implemented. Server-selected independent Native roots preserve all original artifact schemas and the Operator's unowned store. Construction-time opt-in only; default personal mode remains unchanged. New users have no input registrations. [ADR0044](../adr/0044-beta-research-accounts.md) records this boundary; its number was reserved by the coordinator.

Verifier: actual existing Python313/one-core Windows Job runs are retained under `output/beta-accounts-20261117/`. Initial `red-01` is a missing-module setup failure, not a behavior RED. `green-01` records an incorrect import, `green-02/03` an incorrectly selected old venv lacking pg8000; no package was installed or dependency mocked. The corrected existing interpreter yielded `green-04`15PASS. Actual subsequent behavior REDs cover raw storage error, hardlinked DB, absent OpenAPI schema, blocking authentication and cross-origin authenticated Operator WebSocket. `boundary-green-01`19PASS, `storage-green-01`21PASS, `schema-green-01`22PASS, `async-origin-green-01`24PASS. Windows prevents the original DB rename probe, so the named-file disappearance test explicitly simulates that condition; its harness failure is preserved.

`affected-01`:40PASS/15.63s pytest,17.22s owned run, exit0. Selection comprises the24 new account tests,10 recovery API tests,4 noncomputing Native collection checks and2 workstation availability/Origin checks. A real valid retained engineering report/decision supplies positive owner download controls; foreign A is denied known B IDs and artifacts, while Operator/B original bytes match. Per-user cold app reopening preserves A's session/job and revoked B remains denied. An Operator-only registration marker proves the tester options endpoint uses its own service. No engine matrix or real study executes.

Full src/tests/tools Ruff passes; final changed-file formatting and independent review are still pending at this checkpoint. No full backend suite, browser, CI, new service/dependency, SDK/provider/model/data/trading or actual recipient invitation was run. Source-wide lint is not runtime or financial qualification.

Every test after the initial launcher attempts uses the unchanged existing `_OwnedChild`, queried job flags8720/affinity1 and committed-memory cap536870912B,75s outer wait. `schema-green-01` and later record the verified active0 after own-only cleanup plus CLOSED process/job handles and closed stdin/log. Earlier terminal snapshots may show active1 after pytest exits; cleanup requests termination, so this is not natural whole-tree-zero evidence. RSS is not measured. All failures/fixtures/old allocations remain; the128MiB disk hold is separate from the512MiB runtime commit limit.

Planner/Quant: current separate Quant package adjudication permits internal restricted1h charts but does not qualify RTH daily research or external raw-data redistribution. This account implementation does not execute on it or create data rights. The human paused UX after computer restarts; no cause is attributed to account tests. Frontend, account UI and joint publication remain paused; original Product does not take them over. This is a backend increment, not the complete independent-research goal or user-facing beta delivery.
