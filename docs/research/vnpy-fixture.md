# vn.py fixture workflow — issue177

## Start locally

Use a separately installed Windows Python3.12 environment containing official
vnpy4.5.0, vnpy_ctastrategy1.4.1 and vnpy_sqlite1.1.3. This slice does not install,
package or redistribute that environment. The pinned synthetic CSV comes from the
retained engine bakeoff; no market data download or account is needed.

```powershell
$env:PYTHONPATH = (Join-Path (Get-Location) 'src')
python -m quantmesh.api.vnpy_fixture --python C:/external-vnpy/Scripts/python.exe `
  --fixture C:/fixture/fixture.csv --root output/vnpy-fixture/jobs --port 8765
```

Open the bundled workstation at `http://127.0.0.1:8765/app/research/jobs`,
select **vn.py official strategies · fixture experiment**, configure parameters
and costs, submit, then **Open verified report** and **Download report JSON**.
Default production workstation routes do not enable this external experiment.
For frontend development, use a second terminal: `cd frontend`,
`npm run dev -- --host 127.0.0.1 --port 5178`, then open the same route on port5178.
`python tools/build_frontend.py` rebuilds the committed package bundle;
`python tools/build_frontend.py --check` verifies it matches frontend source.

费用单位：手续费为成交额bps；半价差和滑点为每单位每笔成交USD，二者相加交给原生引擎。
报告保留原生逐日盯市和成交语义；固定合成数据仅证明工作流，不能证明策略盈利能力。
进程重启后活动任务不恢复。已完成报告应下载保存；输出目录保留的内容哈希文件不是生产任务库。

## Acceptance evidence (2026-10-16, independent d90 worktree)

- Planner/Quant: tracked spec and plan under `docs/superpowers/`, ADR0029;
  scope approved directly by operator, acknowledged by main coordinator.
- Implementer: separate API/DTO/runner and bounded Research jobs panel. Imports
  unchanged official strategies; fixed1950replay/2340warmup bars and source pins.
- Verifier: backend contract/API28passed/1.93s after RED6failed19passed. Tests cover
  malformed costs/params, identity/idempotency, capacity, cancel/timeout/failure
  cleanup, corrupt report and independent cashbook/lifecycle/date checks.
- Verifier: actual native API acceptance1passed/9.63s, four real owned processes:
  DoubleMA twice with identical report hash, doubled costs, AtrRSI33fills.
  Baseline end balance100045.48285USD; doubled costs100043.5957USD. Source/fixture
  hashes and lifecycle match. Actual raw logs/native reports in
  `output/vnpy-fixture/{native-final.log,native-final/}` (ignored local evidence).
- Verifier: frontend existing baseline14 plus vn.py6 tests pass (20total/5.86s).
  RED catches retained form mismatch and running→queued regression before fixes.
  Build succeeds; current lint warnings are five existing component-export warnings.
- Verifier: real browser selected ATRRSI then DoubleMA, set fast8/slow18/fee6bps,
  submitted, observed succeeded1950/1950 and opened SHA-verified report.31fills,
  end100046.09744USD, fees1.89256USD, spread+slippage0.31USD. Actual downloaded
  reportSHA256 `22298fe1cfb9383fc8bec0092fd0d8b190c68cba50aa1130e3950ac528f0b7fe`;
  requestSHA256 `7b416f555fb5566683b990b94c408dc9b6a6e630dd298b73843b16222e7b5fff`.
  `output/vnpy-fixture/browser-desktop.png` and `browser-report-ax.txt` show the loop.

## Remaining delivery gates

Two bounded read-only review rounds are complete: final PASS, no remaining P1/P2.
All three initial P2 findings have RED/GREEN evidence: retained active GET404
recovery; cancellation capacity held until child cleanup; startup adapter/runner
source drift rejection. Final focused backend31passed/1.79s; frontend31passed/8.81s.
The final reviewed native source passed four real runs in8.47s, exit0, at
`output/vnpy-fixture/{native-reviewed.log,native-reviewed-exit.json,native-reviewed/}`.
The full frontend gate passes35files/436tests/115.01s, explicit exit0.

Built-package browser acceptance uses the optional API's own served SPA at
port8765: fast8/slow18/fee6bps yields the same native31fills/end100046.09744USD.
Actual downloadSHA256 `57134549cb2f95127c3a129d24656ccb03723d25f057469643f062a4780f6720`;
requestSHA256 `2f4c74054819c196da9ce0105a9e8549bbfa875e0636c040a5fd7affde8bbb4d`.
Earlier dev-server evidence above remains bound to its original adapter hashes.
`browser-built-{desktop.png,mobile-report.png,ax.txt,downloaded-report.json}` and
`browser-built-mobile-layout.json` preserve the final loop.
Viewport is390px and the document content is375px (scrollbar included in viewport);
there is no horizontal document overflow. Full-page mobile capture was unavailable;
normal viewport capture succeeded and includes the actual report.

### Windows full backend gate did not complete

`python -m pytest -q --basetemp output/vnpy-fixture/pytest-full` was interrupted
after roughly10minutes at9%, exit-1. It is **not a passing gate**. Read-only py-spy
stacks show existing demo seeding in DuckDB `Lake.read_bars:216` and later manifest
scanning; root cause is undetermined. The original inbox testcase isolated in one
fresh process passes1test/51.45s/exit0, so a permanent deadlock or a known environment
bug is not established. Related lake/demo/inbox source has no diff against d90.

The main coordinator requested a bounded stop after verifying owned PID72068,
Python executable, exact command, cwd, start time and empty child list. No other
process was stopped. Raw logs/exit/stack/identity receipts are
`backend-full{.log,-exit.json,-stack.txt,-stack-stop.txt,-stop-receipt.json}` and
`backend-blocker-probe{.log,-exit.json}` under `output/vnpy-fixture/`.
No unrelated source/dependency repair and no second local full run were attempted.
Normal Linux PR CI must supply applicable full gates; Draft PR is not merge-ready
until required CI and human review pass. No final completion, production admission
or deployment claim follows from the focused/native/frontend green evidence.
Shared iteration/roadmap/reuse updates belong to the main coordinator.

The experiment retains at most32jobs per process and one owned attempt at a time.
Export completed reports before restarting to reset this bounded local history.

Final bounded regression across the new adapter/API and unchanged baseline job,
job API, report artifact and options suites passes106tests/1skip/28.50s, exit0
(`backend-boundary.log`, `backend-boundary-exit.json`). Existing generated OpenAPI
is current, bundle--check is current, Ruff src/tests/tools and formatting pass.
Frontend locked-license review passes362packages; its lock is unchanged. These
results remain separate from the interrupted full backend gate above.

## Regression commands

```powershell
python -m pytest tests/test_vnpy_fixture.py tests/test_vnpy_fixture_api.py -q
python -m ruff check src/quantmesh/research/vnpy_fixture*.py src/quantmesh/api/vnpy_fixture.py tests/test_vnpy_fixture*.py
git diff --check
```

External native test is explicit opt-in: set `QUANTMESH_VNPY_PYTHON`,
`QUANTMESH_VNPY_FIXTURE` and optionally `QUANTMESH_VNPY_EVIDENCE`, then run
`python -m pytest tests/test_vnpy_fixture_native.py -q`. Otherwise it skips honestly.
From frontend: `npm exec vitest run src/screens/VnpyFixturePanel.test.tsx
src/screens/ResearchJobs.test.tsx -- --maxWorkers=1 --pool=threads
--no-file-parallelism`, `npm run build`, `npm run lint`.

## Upstream and runtime packet

[Official CTA module](https://github.com/vnpy/vnpy_ctastrategy) and
[official lifecycle documentation](https://www.vnpy.com/docs/cn/community/app/cta_strategy.html).
The retained official CTA wheelSHA256 is
`d625ebbff1fcf1a61794bf7c75c13f4bcfea333b3d80d0ada36292a09100288f`.
FixtureSHA256 is
`b27b6ed461cf58e9e1c3e4a40edb9e718feab6ace52cc29afb38ef6aa8f7dd96`.
Official MIT LICENSE and unmodified source oracle are retained externally under
`output/0038-strategy-framework-research/bakeoff/upstream/cta-wheel-original/`;
49distribution metadata/license inventory and prior42check bakeoff are preserved
there. Complete external transitive licensing/security/release qualification is
not established by these fixtures and no closure is added to core dependencies.
