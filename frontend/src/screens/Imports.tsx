import { useRef, useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { CircleCheck, CircleX, Database, Upload } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Page } from '@/components/page'
import { Notice, Surface, useSurface } from '@/components/state'
import { api, ApiError, type ImportCommitResult, type ImportPreview } from '@/lib/api'
import { dateTime } from '@/lib/format'

// The canonical OHLCV fields the lake accepts; the required four are
// exactly what commit_import enforces on the backend.
const CANONICAL_FIELDS: { field: string; required: boolean }[] = [
  { field: 'timestamp', required: true },
  { field: 'open', required: true },
  { field: 'high', required: true },
  { field: 'low', required: true },
  { field: 'close', required: true },
  { field: 'volume', required: false },
]

const INTERVALS = ['1m', '5m', '15m', '1h', '4h', '1d', '1w']
const VENUES = ['moomoo', 'hyperliquid', 'polymarket', 'kalshi']
const INSTRUMENT_TYPES = ['equity', 'perpetual', 'prediction']

function cell(value: string | number | boolean | null): string {
  if (value === null || value === undefined) return '—'
  if (typeof value === 'string') return value.length > 24 ? `${value.slice(0, 22)}…` : value
  return String(value)
}

/** Data imports: CSV / JSON / Parquet → preview → field mapping →
 * validation → lake write with a dataset manifest. Imports always
 * create new datasets under the demo lake and never touch seeded
 * state; rejection reasons come back per row, and a reset clears the
 * import sessions (the committed datasets stay until the next reset). */
export function ImportsScreen() {
  const queryClient = useQueryClient()
  const committed = useSurface(['imports'], api.imports)

  // Upload form state.
  const fileInput = useRef<HTMLInputElement>(null)
  const [fileName, setFileName] = useState('')
  const [dataset, setDataset] = useState('')
  const [interval, setInterval] = useState('1d')
  const [venue, setVenue] = useState('moomoo')
  const [symbol, setSymbol] = useState('')
  const [instrumentType, setInstrumentType] = useState('equity')
  const [uploadError, setUploadError] = useState<string | null>(null)

  // Preview + mapping state (ephemeral: reset clears it server-side).
  const [preview, setPreview] = useState<ImportPreview | null>(null)
  const [mapping, setMapping] = useState<Record<string, string>>({})

  const upload = useMutation({
    mutationFn: (file: File) => api.importUpload(file),
    onSuccess: (data) => {
      setPreview(data)
      setMapping(data.suggested_mapping)
      setUploadError(null)
    },
    onError: (cause: unknown) =>
      setUploadError(cause instanceof ApiError ? cause.message : String(cause)),
  })

  const commit = useMutation({
    mutationFn: () => {
      if (!preview) throw new Error('no preview to commit')
      return api.importCommit({
        session_id: preview.session_id,
        dataset,
        interval,
        venue,
        symbol,
        instrument_type: instrumentType,
        mapping,
      })
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['imports'] })
    },
  })

  // The last commit result (accepted/rejected counts + coverage) and
  // the server-side committed list, which refreshes via the invalidation.
  const [lastCommit, setLastCommit] = useState<ImportCommitResult | null>(null)

  const missing = CANONICAL_FIELDS.filter(
    ({ field, required }) => required && !mapping[field],
  ).map(({ field }) => field)
  const unknown = Object.keys(mapping).filter((field) => !CANONICAL_FIELDS.some((c) => c.field === field))
  const mappedColumns = Object.values(mapping).filter(Boolean)
  const unmappedColumn = preview?.columns.some((column) => !mappedColumns.includes(column.name)) ?? false

  const canCommit =
    preview !== null &&
    dataset.trim() !== '' &&
    symbol.trim() !== '' &&
    missing.length === 0 &&
    unknown.length === 0 &&
    !unmappedColumn

  function resetForm() {
    setPreview(null)
    setMapping({})
    setLastCommit(null)
    setFileName('')
    setUploadError(null)
    if (fileInput.current) fileInput.current.value = ''
  }

  return (
    <Page
      title="Data imports"
      description="CSV, JSON or Parquet → preview, field mapping, per-row validation with rejection reasons, and a dataset manifest under the demo lake. Imports only create new datasets — seeded state is never overwritten."
      actions={
        preview !== null ? (
          <Button variant="ghost" size="sm" onClick={resetForm}>
            Discard preview
          </Button>
        ) : undefined
      }
    >
      <div className="space-y-5">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="flex items-center gap-2 text-base">
              <Upload className="size-4" aria-hidden /> Import a file
            </CardTitle>
            <CardDescription>
              At most 25 MiB and 100,000 rows. Timestamps may be ISO-8601 or epoch seconds/millis; OHLCV
              values must be numeric.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex flex-wrap items-center gap-3">
              <input
                ref={fileInput}
                type="file"
                accept=".csv,.json,.parquet,text/csv,application/json"
                className="block max-w-full text-sm file:mr-3 file:rounded-lg file:border-0 file:bg-muted file:px-3 file:py-1.5 file:text-sm file:font-medium file:text-foreground hover:file:bg-muted/70"
                onChange={(event) => {
                  const file = event.target.files?.[0]
                  if (!file) return
                  setFileName(file.name)
                  setUploadError(null)
                  upload.mutate(file)
                }}
              />
              {fileName && (
                <span className="font-mono text-xs text-muted-foreground">{fileName}</span>
              )}
            </div>
            {uploadError && (
              <p className="flex items-start gap-2 rounded-lg border border-destructive/40 bg-destructive/10 px-3 py-2 text-xs text-destructive">
                <CircleX className="mt-0.5 size-3.5 shrink-0" aria-hidden />
                <span>{uploadError}</span>
              </p>
            )}
            {upload.isPending && <Notice>Parsing the file…</Notice>}
          </CardContent>
        </Card>

        {preview && (
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="flex items-center gap-2 text-base">
                <Database className="size-4" aria-hidden /> {preview.filename}
                <Badge variant="outline" className="font-mono text-[10px]">
                  {preview.format}
                </Badge>
                <Badge variant="outline" className="font-mono text-[10px]">
                  {preview.rows} rows
                </Badge>
              </CardTitle>
              <CardDescription>
                Map each canonical field to a file column. Suggested mappings were inferred from the
                column names; required fields are marked.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                {CANONICAL_FIELDS.map(({ field, required }) => (
                  <div key={field} className="space-y-1.5">
                    <Label htmlFor={`map-${field}`}>
                      {field}
                      {required && <span className="ml-1 text-destructive">*</span>}
                    </Label>
                    <select
                      id={`map-${field}`}
                      className="h-8 w-full rounded-lg border border-input bg-background px-2 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
                      value={mapping[field] ?? ''}
                      onChange={(event) =>
                        setMapping((current) => ({ ...current, [field]: event.target.value }))
                      }
                    >
                      <option value="">Not mapped</option>
                      {preview.columns.map((column) => (
                        <option key={column.name} value={column.name}>
                          {column.name} · {column.inferred}
                        </option>
                      ))}
                    </select>
                  </div>
                ))}
              </div>
              {missing.length > 0 && (
                <p className="text-xs text-destructive">
                  Required fields without a column: {missing.join(', ')}
                </p>
              )}

              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                <div className="space-y-1.5">
                  <Label htmlFor="import-dataset">Dataset name</Label>
                  <Input
                    id="import-dataset"
                    value={dataset}
                    onChange={(event) => setDataset(event.target.value)}
                    placeholder="my-operational-data"
                  />
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="import-symbol">Symbol</Label>
                  <Input
                    id="import-symbol"
                    value={symbol}
                    onChange={(event) => setSymbol(event.target.value)}
                    placeholder="AAPL"
                  />
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="import-interval">Interval</Label>
                  <select
                    id="import-interval"
                    className="h-8 w-full rounded-lg border border-input bg-background px-2 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
                    value={interval}
                    onChange={(event) => setInterval(event.target.value)}
                  >
                    {INTERVALS.map((value) => (
                      <option key={value} value={value}>
                        {value}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <div className="space-y-1.5">
                    <Label htmlFor="import-venue">Venue</Label>
                    <select
                      id="import-venue"
                      className="h-8 w-full rounded-lg border border-input bg-background px-2 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
                      value={venue}
                      onChange={(event) => setVenue(event.target.value)}
                    >
                      {VENUES.map((value) => (
                        <option key={value} value={value}>
                          {value}
                        </option>
                      ))}
                    </select>
                  </div>
                  <div className="space-y-1.5">
                    <Label htmlFor="import-type">Type</Label>
                    <select
                      id="import-type"
                      className="h-8 w-full rounded-lg border border-input bg-background px-2 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
                      value={instrumentType}
                      onChange={(event) => setInstrumentType(event.target.value)}
                    >
                      {INSTRUMENT_TYPES.map((value) => (
                        <option key={value} value={value}>
                          {value}
                        </option>
                      ))}
                    </select>
                  </div>
                </div>
              </div>

              <div className="overflow-x-auto">
                <table className="w-full min-w-[640px] text-sm">
                  <thead>
                    <tr className="border-b border-border text-left text-xs text-muted-foreground">
                      <th className="py-1.5 pr-3 font-medium">Row</th>
                      {preview.columns.map((column) => (
                        <th key={column.name} className="py-1.5 pr-3 font-medium">
                          {column.name}{' '}
                          <span className="font-mono text-[10px] font-normal text-muted-foreground">
                            {column.inferred}
                          </span>
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {preview.preview.map((row, index) => (
                      <tr key={index} className="border-b border-border/60">
                        <td className="py-1.5 pr-3 font-mono text-xs text-muted-foreground">
                          {index + 1}
                        </td>
                        {preview.columns.map((column) => (
                          <td key={column.name} className="py-1.5 pr-3 font-mono text-xs">
                            {cell(row[column.name] ?? null)}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              <Button
                className="gap-1.5"
                disabled={!canCommit || commit.isPending}
                onClick={() =>
                  commit.mutate(undefined, {
                    onSuccess: (result) => setLastCommit(result),
                  })
                }
              >
                <CircleCheck className="size-4" aria-hidden />
                {commit.isPending ? 'Committing…' : `Commit dataset (${preview.rows} rows)`}
              </Button>
              <p className="text-[11px] text-muted-foreground">
                Rows that fail validation are rejected with their reason — the file is never
                half-imported. An existing dataset name is refused (imports create new datasets only).
              </p>
            </CardContent>
          </Card>
        )}

        {lastCommit && (
          <Card className="border-emerald-500/40">
            <CardHeader className="pb-2">
              <CardTitle className="flex items-center gap-2 text-base text-emerald-500">
                <CircleCheck className="size-4" aria-hidden /> {lastCommit.dataset} committed
              </CardTitle>
              <CardDescription>
                Source <code className="font-mono">{lastCommit.source}</code> · license{' '}
                <code className="font-mono">{lastCommit.license}</code> · revision{' '}
                {lastCommit.revision} · {dateTime(lastCommit.generated_at)}
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-3 text-sm">
              <div className="flex flex-wrap gap-2">
                <Badge variant="default">{lastCommit.accepted} accepted</Badge>
                {lastCommit.rejected > 0 && (
                  <Badge variant="destructive">{lastCommit.rejected} rejected</Badge>
                )}
              </div>
              {lastCommit.rejections.length > 0 && (
                <div className="overflow-x-auto">
                  <table className="w-full min-w-[480px] text-sm">
                    <thead>
                      <tr className="border-b border-border text-left text-xs text-muted-foreground">
                        <th className="py-1.5 pr-3 font-medium">Row</th>
                        <th className="py-1.5 font-medium">Reason</th>
                      </tr>
                    </thead>
                    <tbody>
                      {lastCommit.rejections.map((rejection) => (
                        <tr key={rejection.row} className="border-b border-border/60">
                          <td className="py-1.5 pr-3 font-mono text-xs">{rejection.row}</td>
                          <td className="py-1.5 font-mono text-xs text-destructive">
                            {rejection.reason}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
              {lastCommit.coverage.map((entry) => (
                <p key={`${entry.interval}-${entry.venue}-${entry.symbol}`} className="font-mono text-xs text-muted-foreground">
                  {entry.interval} · {entry.venue}:{entry.symbol} · {entry.rows} bars ·{' '}
                  {dateTime(entry.start)} → {dateTime(entry.end)}
                </p>
              ))}
            </CardContent>
          </Card>
        )}

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="flex items-center gap-2 text-base">
              <Database className="size-4" aria-hidden /> Committed imports
            </CardTitle>
            <CardDescription>
              Datasets created through this import path, from their manifests under the demo lake.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <Surface
              query={committed}
              title="Imports"
              empty={
                <Notice>
                  No operator-imported datasets yet — upload a CSV, JSON or Parquet file above.
                </Notice>
              }
            >
              {(datasets) => (
                <div className="space-y-2">
                  {datasets.map((entry) => (
                    <div
                      key={entry.dataset}
                      className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-border/70 px-3 py-2 text-sm"
                    >
                      <div className="min-w-0">
                        <p className="font-mono">{entry.dataset}</p>
                        <p className="mt-0.5 font-mono text-[10px] text-muted-foreground">
                          {entry.source} · {entry.license} · revision {entry.revision} ·{' '}
                          {entry.series} series · {entry.rows} rows · {entry.start ?? '—'} →{' '}
                          {entry.end ?? '—'}
                        </p>
                      </div>
                      <Badge variant="outline" className="font-mono text-[10px]">
                        {entry.generated_at}
                      </Badge>
                    </div>
                  ))}
                  {datasets.length === 0 && (
                    <Notice>No operator-imported datasets yet — upload a file to create one.</Notice>
                  )}
                </div>
              )}
            </Surface>
          </CardContent>
        </Card>
      </div>
    </Page>
  )
}
