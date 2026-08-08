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
- Blockers: none external; the current ambient `.venv` license inventory drift
  is an actionable RC gate recorded in iteration 0013

## Current state

M0-M10 are complete and merged through PRs #65-#71. PR #72 fixed
PYSEC-2026-1845, and PR #73 recorded clean-checkout release-candidate
verification. The repository review reconciled CONTEXT.md, ROADMAP.md, the
iteration index and iterations 0006-0012 with that merged reality and opened
iteration 0013 as the release frontier.

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

1. Complete release metadata and dependency-security contract work in
   iteration 0013 Phase B, including deterministic handling of the current
   `license-expression`/`boolean.py` ambient-environment drift.
2. Build the clean-checkout, one-command release verification path and ensure
   it leaves no generated `golden-root/` in the checkout.
3. Produce release notes, installation/start/stop/reset instructions and a
   short English/Chinese acceptance checklist.
4. Merge one coherent RC PR after CI, Security and fresh-clone verification;
   tag the verified main commit `v0.1.0-rc1` and hand it to the operator.
5. After the RC is available, deepen architecture in this order: durable JSONL
   persistence, cross-venue reconciliation, then numeric-policy
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
