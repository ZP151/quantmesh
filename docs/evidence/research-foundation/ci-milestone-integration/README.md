# Milestone CI integration repairs

PR175 CI38328514078 on9f088e1 accepts the corrected workflow contexts and runs
real jobs. It fails because three WorkspaceHeader assertions hardcode Singapore's
Oct10 for the Oct9 20:00UTC source instant, and the committed bundle is stale.
Original failed logs remain unchanged. Market-closed coverage and trading fences
were not the failing assertions and their production behavior is unchanged.

Only the test's display-day expectation is made timezone-portable. Both UTC and
Asia/Singapore targeted10-case runs pass. Full frontend419 cases pass, typecheck/
lint exit0. Rebuilt committed assets match current source; independent build
check exits0. This is local build proof, not application deployment.

The approved isolated-service CI obligation was absent from both existing
workflows/core release gate. A new required research_service job installs the
existing81-package Linux lock in its own CPython3.12 venv, runs the existing
--offline gate and uploads separate evidence. The python aggregator now rejects
failure/cancellation/skip of that job. Four local aggregator cases and unchanged
old-job structure are checked. A bounded wiring review has no blocking finding.

Local native testing reuses the existing admitted81-package environment, with no
new package install. Its first gate invocation fails before tests because that
runtime intentionally lacks pip; the separately audited existing gate-only pip
path corrects the harness. The second invocation has80 passed/5 PG skips but the
overall gate still exits1 because native Git cannot resolve a Windows worktree's
common-directory path. Both remain failures; no fake Git result, skipped gate,
shared-venv modification or unproven full local GREEN is used. CI's fresh native
checkout/venv must provide the actual gate result. PostgreSQL, real model calls,
aggregate containment and deployment remain unaccepted by this offline job.

Raw logs/JUnit/lock/license/gate receipts, local review and checks are hashed in
sha256.json. Original owned native evidence roots remain intact. New exact-head
remote CI is pending; no old run is replayed, no issue closed, goal stays ACTIVE.
