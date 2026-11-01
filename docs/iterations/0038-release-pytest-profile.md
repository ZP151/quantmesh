# Iteration 0038 — bounded release pytest diagnosis

Issue: [#269](https://github.com/ZP151/quantmesh/issues/269). Base:
`e2eab51d7476f8e741f2ce2998294a8743ea06c1` (`origin/main`).

**Planner.** User action: inspect two slow nodes in the next ordinary Linux
release log. Measurable outcome: at most two `CI_PROFILE` lines, one per fixed
node, with capped function counts/times and hashed calendar identities. No extra
test invocation, CI run, dependency, broader profiling or product behavior change.

**Quant researcher.** The profile is diagnostic, not evidence of a calendar
optimization. Session argument digests include the pinned calendar version and
do not expose values. Cumulative function times can overlap; calendar wall time
can also overlap across worker threads. The profiler adds overhead. No dataset,
leakage, cost model, strategy, order or trading authority changes.

**Implementer.** The release gate adds `-p tools.ci_profile_plugin` to its
existing full pytest command. The plugin instruments only the two exact call
phases, restores the original calendar method in `finally`, retains at most 256
distinct digest counters and emits at most 12 rows of each kind per node. Its
`cProfile` functions cover the pytest call thread; the calendar wrapper also
counts test worker threads. Synthetic unit tests exercise restoration, failure,
digest distinction, bounded output, fixed targets and hook emission.

**Reviewer.** An independent read-only review of the four source/test paths
reported no P1/P2. It did not run CI or the two slow nodes.

**Verifier.** RED plugin import and release command expectations failed before
implementation. The final two-file targeted command passed 27/27 with the
plugin loaded (15.26 s); Ruff lint, changed-source format and
`git diff --check` passed. The Linux measurements remain pending the next
normally triggered release CI. The Windows `.venv` is missing `pg8000`; its
earlier partial failure does not establish the Linux bottleneck.

**Resource forecast.** Before source edits, the 4 KiB cluster estimate was
59,641,856 bytes for this managed worktree plus 606,208 bytes of Git metadata,
under the approved 64 MiB code/profile hold. The preserved earlier analysis and
failure output was 3,839,885 logical bytes, or 8,323,072 bytes at the same
conservative cluster estimate; this pre-existing output is unchanged. Final
allocation after targeted tests: worktree 60,100,608, Git metadata 610,304,
earlier output 8,323,072 estimated physical bytes; worktree plus Git retain
6,397,952 bytes under 64 MiB. The combined two-hold estimate retains 2,269,184
bytes under 68 MiB. Test-generated caches and `.ci-profile-pytest-tmp` account
for some of that use; an attempted PowerShell cleanup was automatically rejected
by execution policy, so those untracked artifacts remain outside the commit.
No new worktree, virtual environment, CI job, provider call or server action was
made.

## Same-run profile export follow-up — 2026-11-01

Published PR #271 merged as `ca0856e35026da32837818639854be02a1521baa`.
Its ordinary release CI 41296471808 passed 7026 tests with 143 skips and
golden-path 60, but the saved Parent release-job summary contained zero
`CI_PROFILE` rows. Successful `run_step` wrote child stdout only to its temporary
step log; the release summary printed counts, then deleted the temporary root.
The workflow's artifact path consequently found no files. This retained
evidence does not establish whether either target was actually sampled or
whether the plugin emitted a line in the deleted child log.

**Planner.** Preserve the single full pytest and golden gates. Export at most
two validated records into the existing release stdout before successful
cleanup, or report `missing`/`invalid` without treating absence as a profile.

**Quant researcher.** This is evidence retention only. The cProfile thread
scope, calendar digest limits, timing overlap and overhead remain unchanged;
there is no measured Linux bottleneck or optimization claim.

**Implementer.** `tools/release_gate.py` now reads only lines beginning
`CI_PROFILE ` from its full-pytest child log, with an 8192-byte line ceiling,
exact two-node/schema checks, 12-row and 256-identity limits, and duplicate or
non-target rejection. It emits exactly one bounded `CI_PROFILE_EXPORT` result
per target before deleting the temporary root. The original plugin and test
node IDs, assertions, gate exit codes, dependencies and workflow are unchanged.

**Reviewer.** Independent R1 found one P2: an oversized JSON integer reached
`math.isfinite` and raised `OverflowError`, turning an otherwise passing gate
into a failure. A synthetic child-to-cleanup RED reproduced it; the validator
now range-checks integers before calling `math.isfinite` on floats. R2 is
Spec PASS / Quality READY with no remaining or new P1/P2 on this one correction
wave. Neither review ran CI or the two slow nodes.

**Verifier.** A synthetic child process exercising the real `run_step` log,
release summary and cleanup path failed RED with no export. The final scoped
export/plugin/command checks passed 17/17; cases cover success, failure,
missing sample, malformed or oversized line, huge integer, wrong schema, too
many rows, duplicate and non-target records. A broader two-file local run had
36 pass and one unrelated existing Windows timeout-reaping failure: its child
wrote after the timeout; this leaf does not alter that behavior. Ruff lint,
changed-file format and whitespace checks pass. These are synthetic checks,
not a rerun of either slow node, full suite or CI. A future normally triggered
release run is required to learn whether valid profile rows are present.
