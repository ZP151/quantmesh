# Server market source witness

This read-only candidate tool belongs to iteration0038 / issue#169 and
`docs/superpowers/plans/2026-10-13-server-source-witness.md`. It neither installs
OpenD nor authenticates, acquires market rights, changes endpoints or restarts
services. Paper mode must be true and live trading false.

The committed profile is **blocked**. Its normal invocation returns exit2,
`status=pending`, `phase=candidate_qualification`, `reason=profile_blocked`,
before proc inspection, SDK calls or application requests. This result proves
refusal behavior only. It is not server-source acceptance.

## Invocation

Use the reviewed checkout and its already admitted Python environment. Do not
install packages as part of this command. From the repository root:

```bash
python -m tools.verify_server_market_source \
  --profile deploy/aws/opend/gateway-profile.json \
  --expected-build <exact-40-character-lowercase-application-commit> \
  --output output/169-server-witness/<new-run-directory>
```

The output directory must be new. Existing evidence is never overwritten.
Exit1 means failed/invalid evidence or invocation; exit2 means pending.
The tool currently cannot return operational exit0: even complete provider/app
evidence retains `application-source-routing-unverified`. There is no saved-JSON
CLI mode, endpoint override, repair command or operational fixture collector.

For a future qualified run, the coordinator must first obtain actual host,
authentication, rights, wire compatibility and reviewed configuration approval.
Use the pinned10.10.7008 profile and existing validator unchanged. The dedicated
`quantmesh-opend` process must own127.0.0.1:11112 and run the exact pinned
`/opt/quantmesh/opend/10.10.7008/OpenD` bytes. The reader needs complete Linux
procfs visibility and Linux kernel/Python pidfd support; unreadable
processes/fds or unavailable owned-process handles cause refusal. The tool does not
grant privileges or change permissions. Native identity belongs to the Linux
network namespace where the tool runs; the coordinator must establish that
this is the intended source host, not an unrelated namespace or fixture.

## Collected evidence

Before opening the quote-only client, actual procfs observations establish boot
ID, PID/start ticks, all four UIDs, running executable path/digest, socket inode
and endpoint. Two complete observations must agree. Every source/app bracket
has identity checks before and after. SSH/tailscaled listeners, public/IPv6
listeners on11112, shared socket owners, wrong UID/path/hash, disappearance and
identity replacement invalidate the run. A supplied profile or JSON claiming
native ownership cannot supply those observations.

Six brackets are scheduled35seconds apart within a240second collection budget.
Each newly owned child has at most30seconds for synchronous SDK/API work; its
output is capped at2MiB. Reviewed configuration/proc scans/hashes also run in
owned children, each capped at15seconds within the same overall budget. Fixed
configuration reads reject symlinks, nonregular files (including FIFOs) and
oversize content before reading. Three seconds are reserved for bounded cleanup.
Only the owned child can be killed: Linux pidfds hold kernel process identity
and start ticks are checked again. An identity-read error cannot leave a child
running or send a signal to a reused PID. Admission waits for the parent to
obtain that handle; unavailable handles prevent SDK work. SDK output/tracebacks
are suppressed; raw errors are never
archived. The tool touches no Windows GUI/helper/tunnel or production worker.

Provider reads use existing `MoomooOpenDClient`/`SdkTransport` on11112:
`stock_quote` and subscribed raw regular US1m `current_kline`, scoped to
AAPL/NVDA. No general capability probe, trade context, account query, unlock or
order call is used. Raw SDK rows are reduced to quote source clocks and allowed
kline identity/OHLCV fields, using the existing minute-candle adapter.

The application origin is fixed to
`https://quantmesh-staging-8gb.tail99d23c.ts.net`. Requests use HTTPS, disabled
ambient proxies, no redirects and a fixed market-only GET allowlist:

- `/api/health`: exact staging build, live observation runtime, paper/live flags.
- `/api/live/state`: AAPL/NVDA metrics source clocks, declared delay and absent
  quote/depth. Transport unavailability remains a refusal.
- `/api/instruments/moomoo/{AAPL,NVDA}/history?range=1d`: typed historical
  series, private license, unadjusted XNYS1m bars and local-observation lineage.

No account/positions/orders/workspace endpoint is read. The existing workspace
response includes an account view, which is outside this task's prohibition on
account reads. Therefore actual workspace degradation and Paper-proposal
refusal are **not certified** by this tool: the archived metrics projection
records `proposal_allowed=null`, and summary `proposal_gate=unverified` remains.
The coordinator owns the actual browser/workspace receipt, or a separately
reviewed market-only projection of that gate. The tool never creates a paper
proposal to test refusal. This is a deliberate scope ruling, not an inferred
proof that missing depth guarantees every application action is disabled.

## Interpretation

The evaluator requires six timed brackets for both symbols. At least four
completed application OHLCV bars per symbol must match both supplier reads;
partial values must be observed in a supplier bracket. Open-session evidence
also requires actual source-time progression, same-minute OHLCV revisions,
at least two adjacent new minute boundaries and advancing local sequences.
Prices alone, readiness, recent receipt clocks and saved booleans never prove
freshness or personal-PC independence.

Shared `session_freshness` and the pinned XNYS calendar decide coverage.
Latest closed-session coverage is normal: `coverage=latest_session` with
`reason=pending_live_acceptance`. It does not pass the live revisions/boundaries
gate. Unknown source clocks/calendar/provider latency remain unresolved; no
zero-delay assumption or weekday heuristic is introduced. Missing/delayed
coverage, future clocks, inconsistent build/safety/lineage and supplier
disagreement fail closed. An unchanged price with advancing real timestamps
is valid; a changed price without source timestamps is not freshness evidence.

`provider_application=passed` describes only the bounded evidence comparison.
The overall status remains pending. `native_candidate=observed` is a native
process observation in this run, not authenticated vendor-session, intended
host or application-route proof. `pc_independence`, `application_source_routing`,
`proposal_gate`, `browser` and `recovery` remain unverified. They cannot be
overridden by fields in saved samples. The coordinator must separately prove
exact app endpoint/config cutover provenance, actual browser paths/reload,
source-host lifecycle/recovery and lack of PC dependency while preserving the
old source as rollback.

## Local verification and handoff

Only offline fixtures and newly owned test processes run during implementation:

```bash
python -m pytest tests/test_server_market_witness.py -q \
  --basetemp output/169-server-witness/<new-test-directory>
ruff check tools/verify_server_market_source.py tests/test_server_market_witness.py
ruff format --check tools/verify_server_market_source.py tests/test_server_market_witness.py
git diff --check
```

RED/GREEN, related regression, blocked invocation and `HANDOFF.md` live under
the implementation worktree's ignored `output/169-server-witness/`. They are
software evidence. No AWS/vendor request, installation, login, paid operation,
source switch, shared-profile edit or production acceptance accompanies them.
