# QuantMesh v0.1.0-rc8 — operator acceptance

This is a local, read-only research candidate. It does not enable real-money
trading or promote `v0.1.0` by itself.

## Start the exact candidate

```powershell
git clone https://github.com/ZP151/quantmesh.git
cd quantmesh
git checkout tags/v0.1.0-rc8
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev,research,e2e]"
.\.venv\Scripts\quantmesh-workstation --demo --port 8766
```

Open http://127.0.0.1:8766/app/.

## Acceptance checks

1. The version and deterministic-paper/synthetic labels are visible.
2. Settings switches English/简体中文 and System/Light/Dark; both persist after reload.
3. Markets and the bounded watchlist contain labeled demo data.
4. Submit one Hyperliquid `SOL-USD` BUY paper order; it fills and appears in positions and audit.
5. Engage the global kill switch; paper submission is refused; disarm it again.
6. Visit the live cockpit in live mode only; unavailable, stale, replay, and degraded states must be explicit rather than fabricated.

Run `.\.venv\Scripts\python.exe tools\release_gate.py` for the clean-checkout
gate. All order actions above are paper-only; never provide credentials,
private keys, or wallet signatures.
