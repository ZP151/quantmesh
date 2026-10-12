# Research Service Bootstrap Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans or superpowers:subagent-driven-development; preserve ownership, TDD, review and actual verification.

**Goal:** Make the existing independent Research Service executable with explicit private configuration and prove its authenticated HTTP-to-real-PostgreSQL loop on owned local resources.

**Architecture:** This refines the unfinished service startup/deployment preparation in Tasks2/4 of 2026-10-12-research-workers-workstation.md. Reuse create_app/PostgresJobStore and the measured81-wheel Linux environment; no second store, SQLite fallback, new queue or new provider. Default preflight starts no listener/database/model/Worker. Explicit serving constructs the authenticated API on fixed127.0.0.1:8110 with one uvicorn worker and a coordinator-approved build pin. A separate future qualified Worker remains required for report execution.

**Tech Stack:** Existing Python/Pydantic/FastAPI/uvicorn/pg8000 closure; private explicit credential files. No new dependency, global package/daemon, paid host or actual provider.

**Spec:** docs/superpowers/specs/2026-10-12-research-foundation.md; issue#171; implementation scope below does not alter operator A budget/infra approval.

## Global Constraints

- paper=true/live=false; AI remains advisory, no order/account/source/vendor access.
- No server provision/deploy/merge, global config/OS user/package install, Docker/Windows/SSH changes or paid call. No existing DSN/key discovery; do not read ambient secrets or personal credential directories.
- Dedicated runtime configuration is explicit constructor input, never job/request-supplied. Default fixture IDs empty. Existing nine-method JobStore/schema/protocol stay unchanged.
- Two implementation sessions maximum: this bootstrap plus active#169 source witness. Root owns shared app/README/pyproject/ADR/REUSE/ACTIVE/iteration and final integration; child owns only files below.
- Preserve genuine PG qualification at frozen42fbfa5 as historical proof. New service behavior needs fresh own HTTP/SQL proof; do not claim old30tests certify changed code. Do not change the old qualifier's frozen source/count or weaken its admission to reuse it.
- No Linux backtest/Agent process loop until actual aggregate containment/Engine/image admission passes. An API that queues jobs is not completed Linux execution. Missing provider/model remains unavailable; no scripted response masquerades as real AI.

## Review Focus

1. Wrong build/source/runtime must fail before DB creation or binding; config claims alone cannot certify execution identity.
2. Secrets in paths/content/errors/argv/env must not escape; linked/FIFO/device/oversized/world-readable credential files reject with fixed errors.
3. Public/alternate bind, TLS-disabled nonloopback database or request-supplied configuration must not weaken private boundaries.
4. Ambiguous submit/cancel/restart cannot reset the frozen durable job/idempotency/artifact contracts.
5. Local genuine SQL/HTTP proof must not imply worker/model/server/TLS/backup/HA acceptance.

## One independently reviewable slice

Create services/research_agent/src/qm_research_agent/runtime.py,
services/research_agent/src/qm_research_agent/__main__.py,
services/research_agent/tests/test_runtime.py and
docs/runbooks/research-service-bootstrap.md only. Own ignored output/171-service-bootstrap.
Child proposes any shared create_app build-health extension as an exact patch to root, not concurrent edits.

Interfaces:

- ServiceRuntimeConfig: frozen extra-forbid nonsecret object with schema_version1,
  operator_id, expected_build full lowercaseSHA40, owned lake/artifact roots,
  configured_dataset_ids, explicit credential_directory, host literal127.0.0.1,
  port8110. Reject duplicate IDs, invalid identities, relative/link/unsafe roots,
  inconsistent host/port and extra model/order/request configuration. Follow existing
  dataset validators; no fixture auto-discovery or workstation-local fallback.
- load_runtime(config_path: Path) -> configured immutable runtime: bounded explicit
  config input, actual qualified LinuxCPython3.12x86_64 runtime/source admission,
  only named api_token and postgres_dsn in the given owned directory. Linux
  ownership/mode0600, regular-file/no symlink checks before bounded reads,
  fstat/recheck prevent file replacement. Secrets are SecretStr, never repr/JSON.
  No APIkey loading yet. TLS defaults verify-full; sslmode=disable admitted only
  for literal127.0.0.1/::1 own local database; reject ambiguous option duplication.
- build_app(runtime): reuse PostgresJobStore and create_app, configured operator/token/
  dataset IDs. Explicit API start only; no analysis/backtest worker starts here.
  Authenticated /health must exercise real store and expose actual build identity,
  advisory_only plus truthful pending Worker/model capabilities; root integrates
  the minimal constructor/health shared change after receiving proposal/tests.
- python -m qm_research_agent --config OWNED_CONFIG: default redacted preflight,
  nonzero for invalid/unqualified config; no SQL/listener/effects. --serve explicitly
  builds app and runs fixed one-worker loopback uvicorn with access logs disabled,
  no reload/proxy-header trust/endpoint overrides. Errors print fixed categories
  without chained traceback or raw configuration. No secret CLI options/env fallback.

Source admission must measure current repository/actual imports, reject tracked
runtime changes and untracked executable shadow modules, and compare configured
build with actual Git HEAD. It is not a full signed release certificate. Native
proof uses a clean committed candidate on native persistent filesystem, not a
mounted-drive/editable parent. Do not claim a raw configuredSHA is actual build.

- [ ] Write RED runtime tests: fixed bind/runtime/build, unknown/duplicated IDs,
  explicit secret authority/no ambient detection, external/insecure DSN, symlink/
  FIFO/oversize/mode/file replacement refusals, safe repr/errors and default
  preflight has no DB/network/Worker/model calls. Use unique owned --basetemp.
- [ ] Implement minimal config/secret/source admission and CLI, GREEN focused tests,
  Ruff/format/diff. Keep tests meaningful; fixture injected platform does not
  qualify native permissions. Preserve RED/GREEN logs/exits.
- [ ] Propose shared actual-build health extension and tests to root. Wait for
  coordinator integration, then synchronize exact source. Do not edit shared
  store/leases/model limits/source adapters or original gate tests.
- [ ] Run native Linux permissions/preflight checks, using existing audit closure
  read-only only if exact version/import matches. For actual SQL/HTTP, build a NEW
  owned prefix/clean checkout and fresh cluster from already verified PG18.6
  binaries copied/read-only with full rehash; never reuse running/old cluster or
  credentials. No global install. Preserve build-tool/runtime notices; instantiate
  fresh loopback credentials only through0600 temporary input, never argv/logs.
- [ ] Actual bounded test-owned server at8110: unauthenticated401; authenticated
  real-DB health/build identity; configured options; fixture submit/idempotent
  replay/get/cancel survives API process restart with same DB; unavailable DB
  returns503 without leaking DSN. Only fixture jobs, no claimed success without
  executing Worker. Owned PID/start/path/nonce checks before stop; unrelated
  sibling and current vendor/Windows resources untouched. Do not kill DB while
  an actual external service uses it; this cluster must be newly owned.
- [ ] At coherent boundary run all separate-service tests in owned Linux env,
  including real fivePG cases on new cluster: zero skips/errors/failures. Record
  actual new counts rather than assuming30. License/lock/schema/protocol unchanged.
  Avoid entire core/hourly gates; final clean-checkout/full milestone comes later.
- [ ] Fresh Spec/Standards on new bootstrap only, max2rounds; no third original
  service architecture review. Fix RED/GREEN within scope, run fresh native
  final-candidate proof if admitted code changes. Commit/push only owned files.
- [ ] Stop at clean reviewed commit with HANDOFF.md (SHA/files/tests/raw receipts/
  exact invocation/remaining operator deployment and containment gates). Root
  updates shared ledgers, archives evidence and decides integration. No paid
  resource, API key configuration, production deploy or PR merge in child.

Planner: one explicit startup and durable authenticated HTTP/SQL operator loop.
Researcher: fixture workflow only, no algorithm promotion or model effectiveness.
Verifier: real SQL/HTTP receipt independent of mocks; queued/cancelled jobs are
truthful, Linux report execution and real AI pending. This preparation brings the
approved server end state closer but never replaces actual private deployment,
encrypted off-host restore, p95/two-job recovery or human release gates.
