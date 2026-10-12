# Server Market Independence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans or superpowers:subagent-driven-development task-by-task; preserve source safety and operator authentication gates.

**Goal:** Operate registered real-market sources without requiring the personal Windows machine to run OpenD/tunnel.

**Architecture:** Preserve AWS Hyperliquid and Moomoo SDK registrations. Qualify a server-owned official OpenD beside the current private forwarded endpoint, then switch the application only after source/session acceptance. No generic API registry entry can replace the actual authenticated vendor gateway.

**Tech Stack:** Existing AWS Linux/systemd/Tailscale, quote-only moomoo SDK, official vendor OpenD distribution and source-backed observers.

**Spec:** `docs/superpowers/specs/2026-10-12-research-foundation.md`; issue#169 and iteration0038.

## Global Constraints

- Keep paper=true/live=false; do not create/order/unlock trade contexts.
- Preserve Windows GUI/helper/tunnel and installed credential/device files.
- New candidate API port11112 on server loopback; existing forwarded11111 remains intact during qualification.
- Dedicated gateway OS identity, protected vendor state; no credentials in process args, prompts, fixtures or archived logs.
- No public API/control port, automatic latest upgrades or unofficial Docker image.
- Notify operator before new-device login, market-right transfer, charges and final switch. Current A budget does not silently pay for extra Windows cloud or paid data.

## Review Focus

1. Route/SDK readiness with a stopped app collector must not be called healthy ingestion (Task1).
2. A listener owned by tailscaled/SSH must not be classified as native server OpenD (Task1).
3. Concurrent vendor sessions may transfer market authority; stage login with operator before production acceptance (Task2).
4. Credential paths/version mismatch must not leak or trigger blind migration (Task2).
5. Partial bars/closed session/rollback must not be labelled successful real-time acceptance (Task3).

## Task1 — Diagnose actual source and collection independently

Files: create `src/quantmesh/live/session_freshness.py`,
`tests/test_live_session_freshness.py`, `tools/server_market_inventory.py`,
`tests/test_server_market_inventory.py`; modify assigned live feed/API consumers
and tests after reading their existing contracts. Root owns shared workstation
mounts/frontend clients and final UI integration.
Read existing runtime factory/poller implementations discovered with rg; do not
guess or restart production before recording direct cause.

Interfaces: `evaluate_session_freshness(calendar_id: str, policy: SessionPolicy,
now: datetime, last_source_time: datetime | None, interval: str,
provider_delay_seconds: int | None, opening_grace_seconds: int = 120) -> SessionFreshness`.
Typed result includes market_state open/closed/unknown, data_state
fresh/latest_session/delayed/missing/unknown, last_source_at,
expected_last_bar_end, next_open_at, calendar_version and reason. Inject the
existing CalendarService, never hand-roll holiday weekdays. Unknown provider
delay stays unknown rather than silently choosing zero.
`classify_market_path(provider: str, listener_owner: str, upstream_location: str, readiness: str, last_source_time: datetime, session_open: bool) -> dict[str, str]`;
return separate `gateway_location`, `readiness`, `ingestion` and `pc_dependency`.

- [ ] RED test: tailscaled listener + Windows upstream + ready SDK + old source
  in open session returns gateway_location=personal_pc, ingestion=stale,
  pc_dependency=yes; native vendor listener alone is not proof of quote freshness.
  Run `python -m pytest tests/test_server_market_inventory.py -q`.
- [ ] Add RED session cases: weekend/latest-Friday data is latest_session,
  holiday/early-close/DST use pinned calendar, pre-open not failed, closed data
  older than last expected session remains missing coverage, crypto24/7 remains
  delayed by its lag, unknown calendar/latency is unknown, declared15-minute
  delay at Oct12 13:37UTC cannot be treated as a realtime-source failure.
  Run `python -m pytest tests/test_live_session_freshness.py -q`.
- [ ] Implement only typed redacted inventory and offline classification tests.
  Read actual service identity, allowed nonsecret settings and source statuses;
  no vendor XML/logs or raw account environment output.
- [ ] Implement shared session freshness and consume it in diagnostics/live
  status presentation and read-only acceptance helpers. Preserve age/provenance
  and execution fences; closed last-session bars are not current executable
  quotes. Add API regression proving the same policy appears across consumers,
  no per-tool age-only exception. Root integrates typed UI closed-state copy.
- [ ] GREEN same focused tests; actual bounded health/status/readiness evidence
  confirms source topology. Inspect collector lifecycle and allowlisted error
  categories; reproduce a discovered code fault in isolated test before fixing.
  If only process recovery is needed, prepare exact service impact and preserve
  current observations before approved bounded recovery.
- [ ] Commit the diagnostic boundary and distinct route/ingestion conclusions.
  A production repair gets its own bounded RED/GREEN change and applicable review.

## Task2 — Qualify official server gateway and authentication handoff

Files: create `deploy/aws/opend/README.md`, `gateway-profile.json`,
`quantmesh-opend.service`, `tests/test_server_opend_profile.py`.
These are noncredential templates; initial profile never contains actual account
identifier/password/token. Coordinator owns shared deployment settings changes.

Interface: profile specifies pinned vendor version/artifact digest, SDK compatibility,
platform, dedicated identity, loopback11112, owned state path, disabled trade and
approved authentication method. A missing qualified package digest blocks install.

- [ ] RED: profile tests reject public bind, missing digest, executable outside
  dedicated installation, password arguments and inherited Windows device/state.
  Run `python -m pytest tests/test_server_opend_profile.py -q`.
- [ ] Verify official vendor Linux package and compatibility in an isolated
  environment. Official docs support server/command-line deployment; upstream
  agent installer prescribes GUI and is not blindly executed. Choose the
  supported vendor method after package inspection, document any GUI dependency
  and private operator access before installing it on the actual source host.
- [ ] GREEN profile tests and isolated startup proof. Use a private vendor login
  interface operated by the human; do not collect passwords, copy vendor tokens,
  set auto-grab market rights, or use CLI plaintext credential arguments.
- [ ] Present exact source host/resource/digest/private access/permission-transfer
  and rollback steps. Notify operator before login and payment. If Linux
  distribution/auth cannot be qualified, stop live installation and provide a
  separately priced Windows-cloud/vendor alternative; don't claim PC independence.
- [ ] Commit reviewed templates. Install reviewed candidate on a distinct
  server endpoint only after authentication/configuration boundary is accepted.

## Task3 — Server source acceptance and reviewed cutover

Files: create `tools/verify_server_market_source.py`,
`tests/test_server_market_witness.py`; update `docs/runbooks/moomoo-readiness.md`
through coordinator after actual proof. Retain prior source evidence.

Interface: witness records gateway location/process/artifact digest, SDK endpoint,
quote/history status, market session, advancing source times, two actual minute
boundaries, provider-bracket OHLCV, exact application build and safety flags.

- [ ] RED: witness refuses readiness-only, local forwarded gateway, closed
  session, missing sample, mismatched OHLCV or executable identity. Run
  `python -m pytest tests/test_server_market_witness.py -q`.
- [ ] Implement read-only verifier, GREEN focused tests. Against candidate
  loopback11112 verify real current quote/history and vendor metadata; no broker calls.
- [ ] After applicable review and operator source-switch handoff, update the
  exact app endpoint to accepted server gateway. Keep old route as rollback;
  do not terminate it as a test. Source topology/process evidence proves lack
  of PC dependency without manufacturing a Windows outage.
- [ ] In a real open session verify app source progression, minute revisions,
  two appends, supplier OHLCV and browser reload; also Hyperliquid regression.
  Missing permission/authentication remains pending and prompts human action.
- [ ] Record actual server lifecycle/recovery only on owned candidate resources;
  exact deployment/configuration and rollback evidence mirror into iteration.

Sources: [official OpenD command line](https://openapi.moomoo.com/moomoo-api-doc/en/opend/opend-cmd.html),
[official multiple-terminal market rights FAQ](https://openapi.moomoo.com/moomoo-api-doc/en/qa/opend.html).
Time allowance: 2–4 additional working days, human auth wait excluded. Run inside
the same product iteration and two-implementation-session cap; don't start a third writer.
