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

M0-M10 are complete and merged through PRs #65-#71; PR #72 fixed
PYSEC-2026-1845; PR #73 recorded clean-checkout release-candidate
verification. Iteration 0013 Phase A-C are done on
`release/v0.1.0-rc1` (from `origin/main` @ `5708e72`): package
metadata `0.1.0rc1`, the closure-deterministic license gate and
audit-lock contract, the repo golden-path walk and the one-command
clean-checkout release gate — `python tools/release_gate.py`
PASSED on `206fc49` (1801 tests, golden path 53/53, clean clone
proof, temp root removed).

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

1. Open the one RC PR from `release/v0.1.0-rc1` (Phase A-C + release
   notes), wait for CI (release-contract tests on the PR) and the
   Security job (fires on the main push), then squash-merge with the
   standing authority, verify `origin/main` and tag the exact commit
   `v0.1.0-rc1`.
2. Hand the operator the acceptance checklist in
   `docs/release-notes/v0.1.0-rc1.zh-CN.md` (install/start/demo/
   stop-reset/safety/limitations + `python tools/release_gate.py`).
3. After the RC tag is immutable, deepen architecture in this order:
   durable JSONL persistence, cross-venue reconciliation, then
   numeric-policy characterization plus ADR, one short-lived branch
   per slice. Runtime assembly remains secondary.

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
