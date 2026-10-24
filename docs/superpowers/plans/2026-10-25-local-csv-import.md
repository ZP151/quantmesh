# Local daily CSV inspection and reference delivery

Issue [222](https://github.com/ZP151/quantmesh/issues/222), current human product
continuation. Related184 fixed-SPY import and183 retained research;183 explicitly
excludes product implementation, so its scope/results are unchanged.
Actual ACK2026-10-24T16:35:15Z/2026-10-25 00:35:15SGT. Contract by00:50:15SGT,
running API checkpoint02:05:15SGT, hard reviewed-handoff/STOP03:35:15SGT180min.

## Short design and user outcome

Import one already-held daily OHLCV CSV from the ordinary local workstation,
inspect source/date coverage/freshness/duplicate/missing/time/value facts and
the concrete reasons research qualification remains insufficient, retain a
verified input reference for existing experiment planning. No provider contact.

Actual origin/main9cdf321 already has P1's fixed SPY8-member ZIP, immutable
reports/reopen/download; P2 retained experiment inspection; P3 guarded paper
controls; the fixed synthetic vn.py runtime. Do not duplicate these loops.
The missing action is ordinary local CSV ingestion and reference hydration.

Reuse ObjectStore, CalendarService, Bar and DatasetManifest/DatasetRef, with a
narrow adapter under the same explicit research-snapshots-root opt-in. New
local-csv catalog stores canonical request/original CSV/pinned initial report/
reference and optional normalized CSV/manifest as immutable objects. No trusted
catalog admission/pointer or existing mutable lake writes. Identical imports
preserve the first receipt; cold reads verify content and all reference bindings.

Only explicit1d UTC bar-OPEN CSV with six fixed columns is supported initially;
moomoo/XNYS regular or hyperliquid/24/7 daily session grid, declared required
start/end,2MiB UTF8/10000rows/3MiB JSON body. Metadata/header errors422, semantic
quality failures retained201+REJECT. Dates are session labels, never historical
available_at. Source metadata and optional Phase1 preauthorization/post-review/
source-evidence digests remain claims; no new review/capture is required to
inspect a held file. Rights/PIT/action/cost calibration remain unknown even if
the caller claims approval. Unknown receipt time stays null.

Use existing calendar close+30minute research grace for completed daily bars,
not a vendor SLA. Check every raw row before any normalization; never silently
sort/deduplicate/impute data. Report all counts, cap located examples100/check
with explicit truncation. Structural reject yields no runnable normalized data
reference. Structural PASS can expose restricted local_research DatasetRef,
DatasetManifest and normalized CSV ObjectRef; reference is BLOCKED for runner
submission. read_bars verifies the complete pin and returns existing domain Bar
objects for existing baseline interfaces; only generated fixtures exercise the
engineering runner demonstration. No new strategy/backtest engine or synthetic
profitability claim. Imported user data does not enter the fixture runner.

## Ownership / fixed interface

Backend sole writer owns research/local_csv_snapshots.py, its focused rules
helper if needed, api/local_csv_snapshots.py, one include in existing snapshot
router, focused backend tests and this own plan/iteration/operator guide.
UI thread01a15290 owns frontend, tests and generated SPA/client. Contract sent
directly before15min; source response_model enables actual schema generation.
New /api/research/data-snapshots/local-csv POST/list/get/reference and immutable
original.csv/report/reference.json downloads. Full DTOs in the new module.

Do not touch live/buffer.py, server/runtime/credential/OpenD/cap/host, SDK/SSH/
accounts/providers, root Goal/automation/boards, dependencies/locks, frontend/
static or historical OOS. Paper/live and R1/R2/R3 authority unchanged.

## TDD / verification / delivery

- [x] Read actual main/P1/P2/P3, Phase1 pre/post/evidence and existing runner;
  create issue222; send fixed DTO/routes/error contract directly to UI/Quant.
- [x] Actual RED01: new local CSV module absent, one failure. DTO/router schema
  declared; actual workstation OpenAPI has typed POST and responses.
- [x] Implement bounded parse/check/storage/reference hydration; targeted
  pytest tests/test_local_csv_snapshots.py RED/GREEN with own samples.
- [x] Actual API tests for opt-in/origin/stream bounds/typed errors/201REJECT/
  downloads/cold reopen, original P1 API compatibility. Ruff/format/diff.
- [x] Run an owned loopback API, POST correct/incorrect synthetic files, inspect
  reports/reference, download originals and cold reopen; publish actual operation
  entry and limits to UI/main by90min, not only test counts/digests.
- [ ] Freeze candidate; independent Standards/Spec+affected-boundary review,
  at most2rounds/one aggregate correction; final applicable focused checks only.
- [ ] Durable commits and reviewed handoff to sole publisher/root for exactCI
  and normal merge under standing human authority. Preserve all failures/outputs.

Quant role: source/current/PIT/adjustment/volume/action unknown separated from
structural facts. Quant acceptance matrix is supplied independently under
output/0038-strategy-acceptance-research-20261018/local-import-qualification-20261025/;
consume concrete cases once, do not enlarge the platform. No test/JSON count is
a substitute for a usable import→inspect→reference loop.

Checkpoint:19applicable109pass/7existing warnings26.65s exit0,18changed static
checks PASS. Actual CLI port8874 imported correct and invalid owned samples,
returned PASS/INSUFFICIENT versus REJECT+row2, and preserved exact downloads,
IDs/first receipt/history across PID61044→34680 cold restart. Early helper
header-case failure is retained. Finality RED16/GREEN17 and Quant valid_rows
wording are included before freeze; final-head fresh receipt remains required.
