# Active Goal

- Status: active
- Objective: publish a reproducible `v0.1.0-rc1` for local operator
  acceptance, then harden the highest-leverage pre-live architecture modules
  without widening product scope
- Started: 2026-08-08
- Active iteration:
  `docs/iterations/0013-v0.1.0-rc1-and-architecture-hardening.md`
- Branch: `main` at the starting checkpoint; new work must branch from
  `origin/main`
- Pull request: none at the starting checkpoint
- GitHub frontier: zero open issues and zero open pull requests at the
  starting checkpoint
- Blockers: none external; iteration 0013 Phase B resolved the ambient
  `.venv` license drift with the deterministic release-closure contract
  (ambient environments now fail the gate with a precise message)

## Current state

**v0.1.0-rc1 is published.** Iteration 0013 Phases A-D done on
`release/v0.1.0-rc1`; PR #74 (the one RC PR) CI green on `0eb1c6e`
and squash-merged to `main` @ `fb37fcd`; the Security job is green
on the merged main; tag `v0.1.0-rc1` points at the exact verified
commit `fb37fcd` and is pushed. Operator acceptance checklist
delivered in `docs/release-notes/v0.1.0-rc1.zh-CN.md`; gate evidence
in `docs/release-notes/v0.1.0-rc1.md` (1801 tests, golden path
53/53, pip-audit clean, clean clone proof on `206fc49`).

The product is a fixture-verified local workstation. It includes normalized
market data and a local lake, reproducible research and forecasts, paper
execution, Moomoo and Hyperliquid adapters, prediction-market intelligence,
local AI research, portfolio/risk controls, a frontend workstation, recovery,
audit and guarded enablement. No external live operation is enabled.

## Last verified baseline

- Fresh clone of main at `e259341`.
- `pip install -e ".[dev,research,e2e]"`: passed.
- Full suite: 1,790 passed, 0 failed, 0 skipped in 385 seconds.
- Workstation/E2E/ingestion rerun: 135 passed.
- Golden path: 51/51 passed, including fixture ingestion, lake manifests,
  research/forecast artifacts, internal paper execution, all 13 workstation
  screens over loopback, restart recovery and audit-ledger rereads.
- License review and Ruff: passed.
- CI and Security: green after the dependency advisory fix.

## Immediate frontier

1. Operator acceptance of `v0.1.0-rc1` per the zh-CN checklist; on
   acceptance promote metadata/tag to `v0.1.0`, otherwise record
   defects for a later RC.
2. Phase E in the documented order, one short-lived branch per slice
   (current branch: `0013-phase-e-jsonl`): durable JSONL persistence,
   then cross-venue reconciliation, then numeric-policy
   characterization plus ADR. Runtime assembly remains secondary.

## External gates

Moomoo OpenD simulated-account and Hyperliquid testnet drills remain optional
operator-dependent validation. They do not block the local fixture-verified
RC and do not authorize mainnet/live operation.

Real-money trading, mainnet wallet signing, live broker orders, credentials,
paid infrastructure and AI order authority require explicit human approval.
Do not create, request, store or use any such authority while pursuing this
goal.

## Resume instruction

Run `/goal` with the long-running command supplied for iteration 0013. Read
this file, the active iteration and `git status` first. Prioritize getting the
RC into the operator's hands; do not let post-RC refactors delay publishing a
green, reproducible candidate. Record implementation detail and checkpoint
evidence in iteration 0013 and keep this file limited to the current frontier.
