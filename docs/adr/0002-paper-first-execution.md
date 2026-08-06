# ADR-0002: Paper-First Execution

- Status: accepted
- Date: 2026-08-07

## Context

Backtest performance does not prove correct order handling, realistic costs or live reliability. AI-generated signals add another uncertain layer.

## Decision

All strategies progress through research, deterministic replay, internal paper trading and venue paper/testnet execution before live eligibility. Live trading is disabled by default and can only receive orders after deterministic risk approval.

## Consequences

- The paper-trading kernel is the next core milestone.
- Paper and live adapters must share order-state and risk semantics.
- AI components cannot call venue execution directly.
- Promotion evidence is stored in iteration records and experiment metadata.

