# Moomoo OpenD Readiness Probe Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Provide a read-only, machine-checkable readiness report for the private Moomoo/OpenD route and the AAPL/NVDA quote/history entitlements without enabling orders or live trading.

**Architecture:** Keep the vendor boundary in `MoomooOpenDClient` and add a small readiness value model that validates quote and history payloads through the existing `MoomooDataAdapter`. The CLI performs a bounded TCP route check before invoking the SDK and emits stable text or JSON statuses; all failures remain typed and no trade APIs are called.

**Tech Stack:** Python 3.11+, dataclasses, argparse, pytest, existing Moomoo OpenD adapter and settings.

**Spec:** GitHub issue #156 (Iteration 0037 — Private Moomoo/OpenD AAPL/NVDA readiness).

## Global Constraints

- OpenD access is private and read-only; do not open a public port or call order APIs.
- The report must distinguish route unavailable, SDK missing, authentication required, protocol-invalid data, and per-symbol quote/history entitlement failures.
- Default verification symbols are `AAPL,NVDA`; the history probe is bounded to one daily page per symbol.
- Paper mode remains the default and live execution stays disabled.
- No credentials, account data, or raw vendor secrets may be persisted or printed.
- CI is paused; run local tests and checks only and do not push or deploy.

## Review Focus

- A closed or filtered TCP port must stop before SDK calls and report `route_unavailable`.
- A quote success followed by an empty history response must remain `history_unavailable`, never be labeled ready.
- A malformed quote/history payload must be `protocol_error` and must not be mistaken for an entitlement.
- One symbol may be ready while the other fails; the overall report must be `partial` and preserve both rows.
- A capability payload advertising order access must not cause the readiness command to invoke or expose order operations.

### Task 1: Readiness report boundary

**Files:**
- Create: `src/quantmesh/moomoo/readiness.py`
- Modify: `src/quantmesh/moomoo/__init__.py`
- Test: `tests/test_moomoo_readiness.py`

**Interfaces:**
- Consumes: `MoomooOpenDClient.probe`, `.stock_quote`, `.history_kline`, `MoomooDataAdapter`.
- Produces: `ReadinessReport`, `SymbolReadiness`, and `run_readiness(client, codes, interval="1d")`.

- [ ] **Step 1: Write the failing test**

Add tests for a fully ready AAPL/NVDA fixture, a per-symbol history failure, an empty history response, malformed payloads, and an order-capable probe that records no order call.

- [ ] **Step 2: Run the readiness tests to verify they fail**

Run: `python -m pytest tests/test_moomoo_readiness.py -q`
Expected: collection or import failure because `quantmesh.moomoo.readiness` does not yet exist.

- [ ] **Step 3: Write the minimal readiness implementation**

Define frozen dataclasses with stable string statuses. Probe capabilities once, call only quote/history methods, validate each payload with the existing adapter, require at least one valid history bar, and classify each symbol independently. Derive overall status as `ready`, `partial`, or `unavailable`; never include order capability as a readiness success criterion.

- [ ] **Step 4: Run the readiness tests to verify they pass**

Run: `python -m pytest tests/test_moomoo_readiness.py -q`
Expected: all readiness tests pass with no vendor SDK or network.

- [ ] **Step 5: Commit**

```text
git add src/quantmesh/moomoo/readiness.py src/quantmesh/moomoo/__init__.py tests/test_moomoo_readiness.py docs/superpowers/plans/2026-09-23-moomoo-readiness-probe.md
git commit -m "feat: add read-only Moomoo readiness report"
```

### Task 2: Operator CLI and route evidence

**Files:**
- Modify: `src/quantmesh/moomoo/cli.py`
- Test: `tests/test_moomoo_cli.py`
- Modify: `docs/iterations/0036-staging-recovery.md`
- Modify: `docs/ITERATION_PLAN.md`
- Modify: `docs/goals/ACTIVE.md`

**Interfaces:**
- Consumes: `run_readiness` and the existing `Settings` OpenD endpoint fields.
- Produces: `quantmesh-moomoo readiness [--symbols AAPL,NVDA] [--json]` with exit `0` only when every requested symbol is ready, `1` for route/provider/unavailable or partial status, `2` for authentication required, `3` for missing SDK, and JSON output suitable for an operator evidence file.

- [ ] **Step 1: Write the failing CLI tests**

Add tests that stub the route check and readiness runner, assert the default symbols, JSON fields, exit codes for ready/partial/auth/sdk cases, and confirm no order method is reachable from the command.

- [ ] **Step 2: Run the focused CLI tests to verify they fail**

Run: `python -m pytest tests/test_moomoo_cli.py -q`
Expected: failures because the `readiness` subcommand and route helper do not exist.

- [ ] **Step 3: Implement the CLI minimally**

Add a bounded `socket.create_connection` route check with the configured timeout, invoke the report only after route success, render stable text or JSON with endpoint and per-symbol statuses, close the client in every path, and map typed errors to the documented exits. Do not add order or account operations.

- [ ] **Step 4: Run targeted and full verification**

Run: `python -m pytest tests/test_moomoo_readiness.py tests/test_moomoo_cli.py -q`
Run: `python -m ruff check src/quantmesh/moomoo tests/test_moomoo_readiness.py tests/test_moomoo_cli.py`
Expected: all focused tests pass and Ruff reports no violations.

- [ ] **Step 5: Update evidence and commit**

Record the new local command, its fail-closed semantics, the current AWS-to-Windows OpenD route being closed, and the fact that the 8 GB observation remains a later release gate. Run `git diff --check`, then commit:

```text
git add src/quantmesh/moomoo/cli.py tests/test_moomoo_cli.py docs/iterations/0036-staging-recovery.md docs/ITERATION_PLAN.md docs/goals/ACTIVE.md
git commit -m "feat: expose Moomoo readiness probe"
```

## Completion gate

- [ ] Focused readiness and CLI tests pass.
- [ ] Ruff and `git diff --check` pass.
- [ ] No CI run, push, merge, port opening, deploy, or live-trading change occurs while the user has CI paused and the 8 GB observation gate is open.
- [ ] The next operational step is to run the command on the private AWS path after OpenD is made reachable, then append actual AAPL/NVDA entitlement evidence.
