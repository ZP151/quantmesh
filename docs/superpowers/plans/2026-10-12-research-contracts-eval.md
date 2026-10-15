# Research Contracts and Evaluation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans task-by-task after operator approval. Steps use checkbox syntax for tracking.

**Goal:** Freeze persistent research-job contracts and improve validation/evaluation feedback without weakening release gates.

**Architecture:** Domain contracts remain dependency-light in the core; SQLite implements local persistence and an interface permits isolated PostgreSQL later. Validation selection and offline Eval are independent tools with immutable run evidence.

**Tech Stack:** Existing Python/Pydantic/sqlite3/pytest, GitHub Actions, frozen JSON cases and existing workflow tests.

**Spec:** `docs/superpowers/specs/2026-10-12-research-foundation.md`; sequencing/budget in `2026-10-12-research-portfolio.md`.

Status: APPROVED Option A2026-10-12. Task2 is the first-batch contract session;
Task1#132 follows when a first source/calendar slice frees an implementation slot.

## Global Constraints

- Initial strategies: existing momentum, mean-reversion and risk-parity; no uploaded code or new trading authority.
- Defaults: 900-second timeout, 2048 MiB, 1 CPU, 12 model calls, $1 estimated model budget, 2 concurrent jobs.
- Lease 60 seconds, heartbeat 15 seconds; all stale writes fenced by attempt and owner.
- Unknown changed paths and safety/dependency/workflow changes escalate to full release coverage.
- No hourly local all-suite runs while iterating; complete relevant boundary and final fresh-checkout certification.
- Formal 168h is not required; preserve existing source, helper and private route.

## Review Focus

1. Unknown file path or malformed changed-path input cannot silently select fast (Task 1).
2. Same idempotency key with a different configuration cannot overwrite a prior job (Task 2).
3. A changed dataset manifest or unsupported interval cannot be queued as qualified (Task 2).
4. SQLite reopen/cancellation/lease expiry cannot lose accepted work or let a stale attempt finish (Task 2).
5. Missing usage, benchmark changes and known-bad traces cannot create false Eval improvements (Task 3).

## Task 1 — #132 deterministic validation tiers

Recovery ruling: existing unmerged candidate codex/0132-gate-efficiency at
b36a5528c489ad92e0aad363a527317e37ad2cd8 already implements gate_policy.py,
quality_gate.py and related workflow/tests. Its ledger records focused171/1,
FAST446/1 and an interrupted full release attempt, not release certification.
The worktree also preserves uncommitted observer follow-ups; do not erase or
silently absorb them. Start with read-only compatibility/reuse review against
the current integration tree, adapt the committed implementation rather than
writing a second gate framework. File/CLI names below are desired boundary
descriptions; retain the existing qualified entry points instead of creating
a duplicate validation_gates.py if equivalent behavior is already provided.

Files: create `tools/validation_gates.py`, `tests/test_validation_gates.py`,
`docs/runbooks/validation-tiers.md`; modify `.github/workflows/ci.yml` only in
this assigned session. Root reviews workflow/dependency consequences.

Interfaces:
- Produce `select_tier(changed_paths: list[str], event: str) -> str`, exactly
  `fast`, `domain`, `browser`, `release`.
- Produce `build_commands(tier: str) -> list[list[str]]` and CLI
  `python tools/validation_gates.py --tier <tier> [--plan-only]`.
- Machine-readable progress has step, start/end, elapsed, exit, log path and
  slow-test summary. Paths are normalized repository-relative, never executable input.

- [ ] Add `test_unknown_and_safety_paths_escalate`: assert unknown path, risk,
  broker, authentication, lockfile, workflow and gate-tool changes select
  `release`; unsafe absolute/traversal paths reject. Add fast/domain/browser
  command tests and manual/main/tag fallback tests.
- [ ] RED: `python -m pytest tests/test_validation_gates.py -q`; fail because
  selector/entry point is absent. Save exit/log in workspace-owned output.
- [ ] Implement selector and tier command construction; retain complete fresh
  clone `tools/release_gate.py` for final candidates. Fast cannot collect long
  integration/browser cases; safety assertions remain mandatory in every
  applicable PR path. Use an explicit test-family map rather than test-name heuristics.
- [ ] Add `test_step_timeout_and_progress`: bounded owned-process timeout
  produces nonzero exit, final progress and slow-test metadata; failure stops a
  diagnostic run, exhaustive final certification still reports its complete run.
- [ ] GREEN: repeat focused pytest; run `python tools/validation_gates.py
  --tier fast --plan-only`, validate workflow syntax and inspect the command
  plan for release. Run one measured fast gate on the actual checkout; record
  duration as evidence, no unsupported promised speedup.
- [ ] Commit the focused green slice and review #132 acceptance. At integration
  boundary certify exact head with `python tools/release_gate.py`; do not
  amend active PR #166 or rerun its superseded CI.

## Task 2 — Registered baseline submit/status local loop

Files: create `src/quantmesh/research/jobs.py`,
`src/quantmesh/research/strategy_registry.py`,
`src/quantmesh/research/job_store.py`, `tools/research_job.py`,
`tests/test_research_jobs.py`, `tests/test_research_job_store.py`.
Reuse `src/quantmesh/research/reports.py` types and dataset manifest gates;
do not change baseline math or live history retention.

Interfaces (freeze these together before Batch B):
- `jobs.py` defines `StrategySpec`, `DatasetRef`, `RunBudget`,
  `ResearchJobRequest`, `JobRecord`, `ArtifactRef`, `AnalysisRecord`, `AnalysisLease` exactly as
  the spec; all public schemas reject extra fields.
- `get_strategy(strategy_id: str, version: str) -> StrategySpec` returns only
  allowlisted code; initial versions are `1` and interval/universe validation
  reuses existing baseline requirements.
- `canonical_request_digest(request: ResearchJobRequest) -> str` hashes
  canonical UTF-8 JSON of validated inputs; rejects nonfinite values.
- `JobStore` protocol:
  `submit(operator_id: str, idempotency_key: str, request: ResearchJobRequest) -> JobRecord`;
  `get(operator_id: str, job_id: str) -> JobRecord`;
  `claim(owner: str, now: datetime) -> JobRecord | None`;
  `heartbeat(job_id: str, owner: str, attempt: int, now: datetime) -> bool`;
  `request_cancel(operator_id: str, job_id: str) -> JobRecord`;
  `finish(job_id: str, owner: str, attempt: int, state: str, artifacts: list[ArtifactRef], error_code: str | None) -> bool`;
  `claim_analysis(owner: str, now: datetime) -> AnalysisLease | None`;
  `heartbeat_analysis(lease: AnalysisLease, now: datetime) -> bool`;
  `finish_analysis(lease: AnalysisLease, record: AnalysisRecord) -> bool`.
- `SQLiteJobStore(path: Path)` implements this protocol using transactions,
  unique idempotency/digest checks and conditional lease/attempt writes.
  `IdempotencyConflict`, `DatasetRejected`, `StoreUnavailable` are typed domain
  errors. No raw credentials/SQL payloads appear in API/log errors.
- CLI: `python tools/research_job.py submit --request <json> --key <key>
  --store <sqlite>` and `status --job-id <id> --store <sqlite>`.

- [ ] Add `test_request_and_registry_reject_unsafe_inputs`: unknown strategy,
  unsupported interval, empty universe, bad costs, nonfinite parameter, path or
  order-shaped extra field rejects. Pinned stale manifest/export permission
  rejects before store mutation; no network/export occurs implicitly.
- [ ] RED: `python -m pytest tests/test_research_jobs.py
  tests/test_research_job_store.py -q`; expected missing contracts/store.
- [ ] Implement contracts/registry/store/CLI. A local read-only dataset gate
  validates manifest digest and declared permission; later remote mode must
  validate exported bytes again, not trust just request metadata.
- [ ] Add `test_same_key_same_job_and_conflict`: two submissions return one ID;
  same key/different digest raises `IdempotencyConflict`; reopen store preserves
  job. Add `test_expired_attempt_cannot_publish`: expire lease, claim new
  attempt, previous `finish` returns false. Cancelled work cannot finish success.
- [ ] Add `test_analysis_outbox_is_atomic_and_independent`: successful backtest
  finish creates one pending analysis when requested; expired analysis lease
  rejects stale writes; failed analysis preserves backtest succeeded. Cancel
  before backtest completion fences both; cancel pending analysis after a
  completed backtest preserves its result and marks advisory work cancelled.
- [ ] GREEN: focused tests; CLI submit/status on a **test-owned fixture dataset**,
  reopen store and verify same ID, state and input digest. No vendor data is
  uploaded; no strategy experiment is promoted.
- [ ] Commit reviewed contracts and record frozen schema/API digest. Root
  updates the iteration/ADR and integration baseline; Batch B consumers receive
  this commit and exact interface names, not an informal chat paraphrase.

## Task 3 — #160 offline reproducible workflow Eval

Recovery ruling: legacy worktree
C:/Users/15492/.codex-clean/worktrees/quantmesh-eval-harness/QuantMesh contains
uncommitted tools/eval_harness/, tests/test_eval_harness.py, benchmarks and docs.
Preserve its contents. Inspect/reuse qualified behavior in a new owned worktree;
do not rerun a completed experiment or build workflow_eval.py as a duplicate
framework. Its unmerged file calls itself iteration0038; that is not the current
canonical iteration ID or accepted evidence. Mirror validated results under the
current0038 ledger and avoid duplicate index entries. Tests/release acceptance
must be rerun only for the actual adapted candidate, never inferred from dirty files.
Read-only recovery audit confirms the legacy catalog has24 cases and a seven-name
taxonomy different from this approved plan. Adopt a new catalog version/hash for
that migration; retain existing case IDs where acceptance is unchanged. Never
silently relabel an old run or compare incompatible catalogs/verifier bytes.
Retain truthful nullable usage already present in the original scorer. Reuse
tools/eval_harness and its qualified entry points rather than duplicating them.

Files: create `tools/workflow_eval.py`, `tests/test_workflow_eval.py`,
`tests/workflow_eval/cases.json`, `tests/workflow_eval/fixtures/`,
`docs/runbooks/workflow-eval.md`. Existing sourced tests are referenced by
stable test IDs; do not copy upstream strategy code or modify runtime safety.

Interfaces:
- `EvalCase`: case_id, scenario, difficulty, source reference, fixture digest,
  executable acceptance and expected boundary result; freeze 24 cases.
- `EvalRecord`: case/task/run IDs, case catalog hash, code SHA, verifier
  fingerprint, trace reference, verdict, failure category, interventions,
  latency, model/tool calls, tokens/cost with explicit unavailable values.
- `evaluate(catalog: Path, output: Path, baseline: Path | None) -> int`.
- CLI `python tools/workflow_eval.py --catalog tests/workflow_eval/cases.json
  --output <owned-output> [--baseline <prior-output>] [--inject-known-bad]`.
- Seven-way taxonomy is frozen as `specification`, `data`, `tool`, `model`,
  `verification`, `infrastructure`, `policy`; timeout has verdict failed and
  category infrastructure, skip remains skip and is excluded from success.
  Spec approval freezes these names before producing a comparable baseline.

- [ ] Add `test_missing_usage_is_unknown_not_zero`,
  `test_catalog_change_blocks_comparison`, `test_skip_timeout_not_pass` and
  `test_known_bad_fixture_fails`. Each asserts the exact JSON verdict/field.
- [ ] RED: `python -m pytest tests/test_workflow_eval.py -q`; save failing exit.
- [ ] Implement catalog hashing, subprocess test isolation, trace/usage capture,
  category mapping and compatible baseline comparison. Label all scripted
  model responses; no claim about real-model semantic/financial performance.
- [ ] GREEN: focused pytest; run 24-case clean workflow catalog to owned output,
  then repeat with the same catalog and compare IDs/acceptance. Separately run
  `--inject-known-bad`; expected nonzero exit and a real failed verdict, never
  relabel that deliberately broken run green. Preserve both reports.
- [ ] Write concise summary and the issue's Chinese 90-second explanation;
  commit and verify #160's exact acceptance, including scenario/difficulty
  aggregates and task/first-pass/verifier success, not just pytest test count.

## Boundary verification / handoff

- [ ] Run focused changed-domain tests, `ruff check src tests tools`,
  `git diff --check`, dependency/license checks and workflow validation.
- [ ] At coherent slice/final boundaries run repository-required broad checks
  and the exact-head fresh-checkout release gate. Never weaken it to make a
  selected tier appear faster. Native Windows uses new workspace-owned basetemp.
- [ ] Root publishes contract SHA, file ownership, RED/GREEN artifacts, actual
  durations and unresolved limits in active iteration. Consumers start only
  from a reviewed coherent baseline.
- [ ] Reviewer checks all five failure modes; third structural failure returns
  scope to Planner. No duplicate implementation or parallel writes to shared files.
