# External CI feedback controller — Planner scope superseding issue292 logger

Issue292/PR294. This separately authorized Planner reduction supersedes the
in-process feedback design in 2026-11-06-ci-feedback.md; the old specification,
plan, reviews, CI569 and diagnostic originals remain historical evidence.
Base857f8a71e48607b1c4aba0db14d6c1765eb3125e. Implementer owns C; Parent owns
independent two-axis review, normal CI and publication. No third unrecorded
structural patch is authorized. New scope has R1 plus one consolidated known fix.

One developer action runs the same early contract; one outcome is a bounded,
truthful failure/current-node summary outside the process running the tests.
Retain the twelve complete contract modules, ABI/default checks, original tests,
standard --maxfail=1, fixture teardown and every later successful release step.
Keep the original two CI_PROFILE targets and export schema unchanged. Withdraw
only the newly added _Feedback observer and its --ci-events/--ci-log wiring.
The existing plugin may retain the pure collection-required-target check.

Reuse release_gate.run_step and its process ownership, stdout/stderr log and
controller clock. Before spawning, create persistent log and feedback artifacts.
Pytest uses -vv and its built-in JUnit result, with no new dependency. The parent
reads these originals to publish STARTING/RUNNING/current-node/first-failure and
terminal status. Active test subphase is UNOBSERVED; do not infer setup/call/
teardown from a node-start line. Terminal failure node/phase comes from built-in
results, with the ordinary assertion log reference. Do not copy assertion text,
locals, environment, argv or provider data into structured metadata.

Distinguish PASSED, TEST_FAILED, INFRASTRUCTURE_ERROR and TIMEOUT. Pytest internal
errors, missing/malformed/inconsistent terminal evidence, or observer failures
must never turn green. Preserve last observed node and explicit missing evidence;
do not manufacture an assertion or failure phase. Parent elapsed time must remain
real when child fixtures mock os/stat/fstat/time/path/subprocess. Bound metadata
and current-node storage; retain original ordinary/JUnit logs for review.

Source-accurate acceptance uses actual child processes: mocked OS/clock while
parent evidence remains valid; first failure/normal teardown/first-stop; internal
error with last-node and missing evidence; all-pass collection/later steps;
owned timeout and prelaunch persistence. Run the actual CI569 failing None node
without early fixture undo or source changes, plus all four ABI regressions.
CI569 primary remains UNKNOWN: local OFF/ON both passed on pytest9.1.1, while
CI569 used Python3.13.18/pytest9.2.0. Clock contamination was proven separately.
This change must not claim to fix the unknown primary exception.

No baseline test deletion, new skip, quarantine, timeout relaxation, dependency
installation, version probing, SDK/provider action, runtime7 change, broad602/
full-contract/frontend rerun or WSL identity experiment. Only superseded new
_Feedback tests may be replaced; report baseline and new collection differences.
Private publication controls and full normal-CI qualification remain separate.

Capacity uses only central P37/IVV_CI_EXTERNAL_CONTROLLER_SOURCE1_COMMON15_LOCAL16_REMOTE0_NET16MiB_20261106_01:
source1MiB, common15MiB (normal CI raw/archive8, serial scratch4, failure history2,
coordination1). No old hold refund. All new evidence is in controller-scope-01;
record cumulative file bytes rounded to4KiB plus4KiB per directory after each
round, including retained failures, before proceeding to the next round.
