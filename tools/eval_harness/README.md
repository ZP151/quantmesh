# Offline workflow Eval

Issue [#160](https://github.com/ZP151/quantmesh/issues/160), approved research
foundation Task 3. This adapts the existing uncommitted September harness from
the preserved `quantmesh-eval-harness` worktree. There is one entry point:

```powershell
python -m tools.eval_harness run --output output/eval/baseline
python -m tools.eval_harness run --output output/eval/candidate --baseline output/eval/baseline/run.json
python -m tools.eval_harness run --output output/eval/negative --inject-known-bad
```

Use the repository's audited Python environment with pytest/pytest-asyncio and
existing core dependencies installed. No dependency or lock change is needed.
Outputs must be new directories. A complete run with any failed, error or skipped
case exits 1. Invalid input or incompatible comparison exits 2. Baseline failures
are evidence: the three desired legacy audit assertions currently fail against
production. Harness unit tests can pass while that workflow score remains red.

Catalog 2.0.0 freezes 24 existing IDs and unchanged executable acceptance;
taxonomy is specification/data/tool/model/verification/infrastructure/policy.
Legacy 1.x evidence remains incompatible, including its different category names.
Fixture/verifier byte pins, source references and per-case digests are enforced
before any child process. Scoring code and the reused owned-process observer are
also pinned. The child loads the plugin by its fingerprinted absolute path, so
`--repo` cannot shadow it with another checkout's plugin. A changed pin requires an
explicitly versioned benchmark migration,
never editing an old run to claim improvement.

Each case uses an isolated pytest child with a metadata trace, complete raw log,
start/progress/end events, timeout budget and owned scratch directory. Trace
events instrument ModelGateway complete/complete_structured and ToolRegistry
dispatch. A measured zero means no calls crossed these instrumented boundaries;
missing/incomplete telemetry is null. This does not count arbitrary calls outside
those boundaries. Tokens and cost are null: scripted transports are not provider
usage. Human intervention is operator-declared via `--intervention TASK_ID`, not
an inferred measure of all work outside the run. No task retries are performed.

The negative control injects a verifier fault before test calls and retains actual
pytest failed reports and nonzero exit. It is labelled and excluded from candidate
improvement comparisons. Ordinary runs retain the independent historical desired
safety assertions without xfail or inverted assertions. Offline sockets and HTTP
model transport are blocked except numeric loopback IPC; trusted repository
fixtures are not an arbitrary-code sandbox. Scripted responses prove workflow
contracts only, not model reasoning or financial returns.

See [runbook](../../docs/runbooks/workflow-eval.md) and
[benchmark evidence](../../benchmarks/quantmesh_v2/README.md).
