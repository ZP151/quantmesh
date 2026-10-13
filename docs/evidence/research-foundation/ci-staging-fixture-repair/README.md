# Native fixture teardown repair after CI38346386735

Exact57a CI terminates FAILURE: 4487passed/5failed/111skipped/9warnings,
2899.87s. Full actual diagnostic logs identify five staging native admissions;
this is distinct from the old quiet-log inference. Hosted independent service
is separately successful:137passed/5PGskips/81licenses, exact7 top-level
receipts, no recursive fixture upload. Its original still_running field is a
snapshot at service verification; the whole CI is now terminal FAILURE.

Root exact-source native order REDs: Moomoo4pass/1fail leaves four executor
workers; fence1pass/1fail leaves runner and executor. SIGCHLD0 throughout local
snapshots. Original hosted predicate inventory is absent; local proof does not
invent that historical observation. New behavioral shutdown regression fails
on loop.is_closed, after an earlier collector-permission error kept separately.

Only two test files change. asyncio.Runner owns tasks/executor/loop. Fence
cancels its parent task, and a local quiet socket handler sends the same two
burst frames then observes socket closure instead of sleeping an hour. Shared
venue fixture, production stage/admission/fork/pins and trading fences stay
unchanged. Owned thread terminal and closed-loop assertions expose failures.

First attempted green is retained as RED:113pass/5fail/1teardownerror12.63s,
with bounded reviewer P1 about the hour-sleep handler. Corrected full affected
three-file native boundary:118pass/0skip/0fail/0error8.64s. All118 pre-test
snapshots show MainThread/SIGCHLD0. Bounded review closes the initial P1.
Native kernel/C-library threads are not inventoried by Python snapshots:
12fork deprecation warnings remain among17 warnings. This is not live host,
production kernel-thread, vendor, model or full Python3.13 CI qualification.

Ruff/diff pass. Initial dependency seals fail on omitted harness import paths;
those failures are retained, without repeating tests. Corrected dependency
admission proves6669RECORD/81licenses/zero.pyc. No package cleanup or borrowed
environment mutation. Raw outputs, exact patch, review, actual CI streams and
service receipts are flat/hash indexed; binaries/private pytest inputs absent.
New reviewed source requires a new exact-head CI; old runs are never replayed.
