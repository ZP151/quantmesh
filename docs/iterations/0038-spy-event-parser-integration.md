# Iteration 0038 — publisher integration of same-capture SPY event parser

Active workflow: [#205](https://github.com/ZP151/quantmesh/issues/205). The
immutable author iteration and ADR still link #177, which is an unrelated closed
fixture issue. This publisher note corrects the workflow reference without
altering the reviewed author files.

The integration starts at actual `origin/main`
`eee9d03a15852018f40aaa0c26463539c2859ef4` (tree
`93c50c309113ab3dc92300b6ff22e3b45a4e4d33`). The author commits
`6ef815613777a3656cfc60bc69719a589e95c9a2` and
`f3c55b3d89fefd43e87be9a563d102d459092afc` replayed cleanly. All six
author paths in the integration tree equal the final author tree byte for byte.
The author handoff JSON SHA256 is
`d48cbaa8b744dddef4858c56b9a18cbc6b98fb79703d911d6d0e840112ba373d`;
the reviewed bundle SHA256 is
`c5f6df8d34adc3eefe97b9ced5ac37d6f503c09add55c7cf07a709da817e706b`.

One publisher test-only change updates the existing F0 protocol identity pin.
On the exact expected NumPy 2.5.2 runtime, the old main protocol digest
`f5afaf49dd3402193e16e3da0a84f314050aa155aa663879a502ef6884516ddd`
reproduces. With the new offline normalizer source it becomes
`ac871ad84cc1ee20808414d5e989dcce7b7d0d7f59474edbd4c038088cf53457`.
A complete key comparison of the old and new synthetic protocols found only
`normalizer_sha256` changed, from the captured tool
`85ffc0f284f998db81390ea5a95aeba1be6b0486da8efe8aa5b3f67b08fc05ca`
to the new loaded offline tool
`0d94256bb55f7a1a61de4e25142400c091e7d03b584a131bd13b7899002a8a64`.
The engine, five other source hashes, window, rules and cost model are unchanged.
No numeric, cost, window or structural golden was changed.

Local publisher check: the new test file passed 49 tests using the repository
Python environment and an isolated pytest temporary directory; scoped Ruff
check and format check passed. That local environment has NumPy 2.4.6, while
the F0 test explicitly pins 2.5.2, so the exact-lock full suite is a CI gate.
The first local pytest invocation ran 49 tests but exited during global temp
cleanup with a Windows permission error; its output is retained in this task.

This is `FORMAT_COMPAT_ONLY_NOT_DATA_QUALIFICATION`. The immutable capture,
authorization and consumed marker remain original. Independent Quant has
accepted OHLC USD; historical volume shares and feed coverage remain unknown.
There is no qualified actual PostReview, freeze, acceptance or new strategy run.
The software merge does not authorize another capture, create new data facts,
change the one-job budget, or enable Paper.
