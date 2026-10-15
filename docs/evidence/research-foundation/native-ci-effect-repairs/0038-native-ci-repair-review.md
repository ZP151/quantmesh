# Native CI and effect integration repair review

Reviewed workspace: `C:/Users/15492/.codex-clean/worktrees/0038-research-integration/QuantMesh`

Verified HEAD: `4a7fff97f68c60fc02b31b3f6cff363132109ee8`.

Scope: working changes in exactly `.github/workflows/ci.yml`, `tools/release_gate.py`, `tests/test_release_gate.py`, `tests/test_ci_gate_workflow.py`, `tests/test_opend_private_terminal.py`, `services/research_agent/src/qm_research_agent/bounded.py`, and the new `services/research_agent/tests/test_effect_launch.py`. Two bounded source-review rounds; no source edits, environment changes, test execution, provider calls, credential access, server actions, or budget-architecture review.

## Findings

No actionable P0–P3 finding in the scoped working diff.

## Verified source evidence

| Area | Verified location | Assessment |
| --- | --- | --- |
| Release temp privacy | `.github/workflows/ci.yml:189` | Creates the dedicated release temp parent with mode 700 and exports it as TMPDIR before Python/setup and release execution. `tempfile.mkdtemp` at `tools/release_gate.py:391` places the gate root beneath that parent. |
| Release uploads | `.github/workflows/ci.yml:205` | Upload runs under `always()` and selects only `qmesh-release-gate-*/logs/*.log` and `logs/*.jsonl` at lines 211–212. Checkout, venv, pytest temp, and private fixture trees are outside those patterns. Existing successful-run cleanup remains at `tools/release_gate.py:625`; retained failure/crash diagnostics remain available. |
| Service uploads | `.github/workflows/ci.yml:247` | Directory upload is narrowed to top-level JSON, log, and XML files. No recursive fixture-tree upload was introduced. |
| Required service gate | `.github/workflows/ci.yml:254` and `:270` | Service remains a dependency and a required successful result. Working test update at `tests/test_ci_gate_workflow.py:164` executes the actual workflow Python program, including service failure, cancellation, skip, and missing-result denial at line 228. No selector or required-result weakening. |
| Release command | `tools/release_gate.py:534` | Only pytest verbosity changes to `-vv`; exhaustive suite invocation, durations 50, owned basetemp, and 10800-second timeout remain. `tests/test_release_gate.py:126` asserts the complete pytest suffix with no subset/filter arguments. |
| Terminal fixture | `tests/test_opend_private_terminal.py:269` | `O_NOCTTY` prevents the access-mode-negative fixture from acquiring a controlling terminal. It preserves the wrong read/write mode and the `descriptor_access` refusal assertion. Production terminal helpers are unchanged. |
| Owned effect interpreter | `services/research_agent/src/qm_research_agent/bounded.py:37` | Explicit child environment bytecode suppression and interpreter `-B` at line 39 preserve executable choice and module invocation. Private pipe payload, environment authority allowlist, child home, Windows Job Object ownership, Linux process group, timeout, response bound, and cleanup are unchanged. |
| Interpreter regression | `services/research_agent/tests/test_effect_launch.py:14` | Launches a real owned fixture child through `bounded_complete`; reports actual `sys.dont_write_bytecode`, consumes private stdin, asserts true at line 35, and checks fixture-package pyc absence at line 36. It meaningfully tests launch behavior without provider invocation or pretending to qualify the actual model runtime. |

## Verification and limits

`git diff --check` succeeded for the seven scoped paths. Review was read-only except this requested report artifact; tests were not rerun to avoid modifying or qualifying any shared environment.

Coordinator-provided prior observations are contextual evidence, not independently rerun here: 32 release-gate tests passed; 10 workflow tests passed; 121 native private-terminal/staging tests passed after the fixture repair; the bytecode fixture changed from false to true and passed. Actual CI run 38330059615 failed with full pytest SIGHUP rather than timeout. Native offline b107 still has an unresolved credential-output test failure (135 pass, five PG skips, one failure). This review makes no full-native-GREEN, host, PG, provider, credential, or production qualification claim.
