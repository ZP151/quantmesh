# Collector provider binding and GO cadence implementation plan

> For agentic workers: execute the one bounded task with TDD, independent two-axis review and verification. Root owns review/integration/operations; no delegated host or SDK authority.

**Goal:** fixed recovery capture can verify its supplied attributed provider before GO while preserving the original five-second sample schedule.
**Architecture:** reuse ProviderExecution/OperatorReader and the unchanged RoleGrowth algorithm; add only recovery binding plumbing, RestoredRoleGrowth and immediate namespace verification.
**Tech Stack:** existing Python stdlib and pytest; no dependency/environment or upstream code copying.
**Spec:** docs/superpowers/specs/2026-11-05-ivv-collector-provider-go.md

- [x] Create isolated codex/0038-collector-provider-go from actual origin/main f5998dd7; preserve sparse patterns and all frozen/history bytes.
- [x] Rebase tests/test_ivv_collector_namespace.py to v2 data and two legitimate instances. Run Python313 -I -B -Xutf8 pytest with plugin/cache off; RED confirms absent binding/growth support. Preserve RED.log under server/collector-successor-02.
- [x] Change only tools/research/ivv_trusted_runner.py binding/_Provider/READY/peer and tools/research/ivv_dev_native.py role selector. No Operator source edits. Verify real supervisor positiveGO and negative namespace/device/substitution/drift/close/deadline paths.
- [x] Run affected provider/supervisor/growth/Operator suites; broad Ruff src/tests/tools, changed format, diff--check, submodule status and available bare pytest collection. Record concrete sparse/Windows limitations without unrelated fixes.
- [x] RAM measure real builder with actualv2receipt/P24/all7source roles and final Root operations successor; verify decoder/framing/input caps without creating a package/nonce/grant. Freeze complete all-retained capacity, canonical source pins and exact commands.
- [x] Make one coherent green commit with iteration/roadmap/goal evidence; freeze HANDOFF/PINS. Stop without push/PR/CI/merge/publication/host/UI/vault/SDK effects.

Quant role: no source data, leakage, costs, mathematical definitions, selections or confidence semantics change; financialINSUFFICIENT and livefalse remain. Review must inspect strict source/receipt validation, actual GO path and no sampling-state mutation. No third review of the stopped combined candidate. Final release repeats merged-source geometry, immutable binding/current cohort and original input gates under Root authority.
