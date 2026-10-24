import { useEffect, useRef, useState, type ReactNode } from 'react'
import { ArrowRight, RefreshCw, Upload } from 'lucide-react'
import { Page } from '@/components/page'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { usePreferences } from '@/lib/preferences'
import { localCsvApi, MAX_LOCAL_CSV_BYTES, type LocalCsvReport, type LocalCsvRequest } from '@/lib/local-csv-api'
import { explainCsvReason, localCsvCopy } from '@/lib/local-csv-copy'

const control = 'min-h-10 w-full min-w-0 rounded-md border border-input bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50 max-sm:min-h-11'
const link = 'inline-flex min-h-10 items-center gap-2 rounded-md px-3 py-2 text-sm underline underline-offset-4 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring max-sm:min-h-11'
type Busy = 'loading' | 'importing' | 'opening' | null
function readCsv(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onerror = () => reject(new Error('csv_read_failed'))
    reader.onload = () => {
      try { resolve(new TextDecoder('utf-8', { fatal: true, ignoreBOM: true }).decode(reader.result as ArrayBuffer)) }
      catch { reject(new Error('invalid_csv_text')) }
    }
    reader.readAsArrayBuffer(file)
  })
}
export function LocalCsvImport() {
  const { locale } = usePreferences(); const c = localCsvCopy[locale]
  const [history, setHistory] = useState<LocalCsvReport[]>([])
  const [report, setReport] = useState<LocalCsvReport | null>(null)
  const [configured, setConfigured] = useState(false)
  const [file, setFile] = useState<File | null>(null)
  const [form, setForm] = useState({ label: '', symbol: '', start: '', end: '', provider: '', received: '', rights: '', evidence: '', pit: '', sessions: '' })
  const [market, setMarket] = useState<'moomoo' | 'hyperliquid'>('moomoo')
  const [adjustment, setAdjustment] = useState<'raw' | 'adjusted' | 'unknown'>('unknown')
  const [volume, setVolume] = useState<'shares' | 'base_units' | 'contracts' | 'unknown'>('unknown')
  const [busy, setBusy] = useState<Busy>('loading')
  const [error, setError] = useState<string | null>(null)
  const [previous, setPrevious] = useState(false)
  const alive = useRef(false); const pending = useRef(false)
  const errorBox = useRef<HTMLDivElement>(null); const heading = useRef<HTMLHeadingElement>(null); const picker = useRef<HTMLInputElement>(null)
  function message(cause: unknown): string {
    const status = cause && typeof cause === 'object' && 'status' in cause ? Number(cause.status) : 0
    if (cause instanceof Error && cause.message === 'invalid_csv_text') return c.invalid
    if (cause instanceof Error && cause.message === 'invalid_response') return c.invalidResponse
    return ({ 413: c.tooLarge, 422: c.invalid, 415: c.invalid, 503: c.unavailable, 404: c.notFound, 409: c.integrity } as Record<number, string>)[status] ?? c.requestFailed
  }
  useEffect(() => { if (error) errorBox.current?.focus() }, [error])
  useEffect(() => {
    alive.current = true
    localCsvApi.list().then(value => { if (alive.current) { setHistory(value); setConfigured(true) } })
      .catch(cause => { if (alive.current) setError(message(cause)) }).finally(() => { if (alive.current) setBusy(null) })
    return () => { alive.current = false }
    // Explicit refresh owns subsequent reads.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])
  function changed() { setPrevious(report !== null); setError(null) }
  async function refresh() {
    if (pending.current) return
    pending.current = true; setBusy('loading'); setError(null)
    try { const value = await localCsvApi.list(); if (alive.current) { setHistory(value); setConfigured(true) } }
    catch (cause) { if (alive.current) { setError(message(cause)); setConfigured(false) } }
    finally { pending.current = false; if (alive.current) setBusy(null) }
  }
  async function open(id: string) {
    if (pending.current) return
    pending.current = true; setBusy('opening'); setError(null)
    try { const value = await localCsvApi.get(id); if (alive.current) { setReport(value); setPrevious(false); requestAnimationFrame(() => { heading.current?.focus({ preventScroll: true }); heading.current?.scrollIntoView?.({ block: 'start' }) }) } }
    catch (cause) { if (alive.current) setError(message(cause)) }
    finally { pending.current = false; if (alive.current) setBusy(null) }
  }
  const valid = !!file && !!form.label.trim() && /^[A-Za-z0-9][A-Za-z0-9._-]*$/.test(form.symbol.trim())
    && !!form.start && !!form.end && form.start >= '2000-01-03' && form.end <= '2035-12-31' && form.start <= form.end
    && (Date.parse(form.end) - Date.parse(form.start)) / 86400000 <= 3660 && (!form.received || Number.isFinite(Date.parse(`${form.received}Z`)))
  async function submit() {
    if (pending.current || busy || !configured || !valid || !file) return
    pending.current = true; setBusy('importing'); setError(null); setPrevious(report !== null)
    try {
      const body: LocalCsvRequest = { schema_version: 1, label: form.label.trim(), symbol: form.symbol.trim(), venue: market,
        calendar_id: market === 'moomoo' ? 'XNYS' : '24/7', interval: '1d', required_start: form.start, required_end: form.end,
        evidence_kind: 'user_snapshot', csv_text: await readCsv(file), source: {
          provider: form.provider.trim() || 'unknown', received_at: form.received ? new Date(`${form.received}Z`).toISOString() : null,
          license_scope: form.rights.trim() || 'unknown', license_evidence: form.evidence.trim() || 'unknown', pit_status: form.pit.trim() || 'unknown',
          adjustment, volume_unit: volume, session_semantics: form.sessions.trim() || 'unknown',
        } }
      const value = await localCsvApi.import(body)
      if (!alive.current) return
      setReport(value); setPrevious(false); setHistory(current => [value, ...current.filter(item => item.snapshot_id !== value.snapshot_id)])
      requestAnimationFrame(() => { heading.current?.focus({ preventScroll: true }); heading.current?.scrollIntoView?.({ block: 'start' }) })
    } catch (cause) { if (alive.current) setError(message(cause)) }
    finally { pending.current = false; if (alive.current) setBusy(null) }
  }
  const field = (key: keyof typeof form, title: string, type = 'text', maxLength = 120) => <label className="block min-w-0 space-y-1.5 text-sm" htmlFor={`csv-${key}`}>{title}
    <input id={`csv-${key}`} className={control} type={type} maxLength={maxLength} value={form[key]} disabled={busy !== null}
      required={['label', 'symbol', 'start', 'end'].includes(key)}
      min={type === 'date' ? '2000-01-03' : undefined} max={type === 'date' ? '2035-12-31' : undefined}
      aria-invalid={key === 'symbol' ? !!form.symbol && !/^[A-Za-z0-9][A-Za-z0-9._-]*$/.test(form.symbol.trim()) : undefined}
      onChange={event => { changed(); setForm(current => ({ ...current, [key]: event.target.value })) }} /></label>
  return <Page title={c.title} description={c.description} actions={<Button variant="outline" className="max-sm:min-h-11" disabled={busy !== null} onClick={refresh}><RefreshCw className="size-4" aria-hidden="true" />{c.refresh}</Button>}>
    <form onSubmit={event => { event.preventDefault(); void submit() }} className="min-w-0 space-y-4 border-y border-border py-5" aria-label={c.title}>
      <div className="space-y-1.5"><label htmlFor="local-csv-file" className="text-sm font-medium">{c.file}</label>
        <input ref={picker} id="local-csv-file" type="file" accept=".csv,text/csv" disabled={busy !== null || !configured} aria-describedby="local-csv-format"
          className={`${control} file:mr-3 file:rounded file:border-0 file:bg-secondary file:px-3 file:py-1 file:text-secondary-foreground`}
          onChange={event => { changed(); const value = event.target.files?.[0] ?? null
            if (value && (value.size > MAX_LOCAL_CSV_BYTES || !value.size)) { setFile(null); setError(value.size ? c.tooLarge : c.emptyFile); return }
            setFile(value); if (value) setForm(current => ({ ...current, label: value.name.replace(/\.csv$/i, '').slice(0, 120) })) }} />
        <p id="local-csv-format" className="text-xs text-muted-foreground">{c.format}</p><code className="block break-all text-xs">timestamp_utc,open,high,low,close,volume</code>
        <p className="max-w-prose text-xs text-muted-foreground">{c.timestamp}</p>
      </div>
      <div className="grid min-w-0 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {field('label', c.label)}{field('symbol', c.symbol, 'text', 32)}
        <label className="space-y-1.5 text-sm" htmlFor="csv-market">{c.venue}<select id="csv-market" className={control} value={market} disabled={busy !== null} onChange={event => { changed(); setMarket(event.target.value as typeof market) }}><option value="moomoo">Equities · XNYS</option><option value="hyperliquid">Crypto · 24/7</option></select></label>
        {field('start', c.start, 'date')}{field('end', c.end, 'date')}{field('provider', c.provider)}
      </div>
      {form.symbol && !/^[A-Za-z0-9][A-Za-z0-9._-]*$/.test(form.symbol.trim()) && <p className="text-sm text-destructive">{locale === 'zh-CN' ? '代码仅支持字母、数字、点、下划线和连字符，且必须以字母或数字开头。' : 'Use letters, numbers, dots, underscores or hyphens; start the symbol with a letter or number.'}</p>}
      {form.start && form.end && (form.start < '2000-01-03' || form.end > '2035-12-31' || (Date.parse(form.end) - Date.parse(form.start)) / 86400000 > 3660) && <p className="text-sm text-destructive">{locale === 'zh-CN' ? '请选择 2000-01-03 至 2035-12-31 内、不超过 3,660 天的范围。' : 'Choose a window within 2000-01-03 to 2035-12-31 and no longer than 3,660 days.'}</p>}
      {form.start && form.end && form.start > form.end && <p className="text-sm text-destructive">{locale === 'zh-CN' ? '结束日期不能早于开始日期。' : 'Coverage end must be on or after its start.'}</p>}
      <details className="min-w-0"><summary className="min-h-11 cursor-pointer py-3 text-sm font-medium focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">{c.sourceDetails}</summary>
        <p className="mb-4 max-w-prose text-xs text-muted-foreground">{c.sourceHint}</p><div className="grid min-w-0 gap-4 sm:grid-cols-2">
          <div>{field('received', `${c.received} (UTC)`, 'datetime-local')}<p className="mt-1 text-xs text-muted-foreground">{c.receivedHint}</p></div>
          {field('rights', c.rights, 'text', 500)}{field('evidence', c.rightsEvidence, 'text', 500)}{field('pit', c.pit, 'text', 500)}{field('sessions', c.sessions, 'text', 500)}
          <label className="space-y-1.5 text-sm" htmlFor="csv-adjustment">{c.adjustment}<select id="csv-adjustment" className={control} disabled={busy !== null} value={adjustment} onChange={event => { changed(); setAdjustment(event.target.value as typeof adjustment) }}><option value="unknown">{c.unknown}</option><option value="raw">{c.raw}</option><option value="adjusted">{c.adjusted}</option></select></label>
          <label className="space-y-1.5 text-sm" htmlFor="csv-volume">{c.volumeUnit}<select id="csv-volume" className={control} disabled={busy !== null} value={volume} onChange={event => { changed(); setVolume(event.target.value as typeof volume) }}><option value="unknown">{c.unknown}</option><option value="shares">{c.shares}</option><option value="base_units">{c.base_units}</option><option value="contracts">{c.contracts}</option></select></label>
        </div>
      </details>
      <Button type="submit" className="max-sm:min-h-11" disabled={!valid || busy !== null || !configured}><Upload className="size-4" aria-hidden="true" />{c.submit}</Button>
    </form>
    {busy && <p role="status" className="text-sm text-muted-foreground">{c[busy]}</p>}
    {error && <div ref={errorBox} role="alert" tabIndex={-1} className="space-y-2 break-words rounded-md border border-destructive/40 p-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"><p>{error}</p><Button variant="outline" className="max-sm:min-h-11" disabled={busy !== null} onClick={() => picker.current?.focus()}>{locale === 'zh-CN' ? '返回文件选择' : 'Return to file selection'}</Button></div>}
    {report && <section aria-label={c.result} className="min-w-0 space-y-5">
      <div className="space-y-2"><h3 ref={heading} tabIndex={-1} className="scroll-mt-24 break-words text-lg font-semibold focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">{report.label}</h3><p className="text-sm text-muted-foreground"><span>{previous ? c.previous : c.saved}</span> · {report.symbol} · {report.interval}</p>{previous && <p className="text-sm">{c.previousHint}</p>}
        <div className="flex flex-wrap gap-2"><Badge variant="outline">{report.evidence_kind === 'fixture' ? c.fixture : c.supplied}</Badge><Badge variant={report.qualification.structural_status === 'PASS' ? 'outline' : 'destructive'}>{report.qualification.structural_status === 'PASS' ? c.structurePass : c.structureReject}</Badge><Badge variant={report.qualification.status === 'REJECT' ? 'destructive' : 'outline'}>{report.qualification.status === 'REJECT' ? c.rejected : c.insufficient}</Badge></div>
      </div>
      <div className="grid min-w-0 gap-6 lg:grid-cols-2">
        <section className="min-w-0 space-y-3" aria-label={c.coverage}><h4 className="font-semibold">{c.coverage}</h4><dl className="grid grid-cols-2 gap-4 text-sm"><Fact label={c.rows}>{report.coverage.rows}</Fact><Fact label={c.valid}>{report.coverage.valid_rows}</Fact><Fact label={c.expected}>{report.coverage.expected_sessions}</Fact><Fact label={c.range}>{report.coverage.first_date ?? c.unknown} — {report.coverage.last_date ?? c.unknown}</Fact><Fact label={c.age}>{report.freshness.age_sessions ?? c.unknown} · {report.freshness.status}</Fact><Fact label={c.asof}>{report.freshness.as_of}</Fact></dl>
          <details><summary className="min-h-11 cursor-pointer py-3 text-sm focus-visible:ring-2 focus-visible:ring-ring">{c.missing} ({report.coverage.missing_sessions.length}) / {c.unexpected} ({report.coverage.unexpected_sessions.length})</summary><p className="break-words text-xs">{c.missing}: {report.coverage.missing_sessions.join(', ') || '—'}</p><p className="break-words text-xs">{c.unexpected}: {report.coverage.unexpected_sessions.join(', ') || '—'}</p></details></section>
        <section className="min-w-0 space-y-3" aria-label={c.source}><h4 className="font-semibold">{c.source}</h4><p className="text-xs text-muted-foreground">{c.sourceHint}</p><dl className="grid grid-cols-2 gap-4 text-sm"><Fact label={c.provider}>{report.source.provider || c.unknown}</Fact><Fact label={c.venue}>{report.venue} / {report.calendar_id}</Fact><Fact label={c.received}>{report.source.received_at || c.unknown}</Fact><Fact label={c.rights}>{report.source.license_scope || c.unknown}</Fact><Fact label={c.pit}>{report.source.pit_status || c.unknown}</Fact><Fact label={c.adjustment}>{report.source.adjustment}</Fact><Fact label={c.volumeUnit}>{report.source.volume_unit}</Fact></dl></section>
      </div>
      <section aria-label={c.qualification} className="space-y-3 border-t border-border pt-5"><h4 className="font-semibold">{c.qualification}</h4><p className="max-w-prose text-sm">{c.qualificationHint}</p><p className="text-sm"><span className="font-medium">{c.allowed}: </span>{report.qualification.allowed_use.map(use => use === 'inspect_evidence_only' ? c.inspect : use === 'local_protocol_planning_only' ? (locale === 'en' ? 'Plan an experiment' : '规划实验') : use).join(' · ') || c.unknown}</p><ul className="list-disc space-y-1 pl-5 text-sm">{report.qualification.reasons.map((reason, i) => <li className="break-words" key={i}><span title={reason}>{explainCsvReason(reason, locale)}</span></li>)}</ul><p className="text-xs text-muted-foreground">{report.next_action.reason}</p>
        {report.dataset_ref && report.next_action.kind === 'plan_experiment' && report.qualification.structural_status === 'PASS' && report.qualification.allowed_use.includes('local_protocol_planning_only')
          ? <div><a href={`/app/research/jobs?snapshot=${report.snapshot_id}`} className={`${link} bg-secondary text-secondary-foreground`}><ArrowRight className="size-4" aria-hidden="true" />{c.plan}</a><p className="mt-2 max-w-prose text-xs text-muted-foreground">{c.planHint}</p></div> : <p className="text-sm">{c.fix}</p>}
      </section>
      <CsvChecks report={report} />
      <details className="min-w-0 border-t border-border"><summary className="min-h-11 cursor-pointer py-3 text-sm font-medium focus-visible:ring-2 focus-visible:ring-ring">{c.reference}</summary><dl className="grid min-w-0 gap-4 text-xs sm:grid-cols-2"><Fact label="Snapshot">{report.snapshot_id}</Fact><Fact label="Dataset">{report.dataset_ref?.dataset_id ?? c.unknown}</Fact><Fact label="Report SHA256">{report.report_digest}</Fact><Fact label="Original SHA256">{report.lineage.original_sha256}</Fact></dl><div className="mt-3 flex flex-wrap gap-2">{[['original.csv', c.original], ['report', c.report], ['reference.json', c.referenceDownload]].map(([path, text]) => <a key={path} className={link} href={`/api/research/data-snapshots/local-csv/${report.snapshot_id}/${path}`} download>{text}</a>)}</div></details>
    </section>}
    <section className="min-w-0 space-y-3 border-t border-border pt-5" aria-label={c.history}><h3 className="font-semibold">{c.history}</h3>{!busy && configured && !history.length && <div className="space-y-2"><p className="text-sm">{c.empty}</p><p className="max-w-prose text-sm text-muted-foreground">{c.emptyHint}</p></div>}
      <ul className="divide-y divide-border">{history.map(item => <li className="flex min-w-0 flex-wrap items-center justify-between gap-3 py-3" key={item.snapshot_id}><div className="min-w-0 flex-1"><p className="break-words text-sm font-medium [overflow-wrap:anywhere]">{item.label}</p><p className="break-words text-xs text-muted-foreground">{item.symbol} · {item.coverage.first_date ?? c.unknown} — {item.coverage.last_date ?? c.unknown}</p></div><Button variant="outline" className="max-sm:min-h-11" disabled={busy !== null} onClick={() => open(item.snapshot_id)} aria-label={`${c.open} ${item.label}`} aria-pressed={report?.snapshot_id === item.snapshot_id}>{c.open}</Button></li>)}</ul>
    </section>
  </Page>
}
function Fact({ label, children }: { label: string; children: ReactNode }) { return <div className="min-w-0 space-y-1"><dt className="text-xs text-muted-foreground">{label}</dt><dd className="break-words font-mono text-xs tabular-nums [overflow-wrap:anywhere]">{children}</dd></div> }
function CsvChecks({ report }: { report: LocalCsvReport }) {
  const { locale } = usePreferences(); const c = localCsvCopy[locale]; const issues = report.checks.filter(check => check.status === 'REJECT')
  return <section className="min-w-0 space-y-3 border-t border-border pt-5" aria-label={c.issues}><h4 className="font-semibold">{c.issues}</h4>
    {issues.length ? <div className="max-w-full overflow-x-auto focus-visible:ring-2 focus-visible:ring-ring" role="region" aria-label={c.issues} tabIndex={0}><table className="w-full min-w-[580px] text-left text-sm" aria-label={c.issues}><thead><tr className="border-b border-border text-xs text-muted-foreground"><th scope="col" className="p-2 font-medium">{c.issues}</th><th scope="col" className="p-2 font-medium">{c.count}</th><th scope="col" className="p-2 font-medium">{c.location}</th></tr></thead><tbody>{issues.map((check, i) => <tr key={i} className="border-b border-border align-top"><th scope="row" className="max-w-72 space-y-2 break-words p-2 font-normal"><Badge variant={check.status === 'REJECT' ? 'destructive' : 'outline'}>{check.status}</Badge><p>{check.message}</p></th><td className="p-2 font-mono text-xs">{check.count}</td><td className="max-w-sm space-y-2 p-2 text-xs">{check.locations.map((location, j) => <div className="space-y-1 break-words" key={j}><p>{location.date ?? c.unknown} · {locale === 'zh-CN' ? '行' : 'Row'} {location.row ?? c.unknown} · {location.field}</p><p>{locale === 'zh-CN' ? '预期' : 'Expected'}: {location.expected ?? c.unknown}</p><p>{locale === 'zh-CN' ? '实际' : 'Observed'}: {location.actual ?? c.unknown}</p></div>)}{check.locations_truncated && <p>{c.limited}</p>}</td></tr>)}</tbody></table></div> : <p className="text-sm">{c.noIssues}</p>}
    <details><summary className="min-h-11 cursor-pointer py-3 text-sm focus-visible:ring-2 focus-visible:ring-ring">{c.unverified} ({report.checks.filter(check => check.status === 'INSUFFICIENT').length})</summary><ul className="space-y-2 text-sm">{report.checks.filter(check => check.status === 'INSUFFICIENT').map((check, i) => <li key={i} className="break-words" title={check.message}>{explainCsvReason(check.message, locale)}</li>)}</ul></details>
    <details><summary className="min-h-11 cursor-pointer py-3 text-sm focus-visible:ring-2 focus-visible:ring-ring">{c.passed} ({report.checks.filter(check => check.status === 'PASS').length})</summary><ul className="space-y-2 text-sm">{report.checks.filter(check => check.status === 'PASS').map((check, i) => <li key={i} className="break-words">{check.message}</li>)}</ul></details>
  </section>
}
