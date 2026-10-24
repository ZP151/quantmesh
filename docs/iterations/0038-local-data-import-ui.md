# Iteration0038 — Own-data import to protocol planning UI

Issue: [222](https://github.com/ZP151/quantmesh/issues/222). Plan: [local-data-import-ui](../superpowers/plans/2026-10-25-local-data-import-ui.md).

## Planner / product
One user action: import an existing daily CSV, inspect its source/coverage/quality and insufficient qualification reasons, then retain the actual data reference for an existing research protocol entry. Scope and acceptance are recorded in the short plan. Root approved direct implementation2026-10-25; no OpenD prerequisite and no repeated human approval.

## Quant researcher
Technical validity and research qualification remain distinct. Unknown rights/PIT/corporate actions/costs are not converted to zero or qualification. Existing fixture runner is not authorized to execute arbitrary uploaded CSV. The result may support inspection and protocol planning only, according to the server contract.

## Implementer
Read-only baseline confirmed origin/main9cdf321. Reused isolated old UI worktree on new codex/local-data-import-ui branch; old branches preserved. Existing SPY ZIP/P2/P3 routes and server rules stay authoritative. Backend owner is independently implementing ordinary local CSV contracts; no frontend/static file overlap.

## Verifier — first operable checkpoint

Existing Node22.23.2/npm10.9.8 and existing Python313 reused; accepted lock npmci completed, no dependency edits. npmci summary reports2moderate advisories; no fix/force or policy changes. Initial primary.venv schema probe lackedpg8000; the already installed Python313 successfully exported the backend owner actual99-path OpenAPI. The generated client is frontend-owned and must integrate with the independent backend leaf.

Meaningful RED: existing DataReadiness lacked own-CSV mode; API malformedcoverage/source responses initially passed (2failed/7passed). Both now corrected. Focused loop65passed across sevenfiles; actual tsc-b/Vite8.2.4 build and packaging passed. First test-only file-read mismatch used File.text absent in jsdom; FileReader with fatalUTF8 validation exercises actual bytes and works in the real browser. First attempted artifact-writer path used a frontend-relative cwd and failed before writing; retained log is not a product result.

Actual own loopback8878 served the UI bundle with the backend owner source and own snapshot root. A two-row owned synthetic CSV (not real market acceptance) POST returned201/structurePASS/researchINSUFFICIENT, persisted and reopened at375px. Planning reference matched actual dataset identity; downloaded draft contains original reference/BLOCKED/nullresults and no job submission.1440/375 no document overflow, no pageerrors, compact visible controls>=44px. First screenshot pass identified duplicate unknown checks and unfriendly internal receipt copy; a single correction groups repeated detail, preserves primary authoritative reasons and raw text title, and keeps identifiers in disclosure. Programmatic-focus-only probe did not demonstrate keyboard focus-visible; genuine keyboard confirmation remains pending.

Evidence under output/local-data-import-ui:01-mode-red.log,08-api-red.log,14-qualification-green.log,10-build.log,browser-acceptance.json and viewport PNGs. The plan action is intentionally restricted; no uploaded user data reaches the fixture runner.

## Reviewer — one independent UX/safety diff round

Independent source review at eb6405d found three material issues: P1 report capabilityprotocol_planning was confused with reference intended_uselocal_protocol_planning_only, hiding the action; P2 planning showed digest-derived identity and internal evidence wording; P2valid_rows had an overly broad label. The final-browser attempt at that checkpoint independently failed waiting for the planning action. Original review and failed log remain unchanged.

One aggregate correction now consumes the actual report capability, uses the actual captured POST payload as its fixture, and re-reads the matching saved report+reference before planning. Dataset identity is checked field-by-field; a mismatch refuses planning. Primary identity is the human label/symbol/coverage; known reasons are explained with original text in title/details. Parseable UTC/OHLCV rows has an adjacent bilingual explanation excluding session/duplicate/order checks and all qualification/coverage ratios. A rejected-duplicate semantic regression and mismatch/wording cases were added. Corrections:68targeted tests pass, actual tsc-b/Vite packaging passes; final actual-browser confirmation pending. This is author correction evidence, not a second independent structural review or blanket READY claim.

Backend frozen candidate de8befced490a306448addfff77bb9ee2051e472/treefead62d04507c5fa40b85fc1ea61a743aec3af44 supplies the actual typed API. Client regenerated from that exact schema, including valid_rows description. The backend and frontend leaves must integrate together before exact-head CI. No independent leaf may claim missing API/codegen compatibility.
