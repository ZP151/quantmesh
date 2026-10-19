import { useEffect, useRef, useState } from 'react'
import { Page } from '@/components/page'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { VnpyReportComparison } from './VnpyReportComparison'
import type { VerifiedFixtureReport } from '@/lib/vnpy-report-comparison'
import { vnpyFixtureApi as api, type FixtureJob, type FixtureOptions,
  type FixtureReport, type FixtureRequest } from '@/lib/vnpy-fixture-api'

const STORAGE = 'quantmesh.vnpy-fixture.v1'
const inputClass = 'h-9 w-full rounded-md border border-input bg-background px-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50'
type Retained = { request: FixtureRequest; key: string; job?: FixtureJob }
function restore(): Retained | null {
  try {
    const saved = JSON.parse(localStorage.getItem(STORAGE) ?? 'null')
    return saved?.request?.schema_version === 1 && typeof saved.key === 'string' ? saved : null
  } catch { return null }
}
const active = (job: FixtureJob | null) => !!job && ['queued', 'running'].includes(job.state)
function stable(value: unknown): string {
  return JSON.stringify(value, (_key, item) => item && typeof item === 'object' && !Array.isArray(item)
    ? Object.fromEntries(Object.entries(item).sort(([a], [b]) => a.localeCompare(b))) : item)
}
function number(value: unknown): string {
  return typeof value === 'number' && Number.isFinite(value)
    ? value.toLocaleString('en-US', { maximumFractionDigits: 5 }) : 'Unavailable'
}

export function VnpyFixturePanel() {
  const [options, setOptions] = useState<FixtureOptions | null>(null)
  const [unavailable, setUnavailable] = useState(false)
  const [strategy, setStrategy] = useState(() => restore()?.request.strategy_id ?? 'DoubleMaStrategy')
  const [parameters, setParameters] = useState<Record<string, number>>(() => restore()?.request.parameters
    ?? { fast_window: 10, slow_window: 20 })
  const [costs, setCosts] = useState(() => restore()?.request.costs
    ?? { fee_bps: 5, half_spread_price: 0.005, slippage_price: 0.005 })
  const [saved, setSaved] = useState<Retained | null>(restore)
  const [job, setJob] = useState<FixtureJob | null>(() => restore()?.job ?? null)
  const [report, setReport] = useState<VerifiedFixtureReport | null>(null)
  const [reference, setReference] = useState<VerifiedFixtureReport | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [pollStopped, setPollStopped] = useState(false)
  const [jobUnknown, setJobUnknown] = useState(false)
  const mounted = useRef(true)
  const polls = useRef(0)
  const current = useRef<FixtureJob | null>(job)

  useEffect(() => {
    mounted.current = true
    api.options().then(value => { if (mounted.current) setOptions(value) })
      .catch(() => { if (mounted.current) setUnavailable(true) })
    return () => { mounted.current = false }
  }, [])

  function retain(value: Retained) {
    setSaved(value)
    try { localStorage.setItem(STORAGE, JSON.stringify(value)) }
    catch { setError('Browser storage unavailable. Keep this page open and download the completed report.') }
  }
  function accept(next: FixtureJob, retained: Retained) {
    const prior = current.current
    if (stable(next.request) !== stable(retained.request)
      || (prior && (next.job_id !== prior.job_id || next.request_digest !== prior.request_digest
        || next.completed_bars < prior.completed_bars || (prior.state === 'running' && next.state === 'queued')
        || (!active(prior) && next.state !== prior.state)))) {
      throw new Error('Job identity or progress mismatch. Retained setup is preserved.')
    }
    current.current = next
    setJob(next)
    retain({ ...retained, job: next })
  }
  async function refresh() {
    if (!saved?.job || busy) return
    try {
      const next = await api.get(saved.job.job_id)
      if (mounted.current) accept(next, saved)
    } catch (cause) {
      if (mounted.current) {
        if (cause instanceof Error && 'status' in cause && cause.status === 404) {
          setJobUnknown(true)
          setError('This retained job is unknown after an app restart. Create a new fixture job; any downloaded report remains independent.')
        } else setError(String(cause))
        setPollStopped(true)
      }
    }
  }
  useEffect(() => {
    if (!active(job) || pollStopped || busy || jobUnknown) return
    const timer = window.setTimeout(() => {
      if (++polls.current > 60) setPollStopped(true)
      else void refresh()
    }, 1500)
    return () => window.clearTimeout(timer)
  })

  async function submit(event: React.FormEvent) {
    event.preventDefault()
    const retained: Retained = saved ?? {
      key: crypto.randomUUID(), request: { schema_version: 1, strategy_id: strategy, parameters, costs },
    }
    retain(retained)
    setBusy(true); setError(null)
    try {
      const next = await api.submit(retained.request, retained.key)
      if (mounted.current) accept(next, retained)
    } catch (cause) { if (mounted.current) setError(String(cause)) }
    finally { if (mounted.current) setBusy(false) }
  }
  async function cancel() {
    if (!saved?.job) return
    setBusy(true); setError(null)
    try {
      const next = await api.cancel(saved.job.job_id)
      if (mounted.current) accept(next, saved)
    } catch (cause) { if (mounted.current) setError(String(cause)) }
    finally { if (mounted.current) setBusy(false) }
  }
  async function openReport() {
    if (!job) return
    setBusy(true); setError(null)
    try {
      const envelope = await api.report(job.job_id)
      const bytes = new TextEncoder().encode(envelope.text)
      const digest = Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', bytes)))
        .map(byte => byte.toString(16).padStart(2, '0')).join('')
      const value = JSON.parse(envelope.text) as FixtureReport
      if (digest !== envelope.sha256 || digest !== job.report_sha256
        || envelope.request_digest !== job.request_digest || value.request_digest !== job.request_digest
        || value.schema_version !== 1 || stable(value.request) !== stable(job.request)
        || !value.statistics || !Array.isArray(value.daily) || !Array.isArray(value.trades)) {
        throw new Error('Report verification failed. Report bytes and pinned job must agree.')
      }
      if (mounted.current) setReport({ envelope, value })
    } catch (cause) { if (mounted.current) { setReport(null); setError(String(cause)) } }
    finally { if (mounted.current) setBusy(false) }
  }
  function download() {
    if (!report) return
    const url = URL.createObjectURL(new Blob([report.envelope.text], { type: 'application/json' }))
    const anchor = document.createElement('a')
    anchor.href = url; anchor.download = `vnpy-${report.envelope.sha256}.json`; anchor.click()
    window.setTimeout(() => URL.revokeObjectURL(url), 1000)
  }
  function reset() {
    localStorage.removeItem(STORAGE)
    setSaved(null); setJob(null); current.current = null; setReport(null); setError(null)
    polls.current = 0; setPollStopped(false)
    setJobUnknown(false)
  }
  const selected = options?.strategies.find(item => item.strategy_id === strategy)
  const fields = [
    { key: 'fee_bps', label: 'Fee (bps)', step: 0.1, max: 100 },
    { key: 'half_spread_price', label: 'Half spread (USD/unit/fill)', step: 0.001, max: 1 },
    { key: 'slippage_price', label: 'Slippage (USD/unit/fill)', step: 0.001, max: 1 },
  ] as const
  return <Page title="vn.py research" description="Run an official strategy on the pinned small fixture, then inspect its native report.">
    <p className="text-sm text-muted-foreground"><Badge variant="outline">FIXTURE ONLY · experimental</Badge>{' '}
      Synthetic workflow evidence. No investment performance or trading authority.</p>
    {error && <p role="alert" className="rounded-md border border-border p-3 text-sm">{error}</p>}
    <div className="grid gap-6 lg:grid-cols-[minmax(260px,0.8fr)_minmax(0,1.4fr)]">
      <form onSubmit={submit} className="space-y-4 rounded-lg border border-border bg-card p-4">
        <h3 className="font-semibold">Strategy and costs</h3>
        {unavailable ? <p role="status" className="text-sm">vn.py fixture runtime unavailable. Start the optional local fixture app, then reload.</p>
          : !options ? <p role="status" className="text-sm text-muted-foreground">Loading official strategies…</p> : null}
        <label className="block space-y-1 text-sm">Official strategy
          <select aria-label="Official strategy" className={inputClass} value={strategy} disabled={!!saved || busy || !options}
            onChange={event => { const choice = options?.strategies.find(s => s.strategy_id === event.target.value)
              if (choice) { setStrategy(choice.strategy_id); setParameters(Object.fromEntries(choice.parameters.map(p => [p.name, p.default]))) } }}>
            {(options?.strategies ?? []).map(item => <option key={item.strategy_id}>{item.strategy_id}</option>)}
          </select>
        </label>
        <fieldset disabled={!!saved || busy} className="grid grid-cols-2 gap-3">
          <legend className="mb-2 text-sm font-medium">Strategy parameters</legend>
          {selected?.parameters.map(param => <label key={param.name} className="space-y-1 text-xs">{param.name}
            <input aria-label={param.name} required className={inputClass} type="number" min={param.minimum} max={param.maximum}
              step={param.integer ? 1 : 0.01} value={parameters[param.name] ?? param.default}
              onChange={event => setParameters({ ...parameters, [param.name]: event.target.valueAsNumber })} />
          </label>)}
        </fieldset>
        <fieldset disabled={!!saved || busy} className="space-y-3">
          <legend className="mb-2 text-sm font-medium">Execution costs</legend>
          {fields.map(field => <label key={field.key} className="block space-y-1 text-sm">{field.label}
            <input aria-label={field.label} required className={inputClass} type="number" min={field.step} max={field.max}
              step={field.step} value={costs[field.key]} onChange={event => setCosts({ ...costs, [field.key]: event.target.valueAsNumber })} />
          </label>)}
        </fieldset>
        <p className="text-xs text-muted-foreground">Half spread + slippage are charged per unit per fill by the native engine. Starting capital: 100,000 USD.</p>
        <Button type="submit" disabled={!options || busy || !!job}>{saved && !job ? 'Retry same submission' : 'Run vn.py backtest'}</Button>
        {saved && !job && <p className="text-xs">Submission identity retained. Retry uses the same configuration and key.</p>}
        {options && <details className="text-xs"><summary className="cursor-pointer">Pinned fixture and source</summary>
          <p className="mt-2">{options.fixture_label}</p>
          <p className="mt-2 break-all font-mono">Fixture SHA256 {options.fixture_sha256}</p>
          <p className="mt-2">{Object.entries(options.engine_versions).map(([name, version]) => `${name} ${version}`).join(' · ')}</p>
          <p className="mt-2 break-all font-mono">Strategy SHA256 {selected?.source_sha256}</p>
        </details>}
      </form>
      <section aria-label="Native backtest result" className="min-w-0 space-y-4">
        <section className="space-y-3 rounded-lg border border-border p-4">
          <h3 className="font-semibold">Backtest progress</h3>
          {!job ? <p className="text-sm text-muted-foreground">Choose a strategy and submit the fixture to begin.</p> : <>
            <Badge variant="outline">{job.state}</Badge>
            <p role="status" className="text-sm">{job.stage} · {job.completed_bars} / {job.total_bars} bars</p>
            <progress aria-label="Replayed bars" max={job.total_bars} value={job.completed_bars} className="h-2 w-full accent-primary" />
            <p className="break-all font-mono text-xs">Request SHA256 {job.request_digest}</p>
            {job.error_code && <p className="text-sm">Recorded failure: {job.error_code}. Create a new fixture job after reviewing the local attempt log.</p>}
            <div className="flex flex-wrap gap-2">
              <Button variant="outline" disabled={busy} onClick={() => { setError(null); polls.current = 0; setPollStopped(false); void refresh() }}>Refresh status</Button>
              {active(job) && !jobUnknown && <Button variant="outline" disabled={busy} onClick={() => void cancel()}>Cancel backtest</Button>}
              {job.state === 'succeeded' && <Button disabled={busy} onClick={() => void openReport()}>Open verified report</Button>}
            </div>
          </>}
          {pollStopped && <p className="text-xs">Automatic polling paused. Refresh status to retry. Jobs interrupted by an app restart cannot resume.</p>}
          <p className="text-xs text-muted-foreground">Local experimental runtime; active jobs do not recover after restart. Download completed reports to retain them.</p>
          {saved && (!active(job) || jobUnknown) && <Button variant="ghost" disabled={busy} onClick={reset}>New fixture job</Button>}
          {saved && <details className="text-xs"><summary className="cursor-pointer">Submitted parameters and costs</summary>
            <pre className="mt-2 overflow-auto whitespace-pre-wrap break-all">{JSON.stringify(saved.request, null, 2)}</pre></details>}
        </section>
        {report && <section className="space-y-4 rounded-lg border border-border p-4" aria-label="Verified native report">
          <div className="flex flex-wrap items-center justify-between gap-2"><h3 className="font-semibold">Native vn.py report</h3>
            <div className="flex flex-wrap gap-2">
              <Button variant="outline" onClick={() => setReference(report)}
                disabled={reference?.envelope.sha256 === report.envelope.sha256}>
                {reference?.envelope.sha256 === report.envelope.sha256 ? 'Kept as comparison reference' : 'Keep as comparison reference'}
              </Button>
              <Button variant="outline" onClick={download}>Download report JSON</Button>
            </div></div>
          <dl className="grid grid-cols-2 gap-3 text-sm">
            {([['End balance (USD)', 'end_balance'], ['Fills', 'total_trade_count'], ['Fees (USD)', 'total_commission'],
              ['Spread + slippage (USD)', 'total_slippage']] as const).map(([label, key]) => <div key={key}>
                <dt className="text-xs text-muted-foreground">{label}</dt><dd className="font-mono tabular-nums">{number(report.value.statistics[key])}</dd></div>)}
          </dl>
          <p className="text-xs text-muted-foreground">{report.value.semantics}</p>
          <div className="overflow-x-auto"><table className="w-full text-left text-xs"><caption className="mb-2 text-left font-medium">Daily equity</caption>
            <thead><tr><th scope="col">Session</th><th scope="col" className="text-right">Balance (USD)</th><th scope="col" className="text-right">Net P&amp;L</th></tr></thead>
            <tbody>{report.value.daily.map(day => <tr key={day.date} className="border-t border-border">
              <th scope="row" className="py-2 font-normal">{day.date}</th><td className="text-right font-mono tabular-nums">{number(day.balance)}</td><td className="text-right font-mono tabular-nums">{number(day.net_pnl)}</td></tr>)}</tbody>
          </table></div>
          <details className="text-xs"><summary className="cursor-pointer">Inspect fills ({report.value.trades.length})</summary>
            <div className="mt-2 max-h-64 overflow-auto"><table className="w-full text-left"><thead><tr><th scope="col">Time</th><th scope="col">Direction</th><th scope="col">Price</th><th scope="col">Units</th></tr></thead>
              <tbody>{report.value.trades.map((trade, index) => <tr key={index} className="border-t border-border"><td className="whitespace-nowrap py-2">{trade.datetime}</td>
                <td>{trade.direction} / {trade.offset}</td><td>{number(trade.price)}</td><td>{number(trade.volume)}</td></tr>)}</tbody></table></div>
          </details>
          <p className="break-all font-mono text-xs">SHA256 {report.envelope.sha256}</p>
          <details className="text-xs"><summary className="cursor-pointer">Inspect report and lineage JSON</summary>
            <pre className="mt-2 max-h-96 overflow-auto whitespace-pre-wrap break-all">{JSON.stringify(report.value, null, 2)}</pre></details>
        </section>}
        {reference && <VnpyReportComparison reference={reference}
          candidate={report?.envelope.sha256 === reference.envelope.sha256 ? null : report}
          onClearReference={() => setReference(null)} />}
      </section>
    </div>
  </Page>
}
