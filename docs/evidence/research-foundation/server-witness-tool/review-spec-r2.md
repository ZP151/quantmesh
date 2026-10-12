# Spec review — witness ROUND2 (final review round)

Reviewed `9ff1f22b8b07811b09345dd9d1d15125afb1640b...dd871e04663a1c0c8294da7b7f8515360aa0f92f`, limited to the witness, tests and runbook. Read the narrow plan, approved research-foundation server/session requirements, AGENTS, ADR-0004/0025 and ROUND1 reports. No tracked edits, SDK/vendor/network/account/auth/installation operations, full-suite rerun or further agents.

## Finding

**P2 — Evaluate scoped candle freshness before declaring fresh coverage.** `tools/verify_server_market_source.py:666–668` computes the candle policy from `max(completed)` (canonical interval end), even when the latest live-tail bar's validated `freshness_time=min(provider_end,received_at)` is earlier. The plan requires “actual source clocks”; ADR-0025 requires scoped freshness to use “min(provider end, receipt)” and states that old windows cannot rejuvenate it. The ROUND1 fix makes this field mandatory and validates receipt ordering, but never uses its value for coverage.

Offline reproduction: move all supplier labels and application bars back one minute while retaining progressive matching OHLCV, sequences, two boundaries and current quote/metric clocks. Set each latest lineage's receipt/freshness to its canonical start, update exact end/label/age, and validate each app through actual `_application`/`HistoricalSeries`. Every strict contract accepts. `evaluate_samples` reports `provider_application=passed, coverage=fresh`; the shared policy on that scoped candle clock reports `data_state=delayed`. Reproduction: `output/169-server-witness/review-spec-r2-probe.py`, exit0. Require acceptable scoped candle freshness alongside completed-window/quote coverage before passing this subgate; preserve normal closed-session semantics.

## Scope and evidence

The other ROUND1 fixes address owned-child cleanup, bounded native configuration/proc/hash reads, unsupported intermediate bars and US application identity. Fixed HTTP allowlist and quote-only adapter reuse respect the account-read prohibition; actual proposal/workspace UI remains explicitly unverified. Native candidate evidence cannot certify routing, PC independence, browser or recovery, and the overall result remains pending even in the reproduction above.

Inspected recorded related241/focused73 cases, Ruff/format/diff exits0 and blocked actual CLI pending/exit2; these are software/refusal evidence, with no authenticated Linux host or application-route proof.

**Initial result:** one P2 finding; no additional scope or acceptance-claim findings. This is review round2 of2; no third review requested.

## Test-based disposition of the same ROUND2 finding

Inspected only the supplied fix and its exact regression, without reopening structural review. The completed coverage clock now caps at the latest validated scoped freshness clock, floored to the completed minute grid, before calling the unchanged shared bar-end policy. This addresses the reported clock substitution.

Recorded `scoped-clock-red.log/.exit`: 1failed/73deselected, exit1. Recorded `scoped-clock-green.log/.exit`: 74passed/5warnings, exit0. Independently reran only the original offline probe through `_application`/`HistoricalSeries`: exit0; the repaired evaluator returns `provider_application=failed`, `reason=source_coverage_missing_or_delayed`, consistent with the independently evaluated delayed scoped clock.

**Final disposition:** the single ROUND2 finding is resolved by this targeted fix and evidence; no open actionable Spec findings remain in the reviewed scope. Actual Linux authenticated-host, route, proposal/UI, browser, lifecycle and PC-independence acceptance remains unverified. Final candidate commit and related regression evidence belong to the coordinator handoff.
