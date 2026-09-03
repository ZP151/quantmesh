# Iteration 0027 — Evidence-backed Decision Copilot

- Status: active (Slices 1–4 complete; final license closure and PR gate pending)
- Started: 2026-09-02
- Tracking issue: [#122](https://github.com/ZP151/quantmesh/issues/122)
- Branch: `codex/0027-evidence-backed-decision-copilot` from
  `origin/main` at `f77b565`
- Active design:
  `docs/superpowers/specs/2026-09-03-packet-outcome-review-design.md`
- Active executable plan:
  `docs/superpowers/plans/2026-09-03-packet-outcome-review.md`
- Ledger: this file

## Product wedge

For a research-minded individual active trader, turn one ticker into a
verifiable, risk-first decision package in no more than two minutes, make it
executable only as a guarded paper proposal, and preserve it for monitoring,
outcome attribution and replayable review.

The product lesson from [KairoTrend](https://kairotrend.com/) is the value of a
short path from chart context through risk and review. QuantMesh does not copy
its AI signal or pattern-recognition proposition. QuantMesh compresses the same
journey around owned evidence, deterministic risk, paper authority and replay.
The current public Chrome-extension footprint is not treated as evidence that
feature-count parity is a useful target.

## Primary user flow

```text
Ticker / Watchlist
        ↓
Market state and key levels
        ↓
Bull / Base / Bear scenarios
        ↓
Entry zone, invalidation, stop, target and paper size
        ↓
Reject / Watch / Paper proposal
        ↓
Monitoring, outcome attribution and review
```

The flow stays inside Instrument Workspace. Evidence details use in-place
disclosure or drawers and preserve the selected instrument, time range and
draft action.

## Core artifact

`DecisionPacket` is a versioned, replayable composition rather than a BUY/SELL
label. Its deterministic foundation records:

- venue/instrument identity, horizon, as-of time and data freshness;
- market structure, trend state, support/resistance and invalidation levels;
- Bull/Base/Bear scenarios with calibrated probabilities or explicitly labeled
  confidence semantics;
- entry zone, stop, target, R multiple and suggested paper size;
- exact data, manifest, quality, forecast/model, benchmark, out-of-sample,
  leakage and cost evidence references;
- AI explanation/critique with resolvable citations, or an explicit unavailable
  reason when no valid model result exists;
- operator disposition: Reject, Watch or Paper proposal;
- immutable references to risk verdict, confirmed paper order/result and later
  review records.

The analysis snapshot is never rewritten. Later disposition, paper and review
events append a new version or immutable referenced record so the original
as-of decision remains reproducible.

## Vertical slices

### Slice 1 — DecisionPacket foundation

**User action:** select NVDA, inspect one composed decision view and save Reject,
Watch or Paper proposal without leaving Instrument Workspace.

**Observable value:** one deterministic NVDA DecisionPacket survives restart
and reopens with the same evidence and disposition.

**Reuse:** existing instrument history/workspace services, price forecast
artifact and registry, paper proposal ledger/service, risk kernel, audit and
demo acceptance station. Do not add another model framework.

**Stop condition:** NVDA happy path, stale-data block and risk-refusal browser
states pass; the measured ticker-to-save interaction is at most two minutes.

### Slice 2 — Structured Copilot

**User action:** request an explanation or challenge of the deterministic
packet and inspect its citations in place.

**Observable value:** schema-valid AI commentary identifies the exact packet
facts it explains or challenges. Missing service, timeout, invalid schema or
unresolvable citation degrades only the AI panel.

**Reuse:** the existing structured model gateway, analyst/critic boundaries,
redaction, citation resolver and DecisionLog. AI cannot alter scenarios,
evidence gates, size, risk verdict or action authority.

**Stop condition:** both valid cited output and model-unavailable paths preserve
the deterministic packet and action semantics.

### Slice 3 — Local monitoring

**User action:** save one or more local conditions from the packet: enters entry
zone, crosses invalidation, data becomes stale or forecast drifts.

**Observable value:** watch conditions are visible in Instrument Workspace,
survive restart and emit typed local events without provider or order authority.

**Stop condition:** deterministic trigger and non-trigger replay are proven for
NVDA, including stale evidence; no external notification service is required.

### Slice 4 — Outcome and review

**User action:** reopen a past packet and compare its scenarios with the actual
path, paper result and risk execution, then save a review.

**Observable value:** a replayable decision journal connects the original
as-of evidence, operator action, paper outcome, attribution and review without
mutating history.

**Stop condition:** clean-restart NVDA E2E replays the complete packet-to-paper-
to-review lineage and explains both accepted and rejected paths.

## Acceptance criteria

- [x] On the deterministic NVDA acceptance station, timing starts when the
      operator submits the ticker or selects its watchlist row and stops when
      Reject, Watch or Paper proposal is durably saved; elapsed time is at most
      two minutes. Application installation/startup and optional AI latency are
      outside the timer.
- [x] The primary loop remains in Instrument Workspace and requires no CLI,
      database access or route hopping.
- [x] One desktop view makes market state, scenarios, risk, evidence, blockers
      and actions scannable; compact layout preserves the same ordered flow.
- [x] No model service, model timeout or invalid AI result prevents the
      deterministic packet from rendering or being saved as Reject/Watch.
- [x] Stale, low-quality, leakage-affected or missing evidence blocks Paper
      proposal with an actionable reason.
- [x] Every Paper proposal passes the existing deterministic risk kernel and
      an explicit second confirmation before any paper order is created.
- [ ] DecisionPacket, evidence references, operator disposition, paper result
      and review recover from a clean restart and replay without identity drift.
- [x] NVDA E2E covers the happy path, stale-data block and risk-refusal state.
- [x] English and Simplified-Chinese safety semantics, keyboard operation,
      reduced motion and 390 px no-overflow remain intact.

## Non-goals

- Qlib, Darts or any three-framework comparison as an iteration exit criterion.
- Model leaderboard, broad algorithm platform or unrelated research registry
  expansion.
- TradingView/browser extensions, mobile apps or external notification clients.
- Real trading, broker credentials, mainnet signing or autonomous execution.
- Social/community features or a large pattern-recognition catalog.
- More instruments or models before the NVDA loop demonstrates the wedge.

## Safety and evidence invariants

- External venues remain read-only and execution remains paper-only.
- AI output is research input and never direct order authority.
- Synthetic/demo evidence is labeled and cannot qualify real evidence.
- Backtest/forecast claims retain chronological, out-of-sample, cost and
  leakage evidence. Confidence without calibrated semantics is labeled as
  qualitative and cannot masquerade as probability.
- Paper sizing is a suggestion until the existing risk service accepts it; the
  operator's second confirmation remains mandatory.

## Agent delivery contract

- At most two tracks run: this product track and the independent 0021 soak
  maintenance track. Neither edits the other's files or state.
- Every slice starts with Planner/Product's one action, success measure and
  forbidden expansions, followed by Quant Researcher's bounded review of
  leakage, costs, metrics and confidence semantics.
- Implementer owns one API/page/state/test vertical loop. Reviewer evaluates
  the demonstrable boundary in at most two rounds; a third structural failure
  returns the slice for scope reduction.
- Verifier runs targeted checks during development and full gates at slice
  commit/final PR boundaries.
- Each prompt names one deliverable, one stop condition and forbidden actions.
  Side defects and other unrelated findings are recorded without expanding the
  task unless they block its user action or safety acceptance.
- Daily checkpoints state which user loop became possible or more trustworthy;
  test counts and ledger length are supporting evidence, not progress metrics.

## Non-blocking maintenance

- Evaluate the Impeccable v4.1.2 update in a separate maintenance task.
- Regenerate or reconcile the design sidecar with `DESIGN.md` in a separate
  maintenance task. Neither blocks product-direction approval or Slice 1.

## Role evidence — Slice 1 start, 2026-09-02

- **Planner/Product:** selected the two-minute ticker-to-saved-decision wedge,
  one-page constraint, four vertical slices and explicit exclusions.
- **Quant Researcher:** retained exact data/model/benchmark/out-of-sample/cost/
  leakage bindings; forbids converting price quantiles or empirical coverage
  into scenario probabilities; requires trusted manifest/quality pairs and
  separately named promotion/proposal freshness. Account fee and matcher
  slippage are pinned while half-spread is explicitly resolved by the existing
  confirmation quote rather than fabricated as zero.
- **Implementer:** Task 1 completed the DecisionPacket domain through
  `4409bcf9d630`; Task 2 completed Workspace/API/runtime/demo persistence and
  paper-authority binding through `9494d59a5c79`; Task 3 delivered the broader
  Instrument Workspace surface through `d786ec26a791`. Task 3R now owns only
  literal per-metric sample-window rendering and its focused test.
- **Reviewer:** Tasks 1 and 2 each used their two permitted corrective rounds
  and ended APPROVED with no open finding. Task 2 review closed dynamic-clock
  save drift, action concurrency/crash replay, current freshness, complete
  forecast binding, partial-config bypass, reset isolation and corrupt replay
  diagnostics without adding confirmation or order authority.
  Task 3 closed all state, action, replay, time-domain and compact-layout
  findings but exhausted its review ceiling with one metric-window evidence
  association issue. Broad patching stopped and the approved Task 3R scope was
  reduced to that single literal rendering boundary.
- **Verifier:** isolated worktree bootstrap is complete. Before behavior
  changes, the adjacent Python baseline passed `122` tests with `3` skips in
  `365.09s` using a worktree-local basetemp; the adjacent frontend baseline
  passed `35` tests in `4.50s` under Node `22.12.0`.
  Task 1 final verification passed `76` tests with `3` expected skips; focused
  Ruff and `git diff --check` passed.
  Task 2 final verification passed `97` tests with `6` existing dependency
  warnings; OpenAPI freshness, TypeScript, Ruff and diff checks passed.
  Task 3 component verification passed `48` tests before scope reduction;
  Task 3R passed `49` component tests plus focused default/UTC checks. Its
  independent review returned APPROVED/CLEAN. Two older timezone-dependent UI
  assertions are explicitly carried into Task 4 acceptance correction.

## Slice 1 completion evidence — 2026-09-03

- **Planner/Product:** the accepted boundary remained one real ticker/watchlist
  activation followed by one Reject, Watch or pending Paper proposal. The
  browser paths start at `/app/markets/watchlist`, activate NVDA, stay on the
  same Instrument Workspace route, and expose market state, three scenarios,
  risk, evidence, blockers and actions together. Structured Copilot,
  monitoring and outcome/review were not entered.
- **Quant Researcher:** the completed surface preserves literal forecast and
  evidence facts, keeps deterministic blocker codes authoritative, and shows
  the server's original blocker message as labeled evidence. No model service
  is needed for deterministic save, stale evidence remains fail-closed, and a
  risk refusal cannot create an accepted or filled paper order.
- **Implementer:** action results now promote one immutable packet snapshot to
  the whole workspace, so market/scenario/evidence/risk/action columns cannot
  mix a saved result with a fresh background draft. Known blockers have
  understandable English and Simplified-Chinese copy plus their raw server
  evidence; unknown messages fall back verbatim. A test-only portable Git
  discovery ceiling makes the no-repository experiment test honest when its
  basetemp lives below the worktree. Production commit resolution is unchanged.
- **Reviewer:** round 1 required three authoritative browser entry paths,
  cross-column packet ownership, localized blocker evidence, and the complete
  repository gate. All Important findings were closed. The remaining blocker
  taxonomy duplication is recorded as a later design smell; it was not
  refactored inside this slice.
- **Verifier:** Chromium completed independent Reject, Watch and Paper-proposal
  paths in `9.980s`, `9.759s` and `12.423s`, respectively (`3 passed`,
  `9 deselected`, `5 warnings`, `141.49s`, exit `0`). Watch used keyboard
  activation and save. Each path displayed and re-read its exact durable
  packet ID; Paper stopped at its bound pending-confirmation proposal ID.
  Existing API acceptance also reopens the exact complete JSON after a clean
  application restart and records the deterministic examples
  `packet-0e184acac704481ab38feb03` (Reject),
  `packet-1fabf1b1c1491b8c9830aad7` (Watch),
  `packet-37b3005fa521765287051224` (Paper), and
  `proposal-72b8ec44d530596ef34fa90d`. Stale evidence leaves Reject/Watch
  available while producing zero proposal/order; confirmation-time risk
  refusal retains its packet/proposal/rejected-order lineage and produces zero
  accepted or filled order.

The final coherent Slice 1 selection passed `176` tests with `3` expected
skips and `6` warnings in `2141.98s` (`35:41`), exit `0`. The final complete
repository run used a fresh local basetemp and passed `3150` tests with `9`
skips and `7` dependency warnings in `2953.81s` (`49:13`), exit `0`. Its
command was:

```text
.\.venv\Scripts\python.exe -m pytest -q --basetemp \
  .superpowers/sdd/2026-09-02-decision-packet-foundation/pytest-task4-review-full-final
```

The first complete run correctly stopped with `2 failed, 3149 passed, 8
skipped` in `3197.28s`: the local environment lacked the already pinned
`moomoo-api==10.10.7008` extra, and a no-repository unit test accidentally ran
under the worktree because its local basetemp was itself below the Git root.
Installing the repository's constrained `[moomoo]` extra changed only the
fresh `.venv`; `pip check` then reported no broken requirements and the exact
license test passed. The test-only Git ceiling went RED then GREEN locally; the
two former failures passed together before the final full run.

The controller independently repeated the complete repository command at the
final candidate and again received `3150` passed, `9` skipped and `7` warnings
in `2998.64s` (`49:58`), exit `0`. That fresh verification also clarified a
pre-existing release-closure issue rather than hiding it: the exact installed
closure classification/inventory tests pass, but invoking
`tools/license_review.py` directly in this development environment exits `1`
because `cloudpickle==3.1.2`, `formulaic==1.2.2`, `interface-meta==2.0.1` and
`wrapt==2.4.0` are installed transitives absent from the baseline
`requirements-audit.txt`. Slice 1 changes none of the lock, package metadata,
license policy or those dependencies. Per the no-side-defect-expansion rule,
repairing that inherited audit-lock drift is a separate release-maintenance
follow-up; this slice does not claim the direct deterministic release-license
gate is green.

Final static/frontend gates were: full `ruff check .` — clean, exit `0`;
`TZ=UTC npm exec vitest -- run` — `18` files and `167` tests passed in
`39.98s`, exit `0`; TypeScript — exit `0`; lint — exit `0` with four existing
Fast Refresh warnings; OpenAPI client freshness — current, exit `0`; packaged
SPA build — `2080` modules in `17.43s`, exit `0`; and `git diff --check` — exit
`0`. Six pre-existing mirrored skill-script Ruff blockers were changed only by
mechanical import modernization/line wrapping after their `cb8f4b0` provenance
was proved; no skill semantics or version changed. The Task 3 Impeccable result
was `[]`; a review-session duplicate read-only detector invocation also
returned `[]`, modified no file, and was not repeated.

Known limits remain explicit: all acceptance evidence is local deterministic
demo evidence, not real Provider/OpenD or live-trading evidence. Slice 1 proves
packet/disposition/proposal recovery; the unchecked full paper-result and
review replay criterion belongs to the separately approved outcome/review
slice.

## Slice 2 implementer checkpoint — 2026-09-03

- **Planner/Product boundary:** the implementation remains one on-demand action
  against an exact persisted NVDA DecisionPacket. A fresh draft is ineligible;
  the accepted result is a separate immutable advisory record and cannot mutate
  packet, risk, proposal, confirmation or order authority.
- **Quant Researcher:** every advisory item requires a packet-only citation with
  a restricted JSON pointer and canonical value digest. The independent critic
  must pass the complete report; invalid schema, substituted packet identity,
  missing/container/escaped pointer, digest mismatch, critic flag, timeout or
  unavailable model returns only `copilot-unavailable` with no draft leakage.
- **Implementer:** added strict contracts/service/store, two audit decisions,
  same-origin GET/POST routes, optional loopback-only model wiring, generated
  client bindings, localized inline evidence rail, demo reset ownership, and
  packaged SPA assets. Default demo and blank-model workstation paths make no
  model call. DecisionRail inputs and all authority counts remain unchanged.
- **Verifier evidence:** the coherent Python/API/browser selection completed
  `66 passed, 1 failed, 6 warnings in 2278.46s`; its sole failure was a new
  ambiguous `Evidence` region count after the valid scripted report, citation,
  invariance, reload and reset checks had passed. The one authorized isolated
  rerun completed `1 failed, 5 warnings in 132.11s`; it stopped on an exact
  `Market canvas` accessible-name assumption before the degraded POST. The
  test now follows the established non-exact region semantics, but that corrected
  isolated browser case remains the single unverified item for post-review.
  Service/API/component degraded coverage is green. Final component/workspace
  coverage is `23 passed`; generated API freshness, TypeScript, changed-file
  Ruff and packaged-bundle freshness pass.
- **Concern:** do not claim browser degraded-path PASS until the controller runs
  the corrected isolated case. Reviewer, detector and broad slice gate are also
  controller-owned and have not run at this checkpoint.

## Slice 2 completion evidence — 2026-09-03

Slices 1 and 2 are complete. The second and final Slice 2 review found all three
Important items and the one Minor item ADDRESSED, with no new Critical or Important
breakage. The completed product loop lets an operator request and reopen a fully
cited explanation/challenge of an exact persisted packet, while invalid or missing
AI degrades only the panel.

Its single user action requests a complete Base explanation, Bull/Bear challenges,
evidence gaps, limitations and operator questions against an already persisted
packet. Planner and Quant Researcher agree that the advisory result lives in a
separate immutable record keyed to the exact packet, not a child packet or packet
identity field. A fresh draft is ineligible; invalid schema, unresolvable packet/
path/digest, critic refusal, timeout or unavailable model degrades only the panel.
AI supplies no confidence, probability, direction, size, risk approval, blocker
override or action authority.

Final verification is `3179 passed, 9 skipped, 7 warnings in 3823.34s`, exit `0`;
the corrected packaged-SPA Chromium path is `1 passed, 5 warnings in 138.98s`, exit
`0`; UTC Vitest is `19` files / `173` tests, and Ruff, `pip check`, OpenAPI,
TypeScript, lint, production build, diff and the single Impeccable detector are
green. Exact details and the preceding transparent selector failures remain in the
implementer checkpoint above.

## Slice 3 completion evidence — 2026-09-03

Slices 1–3 are complete. The local monitoring panel saves one immutable set of
fixed conditions against an exact persisted packet, displays deterministic typed
facts, and recovers its cursor and terminal event identities after restart. The
entry pullback zone, long-only invalidation, pinned-calendar staleness and exact-
target forecast drift are server-derived; missing or incompatible evidence remains
`not_comparable`. The slice adds no scheduler, notification, provider or order
authority.

The first review found seven Important and two Minor issues. One correction closed
demo reset ownership, locked cursor derivation, rejected-observation handling,
complete replay binding, stale/forecast evidence binding, exact Origin comparison
and UI state/type handling. The second and final review left two structural items;
the design was reduced as required to one atomic activation envelope and canonical
terminal-event revalidation rather than opening a third review loop. Targeted
regressions then passed: monitoring/API `23 passed`, Chromium `1 passed`, and
workspace components `25 passed`. The packaged SPA is current and the single
Impeccable detector run returned no findings.

The one broad slice gate completed with `3203 passed, 9 skipped, 7 warnings in
3522.09s`, exit `0`; UTC Vitest completed `20` files / `180` tests, exit `0`.
Full Ruff, `pip check`, OpenAPI freshness, TypeScript, lint, production build,
bundle freshness and `git diff --check` all exited `0`. Lint retained four existing
Fast Refresh warnings; Vite retained the known local Node 22.11 version and chunk-
size warnings while exiting `0`.

## Current frontier

Slices 1–4 and the bounded Python release-license closure repair are complete.
The only remaining frontier is the final 0027 PR gate. Do not add another product
slice or expand into an exit-order lifecycle,
performance dashboard, AI review, another model framework, Provider/OpenD,
another symbol, external notification or 0021 soak.

## Slice 4 completion evidence — 2026-09-03

An operator can reopen one exact persisted non-draft NVDA action packet in
Instrument Workspace, inspect a frozen 30-session close-based outcome plus exact
paper-risk/watch provenance, classify it and save one immutable review. Exact
packet, proposal, order, fill, monitoring, path and outcome identities are
revalidated on replay. Missing continuous coverage, exit fills or complete costs
remain explicitly unavailable; the UI never fabricates realized R or zero P&L.
The saved review and its embedded outcome reopen with identical IDs after a clean
application reconstruction.

The combined boundary review used its two allowed rounds. After the single planned
correction, two narrowly scoped replay/UI gaps remained: exact order type and
quantity binding, and visibility of accepted/rejected order events. A final
test-first boundary correction fixed only those already identified gaps without a
third review or design expansion. Targeted proof passed: the exact order-tamper
regression `1 passed, 10 deselected` in `65.35s`; the component file `7 passed`;
the packaged Chromium save/restart path `1 passed, 14 deselected, 5 warnings` in
`154.97s`; targeted Ruff, Oxlint, TypeScript, bundle build/freshness and diff
checks exited `0`. The one required Impeccable detector had already returned `[]`.

The one broad Slice 4 gate passed `3217` Python tests with `9` skips and `7`
warnings in `3806.57s`, exit `0`. UTC Vitest passed `21` files / `187` tests;
Ruff, `pip check`, OpenAPI freshness, TypeScript, lint, production build, packaged
bundle freshness and `git diff --check` all exited `0`. Four existing Fast Refresh
warnings and the local Node `22.11.0` versus Vite `22.12+` advisory remained
non-blocking. No Provider/OpenD/model/notification call, real trade, other symbol
or 0021 soak state was touched.

## Final license-closure checkpoint — 2026-09-03

The direct license gate first reproduced the inherited refusal exactly: four
installed transitives were outside the 72-pin audit closure. Dependency metadata
bound them to `joblib -> cloudpickle==3.1.2` and `statsmodels ->
formulaic==1.2.2 -> interface_meta==2.0.1/wrapt==2.4.0`. The audit lock and
license inventory now contain those exact versions, producing a 76-package
cross-platform closure. The conservative parser gained only the exact `MIT`
license-text spelling needed by `interface_meta`; GPL, Commons Clause and unknown
metadata refusal behavior is unchanged.

Test-first evidence recorded the exact MIT spelling RED before implementation.
The first fresh-clone gate then exposed that the resolver had advanced 17 allowed
packages while the audit file still carried older versions; it stopped at
`simplejson==4.1.2` rather than falsely claiming a frozen closure. The lock and
inventory were updated to that fresh resolution, the `simplejson` exception was
version-bound to 4.1.2, and the gate now explicitly refuses any installed version
that differs from its pin. Both new contracts went RED then GREEN. In the retained
fresh environment, `tests/test_security.py` passed `21` tests in `0.36s`; targeted
Ruff and `git diff --check` exited `0`; and `tools/license_review.py` reviewed all
70 installed closure members, tolerated the six documented Linux-only pins and
exited `0` with `all licenses allowed`. No project dependency constraint or
product/runtime behavior changed.

The next fresh gate passed Python license and `pip-audit`, then stopped at two
new registry advisories in transitive frontend tooling: high-severity `fast-uri`
and moderate-severity `qs`. The minimal lock-only repair advances exactly
`fast-uri 3.1.5 -> 3.1.7` and `qs 6.15.3 -> 6.16.0`; no direct dependency or
runtime source changed. Fresh `npm ci` succeeded, `npm audit --audit-level=high`
reported zero vulnerabilities, the 646-package locked frontend license review
passed, and `git diff --check` exited `0`. The final fresh-clone gate remains the
only frontier.
