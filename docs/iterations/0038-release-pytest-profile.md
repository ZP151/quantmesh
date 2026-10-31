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
