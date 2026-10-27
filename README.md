<div align="center">

# QuantMesh

**A local-first workstation for reproducible market research and guarded paper decisions.**

[Quick start](#quick-start) · [Capabilities](#what-you-can-do) ·
[Operating modes](#operating-modes) · [Documentation](#documentation) ·
[简体中文](README.zh-CN.md)

[![CI](https://github.com/ZP151/quantmesh/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/ZP151/quantmesh/actions/workflows/ci.yml)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)

</div>

QuantMesh connects observations, data-quality findings, experiment evidence,
reports and operator decisions. Original inputs and their identities stay
inspectable when you reopen a result; missing evidence remains visible instead
of being treated as a successful strategy or an authorized trade.

## What you can do

- **Inspect local data.** Import a supported daily CSV or snapshot package,
  inspect source, calendar coverage, timestamps and located quality findings,
  and download the preserved original. A structural pass does not establish
  data rights, point-in-time validity or research qualification.
- **Read frozen research evidence.** Inspect supported frozen experiments and
  their pinned input/protocol, cost assumptions, benchmark, risk notes and
  original artifacts. An imported historical result remains a recorded result;
  the interface does not silently rerun or promote it.
- **Run and recover bounded research jobs.** The configured replay workflow
  persists jobs, supports cancellation, reopens an existing report after
  restart, and binds a final Reject or Watch decision to the original report.
  The vn.py fixture experiment is a separate optional runtime with its own
  dependency and license boundary; active vn.py jobs do not resume on restart.
- **Explore markets and decisions.** View labelled charts, scenarios,
  DecisionPackets and outcome reviews. Explicit read-only market modes show
  actual source, age and coverage; the BTC market-data-only mode keeps a bounded
  minute cache. A live quote alone does not qualify a research dataset.
- **Rehearse with deterministic Paper controls.** Proposals pass explicit
  confirmation, quote and risk checks, limits, journals and kill switches.
  Paper is the default; real-money execution is disabled without separate
  authorization and acceptance.
- **Use optional Advisory explanations.** When configured, citation-bound AI
  output can help interpret research evidence. It has no order authority and
  is not required for the local demo. A displayed explanation is not proof of
  strategy skill or an accepted live model call.

## Quick start

The credential-free walkthrough needs **Git and Python 3.13**. These
PowerShell commands use the packaged React app; Node.js is not needed to run
the workstation. From a new directory:

```powershell
git clone https://github.com/ZP151/quantmesh.git
Set-Location quantmesh
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e . -c requirements-audit.txt
.\.venv\Scripts\quantmesh-workstation.exe --demo
```

Open [the local workstation](http://127.0.0.1:8765/app/), inspect NVDA from
Markets or Watchlist, then record a Watch or Reject decision. Keep the terminal
open; press `Ctrl+C` to stop. `--demo` seeds labelled synthetic data and Paper
state. It does **not** attach qualified historical input, the external vn.py
runtime, provider credentials or a real SPY replay. To configure those separate
workflows, start with [local CSV import](docs/research/local-csv-import.md),
[snapshot readiness](docs/research/spy-snapshot-readiness.md),
[frozen experiment inspection](docs/research/frozen-spy-experiment.md) or the
[vn.py fixture guide](docs/research/vnpy-fixture.md).

## Current workstation

These screens were captured from the current merged source using synthetic
demo data and a separately mounted, pre-existing **engineering** replay. The
report's returns are not qualified real-market performance, and its Paper gate
remains closed. The package version shown in the screens is the existing
metadata, not a claim that a newer release has been tagged.

| Overview | Saved research report | Reopened Watch decision |
| --- | --- | --- |
| ![Local synthetic workstation overview](docs/images/workstation-overview-current.png) | ![Saved synthetic engineering report with cost and benchmark comparison](docs/images/research-report-current.png) | ![Original Watch decision reopened from its saved job](docs/images/research-decision-current.png) |

## Operating modes

| Mode | What is available | What it needs |
| --- | --- | --- |
| `--demo` | Seeded, deterministic charts, decisions and Paper walkthrough. | Local install only; all seeded prices and forecasts are synthetic. |
| Configured research | Local import/quality pages, supported frozen packages, bounded replay jobs and report reopen. | Explicit separate storage roots and suitable input. New jobs require their own qualification; vn.py requires an external runtime and its licenses. |
| `--live` | Read-only public Hyperliquid market observations for an explicit watchlist, with source and coverage labels. | Network access and `QUANTMESH_LIVE_WATCHLIST`; recorded coverage is limited to what the runtime has actually observed. |
| `--live --market-data-only` | BTC minute chart with a bounded local observation cache; no strategy summary. | Explicit cache root and budget configuration, loopback and network access; reconnect observation is bounded and there is no initial history backfill. |

The application binds to loopback by default. Connected feeds and optional
model services can communicate outside the machine when explicitly configured.
Market-data access, research eligibility and trading permission are separate.
The current SPY original capture is **not** qualified for a new real-data
backtest: historical volume units and feed coverage remain unresolved. BTC
market observations passed bounded acceptance windows, which do not establish
permanent uptime or complete history. Optional Paper controls use synthetic
thresholds; live trading remains disabled.

## Architecture and documentation

React/TypeScript provides the interface; FastAPI serves the local app and APIs.
Domain, research, risk and execution code sit behind source-specific adapters.
Pinned objects, protocols, reports and journals make accepted workflows
inspectable after restart.

- [Product goals](PRODUCT.md) · [Domain boundaries](CONTEXT.md) ·
  [Architecture decisions](docs/adr)
- [Research guides](docs/research) · [Trusted-data operator guide](docs/runbooks/trusted-data-operator.md) ·
  [Local Paper controls](docs/runbooks/local-paper-controls.md)
- [Release process](docs/release-process.md) · [Contributor guide](AGENTS.md) ·
  [Dependency and license reuse](docs/REUSE_MATRIX.md)

QuantMesh is licensed under [Apache 2.0](LICENSE). Third-party runtimes,
market-data sources and hosted services retain their own license and access
terms. The latest tag is a historical release baseline; this README describes
the capabilities currently merged into `main`, not a new tagged release.
