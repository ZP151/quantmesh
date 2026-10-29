# Issue 251: bounded complete-row acquisition work

## Scope and acceptance

Base: merged PR 250, `38c1fce4ecc6e0716a0769367decba707b67b2c9`.
One user action is inspecting saved history. Preserve every selected key and
full 17-column record with unchanged readonly, transaction and trading-safety
contracts. The new sparse scan model must perform no more than four source-sized
passes for 128 keys; the separate stored wide model must return all selected
records at 128 MiB, one thread, zero temporary disk and readonly access.
No schema, dependency, host, real-data, SDK or trading changes are in scope.

## Implemented checkpoints

- [x] RED: `tests/test_live_buffer_selective_gather.py` measured 134,217,728
  scanned rows against a 4,194,304 bound on merged source. Retained log:
  `output/payload-acquisition-20261029-031519/06-new-test-red.log`.
- [x] GREEN: change only the acquisition loop in
  `src/quantmesh/live/buffer.py` to at most 32 exact `VALUES` join keys and an
  inclusive range. The same new work test passed; a new stored wide test and
  14 boundary cases passed under the owned resource harness. Three isolated
  mutants failed as intended. The six-file source manifest and exact run logs
  are in `output/payload-acquisition-20261029-031519/`.
- [x] Review: independent R1 and final R2 found no actionable issues on the
  frozen six-file source, head `5de5fc09af685b19029c7c4fe74369fa870ee41f`.
- [x] Publisher preparation: mirror this decision and evidence into roadmap,
  iteration and ADR; verify the six source blobs and exact source tree; run
  changed-file Ruff/format and diff checks. The PR's exact-head CI and normal
  merge are subsequent gates recorded in the publisher's final receipt.
- [ ] Sole Server: on that merged source, separately accept the original API
  call, independent raw reference and normal reader/server close within the
  previously authorized host and resource bounds. This is outside this PR's
  software completion claim.

The new targeted tests are `tests/test_live_buffer_selective_gather.py` and
`tests/test_live_buffer_gather_boundaries.py`. The applicable broad verification
is the repository PR CI release gate; do not infer it from the local 16 cases.
The final publisher receipt records the exact run, checks, merge commit and
source catalog for the Server handoff.

## Exact-head CI correction checkpoint

The first PR 252 release run 40815733685 failed only on an unchanged older
snapshot test's hardcoded three-batch expectation for 300 rows. The reviewed
32-key implementation correctly uses ten batches. The publisher changed that
test assertion alone, verified the single formerly failing test, and retained
the failed run receipt. The six reviewed source/test blobs remain identical to
their frozen author versions. A fresh CI run on the corrected head is required;
the failed run is never relabeled as passing.
