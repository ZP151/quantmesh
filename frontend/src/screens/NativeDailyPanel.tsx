import { useEffect, useRef, useState } from 'react'
import { Page } from '@/components/page'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { usePreferences } from '@/lib/preferences'
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
const copy = {
  en: {
    title: 'Fixed native daily study', description: 'Select the fixed candidate and registered evidence, inspect the original result, then save Reject or Watch.',
    input: 'Study input', candidate: 'Candidate', candidateLabel: 'DoubleMA daily overlay · candidate v1', package: 'Registered package', noPackage: 'No package selected', grant: 'Candidate grant', noGrant: 'No grant selected',
    fixed: 'native-daily-v2 · Quantity A · T / TO / B50 / B100 / C · 5 and 10 bps one way', safety: 'INSUFFICIENT financial evidence · Paper and live unavailable',
    engineering: 'Engineering fixture only. Financial evidence remains INSUFFICIENT; Paper and live trading are unavailable.',
    real: 'Declared retrospective research. Private diagnostic once; external API retention applicability UNKNOWN. Financial evidence remains INSUFFICIENT; Paper and live trading are unavailable.',
    realRunning: 'Running · retrospective research', realSucceeded: 'Report ready · retrospective research',
    missing: 'No registered package and candidate grant are selected. Save the admission reasons without calculating a report.',
    unavailable: 'Durable research storage is unavailable. Existing IDs can still be reopened.', loading: 'Reading registered configuration…', retryOptions: 'Read configuration again',
    submit: 'Submit fixed study', insufficient: 'Save insufficient evidence', waiting: 'Waiting for acknowledgement…', retry: 'Retry saved submission', read: 'Read saved study', retained: 'The ID and exact request were saved before submission. Read this ID after an uncertain response.',
    status: 'Study evidence', notRun: 'Not run · evidence insufficient', rejected: 'Not run · admission rejected', running: 'Running · engineering calculation', succeeded: 'Report ready · engineering evidence', failed: 'Calculation failed', interrupted: 'Interrupted · no automatic rerun',
    noReport: 'No report was calculated. No trial was consumed.', noResult: 'No report is available. The reserved trial remains consumed.', trial: 'Trial consumed', yes: 'Yes', no: 'No', verify: 'Verifying original evidence…', paused: 'Automatic status checks paused. Read this ID to continue.',
    decision: 'Research decision', decisionHelp: 'Save one immutable Reject or Watch decision bound to the original admission and report, if present.', reject: 'Reject', watch: 'Watch', reason: 'Reason', saveDecision: 'Save research decision', retryDecision: 'Retry saved decision', pendingDecision: 'Decision acknowledgement is uncertain. Read this ID or retry the saved decision key.',
    admissionDownload: 'Download admission', reportDownload: 'Download report', decisionDownload: 'Download decision',
    reopen: 'Reopen an existing study', id: 'Saved study ID', open: 'Open study', newStudy: 'Start another study', identity: 'Original identity and timestamps', created: 'Created', completed: 'Completed', request: 'Request SHA-256', protocol: 'Protocol SHA-256', packageHash: 'Package SHA-256', grantHash: 'Grant SHA-256',
    artifact: 'Original evidence could not be verified. Reopen this ID to try again.', error: 'The operation could not be confirmed. Your saved ID and request are retained.', notAdmitted: 'Study was not admitted. No trial was consumed; resolve admission checks and retry this saved request.', invalid: 'The server response did not match the fixed study contract. Reopen the saved ID.', invalidId: 'Enter a canonical UUID study ID.', storage: 'The browser could not retain this request. No submission was sent.', conflict: 'The saved request or decision conflicts with the server record. Reopen this ID to inspect the original.', notFound: 'This ID is not recorded by the service. No new study was submitted.',
    comparison: 'Same-cost comparison', base: '5 bps · base', stress: '10 bps · stress', arm: 'Arm', net: 'Net return', equity: 'Terminal equity', drawdown: 'Max drawdown', friction: 'Friction', fills: 'Fills', costs: 'Uncalibrated combined cost proxy. Fee, spread and slippage components are unknown. Fills are not independent opportunities.', arms: 'T: trend · TO: trend with overlay · B50/B100: 50%/100% buy-and-hold · C: cash, 0% interest.',
  },
  'zh-CN': {
    title: '固定原生日线研究', description: '选择固定候选与已注册证据，核验原始结果，再保存拒绝或观察决定。',
    input: '研究输入', candidate: '候选', candidateLabel: 'DoubleMA 日线叠加 · 候选 v1', package: '已注册输入包', noPackage: '未选择输入包', grant: '候选授权', noGrant: '未选择授权',
    fixed: 'native-daily-v2 · 数量方案 A · T / TO / B50 / B100 / C · 单边 5 和 10 bps', safety: '金融证据 INSUFFICIENT · Paper 与实盘不可用',
    engineering: '仅工程样本。金融证据仍为 INSUFFICIENT，不能授权 Paper 或实盘交易。',
    real: '已声明的真实回溯研究，仅一次私人开发诊断；外部 API 留存适用性 UNKNOWN。金融证据仍为 INSUFFICIENT，Paper 与实盘不可用。',
    realRunning: '运行中 · 回溯研究', realSucceeded: '报告就绪 · 回溯研究',
    missing: '未同时选择已注册输入包与候选授权。可保存准入不足原因，不计算报告。',
    unavailable: '持久化研究存储未配置，仍可重开已有 ID。', loading: '正在读取已注册配置…', retryOptions: '重新读取配置',
    submit: '提交固定研究', insufficient: '保存证据不足记录', waiting: '等待服务端确认…', retry: '重试已保存提交', read: '读取已保存研究', retained: '提交前已保存 ID 与完整请求。响应不确定时请读取原 ID。',
    status: '研究证据', notRun: '未运行 · 证据不足', rejected: '未运行 · 准入被拒绝', running: '运行中 · 工程计算', succeeded: '报告就绪 · 工程证据', failed: '计算失败', interrupted: '已中断 · 不自动重跑',
    noReport: '未计算报告，未消耗试验额度。', noResult: '无可用报告，已保留试验占用。', trial: '已消耗试验额度', yes: '是', no: '否', verify: '正在校验原始证据…', paused: '自动状态查询已暂停，可按原 ID 继续读取。',
    decision: '研究决定', decisionHelp: '保存一条不可编辑的拒绝或观察决定，绑定原始准入记录与报告（如有）。', reject: '拒绝', watch: '观察', reason: '理由', saveDecision: '保存研究决定', retryDecision: '重试已保存决定', pendingDecision: '决定尚未确认，请读取原 ID 或按原决定键重试。',
    admissionDownload: '下载准入原件', reportDownload: '下载报告原件', decisionDownload: '下载决定原件',
    reopen: '重开已有研究', id: '已保存研究 ID', open: '打开研究', newStudy: '开始另一项研究', identity: '原始标识与时间', created: '创建时间', completed: '完成时间', request: '请求 SHA-256', protocol: '协议 SHA-256', packageHash: '输入包 SHA-256', grantHash: '授权 SHA-256',
    artifact: '原始证据校验失败，请按原 ID 重开后重试。', error: '尚无法确认操作结果，已保存的 ID 与请求仍被保留。', notAdmitted: '研究尚未获准，未消耗试验额度。请处理准入检查后重试已保存请求。', invalid: '服务端响应与固定研究契约不符，请重开原 ID。', invalidId: '请输入规范 UUID 研究 ID。', storage: '浏览器无法保留请求，未发送提交。', conflict: '已保存请求或决定与服务端冲突，请重开原 ID 查看原记录。', notFound: '服务端未记录该 ID，未提交新研究。',
    comparison: '同成本基准比较', base: '5 bps · 基准', stress: '10 bps · 压力', arm: '比较臂', net: '净收益率', equity: '期末资金', drawdown: '最大回撤', friction: '综合摩擦', fills: '成交笔数', costs: '未校准综合成本代理。费用、价差与滑点拆分未知，成交笔数不代表独立机会数。', arms: 'T：趋势 · TO：趋势叠加 · B50/B100：50%/100% 买入持有 · C：现金，利息 0%。',
  },
}
const reasons: Record<string, [string, string]> = {
  package_missing: ['Package missing', '缺少输入包'], candidate_grant_missing: ['Candidate grant missing', '缺少候选授权'],
  package_not_registered: ['Package is not registered', '输入包未注册'], candidate_grant_not_qualified: ['Candidate grant is not qualified', '候选授权不合格'],
  engineering_fixture_only: ['Engineering fixture only', '仅工程样本'], grant_already_consumed: ['Grant trial already consumed', '授权试验额度已消耗'],
}

export function NativeDailyPanel() {
  const { locale } = usePreferences(); const w = copy[locale]; const zh = locale === 'zh-CN'
  const [options, setOptions] = useState<NativeOptions | null>(null)
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
    if (old?.job_id === value.job_id && ((old.state !== 'running' && value.state === 'running') || (old.decision && !value.decision))) return
    if (old?.job_id === value.job_id && (old.admission.digest !== value.admission.digest || old.request_digest !== value.request_digest
      || old.created_at !== value.created_at || (old.report && old.report.digest !== value.report?.digest)
      || (old.decision && old.decision.digest !== value.decision?.digest) || (old.state !== 'running' && old.state !== value.state))) { setError('invalid'); return }
    const previous = currentIntent.current?.key === value.job_id ? currentIntent.current : retained(value.job_id)
    const next = { key: value.job_id, request: value.request, ...(previous?.decision ? { decision: previous.decision } : {}) }
    currentIntent.current = next; setIntent(next); persist(next)
    currentJob.current = value; setJob(value); setOpenId(value.job_id); identify(value.job_id); setError(null)
  }
  async function loadOptions() { try { const value = await nativeDailyApi.options(); if (alive.current) setOptions(value) } catch (cause) { if (alive.current) issue(cause) } }
  async function read(id: string, expected?: NativeRequest) {
    if (!nativeUuid(id)) { setError('invalidId'); return }
    const token = generation.current; setReading(true)
    try { accept(await nativeDailyApi.get(id, expected), token) } catch (cause) { if (alive.current && token === generation.current) { issue(cause); setPaused(true) } }
    finally { if (alive.current && token === generation.current) setReading(false) }
  }
  useEffect(() => {
    alive.current = true; void loadOptions()
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
  async function submit(existing?: Intent) {
    if (posting.current || job) return
    const pack = options?.packages.find(p => p.package_ref.digest === packageId)
    const grant = options?.grants.find(g => g.grant_ref.digest === grantId && g.package_digest === packageId)
    if (!existing && !options?.configured) return
    const saved = existing ?? { key: pack && grant && pack.job_id ? pack.job_id : crypto.randomUUID(), request: { candidate: NATIVE_CANDIDATE, package_ref: pack?.package_ref ?? null, grant_ref: grant?.grant_ref ?? null, approved_scope_ref: pack?.approved_scope_ref ?? null, protocol_ref: pack?.protocol_ref ?? null } }
    if (!keep(saved)) return
    identify(saved.key); setOpenId(saved.key); setError(null); setPaused(false); setSubmitting(true); posting.current = true
    const token = generation.current
    try { accept(await nativeDailyApi.submit(saved.request, saved.key), token) } catch (cause) { if (alive.current && token === generation.current) issue(cause) }
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
  function reopen() {
    if (!nativeUuid(openId)) { setError('invalidId'); return }
    generation.current++; setJob(null); currentJob.current = null; setEvidence(null); setError(null); setSubmitting(false); setSaving(false); setReading(false); setPaused(false)
    const old = retained(openId); currentIntent.current = old; setIntent(old); identify(openId)
    void read(openId, old?.request)
  }
  function startAnother() {
    generation.current++; currentIntent.current = null; currentJob.current = null; setIntent(null); setJob(null); setEvidence(null); setError(null); setOpenId(''); setReason(''); setSubmitting(false); setSaving(false); setReading(false)
    const url = new URL(location.href); url.searchParams.delete('native_job'); history.replaceState(null, '', url)
  }
  const complete = !!packageId && !!grantId
  const real = job ? job.admission_status === 'ACCEPTED_DECLARED_RESEARCH' : options?.packages.some(p => p.package_ref.digest === packageId && p.evidence_kind === 'reviewed_real')
  const evidenceNote = real ? w.real : w.engineering
  const state = job?.state === 'not_run' ? (job.admission_status === 'REJECT' ? w.rejected : w.notRun) : job?.state === 'running' ? (real ? w.realRunning : w.running) : job?.state === 'succeeded' ? (real ? w.realSucceeded : w.succeeded) : job?.state === 'failed' ? w.failed : w.interrupted
  const verified = evidence?.jobId === job?.job_id ? evidence : null
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
        {!options ? <><p className="text-sm text-muted-foreground">{w.loading}</p>{error && <Button variant="outline" onClick={() => void loadOptions()}>{w.retryOptions}</Button>}</> : !options.configured ? <p className="text-sm text-muted-foreground">{w.unavailable}</p> : <>
          <div className="grid min-w-0 gap-3 sm:grid-cols-2">
            <label className="block min-w-0 space-y-1 text-sm"><span>{w.package}</span><select className={control} value={packageId} onChange={event => { setPackageId(event.target.value); setGrantId('') }}><option value="">{w.noPackage}</option>{options.packages.map(p => <option key={p.package_ref.digest} value={p.package_ref.digest}>{p.label}</option>)}</select></label>
            <label className="block min-w-0 space-y-1 text-sm"><span>{w.grant}</span><select className={control} value={grantId} onChange={event => setGrantId(event.target.value)}><option value="">{w.noGrant}</option>{options.grants.filter(g => g.package_digest === packageId).map(g => <option key={g.grant_ref.digest} value={g.grant_ref.digest}>{g.label}</option>)}</select></label>
          </div>
          <p className="text-sm text-muted-foreground">{complete ? evidenceNote : w.missing}</p>
          <Button className="min-h-11" onClick={() => void submit()}>{complete ? w.submit : w.insufficient}</Button>
        </>}
      </section>}
      {intent && <div className="space-y-2 border-t pt-3">
        <p className="text-xs text-muted-foreground">{w.retained}</p>
        <p className="break-all font-mono text-xs">{intent.key}</p>
        <div className="flex flex-wrap gap-2"><Button className="min-h-11" variant="outline" disabled={reading} onClick={() => { setPaused(false); void read(intent.key, intent.request) }}>{w.read}</Button>{!job && !submitting && <Button className="min-h-11" variant="outline" onClick={() => void submit(intent)}>{w.retry}</Button>}</div>
        {submitting && !job && <p role="status" className="text-sm">{w.waiting}</p>}
        {paused && <p className="text-sm text-muted-foreground">{w.paused}</p>}
      </div>}
      {job && <section aria-labelledby="native-evidence" className="min-w-0 space-y-3 border-t pt-4">
        <h3 id="native-evidence" className="font-medium">{w.status}</h3>
        <p role="status" className="text-sm">{state}</p>
        <p className="text-xs text-muted-foreground">{w.trial}: {job.trial_consumed ? w.yes : w.no}</p>
        {!verified && error !== 'artifact' && <p className="text-sm text-muted-foreground">{w.verify}</p>}
        {verified && <>
          <ul className="space-y-1 text-sm">{job.admission_reasons.map(code => <li key={code} title={code}>{reasons[code]?.[zh ? 1 : 0] ?? code}</li>)}</ul>
          {job.state === 'not_run' && <p className="text-sm">{w.noReport}</p>}
          {['failed', 'interrupted'].includes(job.state) && <p className="text-sm">{w.noResult}</p>}
          {verified.report && <>
            <p className="text-sm text-muted-foreground">{evidenceNote}</p>
            <div className="flex flex-wrap gap-1" aria-label={zh ? '成本场景' : 'Cost scenario'}>{(['base5', 'stress10'] as const).map(value => <Button key={value} className="min-h-11" variant={scenario === value ? 'secondary' : 'ghost'} aria-pressed={scenario === value} onClick={() => setScenario(value)}>{value === 'base5' ? w.base : w.stress}</Button>)}</div>
            <div className="max-w-full overflow-x-auto"><table className="w-full text-left text-sm tabular-nums"><caption className="sr-only">{w.comparison}</caption><thead className="text-xs text-muted-foreground"><tr>{[w.arm, w.net, w.equity, w.drawdown, w.friction, w.fills].map(label => <th key={label} className="px-2 py-2 font-normal first:pl-0">{label}</th>)}</tr></thead><tbody>{nativeArms.map(arm => { const m = (verified.report!.value as unknown as NativeReport).calculation[scenario][arm].metrics; return <tr key={arm} className="border-t"><th scope="row" className="py-2 pr-2 font-normal">{arm}</th>{[percent(m.total_return), usd(m.terminal_equity), percent(m.max_drawdown), usd(m.friction_usd), String(m.fills)].map((value, index) => <td key={index} className="whitespace-nowrap px-2 py-2">{value}</td>)}</tr> })}</tbody></table></div>
            <p className="text-xs text-muted-foreground">{w.arms}</p><p className="text-xs text-muted-foreground">{w.costs}</p>
          </>}
          <div className="flex flex-wrap gap-2"><Button className="min-h-11" variant="outline" onClick={() => download(verified.admission, job.job_id, 'admission')}>{w.admissionDownload}</Button>{verified.report && <Button className="min-h-11" variant="outline" onClick={() => download(verified.report!, job.job_id, 'report')}>{w.reportDownload}</Button>}{verified.decision && <Button className="min-h-11" variant="outline" onClick={() => download(verified.decision!, job.job_id, 'decision')}>{w.decisionDownload}</Button>}</div>
        </>}
        <details className="text-xs"><summary className="min-h-11 cursor-pointer py-3 text-muted-foreground">{w.identity}</summary><dl className="grid min-w-0 gap-2 sm:grid-cols-2">{[[w.id, job.job_id], [w.request, job.request_digest], [w.protocol, job.request.protocol_ref?.digest ?? '—'], [w.packageHash, job.request.package_ref?.digest ?? '—'], [w.grantHash, job.request.grant_ref?.digest ?? '—'], [w.created, job.created_at], [w.completed, job.completed_at ?? '—'], ['Admission SHA-256', job.admission.digest], ...(job.report ? [['Report SHA-256', job.report.digest]] : []), ...(job.decision ? [['Decision SHA-256', job.decision.digest]] : [])].map(([label, value]) => <div key={label}><dt className="text-muted-foreground">{label}</dt><dd className="break-all font-mono">{value}</dd></div>)}</dl></details>
      </section>}
      {job && verified && job.state !== 'running' && <section aria-labelledby="native-decision" className="space-y-3 border-t pt-4">
        <h3 id="native-decision" className="font-medium">{w.decision}</h3>
        {verified.decision ? <p className="break-words text-sm">{verified.decision.value.disposition === 'reject' ? w.reject : w.watch} · {String(verified.decision.value.reason)}</p> : <>
          <p className="text-sm text-muted-foreground">{w.decisionHelp}</p>
          <div className="flex flex-wrap gap-2">{(['reject', 'watch'] as const).map(value => <Button key={value} className="min-h-11" variant={disposition === value ? 'secondary' : 'outline'} aria-pressed={disposition === value} disabled={!!pendingDecision || saving} onClick={() => setDisposition(value)}>{value === 'reject' ? w.reject : w.watch}</Button>)}</div>
          <label className="block space-y-1 text-sm"><span>{w.reason}</span><textarea className={control} maxLength={1000} rows={3} value={pendingDecision?.body.reason ?? reason} disabled={!!pendingDecision || saving} onChange={event => setReason(event.target.value)} /></label>
          {pendingDecision ? <><p className="text-sm text-muted-foreground">{w.pendingDecision}</p><Button className="min-h-11" disabled={saving} onClick={() => void decide(pendingDecision)}>{w.retryDecision}</Button></> : <Button className="min-h-11" disabled={!reason.trim() || saving} onClick={() => void decide()}>{w.saveDecision}</Button>}
        </>}
      </section>}
      <section aria-labelledby="native-reopen" className="space-y-3 border-t pt-4">
        <h3 id="native-reopen" className="font-medium">{w.reopen}</h3>
        <label className="block space-y-1 text-sm"><span>{w.id}</span><input className={`${control} font-mono`} value={openId} spellCheck={false} autoCapitalize="none" onChange={event => setOpenId(event.target.value)} /></label>
        <div className="flex flex-wrap gap-2"><Button className="min-h-11" variant="outline" disabled={!openId || reading} onClick={reopen}>{w.open}</Button>{job && job.state !== 'running' && !submitting && <Button className="min-h-11" variant="ghost" onClick={startAnother}>{w.newStudy}</Button>}</div>
      </section>
    </div>
  </Page>
}
