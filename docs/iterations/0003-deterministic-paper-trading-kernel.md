# Iteration 0003 — Deterministic Paper-Trading Kernel

- Status: completed
- Started: 2026-08-07
- Completed: 2026-08-07 (work complete; PRs #7-#11 remain draft pending merge review)
- Owner: unassigned agent team
- GitHub issue: [#1](https://github.com/ZP151/quantmesh/issues/1)
- Pull request: [draft #7](https://github.com/ZP151/quantmesh/pull/7) (slice #2, issue #2), [draft #8](https://github.com/ZP151/quantmesh/pull/8) (slice #3, issue #3), [draft #9](https://github.com/ZP151/quantmesh/pull/9) (slice #4, issue #4), [draft #10](https://github.com/ZP151/quantmesh/pull/10) (slice #5, issue #5), [draft #11](https://github.com/ZP151/quantmesh/pull/11) (slice #6, issue #6)
- Roadmap milestone: M2

## Outcome

Run a complete order lifecycle locally with reproducible cash, positions, fills and P&L before any external execution is enabled. Achieved: order state machine (#2), deterministic matcher (#3), portfolio accounting with fees/slippage/risk limits (#4), SQLite event persistence with replay and reconciliation (#5), read-only observability API (#6) — 110 tests, all M2 deliverables implemented on branches `feat/2`…`feat/6` with draft PRs #7-#11. Merge of the slice chain into main is the remaining gate.

## Scope

- In scope: account and execution domain models, order-state machine, deterministic matching, costs, risk limits, persistence, replay and reconciliation.
- Out of scope: live venue routing, HFT queue simulation and AI order authority.

## Acceptance criteria

- [x] Identical replay input produces identical fills and portfolio state (replay slice #5).
- [x] Invalid order-state transitions are rejected (slice #2, tests `test_valid_transitions_follow_the_explicit_table`, `test_terminal_states_reject_every_event`, invalid-pair tests).
- [x] Stale or missing quotes fail closed (matcher slice #3; tests `test_stale_quote_fails_closed_for_market_orders`, `test_limit_order_against_stale_quote_fails_closed`, `test_market_order_without_a_touch_fails_closed`, `test_missing_volume_fails_closed_*`).
- [x] Paper account restarts and reconciles from persisted events (persistence slice #5).
- [x] Fees, spread and slippage are visible in P&L (accounting slice #4).
- [x] Account, positions, orders and P&L endpoints return consistent state (API slice #6).
- [x] Kill-switch status is observable (API slice #6).
- [x] Automated tests and verification evidence are recorded here.

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
- Portfolio accounting lives in `execution/` (`src/quantmesh/execution/accounting.py`): `PaperAccount` is the aggregate root — submission is risk-gated, then matched, then applied; every application returns a new account state (immutable, event-derived like the order lifecycle).
- `PaperAccount` is a pydantic model carrying serializable config (`fee_model`, `risk_limits`, `matcher`); `PaperMatcher` became a pydantic BaseModel so it is a normal serializable field (slice #4) — required for persistence (slice #5) and for deterministic risk estimation with slippage.
- Order IDs are deterministic: `client_order_id` if provided, else a per-account `order_sequence` counter (`paper-1`, `paper-2`, …) — no uuid4, so identical input replays identical state.
- P&L is equity-based: `equity = cash + Σ mark × position`; `total_pnl = equity − starting_cash`. `starting_cash` is captured at construction (`capture_starting_cash`, in-place `mode="after"` validator — returning a copy from a top-level validator is unsupported by pydantic during `__init__`). This nets entry/exit fees, spread and slippage into a single number.
- Risk limits run pre-trade in the account (`kill_switch`, `max_order_quantity`, `max_notional`, `max_position_quantity`, cash sufficiency, position sufficiency). Market-order reference price is slippage-adjusted so a cash/notional check cannot pass only to be overrun by slippage. These live in `execution` for now; a dedicated `risk` module owning pre-trade controls remains a roadmap item (ADR-0002 semantics shared).
- `FeeModel.for_notional` = `max(min_fee, round(notional × fee_bps / 10_000, 6))`; a fee is charged on every fill including the closing one, and the fill-triggered sell-fee counts into realized P&L (buy-side fee lands in average cost).
- `apply_fill` returns a new account and closes (pops) a long position when remaining quantity hits zero (`math.isclose`); selling beyond the position raises instead of going short.
- Event sourcing in `execution/store.py` (stdlib `sqlite3`, no new dependency): the `events` table is the single source of truth — orders rebuild by replaying events through `OrderStateMachine.apply`, the account by replaying FILL events through `apply_fill` in global-sequence order. Derived fields are never trusted.
- Append-only events with a monotonic global sequence (`INTEGER PRIMARY KEY AUTOINCREMENT`) and `UNIQUE(order_id, event_sequence)`; `save()` is one transaction (meta + order headers + missing events + snapshot) and idempotent — only events with a per-order sequence beyond the last persisted are appended.
- The `account_snapshot` records reconciliation fingerprints only (derived state plus per-order headers and config): any tampering with or loss of events, order headers or config surfaces as a divergence instead of silent drift. `restore()` returns `RestoreResult(account, divergences)`; empty store and invalid persisted transitions fail closed (the latter as a typed `StoreCorruptionError`).
- Order ids are unique per account: `submit()` rejects a reused `client_order_id` with `ValueError`, so a retry loop can never silently overwrite a live order (also what makes save/restore unambiguous).
- `kill_switch` persists across restart (fail-closed direction: an engaged switch stays engaged).

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
- 2026-08-07: Slice #4 (issue #4) implemented with TDD on `feat/4-portfolio-accounting`:
  - Vertical slices: cash/position math on fills → weighted-average cost and realized P&L → pre-trade risk gates → `submit()` end-to-end → equity-based P&L.
  - Added `FeeModel`, `Position`, `RiskLimits`, `SubmissionResult`, `PaperAccount` in `src/quantmesh/execution/accounting.py`; refactored `PaperMatcher` to a pydantic BaseModel; 19 tests in `tests/test_accounting.py`.
  - /code-review (standards + spec axes): resolved pydantic `PrivateAttr`-cannot-be-injected bug (matcher now a serializable field), deterministic `order_sequence` IDs instead of uuid4, slippage-adjusted cash estimate (overdraw guard), equity-based `total_pnl` (old formula double-counted the sell fee), `apply_fill` full-close path dedup, removed unused import.
  - Determinism: identical inputs (with or without `client_order_id`) produce identical `model_dump()` state; `now` injected through `submit`/`match`; timestamps timezone-aware.
- 2026-08-07: Slice #5 (issue #5) implemented with TDD on `feat/5-persistence-replay`:
  - Vertical slices: append-only events with monotonic sequence → rebuild orders from events → replay fills into an account → restart → reconciliation vs snapshot → tamper detection.
  - Added `EventStore`, `RestoreResult`, `StoreCorruptionError` in `src/quantmesh/execution/store.py`; 18 tests in `tests/test_store.py`; 96 total passing.
  - /code-review (standards + spec axes): resolved two verified must-fixes — (M1) snapshot fingerprint now covers full order headers and config so tampered `orders.side`/`quantity`/config on fill-less orders cannot pass silently; (M2) `submit()` rejects duplicate `client_order_id` so a reused id can never silently drop a newer order at persist time. Should-fixes: typed `StoreCorruptionError` instead of a raw `ValueError` on corrupt logs, `kill_switch` round-trip test + config reconciliation, explicit `is not None` for `starting_cash` (0 is a valid value). Nits: shared fingerprint helpers so save/reconcile cannot drift.
  - Verification evidence below.
- 2026-08-07: Slice #6 (issue #6) implemented with TDD on `feat/6-api-observability`:
  - Vertical slices: account summary → positions with unrealized P&L → orders with event histories → P&L with injected marks → kill-switch status → read-only enforcement.
  - Extended `src/quantmesh/api/app.py` with `create_app(*, account, marks)` — a read-only FastAPI factory (GET /account, /positions, /orders, /orders/{id}, /pnl, /kill-switch); mark prices are injected by reference (the operator's update seam), no clock or feed reads; module-level `app` stays as the smoke-test bootstrap.
  - 14 tests in `tests/test_api.py`; 110 total passing.
  - /code-review (standards + spec axes): zero must-fix code defects. Should-fixes resolved: `/pnl` names unmarked positions in `missing_marks` so excluded-from-equity value is never silent (and `/positions` reports `unrealized_pnl: null`); per-request snapshot of marks removes the check-then-index race; `/kill-switch` and `/account` share the `kill_switch` field name; HTTP-level POST-405 test pins read-only enforcement; rejected-order serialization (reason + null fill fields) covered.
  - Verification evidence below.

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

Slice #4 (branch `feat/4-portfolio-accounting`, commit pending, PR #9):

```text
.\.venv\Scripts\python.exe -m pytest -q: 78 passed (1 pre-existing StarletteDeprecationWarning)
.\.venv\Scripts\ruff.exe check src tests: All checks passed
git diff --check: passed
git submodule status: clean
```

Review gate: /code-review two-axis (standards + spec) — zero remaining actionable findings; fixes verified by the new tests above (equity-based P&L, deterministic order IDs, slippage overdraw guard, apply_fill dedup).

Slice #5 (branch `feat/5-persistence-replay`, commit pending, PR #10):

```text
.\.venv\Scripts\python.exe -m pytest -q: 96 passed (1 pre-existing StarletteDeprecationWarning)
.\.venv\Scripts\ruff.exe check src tests: All checks passed
git diff --check: passed
git submodule status: clean
```

Review gate: /code-review two-axis (standards + spec) — zero remaining actionable findings; fixes verified by the new tests above (header/config tamper detection, duplicate order-id rejection, typed corruption error, kill_switch round trip).

Slice #6 (branch `feat/6-api-observability`, commit pending, PR #11):

```text
.\.venv\Scripts\python.exe -m pytest -q: 110 passed (1 pre-existing StarletteDeprecationWarning)
.\.venv\Scripts\ruff.exe check src tests: All checks passed
git diff --check: passed
git submodule status: clean
```

Review gate: /code-review two-axis (standards + spec) — zero remaining actionable findings; fixes verified by the new tests above (missing_marks naming, marks snapshot, kill_switch field consistency, POST 405, rejected-order serialization).

Follow-up: GitHub Actions `pull_request` runs initially did not fire on the feature branches (runner-acquisition failures observed on main pushes). Resolved 2026-08-07: re-runs for PRs #8/#9 passed with zero code change (confirmed infrastructure, not repository defect), PR #10 re-triggered via an empty commit (`925fd0c`), and checks are green on PRs #7-#11. No code failure observed.

## Risks and follow-ups

- Matching realism must improve incrementally without making replay nondeterministic.
- Persistence design should preserve an auditable event history and derived state.

