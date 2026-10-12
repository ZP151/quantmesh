# Validation tiers — #132 recovered for iteration 0038

Use the existing `tools/gate_policy.py` and `tools/quality_gate.py` entry points.
The committed #132 implementation at `b36a5528` is reused against baseline
`55c6431`; legacy dirty observer experiments were inspected only for their
Git status and were not imported. No second validation framework is introduced.

## Developer action and outcome

Obtain a deterministic changed-path decision, run bounded feedback, and retain
logs and elapsed time. Diagnostic success does not certify a candidate.

```powershell
python tools/gate_policy.py decide --base origin/main --head HEAD
python tools/quality_gate.py fast --base origin/main --head HEAD
python tools/quality_gate.py --tier fast --plan-only
python tools/quality_gate.py domain --domain ai --plan-only
python tools/quality_gate.py browser --plan-only
python tools/quality_gate.py release --plan-only
```

The public selector `select_tier(changed_paths, event)` returns exactly `fast`,
`domain`, `browser` or `release`. Non-PR events select release. Paths must be
repository-relative; malformed/absolute/traversal input selects release and is
never used as executable command input. NUL-delimited Git diffs retain deleted,
renamed and type-changed safety paths. Missing/empty diffs select release.

| Tier | Coverage and use |
| --- | --- |
| fast | Ruff, mandatory paper/live, risk, accounting, secret and persisted-evidence assertions, gate tests and reviewed direct test mappings. Browser and declared slow families are excluded. Documentation changes still keep this safety floor. |
| domain | One named, explicit reviewed test-family map plus mandatory safety assertions. Cross-cutting sources can select multiple independent module jobs. |
| browser | All currently discovered browser E2E modules, including existing live/chart/session cases; Chromium is installed in CI. Route changes also retain selected domain jobs and fast feedback. |
| release | Unknown paths; safety, broker, auth, persistence, dependency, workflow and gate changes; main pushes, version tags and manual runs. CI invokes the full fresh-clone release gate. |

`quality_gate.py --tier fast` without a base deliberately runs an explicit
local diagnostic subset. It does not claim that a safety-changing diff is
eligible for fast-only acceptance. The base-aware command refuses a stronger
decision and prints required follow-up commands. `build_commands(mode,
decision, domain)` retains the existing richer command objects: argv, cwd,
name and timeout, rather than introducing a second command builder.

`quality_gate.py release --diagnostic` is an explicitly acknowledged fail-fast
complete-Python diagnostic, useful only when a broad diagnosis is necessary.
The release plan separately identifies `python tools/release_gate.py` as the
certification command. Diagnostic fast/domain/browser/release jobs never
substitute for that final certification.

## CI policy and evidence

PR classification schedules fast plus applicable domain/browser coverage.
Unrecognized tiers or failed classification schedule release and cannot turn
the aggregate green. The existing `CI / python` job checks every selected job
and requires classification and fast success. Only superseded runs of the same
PR can be cancelled; main/tag/manual runs retain their own run IDs. The Security
workflow remains independent and unchanged.

Each diagnostic command shares the committed release runner's owned-process
observer. `events.jsonl` contains step start/end timestamps, PID, timeout,
elapsed seconds, actual exit code, timeout status, retained log path, sparse
progress/failure events and available slow-test duration rows. Empty slow rows
mean no duration report was available, including timeout before pytest summary.
Live output writes directly to the log, without a pipe reader holding shutdown.
Timeout cleanup targets only the process tree launched by this step. It never
controls a market source, Windows helper, private tunnel or AWS process.

Set `QUANTMESH_GATE_LOGS` to retain local logs at a chosen owned path; otherwise
a fresh `quantmesh-gate-*` temporary root retains them. CI uploads diagnostic
logs after success or failure. Release lifecycle lines and log paths remain in
Actions output; `--keep` retains a successful release's temporary clone/logs.
Pytest commands receive unique owned basetemp roots; only those roots are removed.

## Final boundary

Root runs one complete exact combined-head clean-checkout gate after integration:

```powershell
python tools/release_gate.py --keep
```

This gate keeps version, fresh environment, license/dependency advisory closure,
frontend build/tests/consistency, full pytest without `-x`, golden path and clone
cleanliness checks. A changed candidate SHA invalidates earlier certification.
Neither historical FAST evidence nor the interrupted legacy full attempt is
current release evidence. Do not launch concurrent full suites on this Windows
host. Failed installs or upstream prerequisites remain failed gates; no bypass
is permitted. Current ambient license closure mismatch is recorded in the
recovery handoff, and the root-owned lock is not changed by this slice.

## Coordinator handoff

Planner: one developer action is bounded diagnostic feedback; metric is the
observed FAST duration, with deterministic escalation as acceptance. Non-goals:
product behavior, jobs, UI, strategy math, live authority, deployments or sources.
Quant researcher: no numerical/financial semantics change; cost, leakage,
lineage, paper/live and AI-advisory contracts remain represented by the safety
floor and final exhaustive suite.
Implementer: committed policy/runner/workflow/tests reused, four public tiers,
malformed input rejection, shared progress and slow-test evidence.
Reviewer and Verifier: use the final recovery handoff for fresh RED/GREEN,
review findings and exact boundary results. Root mirrors these role outputs
into iteration0038 and decides ADR/roadmap integration, human review and final
certification. The legacy ADR-0020 is reference evidence, not newly accepted
architecture in this baseline.
