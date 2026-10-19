# QuantMesh Reuse Matrix

## Guarded local paper controls P3 — issue196, 2026-10-20

P3 reuses PaperAccountStore/File, existing journal reconstruction, PaperAccount
risk/matching and the current demo/order/kill-switch flow. The transaction callback
is optional and bound only by explicit synthetic rehearsal configuration. Audit
persistence and OS leases follow existing repository disciplines; no third-party
source or dependency is introduced. Live ApprovalLedger is not reused as paper
resume authority. See [ADR0033](adr/0033-local-paper-control-preflight.md).

## Local frozen-experiment inspection P2 — issue191, 2026-10-19

P2 reuses ObjectStore/ObjectRef and the public verified P1 SnapshotCatalog behind
a narrow inspection adapter. It introduces no dependency or executable upstream
source. Original historical Python source is preserved only as inert package
evidence, never imported or executed. The forecast ExperimentRegistry is not
reused because its forecast-error semantics differ. Raw source bytes stay local;
rights/PIT gaps and existing vn.py external-runtime redistribution limits remain
unchanged. See [ADR0031](adr/0031-frozen-experiment-inspection.md).

## Local SPY snapshot qualification P1 — issue184, 2026-10-19

P1 reuses the repository's ObjectStore/ObjectRef and pinned CalendarService
behind a narrow local historical-snapshot adapter. It adds no packages and copies
no upstream engine or strategy source. The existing externally installed vn.py
runtime and its redistribution limits remain governed by ADR0029. Raw source
market data stays local; public endpoint access is not verified entitlement.
The initial snapshot retains unknown rights/PIT and an unresolved issuer/Yahoo
dividend conflict. See [ADR0030](adr/0030-local-snapshot-qualification.md) and the
[P1 iteration checkpoint](iterations/0038-realdata-workstation-p1.md).

## Merged owner correction; approved live-policy FD leaf (2026-10-17 Singapore)

This checkpoint supersedes the historical owner-correction status below.
PR178, PR179 and PR180 are merged; do not repeat their CI or human approval.
PR180 merged as 6aa231315cf710bfed287337c4a08977665d3731 with complete tree
83531328bfe5cb7d5494e0fa98f473d17d5583af independently matched. Its native
UID10001 snapshot-owner checks pass, including refusal of foreign/root owners.
Merged source, the existing 81-package runtime and source image
5af1ece66f2d4b33f690639cf0f9657adb627c08451438ab21eab4722d1cfd50 are prepared.
The default Worker CLI passes; full live admission still fails when the Worker
opens kernel raw_data with EACCES. These are separate acceptance results.

The operator explicitly approved the bounded live-policy FD design and its
implementation through call_6ab1860457684097b71f21d845eb8ba3. A new branch from
merged 6aa, codex/0038-worker-live-policy-fd, now carries the specification and
plan in docs/superpowers/{specs,plans}/2026-10-17-worker-live-policy-fd.md.
The source/test leaf is implemented and passed two bounded software review
rounds. The first round's R1/R2 test gaps were corrected with runtime bytes frozen;
four isolated mutants each fail at the intended guard, with actual pytest import
path/SHA checked. Final evidence is 18 kernel tests and 94 affected tests passed.
Root independently checked raw evidence, exact source/test hashes, full Ruff,
changed-file formatting, whitespace and submodule pins. The full-format probe
also found 199 unchanged files with zero overlap; that failure is preserved.
The initial real EACCES RED and all exploratory failures remain under
output/0038-kernel-policy-live-fd-fix/; independent review and root receipts are
under output/0038-kernel-policy-live-fd-integration/.

The next gate is new exact-head CI, followed by new Class C two-human merge
approval including SafetyOwner. Design approval does not approve the future
code merge. Earlier operational approvals remain consumed and must not be
requested again. No unmerged source has been deployed.

Only EACCES while opening the fixed held revision's raw_data may use FD3 after
root-owned regular-file, read-only, non-O_PATH and full live-inode checks before
and after bounded positional reads. Preserve all 22 pins, public interfaces,
revision checks, host permissions and capabilities. Native proof observed two
threads with 16 total reads of 62633 bytes at the same digest and offset zero;
virtual stat size zero is not the payload length. That temporary profile was
removed; future native acceptance needs a fresh profile/revision after merge.

Private API remains e2/UID10001/PID99929 and PostgreSQL PID93089 at their last
actual observation. Permanent Worker and advisory are not installed; provider
usage remains zero. Existing pinned pg_dump and host TLS libpq passed a native
loader/version/TLS-attribute preflight without SQL, capture or restore.
Full Option A still requires permanent Worker/recovery, production encrypted
backup/restore, advisory and server OpenD acceptance. No dependencies, new
environment or paid resources were added. Last observed parent usage is
990934679B against 1GB, whole1916303587B against 5GB, free158560460800B; every
future stage needs a fresh forecast and must retain all prior failures.

## Approved private identity cutover; snapshot owner correction (2026-10-16 Singapore)

PR178 and PR179 are merged, with complete candidate/merge trees checked. The
bounded vn.py synthetic Windows product slice is complete; its accepted Windows
full-suite limitation and external runtime redistribution restriction remain.
Do not repeat their CI, review, source staging or earlier native qualifications.

The operator explicitly approved the dedicated locked/nologin qm-research
UID/GID10001, service-only Worker Docker group access, private shared roots and
controlled private API e2 cutover. Actual systemd namespace preflights pass as
10001 with zero capabilities and NNP: source, existing81-wheel runtime and config
are read-only; only the fixture is writable; private home paths are hidden. The
API has no Docker group and its access is denied. The Worker-only probe has
groups988/10001 and reaches the existing Engine without sudo Docker or socket/
host group changes. No dependency, environment or paid resource was added.

Fresh read-only RR counts before and after stopping the old API confirm zero
jobs/outbox/model effects/reservations and empty old lake/artifact roots. The
private API now runs e2a69c5 as10001, authenticated health200/unauthenticated401,
PID99929 and unit SHA2151e9464c087d5d3b3b38ccf6e5a98b35389d7e2c1220fb182f7b35c9f7aaaf.
Actual API512MiB/high384/swap0/CPU50/PID128 controls pass. PostgreSQL remains on
its original identity/unit/data and PID93089; the original d90 API unit/config
remain available for rollback. Existing trading app, Windows/tunnel and model
key/provider are untouched. This is API identity/cutover acceptance only.

An exact e2 source-only image is prepared at
sha256:1be6769b0b97c5a10303e6fdddc2deff5b057bcaf6caf72c08857daaf4ab8d17,
with194files/2804327bytes; its preparation container is removed. The first
attempt refused before container creation because its old harness expected5
images rather than the freshly observed10. That failure is preserved; a new
attempt nonce corrects only the count after checking the exact Engine/base.
The successful phase leaves parent935255635B<1GB, whole1860624543B<5GB and
free158636118016B>50GB. This image is not admitted as a numerical Worker.

An actual native helper probe under10001 identifies a product blocker in
merged e2: seven private-snapshot owner checks assume1000 and reject the
service's own10001-owned0400 single-link metadata. The narrow correction now
derives a matching positive real/effective POSIX process UID internally and
uses it at all seven checks. Root, mixed UID, unavailable identity and foreign
owners fail closed;22pins, modes, FD/no-follow and held/named identity checks,
kernel root ownership and image child10001 remain fixed. No public UID override
or configuration field is added. This unmerged correction is not deployed.

Issue170 software evidence on base5661033c: initial owner regressions fail
7/9 against old source; final WSL owner tests8pass/20deselected and complete
admission file28pass. A consistent simulated UID10001 positive reaches every
changed comparison; seven isolated one-comparison reversions all fail that
test. This is software simulation, not post-fix native qualification. First
review found only test coverage/root-baseline gaps; bounded test-only changes
closed them and round2 passes with no remaining actionable findings. Full
src/tests/tools Ruff, affected-file format, whitespace and submodule metadata
checks pass; the existing NumPy deprecation warning remains. Windows full-suite
and new exact-head required CI are not claimed. Evidence is retained under
output/0038-snapshot-owner-fix/, including both review rounds and failed runs.
The tracked plan is docs/superpowers/plans/2026-10-16-worker-snapshot-owner.md.
Normal merge/deployment still require exact-head CI and Class C approval by
two independent humans including Safety Owner. Prior operational/code approvals
do not certify the new diff. No third structural review or old validation rerun.

Separately, an actual10001 namespace probe reads only the two exact live OCI
blobs through read-only binds while host containerd remains0700. No host ACL,
mode or capability expansion is used. Permanent Worker remains uninstalled;
all22-pin native admission, two-job/cancel/reclaim/report recovery, production
backup/restore, real advisory and server OpenD acceptance remain open. Full
Option A remains active; provider calls remain zero and168h is NOT_REQUIRED.

Evidence: output/0038-pr178-merged-deployment/identity-api-cutover-root-checked.json;
worker-image-owner-red-root-checked.json in the same directory. All first
attempt failures and previous qualification artifacts are retained.

This document records which open-source projects are reused, why they are used, and how much adaptation is expected.

| Component | Upstream | Role | Integration mode | Expected change | License note |
| --- | --- | --- | --- | --- | --- |
| Experimental official-strategy fixture | `vnpy/vnpy`4.5.0, `vnpy/vnpy_ctastrategy`1.4.1, `vnpy/vnpy_sqlite`1.1.3 | Fixed synthetic DoubleMA/AtrRSI product workflow, issue177 / merged PR179 / ADR0029 | Explicit Windows external-process adapter, unchanged official imports, separate API/report, default API disabled | QuantMesh adapter/UI and generated SPA only; no core lock or runtime redistribution | MIT upstream notices/source pins retained externally; full Qt/PySide/shiboken/LGPL and transitive release closure not admitted; isolation does not authorize redistribution |
| Research platform | `microsoft/qlib` | Factor research, datasets, ML workflow, backtesting | Git submodule/reference implementation | Medium | MIT; preserve notices |
| Vectorized research | `polakowo/vectorbt` | Pattern/reference for parameter sweeps | Excluded from runtime | None | Apache-2.0 with Commons Clause; refused by the release-license policy |
| Probabilistic forecasting candidate | `unit8co/darts` | Statistical/ML forecasts, historical backtests and quantile paths | Isolated spike, then optional adapter | Medium | Apache-2.0; review its full dependency closure before admission |
| RL research | `AI4Finance-Foundation/FinRL` | PPO/SAC/TD3 experiments after baselines | Optional reference dependency | Medium | MIT; research use only until validated |
| Integrated research-engine candidate | `AI4Finance-Foundation/FinRL-Trading` (FinRL-X) | Coherent data, selection, allocation, timing, risk, backtest and paper workflow | Evaluated in isolated tooling; rejected from runtime by ADR-0015 after the pinned Windows run failed before verified outputs | None in runtime | Apache-2.0 upstream; no package or transitive dependency enters the release closure |
| Stock broker | `MoomooOpen/py-moomoo-api` / candidate `moomoo-api==10.10.7008` | Moomoo OpenAPI quote/read-only corporate-action transport | Audit submodule; compatible package pending closure admission | Medium | Apache-2.0; the 10.02 audit snapshot lacks the 10.10 split/dividend methods; Task 6 must pin and audit the complete 10.10 optional closure before installation |
| Crypto venue | `hyperliquid-dex/hyperliquid-python-sdk` | Hyperliquid REST, WebSocket and signed actions | Git submodule/package | Light | MIT; never expose private keys to AI |
| Prediction market | `Polymarket/py-clob-client-v2` | Polymarket CLOB client | Git submodule/package | Light to medium | MIT; use the current v2 client, not the archived legacy client |
| Market-data platform | `OpenBB-finance/OpenBB` | Provider registry, research data routing, AI/data-server patterns | Architecture reference only | None | AGPLv3; do not copy into or link with the permissive runtime |
| Public equity data candidate | `ranaroussi/yfinance` | Replaceable personal-research history adapter | Optional provider adapter | Light | Apache-2.0 code; Yahoo data terms and upstream stability reviewed separately |
| Public China-market data candidate | `akfamily/akshare` | Replaceable A/H/US-market research adapter | Optional provider adapter | Light to medium | MIT code; academic-use statement and upstream source terms apply |
| Market calendar | `gerrymanoim/exchange_calendars` 4.13.2 | Versioned XNYS sessions, holidays, early closes and DST | Exact runtime package behind `CalendarService` | Light | Apache-2.0; transitive closure is permissive and pinned |
| Crypto data gateway candidate | `ccxt/ccxt` | Normalized read-only public data across many exchanges | Optional provider adapter | Medium | MIT; private/trading APIs remain out of scope without separate approval |
| Crypto bot | `hummingbot/hummingbot` | Connector contracts, order tracking, market-data streams, Hyperliquid connector | Reference submodule; selectively port patterns | Medium | Apache-2.0 |
| Crypto bot | `freqtrade/freqtrade` | Dry-run, strategy lifecycle, persistence, backtesting and risk controls | Reference submodule or separate companion process | Medium | GPL-3.0; do not copy code into a permissively licensed core without a license decision |
| Quant trading framework | `vnpy/vnpy` | Gateway/app separation, CTA, portfolio, spread and ML research modules | Reference submodule; selectively port patterns | Medium | MIT |
| LLM trading research | `TauricResearch/TradingAgents` | Analyst/researcher/risk/portfolio agent workflow and persistent decision logs | Optional research submodule; adapter around QuantMesh signals | Medium | Apache-2.0; treat output as research, not execution authority |
| Execution engine candidate | `QuantConnect/Lean` | Event-driven simulation and future live execution | Deferred reference | Medium to high | Apache-2.0 |
| Execution engine comparator | `nautechsystems/nautilus_trader` | Deterministic multi-venue research/backtest/sandbox/live semantics; official Hyperliquid, Polymarket and IB adapters | Evaluated isolated tooling and retained only as a removable process-isolated comparator by ADR-0015 | None in runtime; high isolated cost | LGPL-3.0; never part of the release closure or execution authority |
| UI component source | `shadcn-ui/ui` | Accessible React primitives owned and themed by QuantMesh | CLI-copy selected components; never copy the full repository | Medium | MIT; preserve generated component notices where supplied |
| Data grid candidate | `TanStack/table` | Dense positions, orders, instruments and audit tables | Package behind QuantMesh table components | Light to medium | MIT; verify selected release during ADR spike |
| Market chart | `tradingview/lightweight-charts` 5.2.0 | Candlestick, comparison and forecast-boundary market views | Exact npm package behind the single `InstrumentChart` adapter | Light | Apache-2.0; package has no separate NOTICE; built-in attribution logo and user-visible TradingView link retained |
| Analytics chart candidate | `apache/echarts` | P&L, exposure, calibration and scenario visualizations | Package behind a chart adapter | Light to medium | Apache-2.0; preserve notice |
| Frontend design skill | `Leonxlnx/taste-skill` @ `e988add20dab0fa97d7a76781c48961c8184288e` | Anti-template design and design-system selection | Project-scoped Codex/Claude skill; advisory outside dashboards | None | MIT; license preserved under `docs/third-party/` |
| Product UI skill | `pbakaus/impeccable` @ `aee6ce9352b842217b3f57c78296a7a4fa35a7f3` | Product context, UX shaping and bounded visual QA | Project-scoped Codex/Claude skill | None | Apache-2.0; upstream notice preserved under `docs/third-party/` |
| Frontend test runner | `vitest` 3.2.x | Unit/component test runner for the React SPA (Phase E) | Dev dependency behind `npx vitest run` | Light | MIT |
| Browser DOM for tests | `jsdom` 26.x | jsdom environment for component tests (Phase E) | Dev dependency (Vitest `environment: "jsdom"`) | None | MIT |
| React testing library | `@testing-library/react`, `@testing-library/jest-dom`, `@testing-library/user-event` (16/6/14) | Component queries, matchers and user-event simulation | Dev dependencies; the E2E surface stays Playwright | Light | MIT (all three) |
| Frontend linter | `oxlint` 1.x | Fast lint pass for the SPA source | Dev dependency behind `npm run lint` | Light | MIT |
| OpenAPI type generator | `openapi-typescript` 7.13.0 | Generate the committed workstation contract from FastAPI OpenAPI | Exact dev dependency behind deterministic `generate:api` / `check:api` scripts | Light | MIT; frontend lock closure is 646 packages and offline-allowlisted |
| Typed OpenAPI transport | `openapi-fetch` 0.17.0 | Execute the generated Task 6 history path without handwritten URL or DTO shapes | Exact runtime dependency behind `api.history` | Light | MIT |
| Private host network | `tailscale/tailscale` stable client + Tailscale Serve | Tailnet-only HTTPS proxy to the loopback staging workstation | Host-managed external service; no Python/frontend dependency and no Funnel | None in application | BSD-3-Clause client; hosted-service terms apply separately |
| Linux Worker containment candidate | `docker/cli` with an operator-managed local OCI Engine | Per-attempt cgroup/namespace controls behind `LinuxOwnedProcess` | External CLI adapter only; no copied upstream code, package, image or daemon admitted yet | None in core closure | CLI [Apache-2.0](https://github.com/docker/cli/blob/master/LICENSE); exact Engine/image/OS rights and native capability qualification remain deployment gates; Desktop is not bundled |
| Owned database fixture | PostgreSQL18.6 official source | Genuine disposable local service/store acceptance | Privately built external test server only; no source/binary embedding or system install | None in application closure | Permissive PostgreSQL license/COPYRIGHT preserved with SHA-pinned source; separately extracted Bison/Flex/m4 build tools retain notices outside runtime; TLS/HA/backup production qualification remains open |
| PostgreSQL Python driver | `tlocke/pg8000` 1.31.5 | Existing PostgreSQL research job store | Synchronous DB-API adapter behind `PostgresJobStore`; no upstream source copied | BSD-3-Clause; LGPL packages remain classified but are not admitted to this runtime | PyPI wheel SHA256 `0af2c1926b153307639868d2ee5cef6cd3a7d07448e12736989b10e1d491e201`; preserve BSD notice |
| Off-host backup candidate | `restic/restic`0.19.1 | Encrypted removable research DB/artifact backup | Actual external CLI audited and qualified on owned local PG/report fixtures; no core dependency, copied upstream code/binary or production/off-host install | None in application closure | [BSD-2-Clause](https://github.com/restic/restic/blob/v0.19.1/LICENSE); signatures,79 Go modules/98 notices verified, Apache/MIT/BSD and unmodified MPL source retained externally. Local recovery proof does not admit production/off-host use |
| Private terminal backend candidate | `tmux/tmux`3.4-1ubuntu0.1 / signed Ubuntu amd64 package | Server-owned private OpenD operator terminal that can outlive a creation client | External removable CLI audited on20 packages/17 sources/27 ELF; owned local detached-creation lifetime/cleanup proof accepted, no core dependency or host install | None in application closure | ISC/BSD/MIT tmux notices and unmodified external LGPL OS/helper source/notices retained; exact signed snapshot supports reproducibility, not current security suitability. Actual target closure/systemd/human terminal qualification remains open |

## Selection rule

QuantMesh owns the normalized domain models, connector contracts, risk engine, orchestration, audit trail and product UI. Upstream projects remain isolated behind adapters whenever possible.

For the RC2 frontend, “reuse shadcn/ui” means copying selected components with
the official CLI and then owning their source and visual treatment. It does not
mean forking the full showcase application or shipping its default theme.

## Similar-project lessons

- FinRL-X demonstrates a weight-centric pipeline spanning data, selection,
  allocation, timing, risk, backtest and paper execution. Its pinned Windows
  bake-off failed at the `bt`/MSVC build before verified outputs, so ADR-0015
  rejects runtime adoption and QuantMesh proceeds with its native contracts.
- NautilusTrader demonstrates consistent event semantics from research through
  sandbox/live and already exposes relevant multi-venue adapters. Its pinned
  deterministic replay still mismatched QuantMesh account contracts and lacked
  a standalone offline sandbox path, so it remains removable isolated tooling,
  not an approved runtime dependency.
- OpenBB demonstrates a provider-registry and “connect once, consume everywhere” data layer. QuantMesh should borrow the provider contract, not the full AGPL application surface.
- Hummingbot demonstrates that a strategy should not know exchange-specific REST/WebSocket details. QuantMesh keeps this separation through `MarketConnector` and `ExecutionConnector`.
- Freqtrade demonstrates a practical dry-run promotion path, SQLite persistence, strategy file loading and explicit risk controls. These are high-value product patterns for the first paper-trading release.
- VeighNa/vn.py demonstrates a gateway/app split and reusable CTA, portfolio, spread and algorithmic-trading modules. Its `vnpy.alpha` module is also a useful reference for dataset/model/lab separation.
- TradingAgents demonstrates structured analyst, trader, risk and portfolio roles, persistent decision logs and local-model support. QuantMesh should use this as an AI research workflow while keeping order authority in deterministic code.
- Hummingbot already lists Hyperliquid spot and perpetual connectors, so it is a candidate for a future isolated crypto execution service instead of reimplementing every exchange detail in the MVP.

## Excluded from the first MVP

- LEAN is not pulled into the permissive runtime because it adds substantial
  engine/deployment complexity. ADR-0015 resolves NautilusTrader's LGPL
  boundary as isolated comparator only and rejects FinRL-X runtime admission.
- FinRL is kept optional because reinforcement learning is not the first validation path.
- Backtrader is not selected for the core because the active fork is GPLv3 and Qlib/VectorBT cover the initial research needs.
- OpenBB and Freqtrade may be checked out for reference, but their AGPL/GPL licenses make direct code embedding a deliberate later decision.

## License checklist

Before distributing QuantMesh outside personal use:

1. Pin every upstream commit and record the commit in `git submodule status`.
2. Preserve upstream license and attribution files.
3. Run a dependency license scan in CI.
4. Keep Commons-Clause/GPL/AGPL projects out of the runtime unless the project
   license policy is explicitly changed; study patterns without copying code.
5. Review broker and prediction-market terms separately from open-source licenses.
