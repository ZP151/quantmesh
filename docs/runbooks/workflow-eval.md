# Replaying workflow contract evidence

Run `python -m tools.eval_harness run --output <new-owned-directory>` from the
checkout identified by the evidence code revision. The default frozen catalog is
`benchmarks/quantmesh_v2/dataset.json`; `--catalog`/`--dataset` and `--repo` select
explicit inputs. Use `--timeout 120` for comparable evidence. The frozen cases
reference existing offline pytest contracts, synthetic scripted inputs and three
unchanged desired safety assertions from the September audit.

Before replay, install the existing audited dependencies; no model API or DB is
required. Inspect `run.json` for code SHA, source hash, dirty diff hash,
environment, catalog hash, verifier fingerprint and input-stability results.
Restore the exact source revision and matching test/harness bytes. A replay
re-executes acceptance; timing, process IDs, temporary paths and fresh model calls
are not promised byte-identical. Metadata traces contain report phases and
instrumented boundary outcomes; test source bytes contain scripted fixtures.

`results.jsonl` and `trace/<task-id>.json` retain each verdict, fixture digest,
verifier digest, interventions and nullable usage. `logs/<task-id>/` retains full
raw stdout/stderr plus events with owned PID, timing, exit and timeout. The reused
observer terminates only its own child tree on timeout. Timeout is failed with
infrastructure category; skip/xfail/xpass remain skipped. Setup/collection/teardown
errors are error with infrastructure category. Task success uses all 24 cases as
denominator. Verifier success counts collected pytest items; it is a distinct
denominator, including parameterized and class selectors. The plugin saves all
collected IDs before calls; timeout retains that full denominator and gets no
verifier passes. When collection evidence is unavailable, the denominator and
verifier success rate remain null. Categories describe observed acceptance boundaries, not
proven root causes.

Compare with `--baseline <prior-run>/run.json`, or:

```powershell
python -m tools.eval_harness compare output/eval/baseline/run.json output/eval/candidate/run.json --output output/eval/comparison.json
```

Only complete stable runs with equal schema/taxonomy, catalog/verifier hashes,
timeout and exact case IDs/acceptance/digests can compare. Explicit complete status
and source, verifier and catalog stability flags are required. Code changes are the
subject of comparison; environment equality is reported separately. A regression
is a prior pass becoming non-pass; denominator is prior passes. Latency is measured
per subprocess, including startup. No speed or performance claim follows from two
samples. Legacy 1.x catalogs/runs are incompatible and must remain unchanged.

The production catalog is frozen once after review using the existing seed:

```powershell
python -m tools.eval_harness freeze --cases benchmarks/quantmesh_v2/cases.json --output benchmarks/quantmesh_v2/dataset.json
```

The freeze command refuses overwrite. `cases.json` preserves the 24 IDs, sources
and desired assertions; its migration changes category labels and the path of the
three copied audit verifiers. Retrieval maps to data, context to policy; explicit
authority/origin/quote-fence cases map to policy. No historical run is relabelled.

`--inject-known-bad` adds a labelled verifier fault and must exit 1 with actual
failed reports. Keep this output separately; it cannot become a comparable
improvement. Scripted fixtures certify only local workflow/contract behavior.
Real PostgreSQL, Linux containment and paid model semantics remain pending under
their own issues. A red normal baseline must be repaired by the production owner;
never remove cases, invert assertions or manufacture a green catalog here.
