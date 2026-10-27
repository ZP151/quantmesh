# SPY same-capture event representation compatibility — bounded plan

> For implementation: use executing-plans/TDD, one bounded independent review and
> verification-before-completion. Root selected this exact two-production-file lock;
> implementation is active in the isolated spy-event-parser-compat leaf.

Status: source6ef815613777a3656cfc60bc69719a589e95c9a2 reviewed READY by one
fresh narrow R1,0 findings.49 new targeted checks and actual EVENT-ONLY receipt
pass. Actual data qualification/numerical execution remain outside this delivery.

Actual ACK2026-10-27T03:22:03Z (SGT11:22:03); this plan deadline03:37:03Z.
The new human timebox is approved, not waiting for an owner: first verifiable
increment<=05:22:03Z, reviewable slice<=07:22:03Z, counted from this same ACK.
Recommended tighter delivery: first targeted GREEN<=04:22:03Z and reviewed offline
packet<=05:22:03Z. Technical selection/file lock by root is the next coordination
step, not another human or budget approval; do not reset clocks at implementation.

## One action and acceptance

Read the same immutable captured events offline with a narrowly named v3
representation profile. Correctly interpret the two recorded English-month cash
dividends while retaining their exact original bytes/source identity and every
existing qualification gate. Outcome is parser compatibility plus honest lineage,
not qualified data, a strategy verdict, a new capture or a financial calculation.

Authoritative actual review: POSTREVIEW-RESULT.md SHA256
fc198a08fee5d7fbd5f1ade677d7a1f35266b7970ed6088ab3e2383661577a5e.
Immutable actual raw d882c232ed68666ea35d1d3876470bcc60853c6f7678d281cda9403a58e3d9ae;
authorization bb456ef4a8c54bcd84caae1cd55d3b09e71a3f1a784736b8ebdf9249297f38de;
consumed marker828286295b5a3a41892fc969eb083f5452b56a836116a82a788306a7787143ac.
Actual source commit eee9d03a15852018f40aaa0c26463539c2859ef4 / tree
93c50c309113ab3dc92300b6ff22e3b45a4e4d33 (merged PR232).
Recorded collector tool SHA85ffc0f284f998db81390ea5a95aeba1be6b0486da8efe8aa5b3f67b08fc05ca.
`READ-ONLY-BOUNDARY.json` independently matches actual tool bytes to that Git blob
and records all five captured module hashes and unchanged engine hash. Inspection
imports no project module and creates no normalized input or authority marker.

## Diagnosis: capture identity and normalization identity are separate

Actual capture schema3 contains original responses, auth hash, intent ref and
request/receive timestamps. It does NOT contain normalizer/source-code hashes.
The existing protocol's `normalizer_sha256` is the offline freezer source hash;
`source_code_sha256` identifies that normalizer's reused runtime modules. Existing
freeze/reopen checks guard the loaded current tool/modules, not an asserted
equality between a future tool and old capture source. Original source identity
currently lives in the sealed capture/source package and independent actual review.

Therefore do not forge a raw source hash or patch PRE/auth to make new code match.
Keep the capture/source package untouched. For this single cohort, add a small,
explicit `normalization` block to the existing v3 protocol only when a new named
profile is selected by the independently issued PostReview. It records profile
version plus fixed original capture/source tuple (capture/auth/intent digests,
PR232 commit/tree, captured tool hash and five captured module hashes). The
existing protocol `normalizer_sha256` records the NEW actually loaded offline
tool hash; it must not be replaced by85ffc. Current runtime module hashes retain
their existing meaning. No new public schema version or permission platform.

The block is hash-bound by existing protocol/freeze/acceptance/report refs. Existing
post-review and protocol thin proofs already travel to the job CAS; do not add a
ninth proof object, raw history copy, frontend field or untrusted source-code path.
Cold verification must derive the expected block from the validated PostReview
profile and fixed cohort, not accept arbitrary metadata copied from the protocol.
Old v3 without a profile emits exactly its previous field set; old v1/v2 contracts
and saved bytes remain untouched. Reopening preserves recorded original hashes,
never backfills current hashes into a historical object.

## Recommended implementation shape

Use a v3-only `opend_spy_cash_dividend_en_month_v1` profile, scoped to the exact
raw/auth/intent/source tuple above. Do not globally widen `_day` or
`_cash_statement`, and do not relax existing evidence models. A separate strict
PostReviewV3-compatible subclass selects this profile and the exact format token
`english_month_abbrev_day_year`; legacy PostReviewV3 stays byte/field compatible.

Inside the freezer, a read-only preparation helper makes an explicitly derived
event view before passing it to the unchanged `_normalize_payload` and `_actions`:

1. Parse English ex dates with a fixed ASCII Jan..Dec table and exact fullmatch
   `Mon D, YYYY`, then construct a calendar date. No locale-sensitive `%b`, guessing,
   `dateutil`, extra whitespace or two-digit-year acceptance. Reject impossible
   dates, unknown month/case and alternate forms outside the named profile.
2. Filter by the ORIGINAL locked121-session set BEFORE examining statement or pay
   syntax. Preserve all31 original rows and their raw bytes. Out-of-window Cash
   Gain is not a reason to accept a new cash syntax; do not interpret its amounts.
   Ex dates still must parse so membership is known. No event is silently dropped
   from the source; only the established window selection controls derivation.
3. Within the window, this profile accepts only exact single-component
   `Cash Dividend: <positive decimal>USD`. Cross-check using Decimal against exactly
   one same-ex original `adjustment_factors.per_cash_div`, including currency USD.
   Validate original factor numeric domain before converting its decimal string.
   No tolerance in this new unit/amount inference, no sums of compact components,
   no sign/exponent/unknown currency/ambiguous unit, no Cash Gain/Special/stock
   interpretation. Missing/duplicate/conflicting factor proof refuses.
4. Parse present actual pay fields with the same fixed month table; do not infer
   dates or fill zero. Root clarification: preserve the original rule allowing a
   missing warmup pay date; do not turn this cohort's two present dates into a new
   universal gate. Original actions reject missing observation pay and pay<ex.
   Preserve original ex/pay distinction. Derive canonical ISO event dates
   and the established explicit USD-per-share representation ONLY in this local
   derived view after exact cross-proof; never mutate raw or PostReview bytes.
5. Feed that derived view into existing original actions/normalization using a
   derived ISO-format evidence view. Original noncash ratio, split, duplicate,
   reconciliation, window, OHLCV, costs and cash math remain authoritative. Keep
   `_day`, `_cash_statement`, `_actions`, `_normalize_payload` ASTs unchanged.

For actual rows this means2026-09-18→2026-10-30/1.88883USD and
2026-06-18→2026-07-31/1.90352USD, both warmup ex events. They cannot be removed
to make a parser pass; warmup still has no holdings and later pay creates no
invented receivable. No strategy calculation is part of this software slice.

## Exact proposed file lock (single implementation writer)

Production, two files only:

- `tools/research/freeze_opend_spy_daily.py`: strict profile/date/Decimal helper,
  PostReviewV3-only profile dispatch, derived-view preparation, protocol lineage
  construction/reopen validation. Original parser/math/transport ASTs stay unchanged.
- `src/quantmesh/research/spy_replay.py`: select the same strict PostReview profile
  during cold proof checks and compare the protocol extension against its validated
  expected lineage. No engine/calculator/job/request/decision behavior changes.

Tests, one NEW file only:
`tests/test_spy_event_parser_compat.py`.

Owned documentation:
`docs/superpowers/plans/2026-10-27-spy-event-parser-compat.md` (promote this selected plan),
`docs/iterations/0038-spy-event-parser-compat.md` (roles/RED/GREEN/actual limitations),
`docs/adr/0035-spy-private-policy-exception-once.md` (small offline-lineage amendment).

No frontend/API/generated client, dependencies/locks, provider/feed, policy helper,
engine/SMA100, database, shared roadmap/Goal, host or publisher files. Implement
from actual merged PR232 or the then-current origin/main that contains it, in a
fresh isolated worktree after checking attachment inventory. Do not alter the
previous reviewed branch or its immutable delivery packet.

## RED/GREEN and independent review

- [x] Add only the new test file. Run `python -m pytest
  tests/test_spy_event_parser_compat.py -q` with owned unique basetemp and preserve
  the missing-profile/date/cash/lineage RED. No old44 tests or F0 rerun.
- [x] Locale-independent positives for both actual event lexemes; strict invalid
  dates/months/case/whitespace and impossible dates. Prohibit locale calls in the seam.
- [x] Exact Decimal cross-proof positive; absent/duplicate/same-date wrong amount,
  currency, exponent, zero/negative, compound and in-window noncash all refuse.
- [x] Out-of-window Cash Gain stays uninterpreted after ex-date filtering; the two
  warmup records/pay dates survive, without generating warmup cash holdings.
- [x] Explicit profile only on this v3 cohort; wrong raw/auth/marker/source hashes,
  unknown/partial profile, v1/v2 profile laundering all refuse. Existing legacy parser
  vectors still have the same results through new-file regression cases only.
- [x] Controlled v3 freeze/reopen/report-proof tests retain original capture/source
  identity and record a distinct new normalizer hash/version; missing/altered
  lineage fails warm and cold without current options. Calculator is a sentinel,
  never a real strategy. Existing8 proof refs and all object limits stay unchanged.
- [x] After GREEN, scoped Ruff/format/diff and original engine/strategy/cash/date/
  cost/window/transport AST/raw pins. New targeted file only; no old whole suites,
  CI, dependency install, SDK, host, new timestamps/window/nonce/authority.
- [x] One fresh narrow independent reviewer checks only this parser/lineage diff,
  with at most known-fix R2. Do not re-review the old v3 slice or F0. Sole publisher
  owns exact-lock API generation/build/CI/PR/merge/deployment.
- [x] Optional ignored actual EVENT-ONLY probe rehashes immutable raw/auth/marker
  before/after and checks just the derived event representation, labels
  `FORMAT_COMPAT_ONLY_NOT_DATA_QUALIFICATION`, and emits no normalized prices,
  freeze, qualified PostReview, acceptance or financial result.

## Data / authority / stop gates

B remains independently INSUFFICIENT until actual volume-shares unit, historical
feed coverage and source price-USD mapping are bound. Do not manufacture feed,
infer units from integer volumes, use target Instrument currency as source proof,
or issue a passing PostReview just to exercise the new parser. Quant's separately
bounded official-static investigation owns those facts. Current format software
progress can proceed without waiting for it or a host.

Canonical once marker is consumed permanently. No new capture/SDK/nonce/root pin,
auth/PRE/raw edit, source switch, terms/customer research, prices or event acquisition.
Internal approval remains HUMAN_APPROVED, external applicability UNKNOWN and
provider_permission_verified=false. Original121=100+21, SMA100, cost5/10bps,
benchmarks, cash ordering and all data/math/budget gates remain. No strategy
promotion, financial PASS or paper authority. Goal stays ACTIVE under root.

If a required implementation needs another production file, broad schema/UI or
gate weakening, return the exact counterexample to root before expanding. Otherwise
root's one technical file-lock selection is sufficient to implement under existing
human authority. Once all actual gates plus real freeze/acceptance exist, the
already authorized one actual job/report/Reject-or-Watch/cold reopen proceeds
without another human approval. This plan neither creates nor claims those inputs.
