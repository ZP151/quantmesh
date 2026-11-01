# Two-node release pytest profile — issue 269

## Goal and design

On the next ordinary Linux release run, use the existing single full pytest process
to emit one bounded diagnostic line for each of two fixed slow nodes. Register
`tools.ci_profile_plugin` only in `tools/release_gate.py`'s full pytest command.
The plugin profiles the pytest call thread with stdlib `cProfile` and temporarily
wraps `CalendarService.sessions` to count all-thread calls by SHA-256 of immutable
calendar ID, dates, policy and pinned version. It restores the method after each
call phase. Each line contains at most 12 functions and 12 calendar digests;
only 256 distinct digests are retained. Times overlap and include overhead.

No second pytest invocation, gate timeout change, golden-path change, product
calendar/ledger/provider edit, real data use or new dependency is permitted.

## Execution and evidence

- [x] Test first: `python -m pytest -q tests/test_ci_profile_plugin.py` failed at
  collection because the plugin did not exist. The release command expectation
  also failed before insertion.
- [x] Implement the plugin and register it in the one full pytest command.
- [x] Targeted green: `python -m pytest -p tools.ci_profile_plugin -q
  tests/test_ci_profile_plugin.py
  tests/test_release_gate.py::test_full_pytest_command_is_exhaustive_with_duration_reporting
  --basetemp .ci-profile-pytest-tmp` passed 7 tests. Ruff checks passed.
- [x] Independent read-only review found no P1/P2 in the four source/test paths.
- [x] Final same-byte targeted checks: the plugin loaded explicitly and 27/27
  synthetic/release-gate tests passed; Ruff lint, changed-source format and
  `git diff --check` passed. The physical worktree-plus-Git estimate was below
  64 MiB after testing.
- [ ] Commit and PR handoff.
- [ ] A later normally triggered Linux release CI run supplies the two actual
  profiles; this preparation does not trigger or replace that gate.

The release and golden gates remain mandatory at the eventual PR boundary.
The two slow nodes and the full suite are explicitly excluded from local checks
in this preparation because the reused Windows environment lacks `pg8000`.
