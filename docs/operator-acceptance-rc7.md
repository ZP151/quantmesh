# QuantMesh v0.1.0-rc7 — operator acceptance

This is a **read-only, research-only release candidate**. Acceptance does
not promote `v0.1.0`. The release gate was run from a clean clone of the
exact tagged tree (`c1ea037`, tag `v0.1.0-rc7`).

## Build and verify

```powershell
# From any directory:
git clone https://github.com/ZP151/quantmesh.git
cd quantmesh
git checkout tags/v0.1.0-rc7
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev,research,e2e]"

# Verify version:
.\.venv\Scripts\python.exe -c "from quantmesh import __version__; print(__version__)"
# → 0.1.0rc7

# Verify the release gate (15 steps, ~15 min):
.\.venv\Scripts\python.exe tools/release_gate.py

# Run golden path (53 checks, ~2 min):
.\.venv\Scripts\python.exe tools/golden_path.py
```

## Start the workstation

```powershell
# Demo mode (deterministic, labeled, no credentials needed):
.\.venv\Scripts\quantmesh-workstation --demo --port 8766

# Live mode (adds read-only multi-venue cockpit with replay lake):
.\.venv\Scripts\quantmesh-workstation --live --port 8766
```

Then open http://127.0.0.1:8766/app/ in a browser.

## What to verify

### SPA routes (13 screens)
http://127.0.0.1:8766/app/overview
http://127.0.0.1:8766/app/watchlist
http://127.0.0.1:8766/app/instruments
http://127.0.0.1:8766/app/positions
http://127.0.0.1:8766/app/orders
http://127.0.0.1:8766/app/pnl
http://127.0.0.1:8766/app/experiments
http://127.0.0.1:8766/app/promotions
http://127.0.0.1:8766/app/forecasts
http://127.0.0.1:8766/app/risk
http://127.0.0.1:8766/app/audit
http://127.0.0.1:8766/app/kill-switch
http://127.0.0.1:8766/app/enablement

### Cockpit (live mode only)
http://127.0.0.1:8766/app/cockpit

- Watchlist shows venue, symbol, label, bid/ask/mid/spread, last trade,
  event/receive time, sequence, age, and the price-trend sparkline.
- Filter the watchlist by typing in the search bar (symbol or venue).
- Instrument detail: chart, book depth, trade tape, metrics + evidence.
- Recorded Replay card: extent, window actions (5/15 min / all), violet
  Replay mode banner, clear action.

### Theme and language
- Settings page (`/app/settings`): switch between System/Light/Dark theme
  and English/简体中文. Reload to confirm persistence.

### Safety invariants
- No credentials, mainnet wallets, real-money or AI order authority.
- Demo data is labeled "synthetic"; live data is labeled "real".
- Replay is strictly read-only — never folded into the live cache.
- Kill switch and enablement work; paper orders respect the quote fence.

## Release gate evidence

Branch: `0019-rc7`  Merge commit: `c1ea037`  Tag: `v0.1.0-rc7`

Release gate 15/15 PASSED on the exact tagged tree (see ACTIVE.md for
per-step durations). Key numbers:
- Frontend Vitest 73/73
- Backend pytest 2134/2134
- Browser E2E 7/7 (desktop, tablet 768 px, mobile 390 px)
- Golden path 53/53
- pip-audit clean, ruff clean, license review clean

## Promotion to v0.1.0

This RC **does not** promote `v0.1.0`. Promotion requires a separate
recorded operator verdict after acceptance of this RC is explicitly
declared. No new functionality, version bumps, or release tags should be
applied to this tree after operator sign-off except the promotion itself.
