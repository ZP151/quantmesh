# #173 complete HANDOFF — local fixture workstation slice

Status: COMPLETE for approved Task3 local fixture API–UI slice; review round2/2 clear. No final milestone release, private deployment, real-model, PostgreSQL or Linux qualification is claimed.

Exact final source HEAD and pushed branch: b9daa42830ac240dc8354e457485a6f0e87ca297 / codex/173-workstation.
Exact approved baseline: 1fde6dcde715011cbfcc2bfff56f665dd66c85ea.
Root integration: backend source de9b4438aafbc09acecf54880309c2fe551db26c -> root379797d; UI source ed04f241609d8ad108aeab4228d6c7b09d988318 -> root7e5834b. Root shared backend eb6e16e7cc78815795baadc9e993ab03d455557e and navigation2a6eafb5ac6e0ff54281edaf7930f0c97767240e synchronized as equivalent ca7e459/d88eeeb. Root should cherry-pick ONLY remaining leaf fixes ed5c12ea78c4a0a43f65b9c6d4e55ba6610e2407 then b9daa42830ac240dc8354e457485a6f0e87ca297. Do not reapply equivalent shared commits. Worktree tracked/untracked status clean; HEAD == origin/codex/173-workstation.

## Planner/Product handoff

One user action: choose a registered baseline and authoritative configured pinned fixture, submit one durable job, then reopen its immutable report/status after reload and cancel active work. Observable success is the completed and retained user loop, not test counts. No custom Python, new strategies, engine/refactor/dispatcher, production source/Windows helper/AWS changes, new global/paid resources, PR/merge/deploy, retired soak or completed160/170/171/172 implementation/Eval redo.

## Quant Researcher handoff

V1 explicitly fixture/test-only. Momentum, mean_reversion and risk_parity version1 use existing engine/cost/window contracts; fees/half spread/slippage each positive. Qualified choices reuse pin/coverage/chronology/time validation and reject unknown rights, unsupported manifests, path escape/link and insufficient aligned input. Fixture results prove workflow only. Raw canonical JSON may contain synthetic annualized metrics; these are not investment performance, model skill or strategy promotion. Usage/tokens/cost before a model call stay null/unavailable; AI is optional advisory, with no execution/order/proposal authority.

## Implementer handoff

Seven owned new leaf files:
- src/quantmesh/research/job_options.py
- src/quantmesh/research/service_client.py
- src/quantmesh/api/research_jobs.py
- tests/test_research_job_options.py
- tests/test_research_jobs_api.py
- frontend/src/screens/ResearchJobs.tsx
- frontend/src/screens/ResearchJobs.test.tsx

Construction-time IDs and authoritative Worker input root govern options/admission. LocalResearchClient rejects root mismatch; remote mode never reads the PC lake as a pretend export. Backend facade exposes typed submit/get/cancel/artifact/options and fixed safe errors, Noneclient503, no HTTP baseline/Worker startup. Remote TLS private allowlist, backend SecretStr bearer, no redirects/implicit retries,1MiBJSON/16MiBartifact limits, operator/job/config identity and verified schema/SHA/size/report lineage. Registered strategy validation remains; historical reads/replay verify the frozen job implementation rather than today's engine. Current-engine execution checks remain Worker-owned.

Root exclusively authored shared workstation/api/schema/nav/messages/App/service-options and iteration edits. Initial exact proposal shared-proposal.patch was validated against source baseline and consumed/adapted by root; it is historical and must not be reapplied to current integration. No additional shared source fix is needed. Root constructor is research_jobs_client; research API mounts at /api only and uses existing origin guard for POST. Service new admissions require configured IDs; retaining an ID allows existing same-key replay after input bytes disappear. Removing ID explicitly rejects submission/replay; read existing job by known job_id. Frozen nine-method store/schema and numerical engine unchanged.

UI retains key+payload BEFORE every send, including ambiguous retry; no automatic resubmit on refresh. Definite409/422 refusal permits explicit reconfiguration/new submission, persists across reload, and its reset affordance is durably cleared before any retry. Polling is active-only and bounded60*3s, pauses on failure and exposes manual refresh. Read generations plus request/job/engine/time/cancel fences prevent stale status overwrites. Cache restore checks SHA/size and current job after await. Reports use IndexedDB with explicit storage failure, remain downloadable during authoritative outage; retained versus fetched status and job.updated_at are visible. Native configuration/status/report layout preserves incumbent black/green workstation.

## Reviewer handoff

Only two independent whole-boundary Spec/Standards rounds ran. Round1 found6P2 issues, all reproduced before fixes: authoritative-root mismatch, historical engine-read breakage, status/cancel race, cached-report selection race, definite-refusal dead end, missing retained source/time label. RED review-backend-red2.log/exit1(2fails), review-ui-red.log/exit1(5fails). GREEN focused2backend and14UI plus broader gates. Round2 is clear on both axes; impeccable disposition: ship. Reviewers wrote review-spec-round1.md, review-standards-round1.md, review-spec-round2.md, review-standards-round2.md. No third review or structural patch cycle. Keyboard disclosure/focus and narrow viewport are witnessed; screenshot scaling is recorded, no full accessibility/contrast certification claimed.

## Verifier handoff

All original raw logs and .exit files preserved under output/173-workstation. Core imports verified from THIS worktree/src through PYTHONPATH, never editable root. Root audited-venv and locked service venv read-only; root existing node_modules consumed via ignored local junction, no lock change. Pytest basetemps unique and workspace-owned.

TDD: red-options.exit2 missing new options module; red-api.exit2 missing new facade module; red-more.exit1 remote409 mapping; corrected green/checkpoint logs. UI red-ui-confirmed.exit1 missing screen; saved-controls/cache-integrity RED then GREEN; review regressions RED then GREEN. Earlier incorrect launcher attempts are retained, not substituted for actual passing evidence.

Fresh final candidate boundary: review-green-api-boundary.log/.exit —223pass/1 native symlink privilege skip/78.64s/exit0. Fullfrontend review-green-frontend.log/.exit —419pass/33files/16.41s/exit0. Schemacheck/lint/typecheck/build all0 in review-green-*. Existing chunk/FastRefresh/deprecation warnings retained. Ruff check/format and diff pass. After final review, post-review-final.log/.exit —39pass/1skip, post-review-ui.log/.exit —14pass; post-review-ruff/format exit0. No hours-long full core/release certification run or real PG pass claimed. Root service proof remains25pass/5PGskip, separately qualified by root; default native PG gate remains pending.

Real browser user loop (Edge, loopback18765, LOCAL_FIXTURE_ONLY): first momentum job63165bb4809e4efb8d19eb0444004260 queued→owned Windows Worker→succeeded,10windows/report3274bytes/SHA47008015161a42850f41014c5cf4d27951f940b1eac635a4b186f17dcb256c0a; actual download byte-equal. Production AdvisoryRunner with unconfigured provider/price yields unavailable/model_unavailable and all usage/cost null, independent backtest succeeds. Second mean_reversion9dd067854858409292e72382c57b8725 genuinely cancelled while queued. Database exactly2rows at this checkpoint, reload caused no resubmit.

After fixes, exact-head risk_parity job71688feb832e4d498ef1324f07ea6647 queued→succeeded,10windows/report3641bytes/SHA124f692e0bfff4c11fb15e725d800b37dc63052c5c69b2a51ce72d4b35db2566. Worker runtime.git_commit exactly b9daa42830ac240dc8354e457485a6f0e87ca297; all actual downloads equal raw immutable publication. Total3 intentional fixture jobs (two successive baseline runs plus one cancelled job); no silent rerun. Authoritative-service marker returns503 options/status while /api/markets200; cached report after reload is SHA-verified and retained/status-source/time labelled. Mobile390x844/document scrollWidth375, status/report wrap; native keyboard Tab/Enter expands report JSON.

Primary exact-head machine evidence: browser-reviewed-witness.json/.log/.exit0. Earlier browser-witness.json/.log/.exit0 and browser-report-identity.log retained. DOM browser-reviewed-queued/report/service-down/keyboard.txt; desktop/outage/mobile-status/mobile-report screenshots named LOCAL_FIXTURE_ONLY-reviewed-*.png. Screenshot CDP-fullPage and download-event APIs timed out; ordinary native screenshots and actual downloaded file bytes independently completed the evidence. No fabricated HTTP/job states. Availability markers affected only this fixture authority; old production/chart/runtime remained untouched. Markets fixture is empty, not a real live-chart witness; existing chart/paper paths covered in boundary suites.

## Operational needs and cleanup

Fixture server/Worker were test-owned only; final owned PID48168 command identity checked and stopped. fixture-cleanup.log records cleanup; owned lake/SQLite/reports/receipts/screenshots preserved. No global Worker, process/OS/Docker/WSL, broker/helper/tunnel or production change. Native Linux/image/OCI/Task2, real PostgreSQL, approved real provider/model/price/egress/keys, AWS service deployment/restore and existing Windows recovery/operator/human/CI/full clean-checkout gates remain pending with root. No paid call/resource. Formal168h not required. Root mirrors final roles/user-loop/review/evidence into ACTIVE/iteration and creates one final milestone PR after its remaining gates; this session creates no PR or merge/deployment.
