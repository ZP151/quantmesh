# Iteration0038 — real-data qualification user loop, P1

Issue: [184](https://github.com/ZP151/quantmesh/issues/184).
Status: local user loop verified; independent round2 READY / ship; delivered in
[Draft PR187](https://github.com/ZP151/quantmesh/pull/187). Future PR review/merge
is pending; the local user loop is not production or research admission.

## Planner

One user action: import the retained SPY daily snapshot and inspect whether its
evidence is sufficient for research. Stop after an actual local import, readable
located findings, reopening, and original package/report downloads.

The operator approved the presented P1 short design through the main coordinator
on 2026-10-19: “全部批准，继续执行”. Approved design SHA256:
`4e4f32246b63e41108acdc2cc9adca2e199e681a2d4c2d2b44f3fdac0bac9e31`.
The receipt is retained in local evidence as `P1-APPROVAL-CONSUMED.json`.
This approval covers P1; later P2/P3 designs and a future PR are separate gates.

This branch starts at PR182 candidate `45c6d5c826b30a6b84ab4eef3a9a6087efdaeb9c`.
The release owner's actual postmerge receipt was consumed: PR182 squash merged as
`d4bee7f38de8d44d46e4fa8b1e32606d3d50361e`; its complete, non-truncated tree
`71317a416d18312a7c652de51e981b468d6e53ae` equals the approved candidate tree.
This task did not rerun PR182 CI/review or perform its merge. The P1 PR requires
its own future review and merge authority.

P1's tested source checkpoint is `5bde30e`. Normal merge `3e1c2be` includes the
actual PR182 squash as an ancestor. Equivalent squash-history conflicts in the
iteration/startup/generated resources were resolved to the already tested P1
content after proving the incoming main tree equals its approved baseline.
The whole merged tree equals the tested P1 tree
`ac1213f94feb50b6024c597565622498c58e3146`; no force or source-behavior change
was needed. The subsequent closeout commit updates this checkpoint only.

Explicit exclusions: new backtest engine, provider onboarding, new dependencies,
paid data/models, server/deployment work, credential changes, live trading, and
rerunning the consumed historical OOS. The existing vn.py workflow is preserved.

## Quant researcher

Read-only inspection of the retained source confirms 2,965 rows spanning
2015-01-02 through 2026-10-16, with the same 2,965 pinned XNYS sessions.
Normalized timestamps/OHLCV match original Yahoo bytes within the documented
decimal tolerance; this establishes consistency, not historical availability.
Both sources have 47 dividends in range. The unresolved 2021-12-17 amount differs
by USD0.003431. Public endpoint access does not establish product, redistribution
or trading entitlement. Historical PIT/revisions and executable NBBO remain
unverified. These gaps must stay visible and cannot become green by editing a
manifest. Raw issuer spreadsheets are retained; this slice does not independently
validate their derived distribution JSON against spreadsheet cells.

The historical SMA100 daily-open proxy experiment remains REJECT, formal R1/R2
INSUFFICIENT, R3 NOT_AUTHORIZED, with its final OOS consumed. No new evaluation
has been run. Fixture evidence is engineering-only. Paper remains the default;
this data-import page grants no execution authority.

## Implementer

Two independent writers delivered bounded backend and frontend files. Existing
ObjectStore and CalendarService are reused. Parent owns generated API/bundle,
documentation, integration and acceptance. Installed frontend dependencies were
copied to an independent ignored directory; no install or upgrade occurred.

Actual-package preflight caught an overreach beyond the approved contract: the
initial checker compared the normalized dividend column to Yahoo, although the
frozen source generator filled that column from issuer data. Synthetic regression
tests now distinguish CSV-to-issuer normalization at USD1e-8 from issuer-to-Yahoo
source conflict at USD0.001. No original bytes or conflict tolerance changed.
The incorrect first report/store and its failure evidence remain preserved.

## Reviewer and verifier

Expected behavioral RED and subsequent GREEN logs are retained for both writers.
Parent's final bounded integration checks pass 58 backend tests and 65 frontend
tests, including existing startup wiring, navigation and the changed message
dictionary. TypeScript/package build, API generation check, targeted Ruff and
whitespace checks pass. Existing upstream deprecation warnings and the bundled
chunk-size advisory remain recorded; no dependency changes were made for them.

The actual built page imported the local original-byte ZIP, displayed structural
PASS/research INSUFFICIENT with 2,965 rows and the located 2021-12-17 conflict, and
downloaded original ZIP/report bytes verified against the source/API digests.
The original ZIP is 839,291 bytes, SHA256
`e39b89d1b21c4d8f59e1108a5d604828b94a65b0dda0a2cbc6cbc525f976e989`.
A controlled stop/restart preserved the import time, pinned report bytes and
single history entry. The actual UI history action reopened it; identical
reimport did not add a version or replace the first receipt.

Independent round1 requested three bounded fixes. One TDD batch and the same
reviewer's round2 confirmed all three resolved, with no observed regression:

| Material fix | Final evidence |
| --- | --- |
| Synthetic demo wording contradicted the real import | Banner, footer and title in both locales now label seeded account/data separately from imported research evidence. Paper/kernel constraints remain explicit. |
| Mobile history control overflowed | Reopen control wraps within its width; final375px viewport/body/scroll width all375. Desktop1280px viewport/body1265 remains contained; table scroll is local. |
| Dividend reason described only the method | First qualification blocker names the disagreement on2021-12-17; located expected1.636431 / actual1.633 is unchanged. |

The final rebuilt page imported the same original ZIP into a new owned acceptance
root without rewriting either prior immutable store. Its pinned JSON is 7,497 bytes,
SHA256 `4d55344d80a8e8c2d0325d84c7ef490bf7f0d26774df953cdacd896bc59ed567`.
Actual browser downloads match source/API digests. A fresh controlled PID22360→29780
restart and actual UI history click preserve that exact report, original import
time and qualification. Identical reimport after restart still yields one entry.
All seven original member references match their preserved source bytes. The
historical protocol and result hashes remain unchanged; no real-data strategy or
consumed-OOS evaluation was performed by this slice.

Round2 disposition: **ship / READY**, three resolved, zero partial/unresolved.
No prior full/native/436-test acceptance or third review round was repeated.
The interface proves this local evidence loop, not data entitlement, economic
validity, forward paper evidence, production deployment or strategy promotion.

Key local receipts under `parent/`: `api-acceptance-final.json`,
`browser-download-verified-final.json`, `cold-reopen-final.json`,
`browser-reopen-final.json`, `dedup-lineage-final.json`, `viewports-final.json`,
and `frozen-originals-preserved-final.json`. Review reports are `review-round1.md`
and `review-round2.md` beside that directory. The operator guide is
[SPY snapshot readiness](../research/spy-snapshot-readiness.md).

Local evidence root: `output/0038-realdata-workstation-product/`. The authority
checkout holds the task/approval/package records; the isolated
`0038-realdata-workstation/QuantMesh` worktree holds source-writer logs, review and
the `parent/` acceptance receipts above. Canonical `progress.json` names that exact
worktree and its source ownership. Raw data and test output stay ignored and local.
