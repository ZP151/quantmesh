# SPY snapshot data readiness — issue184

This local research page preserves a particular historical data package and shows
its qualification gaps. Import success does not grant research promotion or trading
authority. The existing vn.py synthetic backtest page has its own runtime and
evidence; importing this package does not silently replace its input.

## Local use

From the repository with its existing Python dependencies:

```powershell
$env:PYTHONPATH = (Join-Path (Get-Location) 'src')
python -m quantmesh.api.workstation --demo --demo-root output/readiness-demo `
  --research-snapshots-root output/research-snapshots --port 8864
```

Keep the snapshot root outside the resettable demo root. Open
`http://127.0.0.1:8864/app/research/data-readiness`. Choose a local supported ZIP,
import it, inspect the eligibility reasons and located findings, and download the
original package and pinned report. Reloading reads the preserved local snapshot.
Without the explicit root the snapshot API is unavailable; enabling vn.py is not
required for data inspection.

No provider login, download or dependency installation occurs during import.
Original source packages stay local and must not be committed or redistributed
without the appropriate entitlement.

## Initial package contract

Schema `qm.spy-daily.snapshot.v1` accepts SPY/USD daily data in exactly eight ZIP
members. It is a retained historical snapshot format, not a general vendor import:

```text
manifest.json
normalized-bars.csv
normalized-distributions.json
calendar-sessions.csv
data-quality.json
raw/yahoo-SPY-20150101-20261016.body
raw/issuer-distribution-history.body
raw/issuer-SPY-nav-history.body
```

The manifest names the schema, symbol, evidence kind, required date range, source
metadata and SHA256 of each of the other seven members. Source metadata records
provider, feed, URL, receipt time, license scope/evidence, price/volume units,
session semantics and PIT status. These are assertions preserved from the source,
not independent proof of entitlement or point-in-time availability.

Normalized bar columns are
`date,open,high,low,close,volume,timestamp_utc,dividend`. Their values are compared
with the retained Yahoo response; the pinned XNYS calendar checks session coverage.
The package is capped at 8MiB compressed, 16MiB expanded and 10,000 bars. It is read
without extracting paths supplied by the archive. Unsupported/malformed packages
are refused. Semantic defects in an otherwise supported package produce located
REJECT findings rather than a success-colored report.

## Read the outcome

Structural PASS means the implemented consistency checks passed. Qualification
also requires evidence those checks cannot establish. The retained real snapshot
has 2,965 rows from 2015-01-02 through 2026-10-16, unknown product/trading and
redistribution rights, unverified historical PIT/revisions, and an unresolved
2021-12-17 dividend amount conflict. Its research eligibility remains INSUFFICIENT.
Retaining issuer spreadsheets is not independent validation of their derived JSON.
Fixtures remain engineering-only. Missing values stay unavailable.

Freshness shows coverage relative to completed XNYS sessions with a 30-minute
research grace. It is not a vendor SLA or proof of when historical prices became
available. The current freshness display may change with time; the downloaded
initial report remains pinned to the import evidence. Report and archive digests
identify the exact downloaded bytes.

The earlier SMA100 daily-open proxy experiment remains REJECT; formal R1/R2 are
INSUFFICIENT and its final OOS has already been consumed. Importing or reopening
data does not rerun that experiment, reset its trial history or promote a strategy.
