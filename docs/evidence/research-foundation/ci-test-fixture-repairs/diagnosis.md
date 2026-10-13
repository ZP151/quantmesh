# Old CI38330059615 quiet-failure diagnostic

Bounded historical diagnostic, performed 2026-10-13. This report does not qualify a new candidate or supersede any native-service, terminal, source, or portfolio evidence.

## Verified observations

- Historical candidate: `216b378192bbc0a1742a28b7a1fc75a86ae2fda9`; locally verified tree `6a7fa1c9baddd62ed1e958fb3bb91861468105e5`.
- The old log reports execution of test-merge `1313c77aae39e76c3f168b25810926258c676d49`. That Git object is absent from the local object store. Candidate/merge tree equality was supplied by the coordinator; this diagnostic independently verifies only the candidate tree. No remote fetch was attempted.
- `output/0038-ci216b-terminal/failed.log` has 40 complete 72-symbol progress rows, then 34 symbols without a percentage: 2,914 visible statuses, 14 `F` markers and 20 `s` markers. The first complete row is 1%, so the visible run starts at its first progress row. Every full row is retained in `progress.json`.
- Failures occur at symbol ordinals 458; 1815,1822–1826,1840–1845; and 2189. These are **status-symbol positions**, not recorded node IDs.
- All percentages are consistent with total count 4,561–4,565 under pytest's floor percentage calculation.
- The full-suite step ends with exit code `-1`, `timed_out:false`, after 2,375.659 seconds; the log contains no pytest failure traceback or short test summary. On POSIX a subprocess return code of -1 denotes SIGHUP, but this diagnostic does not investigate the signal sender. This process termination is distinct from the 14 already printed failures.

## Bounded collection and mapping limits

An exact-candidate `git archive` was exported into the new owned directory `/var/tmp/quantmesh-ci-quiet-collection-sadscdcz/candidate`. Only collection ran broadly, with a 60-second bound, `-B`, `PYTHONDONTWRITEBYTECODE=1`, plugin autoload disabled, explicit pytest-asyncio, and cacheprovider disabled. Fixtures and test bodies were not executed during collection. Collection completed with exit 0 in 8.60 seconds, collecting 4,513 items with no collection errors.

The available native runtime is Python 3.12.3/pytest 9.1.1; old CI was Python 3.13.16 with release extras. Runtime lacks arch, lightgbm, sklearn, scipy, Playwright and moomoo. Six Playwright modules call module-level importorskip, changing collection order. Therefore **the collected item indices cannot be directly treated as CI failure node IDs**. No dependencies were installed or faked.

Static AST inspection adds the following source-defined counts solely for inference:

| Omitted module | Static count |
|---|---:|
| `tests/test_instrument_workspace_e2e.py` | 3 |
| `tests/test_live_chart_e2e.py` | 1 |
| `tests/test_live_e2e.py` | 7 |
| `tests/test_live_prediction_e2e.py` | 5 |
| `tests/test_spa_e2e.py` | 20 |
| `tests/test_workstation_e2e.py` | 16 |

These 52 items produce an inferred total of 4,565, matching every recorded percentage. The reconstructed browser-module skip positions match all 16 visible browser-skip symbols at ordinals 1711–1713,1908,1954–1960,2174–2178. The three earlier skips map to platform-specific FinRL containment tests, and ordinal2702 maps to the SDK-absence test; their precise runtime reasons are not recorded. The reconstruction's last visible status maps to `test_wrong_descriptor_access_mode_refuses[0]`, and its next item maps to `[1]`, consistent with the coordinator's separately investigated terminal boundary. These agreements strengthen the reconstruction but do not remove the collection/version/dependency divergence.

## Candidate identities — inference only

| Status ordinal | Old-log line:column within status row | Row percentage | Candidate node ID |
|---:|---|---|---|
| 458 | 88:26 | 11% | `tests/test_ci_gate_workflow.py::test_required_python_check_aggregates_all_gate_failures` |
| 1815 | 107:15 | 41% | `tests/test_linux_owned.py::test_fixed_creation_and_gated_start` |
| 1822 | 107:22 | 41% | `tests/test_linux_owned.py::test_creation_failure_never_guesses_container` |
| 1823 | 107:23 | 41% | `tests/test_linux_owned.py::test_output_limit_is_failure` |
| 1824 | 107:24 | 41% | `tests/test_linux_owned.py::test_terminal_output_cannot_succeed[oversized]` |
| 1825 | 107:25 | 41% | `tests/test_linux_owned.py::test_terminal_output_cannot_succeed[symlink]` |
| 1826 | 107:26 | 41% | `tests/test_linux_owned.py::test_transient_cleanup_can_retry_exact_ownership` |
| 1840 | 107:40 | 41% | `tests/test_linux_owned.py::test_admission_and_owned_cleanup[cgroup]` |
| 1841 | 107:41 | 41% | `tests/test_linux_owned.py::test_admission_and_owned_cleanup[digest]` |
| 1842 | 107:42 | 41% | `tests/test_linux_owned.py::test_admission_and_owned_cleanup[attach]` |
| 1843 | 107:43 | 41% | `tests/test_linux_owned.py::test_admission_and_owned_cleanup[nonce]` |
| 1844 | 107:44 | 41% | `tests/test_linux_owned.py::test_admission_and_owned_cleanup[id]` |
| 1845 | 107:45 | 41% | `tests/test_linux_owned.py::test_actual_oom_is_failure` |
| 2189 | 112:29 | 48% | `tests/test_live_router.py::TestStateEndpoint::test_root_and_api_mounts_agree` |

The coordinator separately identified/repaired the first CI-aggregation assertion. This diagnostic supplies its index match, not fresh validation of that repair.

## One actual narrowed reproduction

Only `tests/test_linux_owned.py::test_fixed_creation_and_gated_start` was executed at exact216b, in the owned export. Its engine fixture replaces `LinuxExecutionProfile.invoke` and `_attach` with fake objects; no Docker daemon, real source provider, credentials, model endpoint or live service was touched. Process UID/GID were 1000/1000; fixture profile UID/GID are explicitly 10001/10001. The test actually failed:

```text
src/quantmesh/research/linux_owned.py:307
os.chown(self.output, profile.uid, profile.gid)
PermissionError: [Errno 1] Operation not permitted
1 failed, 1 warning in 2.11s
```

This establishes the local target's failure cause: the command fixture patches the engine boundary but leaves the POSIX ownership mutation real. This exception occurs before fake container creation. The other inferred cluster tests call the same constructor through the same fixtures, making shared ownership failure a source-supported explanation, **not twelve independently reproduced failures or a recovered old-CI traceback**. The actual CI runner's numeric UID/GID are not available in the old log; no 1001 claim is made. No production ownership behavior was changed.

## Live-router source hypothesis — not reproduced

The inferred 48% test at `tests/test_live_router.py:184` makes two sequential requests and compares `without_clock` results. That helper strips kind-level `age_ms` and ignores top-level `generated_at`, but retains `session_freshness`. At exact216b, `feed.py:606` adds per-kind session freshness and `feed.py:622` adds per-instrument session freshness; `_session_view` serializes `SessionFreshness`, whose `evaluated_at` is set to each request's `now` (`session_freshness.py:69`). Thus the comparison retains request-specific nested timestamps. This is a concrete source-supported hypothesis for the inferred candidate; the old assertion payload is absent and no second reproduction was authorized or run.

## Preserved runtime and scope

The 81 runtime RECORD-file SHA-256 values were identical before/after collection and after the single reproduction; bytecode count remained zero. Raw collection/reproduction stdout, stderr, commands, environment without inherited credentials, exit codes, hashes, static source excerpts, node IDs and inferred maps accompany this report. Export contains no `.git`; collection uses exact source but does not recreate the CI installation metadata or plugin closure.

No repository source edits, historical evidence overwrites, installs, network calls, old CI reruns, full local test executions, daemon operations, or production/source qualification were performed. Investigation stops here; coordinator owns any fixes and their subsequent evidence. For the next new-head CI, a persisted collection list plus failure-node diagnostics before fatal process termination would eliminate this index reconstruction's uncertainty. This is a diagnostic recommendation only.
