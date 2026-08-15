# ADR-0018 — Execution numeric policy

- Status: accepted
- Date: 2026-08-15
- Deciders: solo delivery (iteration 0025, issue #116)
- Related: ADR-0006 (reconciliation tolerance policy), ADR-0002 (paper-first
  execution), iteration 0013 Phase E (the recommendation this records)

## Context

Price, quantity, fee and tolerance behavior across execution, risk, portfolio
and reconciliation uses distributed float operations with a small set of local
conventions. Iteration 0013 Phase E ranked "execution numeric policy" a Strong
follow-up: write characterization tests and an ADR covering tick size, lot size,
quantization and comparison, with no representation change.

## Decisions

### 1. The local quantization unit is six decimal places via `round(x, 6)`

Fees (`FeeModel.for_notional`), market-order slippage (`PaperMatcher`) and the
slippage-adjusted risk reference all quantize with `round(value, 6)`, which is
Python's round-half-to-even. Sub-micro amounts quantize to zero. No production
path uses `Decimal`; the one `Decimal` usage is the framework scorecard's
`ROUND_HALF_UP` to two places, which is a reporting quantization, not execution.

### 2. Basis points convert to a decimal fraction via `value / 10_000`

`fee_bps`, `slippage_bps` and every reconciliation tolerance share the same
`bps / 10_000` fraction, so `10_000 bps == 1.0` and `1 bps == 0.0001`.

### 3. Comparison tolerances default to exact and are bps-relative

`ReconcileTolerance` defaults every field to zero (exact). Quantity, price and
position drift compare `abs(diff) / reference > bps / 10_000`; fee drift
compares an absolute `fee_abs`. Any nonzero tolerance is an explicit operator
decision (ADR-0006 d. 3).

### 4. Zero/equality checks use `math.isclose`

Fill-side and position-side zero checks use `math.isclose(..., 0)` (or
`math.isclose` with a small `abs_tol`) rather than exact `==`, so accumulated
float residue does not fabricate a zero position or a phantom fill.

### 5. Venue tick size is metadata, not a local quantization unit

Venue tick size (`MarketQuote.tick_size`, `minimum_tick_size`) is validated as
positive metadata and surfaced, but no execution component re-quantizes to a
venue tick grid — the local unit is six decimals regardless of the venue's
tick. This is the recorded gap: a future live-trading slice must reconcile the
six-decimal unit with each venue's tick/lot grid before orders leave the paper
boundary.

## Consequences

- Positive: the conventions are pinned by tests, so a representation change is
  now a deliberate, reviewed decision instead of a silent drift.
- Negative: there is no single numeric-policy module — the conventions are
  conventions, applied inline; a future change must touch several call sites.
- Open: tick/lot-size enforcement at the live boundary is deferred (live is
  disabled by default); fees, slippage and P&L remain binary-float, not
  decimal, which is acceptable for the paper/simulated surface.
