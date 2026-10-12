# Research Workers and Workstation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans task-by-task after operator approval and contract freeze. Steps use checkbox syntax for tracking.

**Goal:** Turn registered research requests into recoverable backtest reports and optional bounded Agent analysis visible in the workstation.

**Architecture:** Backtest and Agent workers implement the frozen JobStore boundary. A separately locked Research Service exposes private submission/status/artifact routes; the workstation owns validated presentation and all paper/risk authority.

**Tech Stack:** Existing baseline/ReportRegistry/ModelGateway; isolated FastAPI/PostgreSQL/LangGraph environment, React and existing generated API client; owned worker subprocesses and immutable artifacts.

**Spec:** `docs/superpowers/specs/2026-10-12-research-foundation.md`; interfaces in `2026-10-12-research-contracts-eval.md` Task 2; schedule/budget in `2026-10-12-research-portfolio.md`.

Status: APPROVED Option A2026-10-12; execute after contract freeze. No workers
or paid servers launched at approval checkpoint; announce paid/auth/key steps.

## Global Constraints

- JobStore/contracts/defaults come from the reviewed freeze; no unilateral signature or state additions.
- Existing numerical engine and typed AI gateway are reused; no AI order authority.
- Preserve the accepted Windows GUI/helper/source/tunnel; failure tests stop only job-owned resources.
- New service dependencies stay out of the core lock/release closure; audit both complete environments.
- Initial concurrency 2, lease 60 seconds/heartbeat 15 seconds, job caps 900 seconds/2048 MiB/1 CPU/12 calls/$1 estimate.
- Dataset export is permission-checked and immutable; no private account/vendor credentials leave their host.
- Server deployment waits for selected A/B budget and explicit resource approval; foundation v1 rejects arbitrary Python uploads.

## Review Focus

1. Worker crash after upload, lease loss or cancellation cannot publish duplicate/stale results (Task 1).
2. Mutable dataset files, corporate/time-order corruption or path traversal cannot bypass the pin (Task 1).
3. Agent checkpoint replay cannot repeat paid/external side effects without an idempotency check (Task 2).
4. API/provider failure, injected credential or unknown price cannot leak secrets or turn a failed analysis into a successful trade (Task 2).
5. Service outage/reload/version mismatch cannot turn UI pending into false success or break accepted charts (Tasks 3–4).

## Task 1 — Backtest worker with fenced publication

Files: create `src/quantmesh/research/job_runner.py`,
`src/quantmesh/research/job_artifacts.py`,
`tests/test_research_job_runner.py`, `tests/test_research_job_artifacts.py`.
Reuse `run_baseline_report` from `baselines.py`, existing `ReportRegistry`,
`CostModel`, `WalkForwardSpec` and `UniverseMember`. Do not refactor baseline math.

Interfaces:
- `run_next_job(store: JobStore, owner: str, inputs_root: Path, artifacts_root: Path) -> JobRecord | None`;
  executes only allowlisted baselines in an owned bounded subprocess.
- `canonical_result(report: StrategyReport) -> bytes` includes numerical
  metrics/windows, strategy/code/config/input digests; excludes wall-clock
  created_at and worker receipt IDs. Full receipt remains separately archived.
- `publish_result(job: JobRecord, canonical_bytes: bytes, root: Path) -> ArtifactRef`;
  wrap canonical numerical JSON as a report envelope with schema_version=1,
  request_digest=job.request_digest, verified job.implementation_digest and result.
  Compare queued engine digest before running; bind full actual worker build and
  dependency fingerprint separately, do not call a two-file SHA the full runtime.
  Write atomically under
  `<job_id>/<sha256-of-envelope>.json`; ArtifactRef byte_size/SHA256 describe
  envelope bytes. Store verifies every ref and exactly one report with matching
  request_digest; Worker owns numerical schema validation. Full receipt remains
  separately archived. See proposed ADR-0026; final contract digests await review.
- Per-attempt report registries are isolated to avoid concurrent writes to
  existing append-only JSONL. Only current lease can `JobStore.finish` success.

- [ ] Write `test_pinned_baseline_matches_existing_engine` using frozen fixture
  bars and nonzero costs: numerical outputs match existing engine; canonical
  bytes equal across two attempts although receipt time may differ.
- [ ] RED: `python -m pytest tests/test_research_job_runner.py
  tests/test_research_job_artifacts.py -q`; absent runner/publication fails.
- [ ] Implement fixture/local export loading, digest and chronology validation,
  isolated per-attempt registry and baseline adapter. Use `run_baseline_report`
  with explicit dataset/revision/strategy/interval/universe/window_spec/costs/
  code SHA/registry; no fresh unpinned source queries inside the run.
- [ ] Add `test_old_attempt_and_cancel_cannot_publish`,
  `test_crash_after_object_upload_leaves_no_success`,
  `test_changed_manifest_and_traversal_reject` and
  `test_timeout_kills_only_owned_worker`. Assert known sibling survives and
  expired/old owner finish returns false. Retried work may recompute; one
  authoritative artifact set is published.
- [ ] GREEN: repeat focused tests. Demonstrate submit → claim → baseline →
  persistent succeeded report in a test-owned local job store, then simulated
  owned-worker crash → expiry/reclaim within 90 seconds at declared load.
- [ ] Commit the coherent local worker/report user loop with RED/GREEN and
  actual recovery timing. Remote store/service consumes the same interface.

## Task 2 — Independent advisory Research Service and Agent

Files: create `services/research_agent/pyproject.toml`, `requirements.lock`,
`src/qm_research_agent/app.py`, `store.py`, `orchestrator.py`, `budgets.py`,
`artifacts.py`, `tests/test_store.py`, `test_agent.py`, `test_service.py`,
`deploy/compose.yaml`, `README.md`; create `tools/research_service_gate.py`.
The session owns this directory; root owns changes to global CI/ADR and clients.

Interfaces:
- `PostgresJobStore(dsn: SecretStr)` implements frozen `JobStore` with unique
  constraints, transaction-based claim and fenced conditional writes. DSN never
  enters run artifacts/logs. Schema migrations are versioned and rollback-tested.
- `create_app(store: JobStore) -> FastAPI`: private authenticated `POST /v1/jobs`,
  `GET /v1/jobs/{job_id}`, `POST /v1/jobs/{job_id}/cancel`,
  `GET /v1/jobs/{job_id}/artifacts/{artifact_id}`, `/health`.
  Admission uses the configured operator identity, not a body-supplied identity.
- `run_analysis(job: JobRecord, report: ArtifactRef, gateway: ModelGateway) -> AnalysisRecord`;
  model input is approved report/context only, with cited immutable evidence.
  Claim/heartbeat/finish the separate `AnalysisLease`; backtest success is never
  reset by an advisory retry. Return structured failed/unavailable analysis
  when provider or permission is missing.
- `reserve_call(job_id: str, request_digest: str, estimated_usd: Decimal) -> bool`;
  durable usage reservation precedes external calls; recorded response allows
  resume without recalling that completed call. Unknown price rejects paid call.
- Real-provider metadata includes usage availability and a versioned price table;
  actual response is replayed, not regenerated for an old report.

- [ ] Audit a pinned LangGraph OSS closure and Python compatibility in the
  independent environment, record license decision and lock digests. Use a
  separately isolated RD-Agent/Qlib bake-off only if approved; $25 maximum,
  five fixed tasks, no production dependency admission inferred from its result.
- [ ] Write store concurrency/fencing tests, Agent resume/secret/budget/schema
  tests and API tests. RED: run service tests with its own environment:
  `python -m pytest services/research_agent/tests -q` from that configured venv;
  fail for absent service, not for missing unrelated core dependencies.
- [ ] Implement persistent checkpointing, idempotent model-effect records,
  PostgreSQL JobStore and service adapters. Keep local SQLite behavior behind
  the same protocol. Reject arbitrary artifact URLs/paths and do not allow
  request-supplied model endpoints. Remote egress uses construction-time
  allowlists and the existing gateway's explicit remote consent boundary.
- [ ] Add `test_paid_call_not_repeated_after_checkpoint_resume`,
  `test_ambiguous_model_timeout_requires_operator_retry`,
  `test_unknown_price_and_budget_exhaustion_block_calls`,
  `test_auth_identity_and_artifact_access`,
  `test_model_failure_preserves_backtest`,
  `test_secret_and_order_fields_reject`. Concurrent reservations cannot exceed
  estimated allowance; denial is explicit, not empty analysis labelled success.
  Archive completed model effects before checkpoint advancement; an ambiguous
  provider timeout is unavailable with unknown effect, not silently recalled.
- [ ] GREEN: same service tests with scripted gateway and disposable PostgreSQL
  database. Store tests reopen/restart service, compete two workers, and verify
  one accepted job and one published result. Scripted fixtures are labelled.
- [ ] Commit service gate/locked dependencies and prove isolated CI environment
  does not enlarge core release dependencies. A separate gated real API run
  waits for operator provider/model/price/egress approval and records actual cost.

## Task 3 — Workstation submit/status/report loop

Files: create `src/quantmesh/api/research_jobs.py`,
`src/quantmesh/research/service_client.py`, `tests/test_research_jobs_api.py`,
`frontend/src/screens/ResearchJobs.tsx`, `ResearchJobs.test.tsx`.
Root alone modifies `src/quantmesh/api/workstation.py`, frontend `App.tsx`,
shared API client/generated schema and existing Research navigation.
Read PRODUCT and invoke project impeccable before shaping this surface.

Interfaces:
- `ResearchServiceClient.submit(request: ResearchJobRequest, key: str) -> JobRecord`,
  `.get(job_id: str) -> JobRecord`, `.cancel(job_id: str) -> JobRecord`,
  `.artifact(job_id: str, artifact_id: str) -> bytes`.
- QuantMesh API routes: `/research/jobs` submit, `/research/jobs/{job_id}` read,
  `/research/jobs/{job_id}/cancel`, `/research/jobs/{job_id}/artifacts/{artifact_id}`;
  local mode binds SQLite/worker adapter, remote mode uses approved private endpoints.
- UI exposes registered strategy/version, pinned data/config/costs, status,
  cancel, canonical report download and optional cited analysis. Advisory versus
  deterministic artifacts and unavailable usage/cost are distinct.

- [ ] Add `test_submit_idempotency_409_and_unavailable_503`,
  `test_unknown_schema_and_artifact_digest_reject` and UI tests for queued →
  succeeded, failed/cancelled, reload preservation, absent Agent and no order UI.
- [ ] RED: `python -m pytest tests/test_research_jobs_api.py -q`;
  in frontend run `npx vitest run src/screens/ResearchJobs.test.tsx`.
- [ ] Implement typed facade and submit/status/report surface. Bound retries,
  show measured input/code lineage, and poll only active jobs. No synchronous
  backtest in web request and no hidden rerun on refresh.
- [ ] GREEN: focused tests; root generates/checks API schema, then runs frontend
  typecheck/lint/build and API tests. Keep accepted Markets/Watchlist chart and
  paper decision regression paths in the relevant boundary suite.
- [ ] Record actual browser submit → pending → report → reload, cancellation,
  model unavailable and service unavailable. Commit the user loop; root owns
  shared integration edits and the active iteration evidence.

## Task 4 — Approved private deployment and recovery acceptance

Files: create `docs/runbooks/research-service.md`,
`docs/evidence/research-foundation/acceptance-schema.json`,
`tools/verify_research_service.py`, `tests/test_research_service_witness.py`.
Root coordinates architecture ADR and ACTIVE/iteration updates; no implicit
Windows startup changes or reuse of stale AWS/OpenD authentication URLs.

Interfaces: `python tools/verify_research_service.py --origin <private-origin>
--expected-build <merged-sha> --profile recoverable|redundant --output <owned-dir>`.
Default read-only verification; disruptive worker/backup tests require explicit
test-owned resource identifiers and a checked operator-approved profile.

- [ ] Add witness tests: wrong build/profile/digest, unavailable job store,
  unknown cost and incomplete recovery evidence fail. RED: `python -m pytest
  tests/test_research_service_witness.py -q`.
- [ ] Prepare pinned packages/images, exact resource bill and private ingress,
  encrypted backup/restore, secret setup and rollback. Review concrete A/B
  deployment before paid resource creation. Limit service memory/CPU and global
  worker admission; a base 8 GB host has 2 vCPU, not unlimited parallel capacity.
- [ ] GREEN: focused witness tests, final exact-head core release gate and
  separately locked service test/license gate. New native checks use a unique
  workspace-owned basetemp. Wait for all required CI and human reviews.
- [ ] Deploy only merged reviewed code; verify exact service and existing
  workstation health with paper=true/live=false. Real model run uses approved
  report context without credentials; record provider, response digest and usage.
- [ ] Measure submission p95 under 2 jobs, process restart and job lease recovery,
  Agent failure isolation, owned-worker timeout, off-host backup restore on an
  isolated target, report digest continuity and budget exhaustion. Targets are
  not claimed until the actual witness passes.
- [ ] If B approved, provision distinct-AZ research hosts plus encrypted managed
  HA PostgreSQL; verify both private endpoint paths, owned-host failure/failover,
  artifact availability and no missing accepted job. Measure DB failover separately.
  This does not test or certify Windows/provider/workstation host redundancy.
- [ ] Record merged/deployed/operator-tested states and unresolved operational
  gates. Operator accepts foundation before any new strategy trials begin;
  overall long goal remains ACTIVE and formal168h stays not required.
