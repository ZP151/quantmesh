# #169 server-source-witness handoff

Status: COMPLETE bounded software deliverable; final Spec and Standards round2
clear, including exact final clock-fix disposition. No third structural review.
Branch: codex/0038-server-source-witness.
Worktree: C:/Users/15492/.codex-clean/worktrees/4a9b/QuantMesh.
Frozen baseline exactly verified clean at start:
9ff1f22b8b07811b09345dd9d1d15125afb1640b.
Candidate head: d8b69651d492bed4880b0c61f94d7367848e8d8f.
Commits: abe77d0af39e096b90b8a86a5b4f065570d4a172,
dd871e04663a1c0c8294da7b7f8515360aa0f92f.
Final scoped-clock fix: d8b69651d492bed4880b0c61f94d7367848e8d8f.

Only tracked changes:
- tools/verify_server_market_source.py
- tests/test_server_market_witness.py
- docs/runbooks/server-market-source-witness.md

## Evidence

All paths below are relative to this ignored owned output/169-server-witness/.
Full command/results and Planner/Quant/Implementer/Verifier roles: progress.md.
- Initial RED: red.log/.exit, 45 failures, exit1, missing new module.
- Behavior RED: boundary-red, flags-red, collection-red, proc-red logs/exits.
- Review RED: cleanup-red (3fail), review-red (4fail), intermediate-red (1fail),
  market-red (1fail); all retained, no false pass labels.
- Final related regression: final-scoped-regression.log/.exit, 242 passed/6 warnings,
  12.11s, exit0, includes74 witness cases plus profile, session/consumer,
  minute SDK/client, workspace history/coverage and quote clock safety tests.
- final-ruff.log/.exit, final-format.log/.exit, final-diff.log/.exit all exit0.
- Actual final-head CLI: blocked-final-head.log/.exit, intentional pending exit2;
  blocked-final-head/summary.json says candidate_qualification/profile_blocked.
- Earlier blocked-invocation.log/.exit preserved (also exit2).
- Review round1: review-spec-r1.md (2 P2), review-standards-r1.md (1 P1/1 P2).
  Fixed by test-first bounded native children/pidfd cleanup/all bar validation/
  scoped receipt freshness. Author self proc scan fix also RED/GREEN preserved.
- Review round2: review-spec-r2.md clear after exact scoped-clock disposition;
  review-standards-r2.md clear, final small fix disposition appended. No third
  structural review. R2 clock RED1fail/73deselected and GREEN74pass retained in
  scoped-clock-red/green logs/exits. Prior241-pass regression retained as historical.

Exact final regression command:

```powershell
python -m pytest tests/test_server_market_witness.py tests/test_server_opend_profile.py tests/test_live_session_freshness.py tests/test_live_session_consumers.py tests/test_moomoo_minute_candles.py tests/test_moomoo_client_market_data.py tests/test_moomoo_workspace_history.py tests/test_workspace_session_coverage.py tests/test_quote_source_time_safety.py -q --basetemp output/169-server-witness/final-scoped-regression-temp
```

Actual blocked invocation (baseline SHA is only the explicit build expectation;
no application request occurs with this profile):

```powershell
python -m tools.verify_server_market_source --profile deploy/aws/opend/gateway-profile.json --expected-build 9ff1f22b8b07811b09345dd9d1d15125afb1640b --output output/169-server-witness/blocked-final-head
```

For an authorized future native run, replace the expected build with the exact
intended app deployment SHA and choose a NEW owned output directory. Use a
qualified profile only after coordinator-owned host/config/human gates, an
already admitted SDK environment, complete proc visibility and Linux pidfds.
No saved-input mode or endpoint override is available.

## Acceptance scope and coordinator gates

This is software preparation, verified with offline proc/provider/app fixtures
and newly owned local test children. No actual Linux gateway/SDK authentication,
AWS request, vendor request, installation, login, payment, account read, trade
call, Windows helper/GUI/tunnel operation, production termination, merge,
deploy, main reset or shared ledger/profile/service/transport change occurred.
Linux pidfd/proc runtime qualification itself remains coordinator-owned actual
evidence; Windows tests exercise the created-child handle and injected Linux
boundaries. Declarations of profile qualification are never native proof.

Tool top-level acceptance always remains pending even if native candidate and
provider/application subchecks pass. App endpoint/config cutover provenance,
host identity/authentication/rights, actual open-session revisions/two-boundary
acceptance, browser/reload, lifecycle/recovery, Hyperliquid operational regression
and personal-PC independence remain separate actual receipts. Closed latest
session is normal coverage with pending_live_acceptance, not a live witness.

Ruling made: no-account-read delegation forbids the existing workspace endpoint
(it includes an account view). Use health/live-state/history only; never infer
actual Paper proposal refusal or workspace UI degradation from missing depth.
proposal_gate stays unverified; root must supply a separate reviewed market-only
gate projection or actual browser receipt. Cost if wrong: conservative pending
acceptance, never fabricated disabled trading or source independence. Runbook
records this rule. No shared code defect is expanded into a repair here.

Root owns ACTIVE/iteration evidence and final integration/PR. Import the three
listed commits (or their final combined tree) without changing local main.
No dependency changes, upstream code copying or deferred smell-only minors.
