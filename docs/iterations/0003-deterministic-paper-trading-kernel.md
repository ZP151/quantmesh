# Iteration 0003 — Deterministic Paper-Trading Kernel

- Status: active
- Started: 2026-08-07
- Completed:
- Owner: unassigned agent team
- GitHub issue: [#1](https://github.com/ZP151/quantmesh/issues/1)
- Pull request: [draft #7](https://github.com/ZP151/quantmesh/pull/7) (slice #2, issue #2)
- Roadmap milestone: M2

## Outcome

Run a complete order lifecycle locally with reproducible cash, positions, fills and P&L before any external execution is enabled.

## Scope

- In scope: account and execution domain models, order-state machine, deterministic matching, costs, risk limits, persistence, replay and reconciliation.
- Out of scope: live venue routing, HFT queue simulation and AI order authority.

## Acceptance criteria

- [ ] Identical replay input produces identical fills and portfolio state (replay slice #5).
- [x] Invalid order-state transitions are rejected (slice #2, tests `test_valid_transitions_follow_the_explicit_table`, `test_terminal_states_reject_every_event`, invalid-pair tests).
- [x] Stale or missing quotes fail closed (matcher slice #3; tests `test_stale_quote_fails_closed_for_market_orders`, `test_limit_order_against_stale_quote_fails_closed`, `test_market_order_without_a_touch_fails_closed`, `test_missing_volume_fails_closed_*`).
- [ ] Paper account restarts and reconciles from persisted events (persistence slice #5).
- [ ] Fees, spread and slippage are visible in P&L (accounting slice #4).
- [ ] Automated tests and verification evidence are recorded here.

## Plan and role assignments

- Planner: split issue #1 into domain state, matcher, accounting, persistence and API slices (done 2026-08-07).
- Quant researcher: define realistic but deterministic fee, spread and slippage assumptions (slice #4).
- Implementer: TDD slices #2 (order lifecycle) and #3 (matcher) completed 2026-08-07.
- Reviewer: two-axis /code-review on slices #2 and #3 completed 2026-08-07; findings resolved.
- Verifier: verification evidence recorded below for slices #2 and #3.

## Decisions

- Follow ADR-0002. The simulator and future live adapters must share order-state and risk semantics.
- Order lifecycle and its state-transition invariants live in `domain` (`src/quantmesh/domain/orders.py`); CONTEXT.md's `execution` boundary now reads "orchestration, persistence and reconciliation". The state machine is the shared semantic base for paper and future live adapters (ADR-0002 consequence).
- Order state is immutable and event-derived: `OrderStateMachine.apply` returns a new `Order`; `OrderEvent` history is the single source of truth for replay (slice #5).
- The transition table is declarative (`OrderStateMachine.TRANSITIONS`, mapping event type to allowed source states); fill completion uses `math.isclose` so fractional quantities (e.g. 0.1 + 0.2 == 0.3) reach FILLED without float-error rejection.
- Event timestamps default to `now(UTC)` at creation; replay determinism relies on persisted timestamps (slice #5).
- The deterministic matcher lives in `execution/` (`src/quantmesh/execution/matcher.py`): fills are a pure function of (order, quote, simulation time) — `now` is injected, no clock reads inside.
- Fail-closed wins over resting: a stale quote, a missing touch, or missing/zero depth rejects the order (both market and limit) instead of risking a phantom fill (product invariant #6). Depth (`quote.volume`) caps fills for both order types; a non-crossed limit order is the only "still working" outcome.
- Slippage (`slippage_bps`, default 5.0) applies to market orders only; limit orders fill at the touch price when crossed (never worse than their limit). Stale boundary is inclusive: a quote exactly `max_quote_age` old is still valid.
- `MatchResult` carries either fills or a rejection, never both; `match_step` gives time priority in submission order and skips terminal orders silently.

## Work log

- 2026-08-07: Created the active iteration and linked GitHub issue #1.
- 2026-08-07: Split issue #1 into five single-session vertical tickets with explicit blocking edges:
  - [#2](https://github.com/ZP151/quantmesh/issues/2) Order lifecycle and deterministic state machine (no deps)
  - [#3](https://github.com/ZP151/quantmesh/issues/3) Deterministic market/limit matching engine (blocks on #2)
  - [#4](https://github.com/ZP151/quantmesh/issues/4) Portfolio accounting with fees and risk limits (blocks on #3)
  - [#5](https://github.com/ZP151/quantmesh/issues/5) SQLite event persistence, replay and reconciliation (blocks on #4)
  - [#6](https://github.com/ZP151/quantmesh/issues/6) Paper account API observability (blocks on #5)
- 2026-08-07: Slice #2 (issue #2) implemented with TDD on `feat/2-order-lifecycle`:
  - Vertical slices: Order construction → transition matrix → fill application → cancel/reject/terminal → `Order.from_request`.
  - Added `Fill`, `OrderEvent`, `Order`, `OrderStateMachine` in `src/quantmesh/domain/orders.py`; 36 tests in `tests/test_orders.py`.
  - /code-review (standards + spec axes): resolved float-equality completion bug (`math.isclose`), added model-boundary validation (filled ≤ quantity), carried `client_order_id` through `from_request`, added declarative `TRANSITIONS` table and invalid non-terminal transition tests.
- 2026-08-07: Slice #3 (issue #3) implemented with TDD on `feat/3-deterministic-matcher`:
  - Vertical slices: market orders (fill price, slippage, fail-closed) → limit orders (cross/rest) → depth-capped partial fills, time priority and determinism.
  - Added `PaperMatcher` and `MatchResult` in `src/quantmesh/execution/matcher.py`; 23 tests in `tests/test_matcher.py`.
  - /code-review (standards + spec axes): resolved missing-volume-unlimited-depth phantom-fill hazard (now fail closed for both order types), reused `OrderStateMachine.TERMINAL_STATES` and `Order.remaining_quantity`, added fills/rejection exclusivity to `MatchResult`, timezone-aware timestamp guard, tests for limit partial fills and remainder re-matching.
  - Caller contract for the next slice (#4): fills → `OrderStateMachine.apply(FILL)`, rejection → `REJECTED`, empty result → order stays working.

## Verification evidence

Slice #2 (branch `feat/2-order-lifecycle`, commits `eb69a5c`, `acd0126`, PR #7):

```text
.\.venv\Scripts\python.exe -m pytest -q: 36 passed (1 pre-existing StarletteDeprecationWarning)
.\.venv\Scripts\ruff.exe check src tests: All checks passed
git diff --check: passed
git submodule status: clean
```

Review gate: /code-review two-axis (standards + spec) — zero remaining actionable findings; fixes verified by the new tests above.

Slice #3 (branch `feat/3-deterministic-matcher`, commit pending, PR #8):

```text
.\.venv\Scripts\python.exe -m pytest -q: 59 passed (1 pre-existing StarletteDeprecationWarning)
.\.venv\Scripts\ruff.exe check src tests: All checks passed
git diff --check: passed
git submodule status: clean
```

Review gate: /code-review two-axis (standards + spec) — zero remaining actionable findings; fixes verified by the new tests above.

Follow-up: GitHub Actions `pull_request` runs have not fired on the feature branches (runner-acquisition failures observed on main pushes); CI verification is pending GitHub infra. No code failure observed.

## Risks and follow-ups

- Matching realism must improve incrementally without making replay nondeterministic.
- Persistence design should preserve an auditable event history and derived state.

