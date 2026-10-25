# Issue205 continuation — original-report-bound sample evidence

## Planner / product

One action: reopen a saved SPY report and see its own sample identity/quality and
read-time complete-session lag without re-running math. Quant's finite contract
SHA78873b12b9fb96c4bc396d6eb4a8aa45abf97faaeef217f427e9222354df580a
and root's explicit next-slice ownership govern. Plan:
docs/superpowers/plans/2026-10-25-spy-sample-evidence.md.
Base345470491e2f83b5c36409c13a16cb04c5357afc; branch codex/spy-sample-evidence.
ACK2026-10-25T07:04:28Z; interface07:19:28Z; first result08:19:28Z;
hard09:04:28Z. PR226/base and old833branch/handoff remain frozen.

## Quant researcher boundary

Only existing long_entries and absolute traded notional/initial capital are
additionally exposed for the UI owner; no new math, annualization or significance.
Fills are executions, not independent opportunities or closed round trips.
F0-v1 is one fixed121-session flat100/volume1000000/no-events engineering golden,
not a market sample or OOS. Real input still needs existing v2 source-use and
POST/acceptance evidence; unknown/PIT/source receipt fields remain unknown/N/A.
No data acquisition, source promotion, Paper/live authority or server dependency.

## Implementer checkpoint

Reused clean existing isolated worktree, new branch from the frozen combined
candidate. New report schema2 adds one bounded SampleEvidence, captured before
math from the same verified input and typed trusted provenance. Source loader
retains safe object references and actual known time/semantic claims, no account
identifiers, arbitrary feed text, paths or credentials. Structural PASS is only
the already-performed121/100+21/order/OHLCV/byte validation, not source qualification.
Missing metadata is not a new all-green admission requirement.

Legacy schema1 is explicitly read-only without evidence backfill/migration;
original bytes, report/decision references and stored job schema1 stay unchanged.
GET-only ReplayJobRead adds SampleFreshnessView. POST submit/decision still return
ReplayJob without the extension. The view reads only that job's verified original
report and current UTC read clock with its pinned XNYS calendar/30min grace.
No current options/input B is used to fill an older job A. No view is persisted.

Interface frozen before deadline in output/spy-sample-evidence/INTERFACE.json,
SHA9410e3372fe078ffd020fc071622d21fe799375f9c9f22a39c60c7f23299446d,
sent through root to UI. DTO-SCHEMAS.json provides generated model shapes too.
Only core/API, one new test file and own records change; engine remains unchanged.

## Targeted verifier evidence

01-delta-red.log:14failed/1passed,5.12s. Meaningful original report1-vs2 and missing
GET view/facts were observed. One loader test initially reused a controlled v2
wire fixture whose volume cap prevents terminal exit; actual direct diagnosis
returned terminal liquidation incomplete. It was corrected to test trusted
metadata construction rather than falsely expect successful math;02-loader-red.log
then shows the intended missing evidence method. All failures remain preserved.

03-delta.log:15passed/6 existing warnings,5.28s. Then four meaningful REDs for
foreign freeze-reference binding and malformed legacy calendar shapes in
04-binding-red.log, followed by bounded guards.05-delta-green.log:23passed/6warnings,
6.66s. Scoped import/style fixes and formatting preserve initial failures in06.
Fresh author07-author-boundary.log:23passed/6warnings,8.17s,exit0; scoped Ruff,
format and git diff --check pass. Only the new targeted test file was selected.

Cases include: exact v2 identity and structural/unknown facts; actual original
v1 report+decision compressed as inert bytes, actual API GET with B configured,
unchanged ledger/artifacts; new A cold-open under B with math refusal sentinel,
unchanged same-key report/decision; actual POST-vs-GET/OpenAPI types; read-clock
movement without writes; half-day/weekend/grace/complete-session lag and unknown
calendar/identity; public evidence claim rejection; safe controlled loader refs;
foreign freeze and stored v2 evidence-pin tamper refusal; no synthetic role upgrade.

F0-v1 bytes/recipe are separately retained in output/spy-sample-evidence/F0-v1/.
Snapshot4bad22e533de50cae86bc5f0f3a8621b93c7435874bcc4917ef256ff4bcf33fa,
protocol a2f4d17a055bdda8520f1a559d3d46f1371761ad1faadec08629b88f1ec46b41.
Named golden test pins these identities and actual0 fills/entries/return/drawdown/
cost/turnover with null Sharpe/Sortino/Calmar; same-cost buyhold still pays friction.
This sample is fixed, not refreshed daily. A changed recipe/bytes requires a new
version. Timestamp declarations are explicitly synthetic, not real source times.
math-provenance.json freshly confirms exact original three-function AST equality;
the engine source is unmodified and no old runner is invoked.

## Reviewer / publisher boundary

Independent bounded review pending, capped at two rounds; new targeted cases only.
This leaf owns no frontend/generated assets, combined CI, publication or server.
Local commit hooks will be bypassed only after scoped checks, not represented as
broad-hook success. UI integration and new release remain sole publisher's work.
No old38/37/20 suites are repeated. Root owns continuing Goal/automation.

## Independent R1 and final evidence handoff

Fresh-context reviewer froze9d9c791c977fb33e69a9a5d5d4f53c4393e4ab99 /
tree e21c8b82b91dee1125fa0d61062f0eae048a19b7. Verdict READY for this bounded
offline backend delta: Standards0 Important/Critical; Spec0 Important/Critical.
Independent targeted new-file run:23passed/6 dependency warnings,6.77s,exit0.
Original report output/spy-sample-evidence/review-r1.md SHA
b19fa9b288325772c5f09b49fb0fa024fcf1f99b1f83d1175cbfa9be1233ae41;
raw review-r1-tests.log SHA
2df5e1721e1e2c7d99f3371274820ec56d259d342b7bb39d0b5ba17064cbdada.
No source correction requested, no second round needed or claimed. Source hashes
are recorded in review-r1-evidence.json; final checkpoint changes only own docs.

As requested by root/UI, actual v2 report and actual in-process ASGI GET response
were read from the already-produced F0 test case, not another numerical run.
Job33a681e4-b4f9-42d9-9981-6f553b65df0c; actual report original SHA
dac34c8c92c47548d480fab775484d67687a6faf69fca6f868c497e0ad6a10e6,
54291bytes. Actual GET JSON SHA
57f5ded972958d6f5d6f2cbc0ac7a4b41ee3ef2488bf9ccda9516ba15b9f1878,
1159bytes. Both200 responses; original header/hash verified, math sentinel0calls,
original ledger SHA unchanged. Evidence construction time07:13:14.920715Z;
controlled read clock actually observed at read start07:16:06.256688Z. Exact
original object path, refs, clocks and file hashes are in
output/spy-sample-evidence/ACTUAL-READ-RECEIPT.json; safe byte examples are
ACTUAL-REPORT-v2.json and ACTUAL-GET-job-v2.json. Earlier EXAMPLE-* artifacts
explicitly remain type-serialization examples, not raw HTTP captures.

Reviewer declines combined UI/browser/release, actual source rights/independent
receipt truth, PIT/finality, real OpenD/server, financial/OOS and Paper/live
judgments. This leaf shares those limits. Original math source unchanged;
no current PR226 source/UI/generated changes, push/CI/server/dependency/data
actions occurred. Final local docs commit still explicitly bypasses hooks after
scoped checks. Final immutable HANDOFF.json records exact actual head/tree and
all artifacts for root and sole publisher. Continuing product Goal remains open.
