# Iteration0038 — Report-bound sample evidence UI

Issue: [205](https://github.com/ZP151/quantmesh/issues/205). Date:2026-10-25 Singapore.
Plan: [sample evidence card](../superpowers/plans/2026-10-25-spy-report-sample-ui.md).
Base:345470491e2f83b5c36409c13a16cb04c5357afc, treefd11f597f3c9bb986a1b507736b5c39e3bedc39b.
ACK07:04:34Z; hard deadline09:04:34Z. This independent slice follows the completed progressive UI/PR226 boundary; it does not reopen that acceptance.

## Planner/Product

User action: reopen one saved report and identify its own sample, cutoff, structural facts and freshness applicability. Success: one compact default card with discoverable identity/timing/source evidence, no next-input metadata substituted into the report. The existing Input→Report→Decision layout remains; source and Paper state stay visible while evidence details, annualized ratios and recovery tools have named native disclosures. Desktop and phone share the same business sequence.

Only SpyReplayPanel.tsx, spy-replay-api.ts, two new focused test files and owned plan/iteration are changed. No backend, generated client, production static assets, dependencies, public fixture selection, qualification controls, market-data capture or service changes. Current PR226,8880 and protected8878 remain untouched.

## Quant Researcher

Frozen research brief SHA78873b12b9fb96c4bc396d6eb4a8aa45abf97faaeef217f427e9222354df580a; backend QM-SPY-SAMPLE-EVIDENCE-API-v1 SHA9410e3372fe078ffd020fc071622d21fe799375f9c9f22a39c60c7f23299446d. Engineering structural checks are separate from source/PIT/review facts and never establish real-data qualification, independent OOS or strategy validity. Paper remainsfalse.

Fixed regression samples do not require daily refresh. Read-time freshness consumes backend completed-session counts with the original snapshot/calendar/role; no browser calendar-day arithmetic. Weekend current/unknown cases are covered. Legacy missing facts stay unknown, synthetic source receipt times are N/A, structural-check time is not provider-review time, and unavailable trial history never becomes zero. Existing long_entries and gross_traded_notional_over_initial_capital are displayed with explicit nonannualized units; fills are not round trips or independent opportunities. Short21-session annualized ratios retain a folded applicability warning.

## Implementer

One report-only sample region shows role/cutoff/structure/read-time applicability. Native keyboard-accessible details hold bounded original identity, source/review facts and hash-only refs. It has no current-options prop. Reportv2 evidence binds snapshot/protocol/cutoff/calendar and nonnull freeze refs; v1 is retained without rewriting. GET validates the independent freshness view; unchanged submit/decision POST responses do not require it, and the UI retrieves GET after acknowledgement. Original artifact bytes, report digest and decision references are preserved.

F0 is the backend's already-computed internal flat fixture, not a public user choice. Read-only actual payload source9d9c791c977fb33e69a9a5d5d4f53c4393e4ab99 (backend documentation freeze5ef3f69e3dba1d3ff7bec3922435375e8aa2da0c): job33a681e4-b4f9-42d9-9981-6f553b65df0c. Actual report54291bytes SHAdac34c8c92c47548d480fab775484d67687a6faf69fca6f868c497e0ad6a10e6; actual GET1159bytes SHA57f5ded972958d6f5d6f2cbc0ac7a4b41ee3ef2488bf9ccda9516ba15b9f1878. Backend read receipt SHA4360ad05d2153375617ad1e63ab48b449f1d6d3dbe77049260d6e96845c0f06e records fixed read clock07:16:06.256688Z, last complete session2026-10-23, lag3 with no daily-refresh requirement and zero math calls during the read. No numerical recomputation by UI.

## Reviewer

Two permitted independent rounds by review_sample_evidence_ui end READY, no remaining material findings. R1 produced a constructed valid-v1+08:00 compatibility case and aggregate freeze-ref binding correction; R2 confirmed32 focused tests. Correction to R1 evidence: raw Python JSON reads prove the actual original v1 stores2026-10-21T16:00:00+00:00. PowerShell JSON conversion displayed+08:00; the reviewer explicitly retracted the actual-artifact failure claim. Newv2 remains UTC validated. No third review, old-suite rerun or unrelated fixes.

## Verifier

Meaningful RED/GREEN logs are retained under output/spy-sample-ui (v1 disclosure, zero/unavailable units, v2 binding/freshness, valid-v1 offset and freeze-ref tamper). Final19-final-tests.log:32passed/2files. Own frontend build and scoped oxlint exit0; git diff --check exit0; detector[] on the target. Existing Vite config/chunk warnings remain. Broad release checks are deferred to the sole publisher under root's explicit scoped verification instruction; this slice makes no full-repository-green claim.

Final recorded-payload browser batch: output/playwright/spy-sample-ui/SAMPLE-CARD-BROWSER.json, actual-backend receipt SHA verified before use. Four cases: v1/v2-F0 at1440x1100 English and390x844 Chinese. Default card170px desktop,190px v1 phone,206px v2 phone; document1350px desktop,1472/1488px phone. Details default closed, Enter expand/collapse works; no optionsB2030 borrowing, horizontal overflow or page errors. Every downloaded report is byte-identical. Zero POSTs/new math calls. Screenshot review found no blocking layout defects; no additional polish cycle.

This is explicitly UI_SAMPLE_EVIDENCE_PREVIEW_ONLY with transport_mocktrue. Actual backend generation/ASGI GET happened separately; it is not a combined live API+SPA acceptance result. UI source freeze/commit/tree and exact evidence hashes are in output/spy-sample-ui/HANDOFF.json for root and the unique publisher.

## Remaining boundary

Root/publisher combines this UI delta with the backend frozen slice after current226 completes, runs release gates and one bounded combined acceptance. UI author stops after immutable handoff. Engineering remains insufficient; real-data qualification and Paper arefalse, live is disabled. Demo feeds can support labelled interface/adapter exercises; real or recorded authorised data is needed for research evidence, and qualified frozen inputs plus independent OOS and deterministic risk gates precede a separate Paper admission. No source alone enables trading.
