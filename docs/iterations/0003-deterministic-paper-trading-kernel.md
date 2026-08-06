# Iteration 0003 — Deterministic Paper-Trading Kernel

- Status: active
- Started: 2026-08-07
- Completed:
- Owner: unassigned agent team
- GitHub issue: [#1](https://github.com/ZP151/quantmesh/issues/1)
- Pull request:
- Roadmap milestone: M2

## Outcome

Run a complete order lifecycle locally with reproducible cash, positions, fills and P&L before any external execution is enabled.

## Scope

- In scope: account and execution domain models, order-state machine, deterministic matching, costs, risk limits, persistence, replay and reconciliation.
- Out of scope: live venue routing, HFT queue simulation and AI order authority.

## Acceptance criteria

- [ ] Identical replay input produces identical fills and portfolio state.
- [ ] Invalid order-state transitions are rejected.
- [ ] Stale or missing quotes fail closed.
- [ ] Paper account restarts and reconciles from persisted events.
- [ ] Fees, spread and slippage are visible in P&L.
- [ ] Automated tests and verification evidence are recorded here.

## Plan and role assignments

- Planner: split issue #1 into domain state, matcher, accounting, persistence and API slices.
- Quant researcher: define realistic but deterministic fee, spread and slippage assumptions.
- Implementer: unassigned.
- Reviewer: unassigned; must include trading-safety review.
- Verifier: unassigned.

## Decisions

Follow ADR-0002. The simulator and future live adapters must share order-state and risk semantics.

## Work log

- 2026-08-07: Created the active iteration and linked GitHub issue #1.

## Verification evidence

Pending implementation.

## Risks and follow-ups

- Matching realism must improve incrementally without making replay nondeterministic.
- Persistence design should preserve an auditable event history and derived state.

