import { nativeDailyCopy as copy, nativeAdmissionReasons as reasons } from '@/lib/messages/research'
import { useEffect, useRef, useState } from 'react'
import { Page } from '@/components/page'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { usePreferences } from '@/lib/preferences'
import { dateTime } from '@/lib/format'
import { evidenceLabel, uiText } from '@/lib/presentation-copy'
import { NATIVE_CANDIDATE, NativeDailyError, nativeArms, nativeDailyApi, nativeRequest, nativeUuid, sameNativeUseBasis, type NativeArtifact, type NativeDecisionRequest, type NativeJob, type NativeOptions, type NativeReport, type NativeRequest } from '@/lib/native-daily-api'

const STORAGE = 'quantmesh.native-daily.v1'
type Intent = { key: string; request: NativeRequest; decision?: { key: string; body: NativeDecisionRequest } }
type Evidence = { jobId: string; admission: NativeArtifact; report: NativeArtifact | null; decision: NativeArtifact | null }
const control = 'min-h-11 w-full min-w-0 rounded-md border border-input bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50'
function retained(id?: string): Intent | null {
  try {
    const v: unknown = JSON.parse(localStorage.getItem(id ? `${STORAGE}.${id}` : STORAGE) ?? 'null')
    if (!v || typeof v !== 'object') return null
    const value = v as Intent
    if (!nativeUuid(value.key) || (id && value.key !== id) || !nativeRequest(value.request)) return null
    if (value.decision) {
      const d = value.decision
      if (!nativeUuid(d.key) || !d.body || !['reject', 'watch'].includes(d.body.disposition) || typeof d.body.reason !== 'string' || !d.body.reason.trim() || d.body.reason.length > 1000
        || !/^[a-f0-9]{64}$/.test(d.body.request_digest) || !/^[a-f0-9]{64}$/.test(d.body.admission_digest) || !(d.body.report_digest === null || /^[a-f0-9]{64}$/.test(d.body.report_digest))) return null
    }
    return value
  } catch { return null }
}
function persist(value: Intent) {
  try {
    const raw = JSON.stringify(value)
    localStorage.setItem(`${STORAGE}.${value.key}`, raw)
    localStorage.setItem(STORAGE, raw)
    return localStorage.getItem(`${STORAGE}.${value.key}`) === raw && localStorage.getItem(STORAGE) === raw
  } catch { return false }
}
function identify(id: string) { const url = new URL(location.href); url.searchParams.set('engine', 'native-daily-v2'); url.searchParams.set('native_job', id); history.replaceState(null, '', url) }
function initialId() { return new URLSearchParams(location.search).get('native_job') ?? retained()?.key ?? '' }
function download(value: NativeArtifact, jobId: string, kind: string) {
  const url = URL.createObjectURL(new Blob([value.bytes], { type: 'application/json' }))
  const link = document.createElement('a'); link.href = url; link.download = `native-daily-${jobId}-${kind}.json`; link.click()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}



export function NativeDailyPanel() {
  const { locale } = usePreferences(); const w = copy[locale]; const zh = locale === 'zh-CN'
  const [options, setOptions] = useState<NativeOptions | null>(null)
  const [savedStudies, setSavedStudies] = useState<NativeJob[] | null>(null)
  const [archiveLoading, setArchiveLoading] = useState(false)
  const [archiveError, setArchiveError] = useState<'archiveUnavailable' | 'archiveIntegrity' | 'archiveInvalid' | 'archiveFailed' | null>(null)
  const archiveRead = useRef(0)
  const revealStudy = useRef<string | null>(null)
  const evidenceSection = useRef<HTMLElement>(null)
  const [packageId, setPackageId] = useState(''); const [grantId, setGrantId] = useState('')
  const [intent, setIntent] = useState<Intent | null>(() => { const id = initialId(); return id ? retained(id) : null })
  const [openId, setOpenId] = useState(initialId)
  const [job, setJob] = useState<NativeJob | null>(null); const [evidence, setEvidence] = useState<Evidence | null>(null)
  const [error, setError] = useState<keyof typeof copy.en | null>(null)
  const [submitting, setSubmitting] = useState(false); const [saving, setSaving] = useState(false); const [reading, setReading] = useState(false); const [paused, setPaused] = useState(false)
  const [reason, setReason] = useState(''); const [disposition, setDisposition] = useState<'reject' | 'watch'>('watch'); const [scenario, setScenario] = useState<'base5' | 'stress10'>('base5')
  const alive = useRef(true); const generation = useRef(0); const currentIntent = useRef(intent); const currentJob = useRef(job); const posting = useRef(false); const deciding = useRef(false)
  function issue(cause: unknown) {
    const code = cause instanceof NativeDailyError ? cause.code : ''
    setError(code === 'artifact_invalid' ? 'artifact' : code === 'study_not_admitted' ? 'notAdmitted' : code === 'not_found' ? 'notFound' : code === 'invalid_response' ? 'invalid' : ['idempotency_conflict', 'decision_conflict'].includes(code) ? 'conflict' : 'error')
  }
  function keep(value: Intent) { if (!persist(value)) { setError('storage'); return false }; currentIntent.current = value; setIntent(value); return true }
  function accept(value: NativeJob, token: number) {
    if (!alive.current || token !== generation.current) return
    const old = currentJob.current
    const advancing = old?.job_id === value.job_id && old.recovery_status && value.recovery_status
      && old.recovery_status.business_key === value.recovery_status.business_key
      && old.recovery_status.registered_attempts < value.recovery_status.registered_attempts
      && value.recovery_status.request_digest_history.includes(old.request_digest)
      && ['failed', 'interrupted'].includes(old.state) && !old.report && !old.decision
    if (!advancing && old?.job_id === value.job_id && ((old.state !== 'running' && value.state === 'running') || (old.decision && !value.decision))) return
    if (!advancing && old?.job_id === value.job_id && (old.admission.digest !== value.admission.digest || old.request_digest !== value.request_digest
      || old.created_at !== value.created_at || (old.report && old.report.digest !== value.report?.digest)
      || (old.decision && old.decision.digest !== value.decision?.digest) || (old.state !== 'running' && old.state !== value.state))) { setError('invalid'); return }
    if (old?.job_id === value.job_id && old.created_at !== value.created_at) { setError('invalid'); return }
    const previous = currentIntent.current?.key === value.job_id ? currentIntent.current : retained(value.job_id)
    const next = { key: value.job_id, request: value.request, ...(previous?.decision ? { decision: previous.decision } : {}) }
    currentIntent.current = next; setIntent(next); persist(next)
    currentJob.current = value; setJob(value); setOpenId(value.job_id); identify(value.job_id); setError(null)
  }
  async function loadOptions() { try { const value = await nativeDailyApi.options(); if (alive.current) setOptions(value) } catch (cause) { if (alive.current) issue(cause) } }
  async function loadSavedStudies() {
    const sequence = ++archiveRead.current
    setArchiveLoading(true); setArchiveError(null); setSavedStudies(null)
    try {
      const records = await nativeDailyApi.savedStudies()
      if (alive.current && sequence === archiveRead.current) setSavedStudies(records)
    } catch (cause) {
      if (alive.current && sequence === archiveRead.current) {
        const code = cause instanceof NativeDailyError ? cause.code : ''
        setArchiveError(code === 'artifact_invalid' ? 'archiveIntegrity'
          : code === 'service_unavailable' || code === 'service_closed' ? 'archiveUnavailable'
            : code === 'invalid_response' ? 'archiveInvalid' : 'archiveFailed')
      }
    } finally {
      if (alive.current && sequence === archiveRead.current) setArchiveLoading(false)
    }
  }
  async function read(id: string, expected?: NativeRequest) {
    if (!nativeUuid(id)) { setError('invalidId'); return }
    const token = generation.current; setReading(true)
    try { accept(await nativeDailyApi.get(id, expected), token) } catch (cause) { if (alive.current && token === generation.current) { issue(cause); setPaused(true) } }
    finally { if (alive.current && token === generation.current) setReading(false) }
  }
  useEffect(() => {
    alive.current = true; void loadOptions(); void loadSavedStudies()
    const id = initialId()
    if (id) void read(id, currentIntent.current?.key === id ? currentIntent.current.request : undefined)
    const lifetime = generation
    return () => { alive.current = false; lifetime.current++ }
    // Mount reads saved identity independently of today's selectable options.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])
  useEffect(() => {
    if ((job && job.state !== 'running') || (!submitting && !job) || !intent || paused) return
    let count = 0
    const timer = setInterval(() => { if (++count > 60) { clearInterval(timer); setPaused(true); return }; void read(intent.key, intent.request) }, 3000)
    return () => clearInterval(timer)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [submitting, job?.state, intent?.key, paused])
  useEffect(() => {
    if (!job) return
    let cancelled = false; setEvidence(null)
    const saved = job
    void (async () => {
      try {
        const [admission, report, decision] = await Promise.all([nativeDailyApi.artifact(saved, 'admission'), saved.report ? nativeDailyApi.artifact(saved, 'report') : null, saved.decision ? nativeDailyApi.artifact(saved, 'decision') : null])
        if (report && !sameNativeUseBasis(admission, report)) throw new NativeDailyError('artifact_invalid')
        const pending = currentIntent.current?.key === saved.job_id ? currentIntent.current.decision : undefined
        if (decision && pending && (decision.value.decision_key !== pending.key || Object.entries(pending.body).some(([key, value]) => decision.value[key] !== value))) throw new NativeDailyError('artifact_invalid')
        if (!cancelled) setEvidence({ jobId: saved.job_id, admission, report, decision })
      } catch { if (!cancelled) setError('artifact') }
    })()
    return () => { cancelled = true }
    // The artifact refs are immutable; polling unchanged metadata does not reread bytes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [job?.job_id, job?.admission.digest, job?.report?.digest, job?.decision?.digest])
  useEffect(() => {
    if (!job || revealStudy.current !== job.job_id) return
    revealStudy.current = null
    evidenceSection.current?.focus()
    evidenceSection.current?.scrollIntoView?.({ block: 'start' })
  }, [job])
  async function submit(existing?: Intent, recovery = false) {
    if (posting.current || (job && !recovery)) return
    const pack = options?.packages.find(p => p.package_ref.digest === packageId)
    const grant = options?.grants.find(g => g.grant_ref.digest === grantId && g.package_digest === packageId)
    if (!existing && !options?.configured) return
    const saved = existing ?? { key: pack && grant && pack.job_id ? pack.job_id : crypto.randomUUID(), request: { candidate: NATIVE_CANDIDATE, package_ref: pack?.package_ref ?? null, grant_ref: grant?.grant_ref ?? null, approved_scope_ref: pack?.approved_scope_ref ?? null, protocol_ref: pack?.protocol_ref ?? null } }
    if (!keep(saved)) return
    identify(saved.key); setOpenId(saved.key); setError(null); setPaused(false); setSubmitting(true); posting.current = true
    const token = generation.current
    try {
      if (options?.packages.some(p => p.job_id === saved.key)) {
        try {
          const original = await nativeDailyApi.get(saved.key)
          if (original.recovery_status && (original.report || original.decision || original.state === 'running')) {
            accept(original, token)
            return
          }
        } catch (cause) {
          if (!(cause instanceof NativeDailyError) || cause.code !== 'not_found') throw cause
        }
      }
      accept(await nativeDailyApi.submit(saved.request, saved.key), token)
    } catch (cause) { if (alive.current && token === generation.current) issue(cause) }
    finally { posting.current = false; if (alive.current && token === generation.current) setSubmitting(false) }
  }
  async function decide(existing?: Intent['decision']) {
    if (!job || !evidence || job.state === 'running' || job.decision || deciding.current) return
    const pending = existing ?? { key: crypto.randomUUID(), body: { request_digest: job.request_digest, admission_digest: job.admission.digest, report_digest: job.report?.digest ?? null, disposition, reason: reason.trim() } }
    if (!pending.body.reason || !keep({ key: job.job_id, request: job.request, decision: pending })) return
    const token = generation.current; deciding.current = true; setSaving(true); setError(null)
    try { accept(await nativeDailyApi.decide(job, pending.body, pending.key), token) } catch (cause) { if (alive.current && token === generation.current) issue(cause) }
    finally { deciding.current = false; if (alive.current && token === generation.current) setSaving(false) }
  }
  function reopen(id = openId) {
    if (!nativeUuid(id)) { setError('invalidId'); return }
    setOpenId(id); revealStudy.current = id
    generation.current++; setJob(null); currentJob.current = null; setEvidence(null); setError(null); setSubmitting(false); setSaving(false); setReading(false); setPaused(false)
    const old = retained(id); currentIntent.current = old; setIntent(old); identify(id)
    void read(id, old?.request)
  }
  function startAnother() {
    revealStudy.current = null
    generation.current++; currentIntent.current = null; currentJob.current = null; setIntent(null); setJob(null); setEvidence(null); setError(null); setOpenId(''); setReason(''); setSubmitting(false); setSaving(false); setReading(false)
    const url = new URL(location.href); url.searchParams.delete('native_job'); history.replaceState(null, '', url)
  }
  const complete = !!packageId && !!grantId
  const real = job ? job.admission_status === 'ACCEPTED_DECLARED_RESEARCH' : options?.packages.some(p => p.package_ref.digest === packageId && p.evidence_kind === 'reviewed_real')
  const evidenceNote = real ? (job?.recovery_status ? w.recoveryReal : w.real) : w.engineering
  const state = job?.state === 'not_run' ? (job.admission_status === 'REJECT' ? w.rejected : w.notRun) : job?.state === 'running' ? (real ? w.realRunning : w.running) : job?.state === 'succeeded' ? (real ? w.realSucceeded : w.succeeded) : job?.state === 'failed' ? w.failed : w.interrupted
  const verified = evidence?.jobId === job?.job_id ? evidence : null
  const useBasis = real && verified ? verified.admission.value.use_basis as Record<string, unknown> : null
  const recovery = useBasis?.diagnostic_mode === 'DEV_TRANSACTION_RECOVERY'
  const additional = useBasis?.diagnostic_mode === 'DEV_ADDITIONAL_TRUSTED_ENVIRONMENT'
  const usage = additional ? useBasis!.capture_usage as Record<string, unknown> : null
  const observed = (key: string) => typeof usage?.[key] === 'number' ? String(usage[key]) : 'UNKNOWN'
  const trustedEnvironment = recovery || additional || useBasis?.diagnostic_mode === 'DEV_TRUSTED_ENVIRONMENT'
  const diagnostic = trustedEnvironment || useBasis?.diagnostic_mode === 'DEV_DIAGNOSTIC'
  const diagnosticLabel = recovery ? w.recovery : additional ? w.additional : trustedEnvironment ? w.trustedDev : w.dev
  const recoveryPacks = options?.configured ? options.packages.filter(p => p.job_id === job?.job_id) : []
  const recoveryPack = recoveryPacks.length === 1 ? recoveryPacks[0] : null
  const recoveryGrants = recoveryPack ? options!.grants.filter(g => g.package_digest === recoveryPack.package_ref.digest) : []
  const recoveryGrant = recoveryGrants.length === 1 ? recoveryGrants[0] : null
  const pendingDecision = intent?.decision
  const usd = (v: number) => new Intl.NumberFormat(locale, { style: 'currency', currency: 'USD' }).format(v)
  const percent = (v: number) => new Intl.NumberFormat(locale, { style: 'percent', maximumFractionDigits: 2 }).format(v)
  return <Page title={w.title} description={w.description}>
    <div className="min-w-0 space-y-5">
      <Badge variant="outline" className="h-auto min-h-5 max-w-full whitespace-normal py-1 leading-relaxed">{w.safety}</Badge>
      {error && <p role="alert" className="break-words text-sm text-destructive">{w[error]}</p>}
      {!job && !intent && <section aria-labelledby="native-input" className="space-y-3">
        <h3 id="native-input" className="font-medium">{w.input}</h3>
        <label className="block space-y-1 text-sm"><span>{w.candidate}</span><select className={control} value={NATIVE_CANDIDATE} disabled><option value={NATIVE_CANDIDATE}>{w.candidateLabel}</option></select></label>
        <p className="text-xs text-muted-foreground">{w.fixed}</p>
        <p className="text-sm text-muted-foreground">{w.inputReview}</p>
        <p className="text-sm text-muted-foreground">{w.captureStatus}</p>
        {!options ? <><p className="text-sm text-muted-foreground">{w.loading}</p>{error && <Button variant="outline" onClick={() => void loadOptions()}>{w.retryOptions}</Button>}</> : !options.configured ? <p className="text-sm text-muted-foreground">{w.unavailable}</p> : <>
          <div className="grid min-w-0 gap-3 sm:grid-cols-2">
            <label className="block min-w-0 space-y-1 text-sm"><span>{w.package}</span><select className={control} value={packageId} onChange={event => { setPackageId(event.target.value); setGrantId('') }}><option value="">{w.noPackage}</option>{options.packages.map(p => <option key={p.package_ref.digest} value={p.package_ref.digest}>{p.label}</option>)}</select></label>
            <label className="block min-w-0 space-y-1 text-sm"><span>{w.grant}</span><select className={control} value={grantId} onChange={event => setGrantId(event.target.value)}><option value="">{w.noGrant}</option>{options.grants.filter(g => g.package_digest === packageId).map(g => <option key={g.grant_ref.digest} value={g.grant_ref.digest}>{g.label}</option>)}</select></label>
          </div>
          <p className="text-sm text-muted-foreground">{complete ? evidenceNote : w.missing}</p>
          <Button className="min-h-11" onClick={() => void submit()}>{complete ? w.submit : w.insufficient}</Button>
        </>}
      </section>}
      {intent && <details open={!job || submitting || paused} className="space-y-2 border-t pt-3"><summary className="cursor-pointer py-2 text-sm focus-visible:ring-2 focus-visible:ring-ring">{uiText('Input and recovery tools', locale)}</summary>
        <p className="text-xs text-muted-foreground">{w.retained}</p>
        <p className="break-all font-mono text-xs">{intent.key}</p>
        <div className="flex flex-wrap gap-2"><Button className="min-h-11" variant="outline" disabled={reading} onClick={() => { setPaused(false); void read(intent.key, intent.request) }}>{w.read}</Button>{!job && !submitting && <Button className="min-h-11" variant="outline" onClick={() => void submit(intent)}>{w.retry}</Button>}</div>
        {submitting && !job && <p role="status" className="text-sm">{w.waiting}</p>}
        {paused && <p className="text-sm text-muted-foreground">{w.paused}</p>}
      </details>}
      {job && <section ref={evidenceSection} tabIndex={-1} aria-labelledby="native-evidence" className="min-w-0 scroll-mt-20 space-y-3 border-t pt-4">
        <h3 id="native-evidence" className="font-medium">{w.status}</h3>
        <p role="status" className="text-sm">{state}</p>
        <p className="text-xs text-muted-foreground">{job.recovery_status ? w.recoveryTrial : w.trial}: {job.trial_consumed ? w.yes : w.no}</p>
        {!verified && error !== 'artifact' && <p className="text-sm text-muted-foreground">{w.verify}</p>}
        {verified && <>
          {real && <><p className="text-sm text-muted-foreground">{evidenceNote}</p>{!additional && !recovery && <p className="text-sm text-muted-foreground">{w.captureAuthority}</p>}</>}
          {diagnostic && <div className="space-y-2 text-sm" role="note" aria-label={diagnosticLabel}>
            <p className="font-medium">{diagnosticLabel}</p>
            {recovery && job.recovery_status && <p className="tabular-nums">{w.recoveryAttempts}{zh ? '：' : ': '}{job.recovery_status.registered_attempts} · {job.recovery_status.last_attempt_state}</p>}
            {additional && <>
              <p>{w.additionalLegacy}</p><p>{w.additionalLimits}</p>
              <p className="tabular-nums">{w.observed}{zh ? `：${observed('actual_contexts')} 个 context、${observed('actual_business_requests')} 次业务请求、${observed('actual_init_connect')} 次 InitConnect、${observed('actual_keepalive')} 次 KeepAlive。` : `: ${observed('actual_contexts')} context, ${observed('actual_business_requests')} business requests, ${observed('actual_init_connect')} InitConnect, ${observed('actual_keepalive')} KeepAlive.`}</p>
            </>}
            <p>{trustedEnvironment ? w.trustedLimits : w.devLimits}</p><p>{w.devQualification}</p>
            <details className="text-xs"><summary className="min-h-11 cursor-pointer py-3 text-muted-foreground">{w.devBinding}</summary>
              <dl className="space-y-2">{[[w.devPolicy, useBasis!.policy_sha256], [w.devAuthorization, useBasis!.authorization_sha256]].map(([label, value]) => <div key={String(label)}><dt className="text-muted-foreground">{String(label)}</dt><dd className="break-all font-mono">{String(value)}</dd></div>)}</dl>
            </details>
          </div>}
          <ul className="space-y-1 text-sm">{job.admission_reasons.map(code => <li key={code} title={code}>{reasons[code]?.[zh ? 1 : 0] ?? code}</li>)}</ul>
          {job.state === 'not_run' && <p className="text-sm">{w.noReport}</p>}
          {['failed', 'interrupted'].includes(job.state) && <>
            <p className="text-sm">{recovery ? w.recoveryHelp : w.noResult}</p>
            {recovery && !job.decision && !pendingDecision && recoveryPack && recoveryGrant && <Button className="min-h-11" disabled={submitting} onClick={() => void submit({ key: job.job_id, request: { candidate: NATIVE_CANDIDATE, package_ref: recoveryPack.package_ref, approved_scope_ref: recoveryPack.approved_scope_ref, protocol_ref: recoveryPack.protocol_ref, grant_ref: recoveryGrant.grant_ref } }, true)}>{w.resume}</Button>}
            {recovery && submitting && <p role="status" className="text-sm">{w.waiting}</p>}
          </>}
          {verified.report && <>
            {!real && <p className="text-sm text-muted-foreground">{evidenceNote}</p>}
            <div className="flex flex-wrap gap-1" aria-label={zh ? '成本场景' : 'Cost scenario'}>{(['base5', 'stress10'] as const).map(value => <Button key={value} className="min-h-11" variant={scenario === value ? 'secondary' : 'ghost'} aria-pressed={scenario === value} onClick={() => setScenario(value)}>{value === 'base5' ? w.base : w.stress}</Button>)}</div>
            <div className="max-w-full overflow-x-auto"><table className="w-full text-left text-sm tabular-nums"><caption className="sr-only">{w.comparison}</caption><thead className="text-xs text-muted-foreground"><tr>{[w.arm, w.net, w.equity, w.drawdown, w.friction, w.fills].map(label => <th key={label} className="px-2 py-2 font-normal first:pl-0">{label}</th>)}</tr></thead><tbody>{nativeArms.map(arm => { const m = (verified.report!.value as unknown as NativeReport).calculation[scenario][arm].metrics; return <tr key={arm} className="border-t"><th scope="row" className="py-2 pr-2 font-normal">{arm}</th>{[percent(m.total_return), usd(m.terminal_equity), percent(m.max_drawdown), usd(m.friction_usd), String(m.fills)].map((value, index) => <td key={index} className="whitespace-nowrap px-2 py-2">{value}</td>)}</tr> })}</tbody></table></div>
            <p className="text-xs text-muted-foreground">{w.arms}</p><p className="text-xs text-muted-foreground">{w.costs}</p>
          </>}
          <div className="flex flex-wrap gap-2"><Button className="min-h-11" variant="outline" onClick={() => download(verified.admission, job.job_id, 'admission')}>{w.admissionDownload}</Button>{verified.report && <Button className="min-h-11" variant="outline" onClick={() => download(verified.report!, job.job_id, 'report')}>{w.reportDownload}</Button>}{verified.decision && <Button className="min-h-11" variant="outline" onClick={() => download(verified.decision!, job.job_id, 'decision')}>{w.decisionDownload}</Button>}</div>
        </>}
        <details className="text-xs"><summary className="min-h-11 cursor-pointer py-3 text-muted-foreground">{w.identity}</summary><dl className="grid min-w-0 gap-2 sm:grid-cols-2">{[[w.id, job.job_id], [w.request, job.request_digest], [w.protocol, job.request.protocol_ref?.digest ?? '—'], [w.packageHash, job.request.package_ref?.digest ?? '—'], [w.grantHash, job.request.grant_ref?.digest ?? '—'], [w.created, job.created_at], [w.completed, job.completed_at ?? '—'], [uiText('Admission SHA-256', locale), job.admission.digest], ...(job.report ? [[uiText('Report SHA-256', locale), job.report.digest]] : []), ...(job.decision ? [[uiText('Decision SHA-256', locale), job.decision.digest]] : [])].map(([label, value]) => <div key={label}><dt className="text-muted-foreground">{label}</dt><dd className="break-all font-mono">{value}</dd></div>)}</dl></details>
      </section>}
      {job && verified && job.state !== 'running' && <section aria-labelledby="native-decision" className="space-y-3 border-t pt-4">
        <h3 id="native-decision" className="font-medium">{w.decision}</h3>
        {verified.decision ? <p className="break-words text-sm">{verified.decision.value.disposition === 'reject' ? w.reject : w.watch} · {uiText('Original reason', locale)}: {String(verified.decision.value.reason)}</p> : <>
          <p className="text-sm text-muted-foreground">{w.decisionHelp}</p>
          <div className="flex flex-wrap gap-2">{(['reject', 'watch'] as const).map(value => <Button key={value} className="min-h-11" variant={disposition === value ? 'secondary' : 'outline'} aria-pressed={disposition === value} disabled={!!pendingDecision || saving} onClick={() => setDisposition(value)}>{value === 'reject' ? w.reject : w.watch}</Button>)}</div>
          <label className="block space-y-1 text-sm"><span>{w.reason}</span><textarea className={control} maxLength={1000} rows={3} value={pendingDecision?.body.reason ?? reason} disabled={!!pendingDecision || saving} onChange={event => setReason(event.target.value)} /></label>
          {pendingDecision ? <><p className="text-sm text-muted-foreground">{w.pendingDecision}</p><Button className="min-h-11" disabled={saving} onClick={() => void decide(pendingDecision)}>{w.retryDecision}</Button></> : <Button className="min-h-11" disabled={!reason.trim() || saving} onClick={() => void decide()}>{w.saveDecision}</Button>}
        </>}
      </section>}
      <section aria-labelledby="native-saved-studies" aria-busy={archiveLoading} className="min-w-0 space-y-3 border-t pt-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h3 id="native-saved-studies" className="font-medium">{w.archive}</h3>
          <Button className="min-h-11" variant="outline" disabled={archiveLoading} onClick={() => void loadSavedStudies()}>{w.archiveRefresh}</Button>
        </div>
        <p className="text-xs text-muted-foreground">{w.archiveHelp}</p>
        {archiveLoading && <p role="status" className="text-sm">{w.archiveLoading}</p>}
        {archiveError && <p role="status" className="text-sm text-destructive">{w[archiveError]}</p>}
        {savedStudies?.length === 0 && <p className="text-sm">{w.archiveEmpty}</p>}
        {savedStudies && savedStudies.length > 0 && <ul className="max-h-96 space-y-3 overflow-y-auto pr-1">
          {savedStudies.map(saved => <li key={saved.job_id} aria-current={job?.job_id === saved.job_id ? 'true' : undefined} className="min-w-0 space-y-2 rounded-md border border-border p-3">
            <div className="flex flex-wrap items-start justify-between gap-2">
              <div className="min-w-0 space-y-1"><p className="text-sm font-medium">{w.candidateLabel}</p><code className="block break-all text-xs text-muted-foreground">{saved.job_id}</code></div>
              <Button className="min-h-11" variant="outline" aria-label={`${w.archiveOpen} ${saved.job_id}`} disabled={reading || submitting || saving} onClick={() => reopen(saved.job_id)}>{w.open}</Button>
            </div>
            <p className="break-words text-xs">{w.created}: <time dateTime={saved.created_at} title={saved.created_at}>{dateTime(saved.created_at, locale)}</time></p>
            <p className="break-words text-sm">{evidenceLabel(saved.state, locale)} · {evidenceLabel(saved.admission_status, locale)}</p>
            <p className="text-xs text-muted-foreground">{w.archiveReport}: {saved.report ? w.yes : w.no} · {w.archiveDecision}: {saved.decision ? w.yes : w.no}</p>
            <details className="text-xs">
              <summary className="cursor-pointer py-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">{uiText('Original evidence', locale)}</summary>
              <div className="space-y-1 break-all font-mono"><p>{saved.state} · {saved.admission_status}</p><p>{saved.created_at}</p></div>
            </details>
          </li>)}
        </ul>}
      </section>
      <details><summary className="cursor-pointer py-3 text-sm font-medium focus-visible:ring-2 focus-visible:ring-ring">{uiText('Open by ID', locale)}</summary><section aria-labelledby="native-reopen" className="space-y-3 border-t pt-4">
        <h3 id="native-reopen" className="font-medium">{w.reopen}</h3>
        <label className="block space-y-1 text-sm"><span>{w.id}</span><input className={`${control} font-mono`} value={openId} spellCheck={false} autoCapitalize="none" onChange={event => setOpenId(event.target.value)} /></label>
        <div className="flex flex-wrap gap-2"><Button className="min-h-11" variant="outline" disabled={!openId || reading} onClick={() => reopen()}>{w.open}</Button>{job && job.state !== 'running' && !submitting && <Button className="min-h-11" variant="ghost" onClick={startAnother}>{w.newStudy}</Button>}</div>
      </section></details>
    </div>
  </Page>
}
