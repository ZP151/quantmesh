# Portfolio budget SPEC review — round 1

Verdict: PASS for the bounded Task 1 service accounting slice. No actionable P0/P1/P2/P3 finding identified in the reviewed candidate. This is not a PostgreSQL, restore, provider, billing, model-performance, or production qualification.

## Scope and identity

- Approved coordinator plan read first: `C:/Users/15492/.codex-clean/worktrees/0038-research-integration/QuantMesh/docs/superpowers/plans/2026-10-13-research-portfolio-budgets.md`, Decisions and Task 1. Approved Option A portfolio allowances and Workers Task 2 were also read for context.
- Review workspace: `C:/Users/15492/.codex-clean/worktrees/10c3/QuantMesh`.
- Baseline: `216b378192bbc0a1742a28b7a1fc75a86ae2fda9`.
- Candidate independently verified as HEAD: `8502eee7600de5edbcbc3e3b56e199b39def1ced`.
- Candidate tree independently verified: `8804b13a37d7071664839e55933048bd4f614547`.
- Read the actual ten-file baseline-to-candidate diff and raw `output/portfolio-budget-handoff.json`; independently checked all ten reported source hashes and all 22 evidence-file hashes. No mismatch. Tracked worktree remained clean.
- AGENTS.md was explicitly revoked and was not applied. No source edits, subagents, core/full suite, secrets, paid calls, server operations, native PostgreSQL operations, or old-architecture re-review.

## Findings

None. There is no defect reproduction to prescribe for this round. The requirement mapping below records the concrete implementation and tests assessed instead of inferring correctness from new DTO/config fields.

Paths in the following table are relative to the exact review workspace above; line numbers were verified in the candidate.

| Approved requirement | Implementation evidence | Behavioral witness and assessment |
| --- | --- | --- |
| Frozen, bounded policy; $50/$200 maxima; finite nonnegative Decimal amounts | `services/research_agent/src/qm_research_agent/accounting.py:28`, `:34`, `:45`; policy re-export in `budgets.py:9` | `test_portfolio_budgets.py:145`, `:150`, `:161`, `:167` reject excessive/malformed/coerced/unpaired values, frozen mutation, and changed identity/caps. Equivalent canonical caps reopen at `:334`. |
| One durable policy per store/schema; additive explicit version authority | `accounting.py:65`, `:87`; singleton slot schema at `:93`, version check at `:67`, binding at `:74` | `test_portfolio_budgets.py:161`, `:213`, `:223`, `:324`, `:348` exercise identity/cap mismatch, unsupported/duplicate/missing version, malformed/incomplete accounting, and admission through an already-constructed ledger after authority mutation. |
| Cross-job aggregate allowance and per-job $1/12-call boundary in same fenced transaction | `budgets.py:46`, `:51`, `:53`, `:66`, `:71`, `:73`, `:77`, `:81`; exact aggregate in `accounting.py:59`, `:154`, `:164` | `test_portfolio_budgets.py:43` uses two independent jobs: first $0.60 accepted, second denied under shared $1.00. `:51` admits $0.10+$0.20 exactly and denies 1e-40 excess; `:59` separately preserves $1 and 12-call boundaries even with a $50 portfolio cap. `:69` uses different jobs and separate SQLite stores/connections with one durable winning effect. |
| Existing transaction serialization; provider invocation after admission/commit | All reserve reads, fencing, admission, clock update and both inserts are nested in `budgets.py:51`. Existing SQLite transaction uses BEGIN IMMEDIATE in `src/quantmesh/research/job_store.py:137`; existing PostgreSQL schema advisory transaction lock in `services/research_agent/src/qm_research_agent/store.py:112` | Unchanged orchestrator calls reserve at `orchestrator.py:196` before `bounded_complete` at `:216`. These boundaries were inspected only to trace this change. SQLite threading is a local witness; independent native PostgreSQL process concurrency remains Task 2. |
| UTC calendar month; store-only time; unresolved prior-period carry; development lifetime | `accounting.py:53`, `:130`, `:132`, `:134`, `:154`; `budgets.py:52` uses the store clock, with no period input in the public API | `test_portfolio_budgets.py:102` parameterizes completed previous-month release versus unresolved carry at the January/February UTC boundary. `:84` separates categories and keeps completed development spend charged after month advance and ledger reopening. `:301` keeps a cancelled unknown reservation charged next month. |
| Backward time, stale leases, duplicates, crash/reopen/rollback cannot create new authority or effects | `accounting.py:132`, `:158`; `budgets.py:53`, `:55` | `test_portfolio_budgets.py:113` denies rollback and expired lease with no new effect. `:189` proves duplicate denial, durable reserved effect through a new ledger, shared-cap denial after reopen, and an injected precommit crash: inserted effect/attribution and clock update roll back; the same allowance remains available afterward. This is deterministic transaction-failure injection, not an actual killed-process/native PG witness. |
| Canonical persisted exact amounts, no float sum or textual amount ordering | `accounting.py:14`, `:59`, `:142`, `:144`, `:145`, `:164`; `budgets.py:66`, `:78`, `:87` | `test_portfolio_budgets.py:51` tiny overage test is meaningful against ambient Decimal rounding. `:324` rejects malformed/noncanonical/reservation-effect price mismatches. `:334` observes canonical strings in SQL. Numeric amounts are compared as exact Fraction ratios of validated Decimals; timestamp comparisons are canonical UTC strings, not amount comparisons. |
| Legacy unattributed history and missing policy fail closed, including zero estimates and remote gateway | `accounting.py:79`, `:116`, `:127`; `budgets.py:73` | `test_portfolio_budgets.py:176` inserts an actual legacy effect, rejects policy activation, and preserves original read tuple. `:125` denies a zero estimate without policy. `:237` constructs ApprovedRemoteGateway but intercepts bounded_complete and proves zero invocations plus budget_exhausted. No paid or network call occurs. |
| Archived response/checkpoint replay without new reservation | Original tuple read/response/checkpoint preserved in `budgets.py:39`, `:93`, `:106`; unchanged replay routes `orchestrator.py:163`, `:185`, `:194` | `test_portfolio_budgets.py:269` parameterizes both checkpointed and response-only replay after lease reclaim through a policy-free ledger. Output equality, one transport body, and one accounting reservation are asserted. `:356` separately prevents malformed completed-without-response state from freeing previous-month allowance. |
| Explicit runtime config only; unknown keys rejected; defaults remain unavailable | `runtime.py:58`, `:62`, `:69`, `:99`, `:117`, `:474`, `:517` | `test_portfolio_runtime.py:27`, `:36`, `:89`, `:94` validate default unavailable state, exact string amounts, pair/coercion/unknown-field/cap rejection, and actual optional bootstrap binding. The build test substitutes SQLite and runtime admission, and is correctly labelled as config/accounting coverage rather than Linux native admission. No model runner is created. |
| Frozen contracts, locks and defaults retained | Only ten allowed files changed; store/core DTO/protocol, dependency locks, source gateway and orchestrator are unchanged in the actual diff | Independently computed schema/protocol digests and both lock hashes match the frozen values below. README explicitly distinguishes estimate accounting from invoices and service authority from external tool/infrastructure spending. |

All test references in the table except the runtime file resolve under `services/research_agent/tests/test_portfolio_budgets.py`.

## Evidence and reproduction

The raw RED `output/portfolio-budgets/red-cross-job.log` shows the old ledger admitting the second independent $0.60 reservation, with failure at the intended shared-cap assertion; it is not merely an absent-class/import failure.

The supplied focused raw log reports 54 passed/0 skipped. The supplied service gate JSON identifies OFFLINE_SCRIPTED_ONLY, windows-cp313-x86_64, PostgreSQL pending, and the raw gate test log reports 88 passed/51 skipped. This review did not repeat the complete service gate.

Fresh bounded independent reproduction, from the exact review workspace, with PYTHONDONTWRITEBYTECODE=1 and PYTHONPATH set only to that workspace's src, service src, and repository root:

```text
C:/Users/15492/.codex-clean/worktrees/ed95/QuantMesh/services/research_agent/.venv/Scripts/python.exe -B -m pytest -c services/research_agent/pyproject.toml services/research_agent/tests/test_portfolio_budgets.py services/research_agent/tests/test_portfolio_runtime.py -q --basetemp=output/portfolio-budgets/spec-r1-owned-20261013-1
```

Observed exit 0: `54 passed, 1 warning in 15.56s`. The warning is the pre-existing exchange_calendars/NumPy deprecation. The new basetemp is inside the candidate workspace; no ambient/shared temp was changed. The service interpreter was reused read-only; no install occurred.

Independent frozen values:

```text
schema:   a645a8bde2b439587f736a6a6875e4ffae77265cdcc2900d0b2def43f5f0de18
protocol: 454cce6bd355465e48a59cb61fbbacb775776cb28c41826e54aff554cf2ccae1
requirements.lock:             7a756138c304061ab5a2e428dca963cdc2ff314314cfe35fc92c4c0ff66b71a3
requirements.linux-cp312.lock: 07f4e7ec64805a375e0bdc707d0158fbdb08bd07d02aa569e2d119496b32592a
```

`git diff --check baseline candidate` exited 0. Final `git status --short` returned no tracked changes.

## Qualification limits and next owner

No code correction is requested from Task 1 by this SPEC round. Send this exact reviewed candidate to the independent Task 2 qualifier after the coordinator's other review axis is resolved. Task 2 must supply real independent PostgreSQL process last-slot admission, independent durable SQL observation before scripted invocation, and pg_dump/pg_restore persistence of exhausted operating/development authority and complete immutable history.

The 51 supplied skips include 46 Linux bootstrap/CLI cases and five opt-in PostgreSQL cases. The 54 fresh tests use SQLite/scripted or mocked runtime paths. None of these results qualifies Linux runtime admission, actual PostgreSQL/advisory-lock behavior, pg_dump/restore, provider invoices, real model quality, paid activation, production TLS, off-host restore, deployment, or a project-wide ceiling for tools bypassing this service. Backups/clones still require fencing of the old spending authority at promotion; this slice does not implement cross-database distributed billing. Those are approved scope limits, not findings against this Task 1 diff.
