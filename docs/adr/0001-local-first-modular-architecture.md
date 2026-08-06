# ADR-0001: Local-First Modular Architecture

- Status: accepted
- Date: 2026-08-07

## Context

QuantMesh must combine research, multiple venues, AI assistance and trading execution while retaining local control of data, credentials and models. Large upstream projects offer valuable capabilities but have different abstractions and licenses.

## Decision

QuantMesh owns venue-neutral domain models, risk rules, orchestration and audit records. External capabilities are integrated behind adapters, package boundaries, Git submodules or separate local processes. Persistent user data and secrets remain local by default.

## Consequences

- Venue SDK upgrades are isolated from strategy code.
- Upstream projects can be replaced without changing core domain semantics.
- Adapter and reconciliation testing becomes mandatory.
- Some functionality may initially run as multiple local processes.

