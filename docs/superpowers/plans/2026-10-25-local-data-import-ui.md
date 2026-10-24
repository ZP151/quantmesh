# Local data import UI implementation plan

> Implement inline with test-first verification; one independent UX/safety review at the complete slice boundary.

**Issue:** https://github.com/ZP151/quantmesh/issues/222 (local research data loop; no OpenD prerequisite).
**Goal:** Import an existing local daily CSV, understand coverage/source/quality/qualification, and carry its real reference into protocol planning without granting fixture-runner authority.
**Base:** actual origin/main 9cdf321; isolated existing UI worktree, branch codex/local-data-import-ui. Backend owner has exclusive API/data/runner ownership.

## Short design / Planner
Operate mode; preserve DESIGN.md black/graphite/green, Geist and owned controls. Extend existing Data readiness with an explicit own-CSV mode while preserving the SPY ZIP view and frozen experiment history. Three sequential regions: choose file + source facts; validation result with separate structure/coverage/qualification; next action with a bound dataset reference for protocol planning. Errors retain the last report but label it as previous; no failed upload can masquerade as current. Source claims are labeled as supplied, unknown evidence stays unknown. Full identifiers live in disclosure/download, not the primary action.

Success: one actual local import produces a persistent server report, can reopen after reload, and offers an honest usable reference/planning action. Desktop and375px have no document overflow,44px compact controls, visible focus, named file input, keyboard-error recovery and wrapping long text. Existing ZIP/P2/P3 behavior remains covered.

## Quant researcher
CSV structural acceptance is not research qualification. Rights, historical availability, revision history, costs and corporate actions remain authoritative server findings. Missing dividend fields never mean no dividends. Daily session labels never establish historical availability timestamps. No synthetic profitability or imported metrics imply research pass; no paper/live order authority.

## Bounded files / non-goals
Frontend: DataReadiness.tsx, new LocalCsvImport.tsx, lib/local-csv-api.ts and copy/tests; generated api/client.ts after backend contract; narrow planning context in existing ResearchJobs.tsx only if required. Own iteration record and this plan; generated src/quantmesh/api/static/app/** after real build. No backend/runner/dependency manifests/locks/CI/global metadata/host/OpenD changes.

## Task and checks
- [x] Read incumbent code, product/design, active P1/P2/P3 ledgers and actual main. Confirm API ownership and native runtime availability.
- [x] Receive minimal backend DTO and exact allowed next action; record frozen contract paths.
- [x] Write interaction/API tests for empty/loading/upload/checking/accepted/quality problems/unknown/failed/reopen and identity-bound planning. Run targeted RED.
- [x] Implement smallest page loop with generated typed API, bounded upload, explicit errors and retention semantics. Run targeted GREEN and old DataReadiness/FrozenExperiments tests.
- [ ] Build actual bundle; first build failure gets a specific cause, no lock workaround. Verify API generation and static currency, lint/typecheck/whitespace.
- [ ] Run real local backend + page; desktop/375px screenshots and keyboard/long-text/error checks in one batch. One aggregate correction and one confirmation maximum.
- [ ] Independent UX/safety diff review once, fix material findings, record evidence in docs/iterations/0038-local-data-import-ui.md, normal commit/push and handoff to publisher/root.

Root explicitly authorized short design followed by implementation without another approval. Existing runtime/deps only; no old failed artifact/CI prerequisite, no environment re-creation, no full545 frontend rerun.
