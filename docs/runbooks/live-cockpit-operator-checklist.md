# Live Market Cockpit — operator acceptance checklist (iteration 0015 Phase G)

The read-only acceptance walk for the Live Market Cockpit prototype. Every
venue stays read-only; the walk never requests, stores or prints credentials
and never touches mainnet, real-money trading or autonomous execution.
Unconfigured or unavailable surfaces must render honestly unavailable — an
empty surface, a failed probe or a closed market is a labeled state, never a
fabricated number.

## 1. Environment

- [ ] Fresh clone of the release commit; `git status --porcelain` empty.
- [ ] Fresh venv; `pip install -e ".[dev,research,e2e]"` from the release
      extras; `python tools/check_release_version.py` agrees with the tag.
- [ ] Clean-checkout release gate run PASSED on the commit
      (`python tools/release_gate.py`), including the full pytest suite and
      the golden path.

## 2. Deterministic demo station (labeled, isolated)

- [ ] `quantmesh-workstation --demo --demo-root <root>` on the loopback port.
- [ ] `/api/demo/status` reports the labeled deterministic root and
      provenance; response headers carry the provenance contract.
- [ ] A second identical station on the same root replays byte-identical
      data; the marker-guarded reset returns the seeded state.
- [ ] Demo data is visually labeled synthetic/demo and isolated from any
      operator data root.

## 3. Live read-only station

- [ ] `QUANTMESH_MOOMOO_WATCHLIST=AAPL,NVDA` (plus
      `QUANTMESH_LIVE_WATCHLIST` / `QUANTMESH_PREDICTION_WATCHLIST` where
      configured) and `quantmesh-workstation --live` on the loopback port.
- [ ] `GET /live/status`: every venue reports `connected` exactly when at
      least one source is `connected`/`lagging`; every source state is one
      of connected/lagging/stale/disconnected/unavailable.
- [ ] `GET /live/state`: every instrument badge and every kind view label
      is one of real/delayed/stale/synthetic/unavailable.
- [ ] **No OpenD daemon on the acceptance host**: the Moomoo surface is
      `unavailable` (probe failed → disconnected), `connected=false`, no
      last-price/volume invented — never a fabricated real-time row. This
      is the degraded-state acceptance check.
- [ ] Replay lake: `<data root>/live/updates.duckdb` exists after the
      station has run; its rows carry the same provenance/gap flags the
      surface shows.
- [ ] `python tools/live_smoke.py --url <station> --watchlist AAPL,NVDA`
      prints `LIVE SMOKE PASSED` (read-only GETs only).
- [ ] Stopping the station and re-running the drill fails honestly
      (non-zero exit, `[FAIL]` per surface) — the drill never passes a
      dead station.

## 4. Browser surface

- [ ] `/app/` loads; the cockpit renders watchlist badges and the connector
      health panel; the Moomoo surface shows unavailable (not blank, not
      fabricated).
- [ ] Paper-order surfaces reject or block on unprovenanced/stale quotes
      (the quote fence's explicit rejections); no order path works on the
      live read-only station beyond the fenced paper surface.
- [ ] Keyboard walk and the mobile/tablet layouts render without
      overflow/clip/contrast failures (Phase E a11y suite green).

## 5. Periodic smoke (optional, recommended)

- [ ] Schedule the read-only drill, e.g.
      `python tools/live_smoke.py --url <station> --watchlist AAPL,NVDA
      --period-minutes 15`; a failed run exits non-zero so a scheduler
      sees it.

## 6. Sign-off

- [ ] All of the above recorded in the acceptance log with the exact
      release commit, gate run id and drill outputs. Acceptance of the
      cockpit prototype does not promote `v0.1.0` — promotion still
      requires the separate recorded "accept RC4, promote to v0.1.0"
      verdict.
