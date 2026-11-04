# IVV Executable Failure Evidence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. No additional agents; Parent owns review and Git.

**Goal:** Preserve discriminating hardened-child executable rejection evidence through the actual existing STOP path.

**Architecture:** Keep the original lazy guard, retain its one resolved value, and attach a closed optional observation only after recovery EXECUTABLE FIRST_FALSE. Reuse origin-marker/IPC/reader/selector machinery and publish a minimal versioned ops successor.

**Tech Stack:** Existing Python3.12 production/Python3.13 offline, pytest/Ruff, stdlib only.

**Spec:** ../specs/2026-11-05-ivv-executable-failure-evidence.md

## Global Constraints

Existing isolation, actor/batch/rate/ownership controls, false predicate rejection and actual UNKNOWN remain. No SDK0 mode, SDK/host calls, retries, source commit/CI by worker, new dependency, Product/math change or old ops overwrite. Server forecast6,647,808+393,216=7,041,024 <=7,340,032 bytes; preserve all failures.

## Review Focus

- Stateful truth/comparison or throwing lookup must preserve exact original semantics.
- Diagnostic stringification/lookup/serialization must not override primary failure.
- Malformed/public-looking secret payload must not enter authenticated STOP output.
- Private namespace drift must not be presented as SAME or host evidence.
- New pure codec dependency must reach actual pinned remote and local selectors.

## Task 1: Complete rejection evidence vertical slice

Files: tools/research/ivv_trusted_runner.py; tests/test_ivv_executable_failure_evidence.py; only necessary parametrization in tests/test_ivv_runtime_failure_evidence.py. Private R/operations-02/{native_packet,transport_profile,return_frame,run_recovery}.py and R/server/executable-evidence-01 evidence.

Interfaces: optional origin_failure.executable_observation, schema in spec. _runtime signature unchanged; select_origin_failure remains the strict public selector. New select_executable_observation(value) and selected nested path/lookup validators are extracted by the actual native_packet.failure_codec_source alongside existing pure functions. Existing _failure_record/_failed_packet/_child_failure/read_runner_failure/select_failure_status propagate the validated origin dictionary unchanged.

- [x] Write actual _runtime and rejection IPC tests plus strict schema/privacy/namespace tests; record RED using isolated pytest bootstrap with repository src/tests first, plugin/cache/bytecode disabled and purpose-owned basetemp.
- [x] Implement per-call retained executable result and recovery-only failure observation; add strict pure validation without changing ordinary guard or exception semantics.
- [x] Create complete operations-02 successor preserving three unchanged modules and changing only pinned-codec extraction dependencies; test the actual source loader and profile STOP selection, no carrier invocation/build.
- [x] Run new tests and existing origin/trusted runner affected tests, scoped Ruff/format and whitespace once at coherent boundary; retain failures.
- [x] Freeze exact source/ops/docs/tests pins, actual geometry/capacity and limits in R/server/executable-evidence-01/HANDOFF.md; Parent stages/commits/reviews/publishes. No native completion claim.

Commands use C:/Users/15492/AppData/Local/Programs/Python/Python313/python.exe -I -B -X utf8 with PYTEST_DISABLE_PLUGIN_AUTOLOAD=1, explicit checkout/src and tests on sys.path, pytest -q -p no:cacheprovider. Per-run full invocations and exit codes are retained in the report. No independent whole-project rerun during this bounded correction; Parent owns final normal CI.
