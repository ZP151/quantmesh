import { useEffect, useRef, useState } from 'react'
import { Download, RefreshCw, X } from 'lucide-react'
import { Page } from '@/components/page'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { api, type ResearchJobOptions, type ResearchJobRecord, type ResearchJobRequest } from '@/lib/api'
import { LocalCsvPlanning } from './LocalCsvPlanning'
import { VnpyFixturePanel } from './VnpyFixturePanel'

// Operate: extend the incumbent black/green workstation. One configuration column,
// one durable status/report column. Fixture truth, nonzero costs and lineage stay
// visible; independent advisory state never controls the deterministic result.
const STORAGE = 'quantmesh.research-job.v1'
const POLL_LIMIT = 60
const POLL_MS = 3000
type Submission = { key: string; request: ResearchJobRequest }
type Saved = { submission: Submission; job?: ResearchJobRecord; refusedStatus?: 409 | 422 }
type ReportCache = { jobId: string; artifactId: string; text: string }

function readSaved(): Saved | null {
  try {
    const value = JSON.parse(localStorage.getItem(STORAGE) ?? 'null') as Saved | null
    return value?.submission?.key && value.submission.request?.schema_version === 1 ? value : null
  } catch { return null }
}

function remember(saved: Saved): boolean {
  try { localStorage.setItem(STORAGE, JSON.stringify(saved)); return true }
  catch { return false }
}

async function reportCache(jobId: string, value?: ReportCache): Promise<ReportCache | null> {
  // Reports can exceed localStorage's quota. Keep verified bytes in this app's
  // IndexedDB, with a bounded test/non-IDB fallback and an explicit retention error.
  if (!globalThis.indexedDB) {
    if (value) localStorage.setItem(`${STORAGE}.report.${jobId}`, JSON.stringify(value))
    return JSON.parse(localStorage.getItem(`${STORAGE}.report.${jobId}`) ?? 'null')
  }
  const database = await new Promise<IDBDatabase>((resolve, reject) => {
    const open = indexedDB.open('quantmesh-research-reports', 1)
    open.onupgradeneeded = () => open.result.createObjectStore('reports')
    open.onsuccess = () => resolve(open.result)
    open.onerror = () => reject(new Error('report_storage_unavailable'))
  })
  try {
    return await new Promise<ReportCache | null>((resolve, reject) => {
      const transaction = database.transaction('reports', value ? 'readwrite' : 'readonly')
      const store = transaction.objectStore('reports')
      const operation = value ? store.put(value, jobId) : store.get(jobId)
      transaction.oncomplete = () => resolve(value ?? operation.result ?? null)
      transaction.onerror = () => reject(new Error('report_storage_unavailable'))
      transaction.onabort = () => reject(new Error('report_storage_unavailable'))
    })
  } finally { database.close() }
}

async function verifyReport(value: ReportCache, ref: ResearchJobRecord['artifacts'][number]): Promise<void> {
  const bytes = new TextEncoder().encode(value.text)
  if (bytes.byteLength > 16 * 1024 * 1024 || bytes.byteLength !== ref.byte_size) throw new Error('artifact_invalid')
  const digest = await crypto.subtle.digest('SHA-256', bytes)
  const hex = Array.from(new Uint8Array(digest), byte => byte.toString(16).padStart(2, '0')).join('')
  if (hex !== ref.sha256 || value.artifactId !== ref.artifact_id) throw new Error('artifact_invalid')
}

function active(job: ResearchJobRecord | null): boolean {
  return !!job && (job.state === 'queued' || job.state === 'running'
    || (job.state === 'succeeded'
      && (job.analysis_state === 'pending' || job.analysis_state === 'running')))
}

function unavailable(value: number | null | undefined): string {
  return value == null ? 'unavailable' : String(value)
}

const inputClass = 'h-9 w-full rounded-md border border-input bg-background px-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50'

export function ResearchJobsScreen() {
  const [engine, setEngine] = useState('baseline')
  const snapshotId = new URLSearchParams(globalThis.location?.search).get('snapshot')
  if (snapshotId !== null) return <LocalCsvPlanning snapshotId={snapshotId} />
  return <>
    <a href="/app/research/data-readiness?format=csv" className="mb-3 inline-flex min-h-11 items-center text-sm underline underline-offset-4 focus-visible:ring-2 focus-visible:ring-ring">Import daily CSV for protocol planning</a>
    <div className="mb-4 flex flex-wrap items-center gap-3 px-1 text-sm">
      <label htmlFor="research-engine">Research engine</label>
      <select id="research-engine" className="h-9 rounded-md border border-input bg-background px-3 focus-visible:ring-2 focus-visible:ring-ring"
        value={engine} onChange={event => setEngine(event.target.value)}>
        <option value="baseline">QuantMesh registered baselines</option>
        <option value="vnpy">vn.py official strategies · fixture experiment</option>
      </select>
    </div>
    {engine === 'vnpy' ? <VnpyFixturePanel /> : <BaselineResearchJobsScreen />}
  </>
}

function BaselineResearchJobsScreen() {
  const retainedRequest = useRef(readSaved()?.submission.request).current
  const [saved, setSaved] = useState<Saved | null>(readSaved)
  const [job, setJob] = useState<ResearchJobRecord | null>(() => readSaved()?.job ?? null)
  const [options, setOptions] = useState<ResearchJobOptions | null>(null)
  const [optionsError, setOptionsError] = useState(false)
  const [strategy, setStrategy] = useState(retainedRequest?.strategy_id ?? 'momentum')
  const [datasetIndex, setDatasetIndex] = useState(0)
  const [train, setTrain] = useState(retainedRequest?.window_spec.train_bars ?? 10)
  const [test, setTest] = useState(retainedRequest?.window_spec.test_bars ?? 5)
  const [step, setStep] = useState(retainedRequest?.window_spec.step_bars ?? 5)
  const [fee, setFee] = useState(retainedRequest?.costs.fee_bps ?? 1)
  const [spread, setSpread] = useState(retainedRequest?.costs.half_spread_bps ?? 2)
  const [slippage, setSlippage] = useState(retainedRequest?.costs.slippage_bps ?? 3)
  const [analysis, setAnalysis] = useState(retainedRequest?.analysis_requested ?? false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [report, setReport] = useState<ReportCache | null>(null)
  const [pollStopped, setPollStopped] = useState(false)
  const [refusedStatus, setRefusedStatus] = useState<409 | 422 | null>(() => readSaved()?.refusedStatus ?? null)
  const [statusSource, setStatusSource] = useState<'retained' | 'authoritative'>('retained')
  const pollCount = useRef(0)
  const statusRead = useRef(0)
  const current = useRef<Saved | null>(saved)
  const mounted = useRef(true)
  const selected = options?.datasets[datasetIndex]
  const chosenStrategy = options?.strategies.find(item => item.strategy_id === strategy)
  const validWindow = Number.isInteger(train) && Number.isInteger(test) && Number.isInteger(step)
    && train >= 2 && test >= 1 && step >= test && !!selected
    && train + test <= selected.minimum_available_bars
  const validCosts = [fee, spread, slippage].every(value => Number.isFinite(value) && value > 0)
  const canSubmit = options?.status === 'configured' && !!chosenStrategy && validWindow && validCosts
    && !saved && !busy

  useEffect(() => {
    mounted.current = true
    let cancelled = false
    api.researchJobOptions().then(value => {
      if (!cancelled) setOptions(value)
    }).catch(() => { if (!cancelled) setOptionsError(true) })
    const retainedJob = current.current?.job
    if (retainedJob) reportCache(retainedJob.job_id).then(async value => {
      const ref = retainedJob.artifacts.find(item => item.kind === 'report')
      if (value && ref) {
        if (value.jobId !== retainedJob.job_id) throw new Error('artifact_invalid')
        await verifyReport(value, ref)
        if (!cancelled && current.current?.job?.job_id === retainedJob.job_id) setReport(value)
      }
    }).catch(() => { if (!cancelled) setError('Retained report integrity verification failed or storage is unavailable.') })
    return () => { cancelled = true; mounted.current = false }
  }, [])

  function accept(next: ResearchJobRecord, submission: Submission) {
    if (!mounted.current) return
    if (current.current?.submission.key !== submission.key) return
    const previous = current.current.job
    if (previous && (next.job_id !== previous.job_id
      || next.request_digest !== previous.request_digest
      || next.implementation_digest !== previous.implementation_digest)) {
      setError('Returned job identity did not match the retained job.')
      return
    }
    if (previous && (Date.parse(next.updated_at) < Date.parse(previous.updated_at)
      || (previous.cancel_requested && !next.cancel_requested)
      || (!['queued', 'running'].includes(previous.state) && next.state !== previous.state))) return
    const value = { submission, job: next }
    current.current = value
    setSaved(value)
    setJob(next)
    setStatusSource('authoritative')
    if (!remember(value)) setError('Job accepted; browser retention failed. Save the job ID before leaving.')
  }

  async function refresh() {
    const retained = current.current
    if (!retained?.job) return
    const sequence = ++statusRead.current
    try {
      const next = await api.researchJob(retained.job.job_id)
      if (sequence === statusRead.current) accept(next, retained.submission)
    } catch {
      if (mounted.current && sequence === statusRead.current) {
        setError('Research service unavailable. Retained status and report remain available.')
        setPollStopped(true)
        setStatusSource('retained')
      }
    }
  }

  useEffect(() => {
    if (!active(job) || busy || pollStopped) return
    if (pollCount.current >= POLL_LIMIT) { setPollStopped(true); return }
    const timer = setTimeout(() => { pollCount.current += 1; void refresh() }, POLL_MS)
    return () => clearTimeout(timer)
    // A response schedules the next check; terminal states and errors stop it.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [job, busy, pollStopped])

  async function submit(retry?: Submission) {
    if (busy) return
    let submission = retry
    if (!submission) {
      if (!canSubmit || !selected || !chosenStrategy) return
      submission = { key: crypto.randomUUID(), request: {
        schema_version: 1, strategy_id: chosenStrategy.strategy_id,
        strategy_version: chosenStrategy.version, dataset: selected.dataset,
        interval: selected.interval, universe: selected.universe, parameters: {},
        costs: { fee_bps: fee, half_spread_bps: spread, slippage_bps: slippage },
        window_spec: { train_bars: train, test_bars: test, step_bars: step },
        budget: { timeout_seconds: 900, memory_mib: 2048, cpu_limit: 1,
          max_model_calls: 12, max_estimated_model_usd: 1 }, analysis_requested: analysis,
      } }
    }
    // Clear a prior refusal durably before a retry: a lost new response must not
    // retain a safe-reset affordance from an earlier rejected attempt.
    if (!remember({ submission })) {
      setError('Browser storage unavailable. Submission was not sent; restore storage before trying again.')
      return
    }
    current.current = { submission }
    setSaved({ submission })
    setRefusedStatus(null)
    statusRead.current += 1
    setBusy(true)
    setError(null)
    try {
      accept(await api.submitResearchJob(submission.request, submission.key), submission)
      pollCount.current = 0
      setPollStopped(false)
    } catch (failure) {
      if (mounted.current) {
        const status = typeof failure === 'object' && failure !== null && 'status' in failure ? failure.status : null
        if (status === 409 || status === 422) {
          const refused = { submission, refusedStatus: status }
          current.current = refused
          setSaved(refused)
          setRefusedStatus(status)
          if (!remember(refused)) setError('Refusal confirmed; browser retention failed. Keep the original key before leaving.')
          else setError(status === 409 ? 'Idempotency conflict: this key belongs to a different request. Retry the saved request or explicitly reconfigure.'
            : 'Pinned request refused. Refresh qualified choices by explicitly reconfiguring.')
        } else setError('Submission response unavailable. The saved request and key are preserved; retry explicitly.')
      }
    } finally { if (mounted.current) setBusy(false) }
  }

  async function cancel() {
    const retained = current.current
    if (!retained?.job || busy) return
    statusRead.current += 1
    setBusy(true)
    setError(null)
    try { accept(await api.cancelResearchJob(retained.job.job_id), retained.submission) }
    catch { if (mounted.current) setError('Cancellation was not confirmed. Refresh status before leaving.') }
    finally { if (mounted.current) setBusy(false) }
  }

  async function openReport() {
    const ref = job?.artifacts.find(item => item.kind === 'report')
    if (!job || !ref || busy) return
    setBusy(true)
    setError(null)
    try {
      const text = await api.researchJobArtifact(job.job_id, ref.artifact_id)
      const value = { jobId: job.job_id, artifactId: ref.artifact_id, text }
      await verifyReport(value, ref)
      if (mounted.current && current.current?.job?.job_id === value.jobId) setReport(value)
      try { await reportCache(job.job_id, value) }
      catch { if (mounted.current) setError('Report opened; browser retention failed. Download it before leaving.') }
    } catch { if (mounted.current) setError('Report unavailable or integrity verification failed. Retained report remains available.') }
    finally { if (mounted.current) setBusy(false) }
  }

  function download() {
    if (!report) return
    const url = URL.createObjectURL(new Blob([report.text], { type: 'application/json' }))
    const link = document.createElement('a')
    link.href = url
    link.download = `${report.jobId}-${report.artifactId}.json`
    link.click()
    setTimeout(() => URL.revokeObjectURL(url), 1000)
  }

  function clearSaved() {
    localStorage.removeItem(STORAGE)
    statusRead.current += 1
    current.current = null
    setSaved(null); setJob(null); setReport(null); setError(null)
    setRefusedStatus(null)
    setPollStopped(false); pollCount.current = 0
  }

  function newJob() {
    if (!job || active(job) || busy) return
    clearSaved()
  }

  function reconfigure() {
    if (job || !refusedStatus || busy) return
    clearSaved()
    setOptions(null); setOptionsError(false)
    api.researchJobOptions().then(value => {
      if (mounted.current) { setOptions(value); setDatasetIndex(0) }
    }).catch(() => { if (mounted.current) setOptionsError(true) })
  }

  const pinnedRequest = job?.request ?? saved?.submission.request
  const fields = [
    { label: 'Train bars', value: train, change: setTrain, minimum: 2 },
    { label: 'Test bars', value: test, change: setTest, minimum: 1 },
    { label: 'Step bars', value: step, change: setStep, minimum: 1 },
    { label: 'Fee (bps)', value: fee, change: setFee, minimum: 0.01 },
    { label: 'Half spread (bps)', value: spread, change: setSpread, minimum: 0.01 },
    { label: 'Slippage (bps)', value: slippage, change: setSlippage, minimum: 0.01 },
  ]

  return <Page title="Research jobs" description="Run a registered baseline on pinned fixture inputs. Inspect durable status and retain its immutable report.">
    <p className="text-sm text-muted-foreground"><Badge variant="outline">FIXTURE_ONLY / v1 research</Badge>{' '}
      Workflow evidence only. Synthetic results do not establish investment performance.</p>
    {error && <p role="alert" className="rounded-md border border-border p-3 text-sm">{error}</p>}
    <div className="grid gap-6 lg:grid-cols-[minmax(260px,0.85fr)_minmax(0,1.4fr)]">
      <section aria-labelledby="research-setup" className="space-y-4 rounded-lg border border-border bg-card p-4">
        <h3 id="research-setup" className="font-semibold">Fixture configuration</h3>
        {optionsError ? <p role="status" className="text-sm">Research service unavailable. No new submission is enabled.</p>
          : !options ? <p role="status" className="text-sm text-muted-foreground">Loading qualified choices…</p>
          : options.status !== 'configured' ? <p role="status" className="text-sm">No qualified fixture inputs. Configure the authoritative Worker input root.</p> : null}
        <label className="block space-y-1 text-sm">Registered baseline
          <select aria-label="Registered baseline" className={inputClass} disabled={!!saved || busy}
            value={strategy} onChange={event => setStrategy(event.target.value)}>
            {pinnedRequest ? <option value={pinnedRequest.strategy_id}>{pinnedRequest.strategy_id} · v{pinnedRequest.strategy_version}</option>
              : options?.strategies.map(item => <option key={item.strategy_id} value={item.strategy_id}>{item.strategy_id} · v{item.version}</option>)}
          </select>
        </label>
        <label className="block space-y-1 text-sm">Pinned fixture
          <select aria-label="Pinned fixture" className={inputClass} disabled={!!saved || busy}
            value={datasetIndex} onChange={event => setDatasetIndex(Number(event.target.value))}>
            {pinnedRequest ? <option value={datasetIndex}>{pinnedRequest.dataset.dataset_id} · r{pinnedRequest.dataset.revision} · {pinnedRequest.interval}</option>
              : options?.datasets.map((item, index) => <option key={`${item.dataset.dataset_id}:${item.interval}`} value={index}>
                {item.dataset.dataset_id} · r{item.dataset.revision} · {item.interval}</option>)}
          </select>
        </label>
        {pinnedRequest ? <p className="text-xs text-muted-foreground">Saved fixture/test inputs · {pinnedRequest.universe.map(item => `${item.venue}:${item.symbol}`).join(', ')}</p>
          : selected && <p className="text-xs text-muted-foreground">{selected.minimum_available_bars} aligned bars · {selected.universe.map(item => `${item.venue}:${item.symbol}`).join(', ')} · fixture/test rights</p>}
        <div className="grid grid-cols-2 gap-3">{fields.map(field => <label key={field.label} className="space-y-1 text-sm">{field.label}
          <input aria-label={field.label} type="number" min={field.minimum} step={field.minimum < 1 ? 'any' : 1}
            className={inputClass} disabled={!!saved || busy} value={field.value}
            onChange={event => field.change(Number(event.target.value))} />
        </label>)}</div>
        {!validWindow && selected && !saved && <p className="text-xs">Use train ≥ 2, test ≥ 1, step ≥ test, and train + test within available bars.</p>}
        <label className="flex items-start gap-2 text-sm"><input type="checkbox" className="mt-1 accent-primary"
          checked={analysis} disabled={!!saved || busy} onChange={event => setAnalysis(event.target.checked)} />
          Request optional advisory analysis. Provider may be unavailable.</label>
        <Button disabled={!canSubmit} onClick={() => void submit()}>Submit fixture job</Button>
        <p className="text-xs text-muted-foreground">Fees, half spread and slippage must each be positive. Evaluation windows do not overlap. No automatic resubmission after reload.</p>
      </section>
      <section aria-labelledby="research-status" className="min-w-0 space-y-4">
        <h3 id="research-status" className="font-semibold">Durable job</h3>
        {!saved && <p className="text-sm text-muted-foreground">Choose qualified inputs and submit once. The saved job and report reopen here.</p>}
        {saved && !job && <div className="space-y-3 rounded-lg border border-border p-4">
          <p className="text-sm">{refusedStatus ? `Submission refused (${refusedStatus}). The original key and payload are retained.`
            : 'Submission not confirmed. The original key and payload are retained.'}</p>
          <p className="break-all font-mono text-xs">Key {saved.submission.key}</p>
          <Button disabled={busy} onClick={() => void submit(saved.submission)}>Retry saved submission</Button>
          {refusedStatus && <Button variant="outline" disabled={busy} onClick={reconfigure}>Reconfigure refused request</Button>}
        </div>}
        {job && <>
          <div className="flex flex-wrap items-center gap-2"><Badge variant="outline">{job.state}</Badge>
            <span className="break-all font-mono text-xs">{job.job_id}</span>
            {job.cancel_requested && <span className="text-xs">Cancellation requested</span>}
          </div>
          <p className="text-sm">{job.analysis_state === 'unavailable' ? 'Agent unavailable'
            : job.analysis_state === 'not_requested' ? 'Agent not requested'
              : `Advisory Agent: ${job.analysis_state}`} · Deterministic backtest: {job.state}</p>
          <p className="text-xs text-muted-foreground">{statusSource === 'retained' ? 'Retained browser status' : 'Authoritative research status'} · Job updated {job.updated_at}</p>
          {job.error_code && <p className="text-sm">Recorded failure: {job.error_code}</p>}
          <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-xs">
            <dt className="text-muted-foreground">Model calls</dt><dd>{unavailable(job.analysis?.usage?.model_calls ?? job.usage.model_calls)}</dd>
            <dt className="text-muted-foreground">Estimated model cost (USD)</dt><dd>{unavailable(job.analysis?.usage?.estimated_model_usd ?? job.usage.estimated_model_usd)}</dd>
            <dt className="text-muted-foreground">Input / output tokens</dt><dd>{unavailable(job.analysis?.usage?.input_tokens ?? job.usage.input_tokens)} / {unavailable(job.analysis?.usage?.output_tokens ?? job.usage.output_tokens)}</dd>
            <dt className="text-muted-foreground">Attempt</dt><dd>{job.attempt}</dd>
          </dl>
          <div className="flex flex-wrap gap-2">
            <Button variant="outline" disabled={busy} onClick={() => { pollCount.current = 0; setPollStopped(false); void refresh() }}><RefreshCw className="size-4" />Refresh status</Button>
            {(job.state === 'queued' || job.state === 'running') && <Button variant="outline" disabled={busy || job.cancel_requested} onClick={() => void cancel()}><X className="size-4" />Cancel job</Button>}
            {job.state === 'succeeded' && <Button disabled={busy} onClick={() => void openReport()}>Open immutable report</Button>}
            {!active(job) && <Button variant="ghost" disabled={busy} onClick={newJob}>New fixture job</Button>}
          </div>
          {pollStopped && active(job) && <p className="text-xs">Automatic checks paused. Refresh status to resume bounded polling.</p>}
          {job.analysis && <p className="text-xs text-muted-foreground">Advisory verdict: {job.analysis.verdict}. Citations: {job.analysis.citations.map(ref => ref.sha256).join(', ') || 'unavailable'}. AI has no order or execution authority.</p>}
        </>}
        {pinnedRequest && <details className="rounded-lg border border-border p-3" open>
          <summary className="cursor-pointer text-sm font-medium">Pinned setup and lineage</summary>
          <dl className="mt-3 space-y-2 break-all text-xs">
            <div><dt className="text-muted-foreground">Baseline / dataset</dt><dd>{pinnedRequest.strategy_id} v{pinnedRequest.strategy_version} · {pinnedRequest.dataset.dataset_id} r{pinnedRequest.dataset.revision} · {pinnedRequest.interval}</dd></div>
            <div><dt className="text-muted-foreground">Costs (bps): fee / half spread / slippage</dt><dd>{pinnedRequest.costs.fee_bps} / {pinnedRequest.costs.half_spread_bps} / {pinnedRequest.costs.slippage_bps}</dd></div>
            <div><dt className="text-muted-foreground">Walk-forward: train / test / step</dt><dd>{pinnedRequest.window_spec.train_bars} / {pinnedRequest.window_spec.test_bars} / {pinnedRequest.window_spec.step_bars}</dd></div>
            <div><dt className="text-muted-foreground">Manifest SHA256</dt><dd className="font-mono">{pinnedRequest.dataset.manifest_digest}</dd></div>
            <div><dt className="text-muted-foreground">Fixture content SHA256</dt><dd className="font-mono">{pinnedRequest.dataset.export_digest}</dd></div>
            {job && <><div><dt className="text-muted-foreground">Request/config SHA256</dt><dd className="font-mono">{job.request_digest}</dd></div>
              <div><dt className="text-muted-foreground">Baseline engine SHA256</dt><dd className="font-mono">{job.implementation_digest}</dd></div></>}
          </dl>
        </details>}
        {report && <section aria-labelledby="canonical-report" className="space-y-3 rounded-lg border border-border p-4">
          <div className="flex flex-wrap items-center justify-between gap-2"><h3 id="canonical-report" className="font-semibold">Canonical report</h3>
            <Button variant="outline" onClick={download}><Download className="size-4" />Download report JSON</Button></div>
          <p className="text-xs text-muted-foreground">Retained immutable fixture report. Includes measured numerical windows, costs and source/config/code lineage; workflow proof only.</p>
          <p className="break-all font-mono text-xs">Artifact SHA256 {report.artifactId}</p>
          <details><summary className="cursor-pointer text-sm">Inspect canonical JSON</summary>
            <pre className="mt-3 max-h-96 overflow-auto whitespace-pre-wrap break-all rounded-md bg-muted/30 p-3 font-mono text-xs">{report.text}</pre></details>
        </section>}
      </section>
    </div>
  </Page>
}
