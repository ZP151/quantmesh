# Server Source Witness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans or superpowers:subagent-driven-development; preserve the two-session cap and operator authentication gates.

**Goal:** Produce a read-only, executable candidate-source witness that cannot mistake a forwarded personal-PC gateway or a readiness response for accepted server market ingestion.

**Architecture:** Refine Task3 of 2026-10-12-server-market-independence.md. Collect native Linux process/socket identity before opening the quote-only SDK, then collect bounded provider/application samples. Distinguish candidate qualification, application evidence and final operator cutover; no saved boolean supplies native identity.

**Tech Stack:** Python standard library Linux procfs, existing pinned Moomoo adapter, typed workspace contracts and XNYS session policy. No new dependencies.

**Spec:** docs/superpowers/specs/2026-10-12-research-foundation.md; issue#169. Existing profile remains blocked and uninstalled.

## Global Constraints

- paper=true/live=false; no trade/account contexts, login, entitlement acquisition or orders.
- Preserve all existing Windows/vendor/SSH resources; no source switching, server installation, process restart, root profile changes or production reads during implementation.
- Current candidate is pinned OpenD10.10.7008/executable SHA e05b901dbe9107061b954a7fe3c059916c4a1e580d8f0a57277d402438898601, dedicated quantmesh-opend identity, loopback11112. Reuse deploy/aws/opend/validate_profile.py without weakening qualification.
- Never read vendor XML/state/logs, process cmdline or environment. Only the separately owned reviewed noncredential configuration is admitted by its existing validator.
- No raw exception, credential or account output; whitelist diagnostics and evidence fields. SDK raw payloads must be reduced to quote/kline lineage fields, never copied wholesale.
- This is test-first preparation, not server independence acceptance. Default invocation with current blocked profile must return pending before network/SDK calls.
- Frozen baseline is the root commit containing this plan. Root owns shared profile, source transport, service wiring, ACTIVE/iteration and final integration.

## Review Focus

1. PID reuse, socket owner changes or disappearance must invalidate the sample.
2. SSH/tailscaled, public/IPv6 listeners and a vendor executable outside the pinned path must not certify native ownership.
3. Closed latest-session data remains normal coverage but cannot pass live revision/two-boundary acceptance; unknown latency/calendar stays unknown.
4. SDK/API hangs and oversized output cannot run indefinitely or disclose vendor messages.
5. A genuine candidate quote witness alone cannot prove application cutover, browser acceptance, lifecycle recovery or personal-PC independence.

## One bounded deliverable

Create tools/verify_server_market_source.py, tests/test_server_market_witness.py and docs/runbooks/server-market-source-witness.md only. Own ignored output/169-server-witness. Do not modify other tracked files; propose shared changes to root if needed.

Interfaces:

- collect_gateway_identity(profile: dict) -> dict: Linux-only native observation. Include boot identity, PID/start ticks, actual UID, resolved executable/digest, exact socket inode and bound endpoint, observed UTC. Read procfs directly; fixture proc readers are injected only for unit tests, never selectable by the operational CLI. Fail closed on incomplete permissions or concurrent identity change. Verify identity again after collection.
- collect_samples(profile: dict, expected_build: str, output: Path) -> dict: first validate qualified profile and machine/process ownership. Use existing MoomooOpenDClient/SdkTransport at11112 and fixed private AWS application origin; no endpoint supplied by fetched content. Six before/application/after samples at35-second spacing, overall owned deadline240seconds. Use an owned child boundary where existing SDK calls may hang; terminate only that newly owned child after verifying identity. No production worker/helper termination.
- evaluate_samples(samples: dict) -> dict: return passed/pending/failed with explicit acceptance phase. Compare canonical raw-US1m provider bars using existing minute_candles adapter, at least four completed OHLCV bars per symbol, same-minute revisions and at least two new boundaries for AAPL/NVDA. Verify exact application build, paper/live flags, private license/local sequence semantics, metrics-only degraded/no bidask/no paper proposal and actual source clocks. Reuse session_freshness, never price-change-only freshness.
- CLI --profile PATH --expected-build SHA40 --output OWNED_DIRECTORY. Runtime accepts only actual native collectors; no saved-input mode silently certifies a new run. Current blocked profile returns nonzero pending with no SDK/network calls. A separate explicitly labelled saved-evidence checker may be added only if needed by tests; it is never native acceptance.

Application origin stays https://quantmesh-staging-8gb.tail99d23c.ts.net. Its endpoint/config cutover provenance and browser/recovery remain coordinator-owned separate receipts: even all provider/application checks passing must say application-source-routing-unverified until that independent proof exists. Never assert PC independence merely because prices match. No extra generic registry or inference of endpoint from readiness.

- [ ] Write RED tests for forwarded/public/wrong UID/path/hash, missing proc proof and PID/socket replacement, including a genuine-looking JSON claim that cannot bypass actual collector admission. Run python -m pytest tests/test_server_market_witness.py -q with a new workspace-owned --basetemp; preserve RED log/exit.
- [ ] Add RED behavior tests: current profile blocks before SDK/API calls; closed latest-session returns pending_live_acceptance; future/missing/unknown source clocks cannot pass; mismatched provider OHLCV, readiness-only and missing revision/two boundaries fail. Add exact build/safety/metrics/private lineage refusals and bounded timeout/output tests.
- [ ] Implement minimal real collectors and evaluation, using existing adapter/policy. No vendor or upstream source copying. Run the same focused tests GREEN, Ruff and git diff --check. Preserve logs, exit codes and actual invocation of blocked profile; that invocation is an intentional pending result, never a pass.
- [ ] Run related profile/session/adapter/workspace regression tests discovered from actual repository names, once at coherent boundary. No full local core suite or repeated historical CI. Commit tested files and retain candidate SHA in handoff.
- [ ] Fresh Spec and Standards review of this new verifier only, max2rounds. Retain fixes/RED/GREEN and final proof. Do not re-review completed Task1/Task2/service/worker architecture.
- [ ] Stop at clean reviewed commit with HANDOFF.md: exact changed files, counts/exits, acceptance scope, operational invocation and remaining actual host/login/cutover/browser gates. Do not merge, deploy, modify shared ledgers or request operator credentials.

Planner: one source witness, no new market feature. Quant researcher: use real session/time ordering, raw US1m normalization and supplier brackets; no returns/strategy effectiveness claim. Reviewer: process authority, auth/trading boundary, incomplete evidence labels. Verifier: test counts support software only; actual authenticated host and open-session/browser evidence remain mandatory.
