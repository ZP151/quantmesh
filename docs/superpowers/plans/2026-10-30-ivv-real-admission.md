# IVV declared-research implementation plan

> Execute inline using executing-plans/TDD; one independent app/integration reviewer, at most R1 plus known-fix R2. Server helper review is consumed, never a third helper audit.

Goal/spec: [approved slice](../specs/2026-10-30-ivv-real-admission.md), issue259. Base428c01bf/tree f2fdabb, branch codex/ivv-real-admission in existing isolated S. Precise file lock and forecast: output/ivv-real-implementation-20261030-1535/{OWNED-FILES,FORECAST}.json.

## Constraints and interface review focus

Default real closed; only trusted exact IVV registration. Keep RealInput/scope/grant/authority-v1/protocol-v3 refs and existing calculation/strategy/kernel unchanged. Original Source28MiB insufficiency/stop is preserved; actual registered capacity is now80MiB including Git/cache/build/failures/reviews. No old dataset/preview/SDK effect. Preserve old ledger/evidence and all holds.

Review: forged known-shape proof with wrong original digest; valid proof binding wrong input-set/root/runtime; two grant aliases sharing the once scope/trial; interrupted reservation/retry; new real report mislabeled as engineering or accepted by loose frontend guards. Every behavior has targeted tests below.

Pre-flight: Server capture_once/normalize_capture outputs are consumed as immutable raw/normalized objects by Product; not imported into the application/engine. Normalize output bars,date/OHLCV/dividend + all121 distributions ex/pay/amount + date/open/close schedule. Server defines frozen raw manifest shape. Product does not write the two Server files until frozen import. Ruling: reuse linked checkout/installed tools, no full baseline or install; explicit task gates override generic setup. Ruling: frontend build must override dist into owned output because old18953 serves existing frontend/dist.

## Task1: Proof/input-set and trusted private registration

Create research/ivv_admission.py and tests/test_ivv_admission.py; adjust native_daily_real.py RegisteredInput only as required. Private registration consumes store and exact package/grant/scope/authority refs plus trusted expected RootGO/acceptance pins; output vetted RegisteredInput. Gate verifies fixed human/scope/effect originals, actual acceptance contents, input-set digest without review_refs, raw/normalized provenance and use facts, source/runtime/window/root/scope-trial identities. Do not expose authority booleans over HTTP. Proposed helper output is packaged through existing ObjectStore, never treated as qualification.
- [x] RED: scripted wrong original/pin, missing content/units/actions/normalclose, wrong window/inputset/runtime/root refuse before math; matching fictional authorities allow only the private registration; default existing real still refused.
- [x] GREEN minimal proof validator and scoped registration with explicit stored proof ref; test scripts patch fixed identities to software-only namespace, never reserve real e285 scope or draftjob.
- [x] Targeted pytest tests/test_ivv_admission.py; retained RED/GREEN, coherent first commit1932ec2 and ledger.

## Task2: Atomic scope/trial + real-only saved evidence

Modify native_daily_real.py/api/native_daily_real.py; tests/test_native_daily_real.py and new IVV tests. Existing _binding input contracts/_calculate_matrix reused. One immutable registration evidence ref on saved job preserves trusted original context for cold read. Real-only admission/report version2 records internal use basis and original refs, provider_verified=false, externalUNKNOWN, financialINSUFFICIENT/Paper-livefalse; old schemas retain exact old behavior.
- [x] RED: one scripted accepted input executes ten-arm shared matrix once; save decision and cold3 originals identical with calculation/calendar disabled; sameUUID changed body conflict; newUUID/newgrant alias same scope/trial blocked; failure/restart remains spent. Independent acceptance content mismatches never consume trial.
- [x] GREEN durable scope/trial key and consumed grant stored together with NativeJob under lease before _compute. Cold verification reads stored proofs/objects without runtime substitution or recalculation. No second ledger/cashbook.
- [x] Affected native daily/IVV tests and first green boundary committed; subsequent Windows actual approval adds ivv_runtime.py/test_ivv_runtime.py with native readback-before-trial and normally closed fixed numerical child, existing _OwnedChild/matrix reused.

## Task3: Existing UI guard/labels and trusted launcher

Modify frontend/lib/native-daily-api.ts, NativeDailyPanel.tsx/test, generated client; new tools/research/open_ivv_workstation.py. Root supplies vetted immutable refs/expected proof pins via trusted local startup; existing create_workstation_app(native_daily_service=...) composes it. Default root CLI remains empty/closed. Controlled loopback18954 only at actual authorized stage.
- [x] RED targeted UI real option/status/report/admission guard and providerUNKNOWN/private once wording; malformed proof/report shape remains refused; old engineering behavior retained.
- [x] GREEN minimal types/labels/strict dual-version checks, no new layout/strategy surface. Generated client with current checkout PYTHONPATH; UI14/type/lint/detector/buildPASS via existing tools with owned DIST_DIR override; old frontend/dist hashes unchanged. Trusted launcher validates independent config pin before writes and ordinary API composition is tested with fictional proofs only.
- [ ] No repeat synthetic browser. Actual375 screenshot and one true UI submit/report/decision/cold reopen happen only after Root GO/new actual accepted data.

## Task4: Frozen helper import, integration review and publication handoff

- [x] Consumed Server frozen exact helper/tests/pins/review receipts; imported only those two files once; interface fd061bdb unchanged; no third helper internals audit.
- [x] Targeted combined137PASS plus helper-to-Product bridge1PASS; after R1 known fix, affected app/runtime72PASS and UI16PASS/type/lint/format/detector/new packagebuildPASS. Independent app R1 P1 closed by sole known-fix R2 READY_SOFTWARE_CONDITIONAL, receipts retained; iteration/ADR/reuse/roadmap updated. No third helper/app audit or unrelated broad tests.
- [x] Software source frozen/released for Root handoff. Final metadata-only checkpoint preserves reviewed code/package bytes; exact final head/tree, pins/normal-startup/served-asset interfaces and original evidence are in ignored HANDOFF/EXEC. Source no push/PR/watch/early capture. Sole Publisher's future exact CI/normal merge/tree/catalog is a separate next gate, not claimed completed here.
- [ ] Root consumes actual release and controls, internal once GO; Server480s conditional capture, original Quant actual input-set review. Only accepted actual refs enable one true job/ten arms and saved report/Reject-Watch/same-ID3 originals,0newcalc/trial. Code GREEN is software evidence only; until that sequence actual Goal remains UNMET.
