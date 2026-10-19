# Inspect the frozen SPY experiment — issue191

Status: implementation and local acceptance in progress. This guide describes
the approved interface; final observed acceptance is recorded in the
[P2 iteration](../iterations/0038-frozen-experiment-p2.md).

## Local startup

Use the existing workstation runtime. Select a snapshot root containing the
previously preserved SPY package and a separate local frozen-experiment root.
Both roots must be outside the resettable demo root.

```powershell
$env:PYTHONPATH = (Join-Path (Get-Location) 'src')
python -m quantmesh.api.workstation --demo --demo-root output/frozen-demo `
  --research-snapshots-root output/research-snapshots `
  --frozen-experiments-root output/frozen-experiments --port 8866
```

Open `http://127.0.0.1:8866/app/research/frozen-experiments`. The separate snapshot
must already be imported through the existing data-readiness page. Choose the
supported frozen ZIP, import it, inspect the recorded verdict and evidence gaps,
then download the original archive/protocol/result/report/receipt. Reopening the
same package reads its verified local objects. Identical reimport preserves the
first receipt and history entry. No vn.py execution runtime is needed to inspect
these retained bytes. Without explicit roots the service remains unavailable.

## Supported original evidence

Schema `qm.frozen-spy-experiment.v1` supports the retained experiment
`QM-REAL-ETF-001-D-20261018`. Its manifest maps every other member to SHA256 and
names the previously preserved snapshot archive SHA256. There are 46 members:

- manifest, protocol, freeze receipt and report;
- the same seven original snapshot input paths;
- five original Python files, retained as inert evidence;
- one result JSON and 24 strategy/benchmark/trades files for eight fixed cases;
- five local report targets: timeline, review, RED/GREEN logs and verification.

The adapter checks every manifest digest, protocol input/code digest, receipt
and result protocol reference, experiment identity and all seven snapshot byte
associations. It refuses malformed/unsafe packages and corrupt reopened objects.
Limits are 8MiB compressed, 32MiB expanded and bounded structured collections.
No ZIP extraction, embedded-code execution or automatic report-link fetch occurs.
Market data and original artifacts remain local and outside Git; public source
access does not prove redistribution or trading entitlement.

## Read the report

These are imported historical results. Verified associations do not independently
recalculate strategy economics, prove historical ordering or qualify the data.
The original primary 5bps next-session daily-OPEN proxy reports positive 26.12%
net return but underperforms its buy-and-hold benchmark. It retains REJECT under
the recorded proxy criterion, formal R1/R2 INSUFFICIENT and R3 NOT_AUTHORIZED.
The final holdout has already been consumed. There is no reset/rerun/promotion
or order action on this page.

One current trial and zero searched parameter variants are separate from unknown
complete prior trial history. Source discovery exposed some 2026 prices; this was
not a pristine blind/prospective test. Freeze dates and created-before-results
are original assertions without independent chronology proof. All eight cases
are fixed diagnostics; the favorable extra-delay case is not selected as a new
winner. Null metrics mean unknown/unavailable, never zero. Confidence intervals
do not represent probabilities of skill or prove intrinsically negative alpha.

Keep unknown PIT/revisions, rights, executable 09:35 NBBO/size/costs, incomplete
trial ledger, utility/risk budget and the unresolved2021dividend conflict visible.
Inspect or download evidence to investigate gaps; importing it cannot upgrade
P1 qualification or enable trading.

## Local API

`/api/research/frozen-experiments` accepts `application/zip` on POST and lists
verified local packages on GET. GET `/{package_id}` reopens one opaque SHA256
identity. GET `/{package_id}/artifacts/{kind}` downloads allowlisted originals:
archive, protocol, receipt, result, report, timeline, review, verification or
manifest. `X-Content-SHA256` is the actual response SHA256; ETag agrees. Caller
file paths are unsupported. Writes retain the workstation's origin guard.

## 中文验收动作

打开“研究 → 冻结实验”，导入原有实验包。确认首页保留历史 REJECT、正式资格不足
和 OOS 已消费；查看主方案与固定诊断、参数和成本、未知历史试验总数及证据缺口。
下载原始包和报告，核对摘要；重复导入后历史仍只有一条，重启后首次导入时间不变。
哈希关联通过不等于重新算过收益，也不证明历史冻结时间或交易资格。
