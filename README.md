<div align="center">

# QuantMesh

**Local-first market research and deterministic paper trading — across equities, crypto and prediction markets.**

[Quick start](#quick-start) · [Documentation](#documentation) · [Roadmap](docs/roadmap/ROADMAP.md) · [中文](README.zh-CN.md)

<br />

`Local-first` · `Paper-first` · `Read-only live data` · `Apache-2.0`

</div>

QuantMesh gives a solo quantitative researcher one auditable loop: observe
sourced market evidence, test a hypothesis, rehearse a paper decision, then
replay and inspect the result.

## Why QuantMesh?

Research evidence is usually split between broker terminals, exchange
dashboards, prediction-market pages and notebooks. QuantMesh keeps the
decision loop local and inspectable.

- **Evidence before action** — every live value carries its venue, timing,
  sequence and freshness state.
- **Paper before capital** — deterministic risk controls, quote fences,
  position limits, a kill switch and an audit trail govern the order path.
- **One local research surface** — compare equities, crypto and event
  probabilities without turning synthetic or stale values into apparent live data.
- **Reproducible by default** — start with a resettable deterministic demo;
  write read-only live frames to the local replay lake when a feed is available.

## Quick start

### Windows PowerShell

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e ".[dev,research,e2e]"
quantmesh-workstation --demo
```

Open <http://127.0.0.1:8765/app/>. The demo is local, deterministic and
labelled; it never sends orders or credentials to an external venue.

<details>
<summary>Optional read-only live mode</summary>

Set a bounded local watchlist, then start the workstation separately from the
demo runtime:

```powershell
$env:QUANTMESH_LIVE_WATCHLIST = "BTC,ETH,SOL,HYPE"
quantmesh-workstation --live
```

Read the [live-cockpit operator checklist](docs/runbooks/live-cockpit-operator-checklist.md)
before connecting optional Moomoo or prediction-market sources.

</details>

## How it works

```text
Market data / research / forecasts
                ↓
Venue · source · event time · receive time · freshness
                ↓
     Local research workstation and replay lake
                ↓
Deterministic paper-risk checks and paper-order decision
                ↓
     Positions · P&L · audit · replay
```

The product treats unavailable, delayed, stale, synthetic and replayed data as
different states. It never estimates missing market values for display.

## What you can use

- A one-command, loopback-only React and FastAPI workstation.
- Deterministic demo data, resettable paper account, watchlists and research
  surfaces.
- Read-only market-data connectors with explicit health, freshness and replay
  semantics where local feeds are configured.
- Paper orders, positions, P&L, risk controls, kill switch and audit records.
- English / Simplified Chinese language and system / light / dark theme
  preferences persisted locally in the browser.

## Product boundary

QuantMesh is not an autonomous trading bot.

- AI may eventually summarize evidence and challenge research; it cannot sign,
  place, cancel or resize orders.
- Paper trading is the default. Mainnet signing, wallet custody and real-money
  execution are outside the current product boundary.
- Secrets remain local. Do not place private keys, broker credentials or
  signed payloads in prompts, commits or issue descriptions.

## Documentation

- [Product strategy](docs/product-strategy.md) — product position and final
  shape.
- [Current iteration](docs/iterations/0019-live-research-surface.md) — live
  research surface delivery record.
- [Roadmap](docs/roadmap/ROADMAP.md) — milestones and outcome criteria.
- [Operator checklist](docs/runbooks/live-cockpit-operator-checklist.md) —
  safe demo and read-only-live operation.
- [Open-source reuse matrix](docs/REUSE_MATRIX.md) — integration, ownership
  and licensing decisions.
- [Threat model](docs/threat-model.md) — execution and credential boundaries.

## Status

QuantMesh is under active local-prototype development. The current focus is a
bounded real-time research surface: market metrics, evidence boundaries,
compact charts and deterministic replay. See
[ACTIVE.md](docs/goals/ACTIVE.md) for the durable handoff state.

## License

[Apache License 2.0](LICENSE)

---

<div align="center">

**Sourced evidence → paper decision → replayable result**

</div>
