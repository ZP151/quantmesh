# Trusted Data Fabric — operator runbook (iteration 0021)

This runbook creates bounded, read-only market-data artifacts and records the
daily evidence required for research qualification. It never places orders,
accepts trading credentials or enables autonomous execution. A missing venue,
failed quality policy or incomplete session is recorded as unavailable or
failed; it must never be replaced with synthetic evidence.

## 1. Preconditions

- Use a fresh clone at the exact candidate commit with
  `git status --porcelain` empty.
- Install a fresh environment with
  `pip install -e ".[dev,research,e2e,moomoo]"`.
- Keep the trusted-data root and evidence root on a local filesystem with
  enough free space. Do not place either root behind a symlink, junction,
  reparse point or hard-linked evidence file.
- Treat both roots as retained acceptance records. Do not edit, rename or
  delete manifests, objects, `candidate.json` or daily reports during the
  evidence window.
- Run Moomoo only when the local OpenD probe is available. No account or order
  permission is required for this read-only workflow.

The evidence store uses canonical hashes, an append-only predecessor chain,
write-time metadata and a second filesystem creation/change-time signal to
detect ordinary late or backfilled reports. Its trust root is the local
operator filesystem. It does not claim to resist an administrator or process
that can rewrite every evidence file and forge Windows file timestamps. Task
14 therefore records each daily report identity in the remote issue/CI audit
trail as an independent witness; local verification alone is not a trusted
timestamping service.

## 2. Verify the installed tools

```powershell
quantmesh-data --help
python tools/trusted_data_soak.py --help
```

The clean-checkout release gate also executes the installed
`quantmesh-data --help` entry point. A source-only import is not sufficient.

## 3. Collect one bounded window

Hyperliquid public candles are limited to BTC, ETH and SOL and to no more than
5,000 interval-aligned candles per symbol:

```powershell
quantmesh-data collect `
  --root C:\QuantMesh\trusted-data `
  --provider hyperliquid `
  --symbols BTC,ETH,SOL `
  --interval 1m `
  --window 2026-08-14T00:00:00Z/2026-08-14T01:00:00Z `
  --collection-cycle daily-2026-08-14
```

When OpenD is available, collect the bounded Moomoo window with `--provider
moomoo`, `--symbols AAPL,NVDA` and an interval of `1m` or `1d`. If OpenD is
unavailable, retain the exact typed unavailable output and leave real Moomoo
acceptance pending.

A refused request exits `2`; an integrity, provider or runtime failure exits
`1`. Collection output records `read_only=true` and the exact producing commit.

## 4. Inspect and replay immutable data

```powershell
quantmesh-data inspect --root C:\QuantMesh\trusted-data
quantmesh-data replay `
  --root C:\QuantMesh\trusted-data `
  --manifest <64-character-manifest-id>
```

`replay` emits success only after manifest, object hashes and typed artifact
contracts have been verified. Restart the process and repeat `inspect` and
`replay` against the same root before freezing the candidate.

## 5. Freeze and observe the candidate

The first observation writes `candidate.json` and one immutable UTC report.
It freezes the clean Git commit and the active policy, calendar and schema
configuration. Later observations must match that baseline.

```powershell
python tools/trusted_data_soak.py observe `
  --data-root C:\QuantMesh\trusted-data `
  --evidence-root C:\QuantMesh\trusted-data-evidence
```

Run `observe` once per UTC day for at least 168 continuous hours. Each report
pins manifest IDs, quality-evaluation IDs and committed checkpoint digests.
Only one report is accepted per UTC date, and each report must be written at
its actual observation time. Preserve every output and scheduler exit code.

The qualifying window requires:

- at least 168 continuous elapsed hours;
- fresh, passing adjusted 1-minute bars for Hyperliquid BTC, ETH and SOL in
  every daily report;
- passing adjusted daily bars for Moomoo AAPL and NVDA through the latest
  completed pinned XNYS session;
- at least four distinct completed XNYS sessions;
- no critical quality, synthetic-row or trust failures;
- one unchanged candidate commit and configuration digest.

Do not freeze the candidate while OpenD or any required target is unavailable.
An unavailable Moomoo probe is honest negative evidence, but it cannot satisfy
this five-target qualification window.

## 6. Verify without promotion

```powershell
python tools/trusted_data_soak.py verify `
  --evidence-root C:\QuantMesh\trusted-data-evidence `
  --data-root C:\QuantMesh\trusted-data `
  --minimum-hours 168 `
  --minimum-xnys-sessions 4
```

An accepted result exits `0`. Within the stated local-filesystem trust model,
any detectable backfilled, late, modified, hard-linked, non-canonical,
changed-baseline or incomplete evidence exits `1` with explicit reasons.
Verification qualifies the frozen research dataset; it
does not authorize release promotion, real-money trading or autonomous order
execution.

## 7. Incident handling and retention

- On collection failure, retain the prior immutable data and record the exact
  failure. Do not manufacture a replacement report.
- On policy, calendar, schema or code change, stop the window and freeze a new
  candidate in a new evidence root after review.
- On integrity failure, stop using the affected root. Copy logs for diagnosis
  but do not repair evidence in place.
- Retain the candidate, every daily report, referenced manifests, object store,
  quality records, checkpoints and final verification output beyond the soak
  window so an independent reviewer can replay the decision.
