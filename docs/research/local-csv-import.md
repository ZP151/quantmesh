# Import an already-held daily CSV

This adapter inspects held files without contacting a provider. It preserves
submitted UTF-8 CSV text and metadata, reports quality facts and retains a
restricted reference. Import does not establish rights/PIT/finality/actions or
research/trading qualification. Existing SPY ZIP/P2/P3 workflows are separate.

## Ordinary local entry

With the existing Python runtime/dependencies:

```powershell
$env:PYTHONPATH = Join-Path (Get-Location) 'src'
python -m quantmesh.api.workstation `
  --research-snapshots-root output/local-snapshots --port 8874
```

The paired UI slice provides CSV mode at
`http://127.0.0.1:8874/app/research/data-readiness`. Its source/build belongs to
the UI owner. The operable backend is
`http://127.0.0.1:8874/api/research/data-snapshots/local-csv`.
Without the explicit snapshot root it returns503. Keep the root outside any
resettable demo root. No vn.py runtime/provider connection is needed to inspect.

## Format and limits

One1d series, explicit moomoo/XNYS regular or hyperliquid/24/7 UTC calendar.
The fixed CSV header and two generated engineering example rows are:

```csv
timestamp_utc,open,high,low,close,volume
2026-10-15T13:30:00Z,100,102,99,101,1000
2026-10-16T13:30:00Z,101,103,100,102,1100
```

Timestamps are UTC bar OPEN, never historical available_at. Date-only exports
and arbitrary column mapping are not guessed. Select the required ISO date
window; it defines expected sessions including missing dates at either end.
Source metadata keeps provider/receipt or null/rights/PIT/adjustment/unit/session
claims and optional Phase1 preauthorization/post-review/source-evidence SHA refs.
Those refs are not independently verified approvals. Do not enter credentials.

Limits:2MiB encoded UTF-8 CSV,10000rows,3MiB complete JSON request, at most3660days
inside the supported2000–2035 calendar. Preserve original files separately when
pre-decoding encoding/BOM bytes matter: the endpoint preserves submitted text.

## Interpret the result

HTTP201 means preserved and inspected, including structural REJECT. Invalid OHLC,
duplicate/missing/out-of-order sessions, wrong UTC open, unfinished sessions and
contradictory receipt chronology have separate located findings. No row is
silently sorted/deduplicated/imputed into accepted input. Total counts remain
complete; located examples cap100/check with explicit truncation. `valid_rows`
counts parseable UTC and valid OHLCV shapes, without deducting session-open,
duplicate or order issues. It is not a qualified-row count or coverage ratio.

Freshness uses completed pinned sessions plus30minute research grace, not a vendor
SLA. Elapsed sessions today do not prove an old file was final when captured.
Unknown receipt stays null. Structural PASS still has research INSUFFICIENT,
R1/R2INSUFFICIENT and R3NOT_AUTHORIZED. Fixtures are engineering-only. Zero volume
does not prove fills; currency/price units remain unverified, so engineering
hydration uses currencyUNKNOWN.

Malformed JSON/header/metadata422local_csv_invalid; oversize413local_csv_too_large;
wrong type415local_csv_content_type; unknown404local_csv_unknown; altered/missing
stored objects409local_csv_integrity_failed; unavailable runtime503. Raw parser
errors and private contents are not returned as public error details.

## Reference and existing backtester

Structural PASS produces existing DatasetRef(permission_class local_research),
DatasetManifest and normalized CSV ObjectRef. REJECT has no normalized reference.
The reference is BLOCKED for fixture job submission and is only protocol-planning
context. It cannot replace the synthetic vn.py fixture or trusted-data catalog.

`LocalCsvCatalog.read_bars(id, expected_ref, engineering_only=True)` verifies the
complete pin and hydrates only explicitly declared generated fixtures into
existing Bar inputs. Acceptance passes those inputs to existing cost-aware
run_walk_forward; it adds no engine or profitability claim. User snapshots remain
blocked even with that flag. Missing research evidence does not block file
inspection, and customer-service replies are not software prerequisites.

GET`/{id}/reference` supplies planning context. Downloads`/{id}/original.csv`,
`/{id}/report`,`/{id}/reference.json` include exact SHA256 headers. First import
time/report remain pinned through identical reimport/cold reopen. Current
freshness is a read-only display; it does not rewrite the initial report.
