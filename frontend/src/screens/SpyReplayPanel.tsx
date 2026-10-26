import { useEffect, useRef, useState } from 'react'
import { Page } from '@/components/page'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { usePreferences } from '@/lib/preferences'
import { spyReplayApi, replayUuid, replayReport, SpyReplayError, type ReplayOptions, type ReplayRequest, type ReplayJob, type ReplayArtifact, type ReplayDecisionRequest, type ReplayReport, type ReplaySampleFreshness, type ReplaySampleFact } from '@/lib/spy-replay-api'

const STORAGE = 'quantmesh.spy-replay.v1'
type Intent = { key: string; request: ReplayRequest; refused?: 'input_pin_mismatch' | 'input_not_qualified' | 'invalid_request'; decision?: { key: string; body: ReplayDecisionRequest } }
const pin = (v: unknown): v is ReplayRequest => !!v && typeof v === 'object' && ['snapshot_digest', 'protocol_digest'].every(k => /^[a-f0-9]{64}$/.test(String((v as Record<string, unknown>)[k])))
function retained(id?: string): Intent | null {
  try { const v = JSON.parse(localStorage.getItem(id ? `${STORAGE}.${id}` : STORAGE) ?? 'null') as Intent | null
    if (!v || !replayUuid(v.key) || !pin(v.request)) return null
    if (v.decision && (!replayUuid(v.decision.key) || !['reject', 'watch'].includes(v.decision.body?.disposition) || typeof v.decision.body.reason !== 'string' || !pin({ snapshot_digest: v.decision.body.request_digest, protocol_digest: v.decision.body.report_digest }))) return { key: v.key, request: v.request }
    return { key: v.key, request: v.request, ...(v.decision ? { decision: v.decision } : {}), ...(['input_pin_mismatch', 'input_not_qualified', 'invalid_request'].includes(String(v.refused)) ? { refused: v.refused } : {}) }
  } catch { return null }
}
function save(v: Intent) { try { const bytes = JSON.stringify(v); localStorage.setItem(`${STORAGE}.${v.key}`, bytes); localStorage.setItem(STORAGE, bytes); return true } catch { return false } }
const control = 'min-h-11 w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50'
const words = {
  en: { title: 'SPY historical replay', subtitle: 'One fixed experiment. Read the original report, then record one final research decision.', input: 'Frozen input', model: 'SPY · SMA100 long / cash', window: '100 warmup sessions · 21 observation sessions', capital: '$100,000 initial capital', costs: '5 bps base · 10 bps stress, one way', compare: 'Same-cost buy-and-hold · cash at 0% interest', insufficient: 'Insufficient financial evidence', guard: 'This replay cannot authorize Paper. Independent out-of-sample and paper evidence are still required.', engineering: 'Engineering fixture · not real-data qualification', reviewed: 'Reviewed frozen input', unavailable: 'No qualified input is configured. An existing job can still be reopened.', loading: 'Reading replay configuration…', start: 'Start fixed replay', waiting: 'Waiting for server acknowledgement…', recover: 'Read status with the same ID', retry: 'Retry the saved request with the same key', retained: 'Request saved before submission. After an uncertain response, read this ID first.', job: 'Replay status', nojob: 'Start a replay or reopen an existing job.', running: 'Running', succeeded: 'Report ready', failed: 'Failed', interrupted: 'Interrupted · no automatic recomputation', polling: 'Status checks paused. Read status to continue.', reopen: 'Reopen by job ID', open: 'Open job', report: 'Original report', verify: 'Verifying original report bytes…', retryReport: 'Read original report again', reportPending: 'Report rendering awaits the frozen metric contract. The verified original is available below.', download: 'Download original report', decision: 'Final research decision', decisionHelp: 'Choose once. The decision binds this request and the verified original report; it cannot be edited.', reject: 'Reject', watch: 'Watch', reason: 'Reason', record: 'Record final decision', pendingDecision: 'The saved decision is awaiting acknowledgement. Read the job before retrying the same decision key.', retryDecision: 'Retry the saved decision', final: 'Final decision recorded', downloadDecision: 'Download original decision', lineage: 'Input and artifact identity', dates: 'Observation window', frozen: 'Frozen at', asof: 'As of', newJob: 'Start another fixed replay', error: 'The operation could not be confirmed. Your saved ID and request are retained.', storage: 'This browser could not save the request. No submission was sent.', conflict: 'A request or decision conflict was reported. Read the job to inspect its original record.', notfound: 'This ID is not currently recorded by the service. No new request was sent.', artifact: 'The original artifact could not be verified. Decision recording remains unavailable.', invalidId: 'Enter a canonical UUID job ID.', busy: 'Reading server state…', snapshot: 'Snapshot SHA-256', protocol: 'Protocol SHA-256', request: 'Request SHA-256', digest: 'Report SHA-256', source: 'Source', noSplit: 'Fee / spread / slippage breakdown is unavailable; never treated as zero.' },
  'zh-CN': { title: 'SPY 历史回放', subtitle: '完成一次固定实验，阅读原始报告，再留下一条最终研究决定。', input: '冻结输入', model: 'SPY · SMA100 持有 / 现金', window: '100 个预热交易日 · 21 个观察交易日', capital: '初始资金 100,000 美元', costs: '基准单边 5 bps · 压力单边 10 bps', compare: '同成本买入持有 · 现金利息 0%', insufficient: '金融证据不足', guard: '本回放不能授权 Paper；仍需独立样本外验证与模拟交易证据。', engineering: '工程样本 · 不代表真实数据资格通过', reviewed: '已审阅的冻结输入', unavailable: '当前没有配置合格输入；仍可按 ID 重开已有任务。', loading: '正在读取回放配置…', start: '开始固定回放', waiting: '等待服务端确认…', recover: '按原 ID 读取状态', retry: '使用原键重试已保存请求', retained: '请求已在提交前保存。响应不确定时，先读取这个 ID。', job: '回放状态', nojob: '开始一次回放，或重开已有任务。', running: '运行中', succeeded: '报告已就绪', failed: '失败', interrupted: '已中断 · 不会自动重算', polling: '自动状态查询已暂停，可手动继续读取。', reopen: '按任务 ID 重开', open: '打开任务', report: '原始报告', verify: '正在校验原始报告字节…', retryReport: '重新读取原始报告', reportPending: '指标展示等待冻结的报告契约；已校验的原始报告可在下方下载。', download: '下载原始报告', decision: '最终研究决定', decisionHelp: '仅能记录一次，绑定本次请求与已校验原始报告，提交后不可编辑。', reject: '拒绝', watch: '观察', reason: '理由', record: '记录最终决定', pendingDecision: '已保存的决定等待确认。请先读取任务，再使用原决定键重试。', retryDecision: '重试已保存决定', final: '已记录最终决定', downloadDecision: '下载原始决定', lineage: '输入与产物标识', dates: '观察窗口', frozen: '冻结时间', asof: '截至时间', newJob: '开始另一轮固定回放', error: '尚无法确认操作结果；已保存的 ID 与请求仍被保留。', storage: '浏览器无法保存请求，因此没有发送提交。', conflict: '服务端报告请求或决定冲突，请读取任务查看原记录。', notfound: '服务端当前没有这个 ID 的记录；没有发送新请求。', artifact: '无法校验原始产物；决定提交仍不可用。', invalidId: '请输入规范 UUID 任务 ID。', busy: '正在读取服务端状态…', snapshot: '快照 SHA-256', protocol: '协议 SHA-256', request: '请求 SHA-256', digest: '报告 SHA-256', source: '来源', noSplit: '费用 / 价差 / 滑点拆分不可用，不按零处理。' },
}
type ErrorKind = 'error' | 'storage' | 'conflict' | 'notfound' | 'artifact' | 'invalidId'
type Step = 'input' | 'report' | 'decision'
type Scenario = 'base5' | 'stress10'
const flow = {
  en: { navigation: 'Replay workflow', input: 'Input', report: 'Report', decision: 'Decision', next: 'Continue to decision', back: 'Review report', tools: 'Reopen and job tools', details: 'Input timing and limitations', metrics: 'Annualized metrics and limitations', safety: 'Paper unavailable · financial evidence insufficient', contract: 'SPY · SMA100 · 100 + 21 sessions · $100,000', cash: 'Cash · 0% interest', sourcePending: 'Original input identity is being read', base: 'Base · 5 bps one way', stress: 'Stress · 10 bps one way', summary: 'Strategy net return', retryOptions: 'Read configuration again' },
  'zh-CN': { navigation: '回放步骤', input: '输入', report: '报告', decision: '决定', next: '继续记录决定', back: '回看报告', tools: '重开与任务工具', details: '输入时间与限制', metrics: '年化指标与限制', safety: 'Paper 不可用 · 金融证据不足', contract: 'SPY · SMA100 · 100 + 21 个交易日 · 100,000 美元', cash: '现金 · 利息 0%', sourcePending: '正在读取原始输入标识', base: '基准 · 单边 5 bps', stress: '压力 · 单边 10 bps', summary: '策略净收益率', retryOptions: '重新读取配置' },
}
function issue(cause: unknown): ErrorKind { return cause instanceof SpyReplayError && cause.status === 409 ? 'conflict' : cause instanceof SpyReplayError && cause.status === 404 ? 'notfound' : 'error' }
function download(value: ReplayArtifact, name: string) { const url = URL.createObjectURL(new Blob([value.bytes], { type: 'application/json' })); const link = document.createElement('a'); link.href = url; link.download = name; link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000) }

export function SpyReplayPanel() {
  const { locale } = usePreferences(); const w = words[locale]; const u = flow[locale]
  const [options, setOptions] = useState<ReplayOptions | null>(null)
  const [intent, setIntent] = useState<Intent | null>(() => retained(new URLSearchParams(location.search).get('spy_job') ?? undefined) ?? retained())
  const [job, setJob] = useState<ReplayJob | null>(null)
  const [report, setReport] = useState<ReplayArtifact | null>(null)
  const [decisionArtifact, setDecisionArtifact] = useState<ReplayArtifact | null>(null)
  const [error, setError] = useState<ErrorKind | null>(null)
  const [artifactError, setArtifactError] = useState(false)
  const [busy, setBusy] = useState(false)
  const [paused, setPaused] = useState(false)
  const [openId, setOpenId] = useState(() => new URLSearchParams(location.search).get('spy_job') ?? retained()?.key ?? '')
  const [disposition, setDisposition] = useState<'reject' | 'watch'>('watch')
  const [reason, setReason] = useState('')
  const [selectedStep, setSelectedStep] = useState<Step | null>(null)
  const [scenario, setScenario] = useState<Scenario>('base5')
  const generation = useRef(0); const alive = useRef(true); const currentIntent = useRef(intent); const currentJob = useRef(job); const locked = useRef(false)
  function retain(value: Intent) { if (!save(value)) { setError('storage'); return false } currentIntent.current = value; setIntent(value); return true }
  function accept(value: ReplayJob, token: number) {
    if (!alive.current || token !== generation.current) return
    const old = currentJob.current
    if (old?.job_id === value.job_id && (Date.parse(old.updated_at) > Date.parse(value.updated_at) || (old.state !== 'running' && value.state === 'running') || (old.decision && !value.decision))) return
    currentJob.current = value; setJob(value); setError(null)
    const pending = currentIntent.current?.key === value.job_id ? currentIntent.current : retained(value.job_id)
    const next: Intent = { key: value.job_id, request: value.request, ...(pending?.decision ? { decision: pending.decision } : {}) }
    retain(next); setOpenId(value.job_id)
    const url = new URL(location.href); url.searchParams.set('engine', 'spy-replay'); url.searchParams.set('spy_job', value.job_id); history.replaceState(null, '', url)
  }
  async function read(id: string, expected?: ReplayRequest) {
    if (!replayUuid(id)) { setError('invalidId'); return }
    const token = generation.current
    try { accept(await spyReplayApi.get(id, expected), token) } catch (cause) { if (alive.current && token === generation.current) { setError(issue(cause)); setPaused(true) } }
  }
  async function loadOptions() { try { const v = await spyReplayApi.options(); if (alive.current) setOptions(v) } catch { if (alive.current) setError('error') } }
  useEffect(() => {
    alive.current = true; void loadOptions()
    const id = new URLSearchParams(location.search).get('spy_job') ?? currentIntent.current?.key
    if (id) void read(id, currentIntent.current?.key === id ? currentIntent.current.request : undefined)
    const lifetime = generation
    return () => { alive.current = false; lifetime.current++ }
  // The saved intent is read only at mount; subsequent recovery is explicit.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])
  useEffect(() => {
    if (job?.state !== 'running' || paused) return
    let count = 0
    const timer = setInterval(() => { if (++count > 60) { clearInterval(timer); setPaused(true); return }; void read(job.job_id, job.request) }, 3000)
    return () => clearInterval(timer)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [job?.job_id, job?.state, paused])
  async function fetchArtifacts(value: ReplayJob, token: number) {
    setArtifactError(false)
    try {
      const result = await spyReplayApi.artifact(value, 'report')
      if (!alive.current || token !== generation.current) return
      setReport(result)
      if (value.decision_ref) {
        const original = await spyReplayApi.artifact(value, 'decision')
        if (alive.current && token === generation.current) setDecisionArtifact(original)
      }
    } catch { if (alive.current && token === generation.current) setArtifactError(true) }
  }
  useEffect(() => { setReport(null); setDecisionArtifact(null); if (job?.state === 'succeeded') void fetchArtifacts(job, generation.current)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [job?.job_id, job?.report?.digest, job?.decision_ref?.digest])
  async function submit(saved: Intent) {
    if (locked.current) return
    // A new attempt makes an earlier refusal obsolete before its response can be
    // lost. An uncertain retry must recover this same key, including after reload.
    const pending: Intent = { key: saved.key, request: saved.request, ...(saved.decision ? { decision: saved.decision } : {}) }
    if (!retain(pending)) return
    locked.current = true; setBusy(true); setError(null)
    const token = generation.current
    try {
      const value = await spyReplayApi.submit(saved.key, saved.request); accept(value, token)
      if (alive.current && token === generation.current) void read(value.job_id, value.request)
    } catch (cause) {
      if (alive.current && token === generation.current) {
        if (cause instanceof SpyReplayError && cause.status === 422 && ['input_pin_mismatch','input_not_qualified','invalid_request'].includes(cause.code)) retain({ ...pending, refused: cause.code as Intent['refused'] })
        setError(issue(cause))
      }
    }
    finally { locked.current = false; if (alive.current) setBusy(false) }
  }
  function start() {
    if (!options?.configured || !options.input || locked.current) return
    const next: Intent = { key: options.input.evidence_kind === 'reviewed_opend_policy_exception_once_v3' ? options.input.policy_exception!.job_idempotency_key : crypto.randomUUID(), request: { snapshot_digest: options.input.snapshot_digest, protocol_digest: options.input.protocol_digest } }
    if (!retain(next)) return
    generation.current++; currentJob.current = null; setJob(null); setReport(null); setDecisionArtifact(null); setPaused(false); setSelectedStep(null); setScenario('base5')
    void submit(next)
  }
  async function record(retry = false) {
    if (locked.current || !job || !report || report.digest !== job.report?.digest || job.decision || intent?.key !== job.job_id) return
    const proposal = retry ? intent.decision : { key: crypto.randomUUID(), body: { request_digest: job.request_digest, report_digest: report.digest, disposition, reason: reason.trim() } }
    if (!proposal || !proposal.body.reason || proposal.body.reason.length > 1000) return
    if (!retain({ ...intent, decision: proposal })) return
    locked.current = true; setBusy(true); setError(null); const token = generation.current
    try {
      const value = await spyReplayApi.decide(job, proposal.key, proposal.body); accept(value, token)
      if (alive.current && token === generation.current) void read(value.job_id, value.request)
    } catch (cause) { if (alive.current && token === generation.current) setError(issue(cause)) }
    finally { locked.current = false; if (alive.current) setBusy(false) }
  }
  function open() {
    if (!replayUuid(openId)) { setError('invalidId'); return }
    generation.current++; currentJob.current = null; setJob(null); setReport(null); setDecisionArtifact(null); setPaused(false); setSelectedStep(null); setScenario('base5')
    void read(openId, intent?.key === openId ? intent.request : undefined)
  }
  const state = job ? w[job.state] : busy ? w.waiting : w.nojob
  const verifiedReport = report && job ? replayReport(report.value, job) : null
  const available: Record<Step, boolean> = { input: true, report: job?.state === 'succeeded', decision: !!job?.decision || (!!verifiedReport && !artifactError) }
  const automaticStep: Step = job?.decision ? 'decision' : job?.state === 'succeeded' ? 'report' : 'input'
  const step = selectedStep && available[selectedStep] ? selectedStep : automaticStep
  const evidenceKind = verifiedReport?.evidence_kind ?? (!job ? options?.input?.evidence_kind : null)
  const onceInput = options?.input?.evidence_kind === 'reviewed_opend_policy_exception_once_v3' ? options.input.policy_exception : undefined
  const exceptionLabel = locale === 'zh-CN' ? '私人诊断 · 单次内部政策例外' : 'Private diagnostic · Single-use internal policy exception'
  const percent = (v: number) => new Intl.NumberFormat(locale, { style: 'percent', maximumFractionDigits: 2 }).format(v)
  return <Page title={w.title} description={w.subtitle}>
    <div className="space-y-2 border-b pb-4">
      <div className="flex flex-wrap items-center gap-2"><Badge variant="outline" className="h-auto whitespace-normal border-amber-500/40 text-amber-600 dark:text-amber-400">{u.safety}</Badge>
        {evidenceKind && <Badge variant="outline" className="h-auto whitespace-normal">{evidenceKind === 'engineering_fixture' ? w.engineering : evidenceKind === 'reviewed_opend_policy_exception_once_v3' ? exceptionLabel : w.reviewed}</Badge>}
      </div>
      <p className="text-sm">{u.contract}</p>
      <p className="text-xs text-muted-foreground">{w.costs} · {w.compare}</p>
      {verifiedReport && <p className="text-sm tabular-nums">{u.summary}: <span className="font-medium">5 bps {percent(verifiedReport.calculation.scenarios.base5.strategy.metrics.total_return)}</span><span className="px-2 text-muted-foreground">/</span><span className="font-medium">10 bps {percent(verifiedReport.calculation.scenarios.stress10.strategy.metrics.total_return)}</span><span className="ml-3 text-xs text-muted-foreground">{verifiedReport.window.score_start} → {verifiedReport.window.score_end}</span></p>}
      {job && !evidenceKind && <p className="text-xs text-muted-foreground">{u.sourcePending}</p>}
    </div>
    {error && <p role="alert" className="border-l border-destructive py-2 pl-3 text-sm">{w[error]}</p>}
    <div className="flex flex-wrap items-center justify-between gap-3">
      <nav aria-label={u.navigation} className="flex flex-wrap gap-1">{(['input','report','decision'] as const).map((item, index) => <Button key={item} variant={step === item ? 'secondary' : 'ghost'} className="min-h-11" disabled={!available[item]} aria-current={step === item ? 'step' : undefined} onClick={() => setSelectedStep(item)}><span aria-hidden="true" className="mr-1 text-muted-foreground">{index + 1}</span>{u[item]}</Button>)}</nav>
      <p role="status" aria-live="polite" className="text-sm">{state}</p>
    </div>
    {busy && job && <p className="text-sm text-muted-foreground">{w.busy}</p>}
    {paused && job?.state === 'running' && <p className="text-sm text-muted-foreground">{w.polling}</p>}
    <div className="max-w-5xl">
      {step === 'input' && <section aria-labelledby="spy-input" className="max-w-2xl space-y-4">
        <h3 id="spy-input" className="text-base font-semibold">{job ? (locale === 'zh-CN' ? '下一轮回放的配置' : 'Configuration for the next replay') : w.input}</h3>
        {job && <p className="text-sm text-muted-foreground">{locale === 'zh-CN' ? '已打开的报告保留原来的输入与日期。' : 'The opened report keeps its original input and dates.'}</p>}
        {options?.input ? <div className="space-y-2 text-sm">
          {job && <Badge variant="outline" className="h-auto whitespace-normal">{options.input.evidence_kind === 'engineering_fixture' ? w.engineering : onceInput ? exceptionLabel : w.reviewed}</Badge>}
          <p>{w.dates}: <span className="font-mono">{options.input.observation_start} → {options.input.observation_end}</span></p>
          <details className="text-xs text-muted-foreground"><summary className="flex min-h-11 cursor-pointer items-center">{u.details}</summary><div className="space-y-2 pb-2"><p className="break-words">{w.asof}: {options.input.as_of_utc}<br />{w.frozen}: {options.input.frozen_at_utc}</p>{options.input.limitations.map((v, i) => <p key={i}>{v}</p>)}</div></details>
        </div> : <p className="text-sm text-muted-foreground">{options ? w.unavailable : w.loading}</p>}
        {!options && error && <Button className="min-h-11" variant="outline" onClick={() => void loadOptions()}>{u.retryOptions}</Button>}
        {onceInput && <p className="text-sm">{exceptionLabel} · {locale === 'zh-CN' ? '外部 API 原件保存适用性：未知' : 'External API storage applicability: Unknown'}</p>}
        {!intent && <Button className="min-h-11" disabled={!options?.configured || busy} onClick={start}>{onceInput ? (locale === 'zh-CN' ? '开始或重开本次诊断' : 'Start or reopen this diagnostic') : w.start}</Button>}
        {intent && !job && <div className="space-y-3"><p className="text-sm text-muted-foreground">{w.retained}</p><code className="block break-all text-xs">{intent.key}</code>
          <Button className="min-h-11" variant="outline" disabled={busy} onClick={() => void read(intent.key, intent.request)}>{w.recover}</Button>
          {!busy && <Button className="min-h-11" variant="outline" onClick={() => void submit(intent)}>{w.retry}</Button>}
          {intent.refused && <Button className="min-h-11" variant="outline" disabled={busy || !options?.configured} onClick={start}>{locale === 'zh-CN' ? '使用当前配置的输入开始' : 'Start with current configured input'}</Button>}</div>}
        {job && (job.state === 'failed' || job.state === 'interrupted' || !!job.decision) && !busy && <Button className="min-h-11" variant="outline" disabled={!options?.configured} onClick={start}>{onceInput ? (locale === 'zh-CN' ? '重开本次诊断' : 'Reopen this diagnostic') : w.newJob}</Button>}
        {job && <Button className="min-h-11" variant="outline" disabled={busy} onClick={() => { setPaused(false); void read(job.job_id, job.request) }}>{w.recover}</Button>}
      </section>}
      {step === 'report' && job?.state === 'succeeded' && <section aria-labelledby="spy-report" className="space-y-3"><h3 id="spy-report" className="font-semibold">{w.report}</h3>
        {artifactError ? <><p role="alert" className="text-sm">{w.artifact}</p><Button className="min-h-11" variant="outline" onClick={() => void fetchArtifacts(job, generation.current)}>{w.retryReport}</Button></> : !report ? <p className="text-sm text-muted-foreground">{w.verify}</p> : <>
          <ReportSample report={verifiedReport!} freshness={job.sample_freshness_view} locale={locale} />
          <ReportView artifact={report} job={job} locale={locale} scenario={scenario} onScenario={setScenario} />
          <div className="flex flex-wrap gap-2 border-t pt-3"><Button className="min-h-11" onClick={() => setSelectedStep('decision')}>{u.next}</Button><Button variant="outline" className="min-h-11" onClick={() => download(report, `${job.job_id}-report.json`)}>{w.download}</Button></div>
        </>}
      </section>}
      {step === 'decision' && job?.state === 'succeeded' && <section aria-labelledby="spy-decision" className="max-w-2xl space-y-3"><h3 id="spy-decision" className="font-semibold">{w.decision}</h3>
            {artifactError && <p role="alert" className="text-sm">{w.artifact}</p>}
            {job.decision ? <><p className="text-sm font-medium">{w.final} · {w[job.decision.disposition]}</p><p className="whitespace-pre-wrap break-words text-sm">{job.decision.reason}</p><p className="text-xs text-muted-foreground">{job.decision.created_at}</p>{decisionArtifact && <Button variant="outline" className="min-h-11" onClick={() => download(decisionArtifact, `${job.job_id}-decision.json`)}>{w.downloadDecision}</Button>}</> : <>
              <p className="text-sm text-muted-foreground">{w.decisionHelp}</p>
              {intent?.decision ? <><p className="text-sm">{w.pendingDecision}</p><p className="whitespace-pre-wrap break-words text-sm">{w[intent.decision.body.disposition]} · {intent.decision.body.reason}</p><Button className="min-h-11" disabled={busy || !report || artifactError} onClick={() => void record(true)}>{w.retryDecision}</Button></> : <form className="space-y-3" onSubmit={e => { e.preventDefault(); void record() }}>
                <fieldset disabled={busy || !report || artifactError} className="flex gap-5"><legend className="sr-only">{w.decision}</legend>{(['reject', 'watch'] as const).map(v => <label key={v} className="flex min-h-11 items-center gap-2 text-sm"><input type="radio" name="spy-disposition" value={v} checked={disposition === v} onChange={() => setDisposition(v)} />{w[v]}</label>)}</fieldset>
                <label htmlFor="spy-reason" className="block text-sm">{w.reason}</label><textarea id="spy-reason" maxLength={1000} rows={3} value={reason} onChange={e => setReason(e.target.value)} disabled={busy || !report || artifactError} className={control} />
                <Button className="min-h-11" type="submit" disabled={busy || !report || artifactError || !reason.trim()}>{w.record}</Button>
              </form>}
            </>}
        <Button className="min-h-11" variant="outline" onClick={() => setSelectedStep('report')}>{u.back}</Button>
      </section>}
    </div>
    <details className="border-t text-sm"><summary className="min-h-11 cursor-pointer py-3">{u.tools}{job ? ` · ${job.job_id.slice(0, 8)}` : ''}</summary><div className="max-w-2xl space-y-3 pb-3">
      {job && <><p className="break-all font-mono text-xs text-muted-foreground">{job.job_id}</p>{step !== 'input' && <Button className="min-h-11" variant="outline" disabled={busy} onClick={() => { setPaused(false); void read(job.job_id, job.request) }}>{w.recover}</Button>}</>}
      <form className="space-y-2" onSubmit={e => { e.preventDefault(); open() }}><label className="block text-sm" htmlFor="spy-open">{w.reopen}</label><div className="flex flex-wrap gap-2"><input id="spy-open" value={openId} onChange={e => setOpenId(e.target.value.trim())} className={`${control} min-w-0 flex-1 font-mono`} autoCapitalize="none" spellCheck={false} /><Button className="min-h-11" variant="outline" disabled={busy} type="submit">{w.open}</Button></div></form>
        {(job || options?.input) && <details className="border-t pt-4 text-xs"><summary className="min-h-11 cursor-pointer text-sm">{w.lineage}</summary><dl className="space-y-3">{[[w.snapshot, job?.request.snapshot_digest ?? options?.input?.snapshot_digest], [w.protocol, job?.request.protocol_digest ?? options?.input?.protocol_digest], [w.request, job?.request_digest], [w.digest, job?.report?.digest]].filter(([,v]) => v).map(([label,value]) => <div key={label}><dt className="text-muted-foreground">{label}</dt><dd className="break-all font-mono">{value}</dd></div>)}</dl></details>}
    </div></details>
  </Page>
}

function ReportSample({ report, freshness, locale }: { report: ReplayReport; freshness?: ReplaySampleFreshness; locale: 'en' | 'zh-CN' }) {
  // Only immutable report facts enter this component. Current options describe
  // the next input and must never fill evidence gaps in an older saved report.
  const zh = locale === 'zh-CN'
  const unknown = zh ? '未知' : 'Unknown'
  const sample = report.schema_version >= 2 ? report.sample_evidence : undefined
  const policy = report.schema_version === 3 ? sample?.policy_exception : undefined
  const synthetic = report.evidence_kind === 'engineering_fixture'
  const fact = (value?: ReplaySampleFact) => {
    if (!value) return unknown
    if (value.value === null) return value.status === 'synthetic' || value.status === 'not_applicable' ? (synthetic ? (zh ? 'N/A · 合成样本' : 'N/A · synthetic') : 'N/A') : unknown
    return value.status === 'synthetic' ? `${value.value} · ${zh ? '合成声明' : 'synthetic declaration'}` : value.value
  }
  // The GET view is ephemeral. Validate its report calendar/role association
  // after the artifact arrives; never reuse a newer input's age or timestamps.
  const roles = { fixed_golden: 'fixed_regression_not_required', historical_diagnostic: 'historical_diagnostic', rolling_diagnostic: 'recent_diagnostic' }
  const view = freshness && freshness.evaluated_snapshot_digest === report.snapshot_digest
    && (freshness.calendar_version === null || freshness.calendar_version === report.window.calendar_version)
    && (freshness.applicability === 'unknown' || (sample && freshness.applicability === roles[sample.sample_role])) ? freshness : undefined
  const freshnessReasons: Record<ReplaySampleFreshness['reason'], string> = {
    fixed_sample_no_daily_refresh: zh ? '固定工程样本，无需每日刷新' : 'No daily refresh required',
    historical_window_not_recency_target: zh ? '历史诊断窗口，不以近期覆盖为目标' : 'Historical diagnostic window, not a recency target',
    current: zh ? '已覆盖近期样本目标' : 'Current for its recent-sample target',
    lags_latest_complete_session: zh ? `落后 ${view?.lag_complete_sessions} 个已完成会话` : `${view?.lag_complete_sessions} completed sessions behind`,
    legacy_sample_role_unknown: zh ? '未知 · 旧报告未记录样本角色' : 'Unknown · legacy sample role not recorded',
    calendar_unavailable: zh ? '未知 · 原始日历不可用' : 'Unknown · original calendar unavailable',
    report_unavailable: zh ? '未知 · 原始报告不可用' : 'Unknown · original report unavailable',
    input_identity_mismatch: zh ? '未知 · 输入身份不匹配' : 'Unknown · input identity mismatch',
    sample_end_after_latest_complete: zh ? '未知 · 截止超过最新完整会话' : 'Unknown · sample ends after latest completed session',
  }
  const role = sample?.sample_role === 'fixed_golden' ? (zh ? '固定工程回归' : 'Fixed engineering regression') : sample?.sample_role === 'rolling_diagnostic' ? (zh ? '近期历史诊断，非独立样本外' : 'Recent historical diagnostic, not independent OOS') : sample ? (zh ? '历史阶段诊断，非独立样本外' : 'Historical diagnostic, not independent OOS') : synthetic ? (zh ? '未知 · 仅知工程来源类别' : 'Unknown · engineering evidence kind only') : (zh ? '未知 · 仅知真实来源类别' : 'Unknown · real-source evidence kind only')
  const structural = sample ? `${sample.quality.rows} ${zh ? '行；缺失' : 'rows; missing'} ${sample.quality.missing_sessions}; ${zh ? '重复' : 'duplicates'} ${sample.quality.duplicate_sessions}` : unknown
  const facts = [
    [zh ? '快照 SHA-256' : 'Snapshot SHA-256', report.snapshot_digest],
    [zh ? '协议 SHA-256' : 'Protocol SHA-256', report.protocol_digest],
    [zh ? '样本标识 / 版本' : 'Sample ID / version', sample ? `${sample.sample_id} / ${sample.sample_version}` : unknown],
    [zh ? '原始截至时间' : 'Original as-of', sample?.as_of_utc ?? report.window.as_of_utc ?? unknown],
    [sample?.timestamp_basis === 'synthetic_declared' ? (zh ? '冻结时间 · 合成声明' : 'Freeze time · synthetic declaration') : (zh ? '冻结时间' : 'Freeze time'), sample?.frozen_at_utc ?? unknown],
    [zh ? '实际请求时间' : 'Actual requested time', fact(sample?.times.requested_at_utc)],
    [zh ? '实际接收时间' : 'Actual received time', fact(sample?.times.received_at_utc)],
    [zh ? '实际 POST 审阅时间' : 'Actual POST-reviewed time', fact(sample?.times.post_reviewed_at_utc)],
    [zh ? '实际审阅时间' : 'Actual reviewed time', fact(sample?.times.acceptance_reviewed_at_utc)],
    [zh ? '实际可用时间' : 'Actual available time', fact(sample?.times.available_at_utc)],
    [zh ? '结构检查' : 'Structural checks', structural],
    [zh ? '来源使用依据' : 'Source use', fact(sample?.source_facts.source_use)],
    [policy ? (zh ? '内部用途' : 'Internal scope') : (zh ? '允许用途' : 'Allowed use'), fact(sample?.source_facts.allowed_use)],
    ...(policy ? [[zh ? '人决定 SHA-256' : 'Human decision SHA-256', policy.once_scope_id], [zh ? '政策原件 SHA-256' : 'Policy document SHA-256', policy.policy_document_ref.digest], [zh ? '唯一采集意图' : 'Single capture intent', policy.capture_intent_id]] : []),
    ['PIT', fact(sample?.source_facts.pit)],
    [zh ? '修订状态' : 'Revision status', fact(sample?.source_facts.revision_status)],
    [zh ? '公司行动覆盖' : 'Action coverage', fact(sample?.source_facts.action_coverage)],
    [zh ? '价格口径 / 币种 / 量单位' : 'Price / currency / volume unit', sample ? [sample.source_facts.price_adjustment, sample.source_facts.currency, sample.source_facts.volume_unit].map(value => fact(value)).join(' / ') : unknown],
    [zh ? '结构复核时间（非供应商审阅）' : 'Structural check time (not provider review)', sample?.last_checked_at_utc ?? unknown],
    [zh ? '复核范围' : 'Check scope', sample ? (sample.check_scope === 'structural_bytes_only' ? (zh ? '结构与字节；非来源资格认证' : 'Structure and bytes; not source qualification') : (zh ? '结构、字节与收据绑定；非独立真实性证明' : 'Structure, bytes and receipt bindings; not independent authenticity proof')) : unknown],
    [zh ? '下次版本触发' : 'Next version trigger', sample ? (sample.next_trigger === 'code_protocol_or_boundary_change' ? (zh ? '代码、协议或边界变化；无需每日刷新' : 'Code, protocol or boundary change; no daily refresh') : (zh ? '新的合格冻结版本；不自动取数' : 'New qualified frozen version; no automatic capture')) : unknown],
    [zh ? '首次查看时间' : 'First viewed time', fact(sample?.first_viewed_at_utc)],
    [zh ? '试验次数' : 'Trial count', `${unknown} · ${zh ? '缺少完整试验历史' : 'trial history unavailable'}`],
    [zh ? '读取时间（独立视图）' : 'Read clock (separate view)', view?.read_at_utc ?? unknown],
  ]
  return <section aria-labelledby="spy-sample" className="space-y-2 rounded-md border px-3 py-3 text-xs">
    <div className="flex flex-wrap items-center justify-between gap-1"><h4 id="spy-sample" className="text-sm font-medium">{zh ? '本报告样本' : "This report's sample"}</h4>{!sample && <span className="text-muted-foreground">{zh ? '旧报告 · 缺失事实保持未知' : 'Legacy report · missing facts remain unknown'}</span>}</div>
    {policy && <p className="text-sm">{zh ? '私人诊断 · 单次内部政策例外 · 外部 API 原件保存适用性：未知' : 'Private diagnostic · Single-use internal policy exception · External API storage applicability: Unknown'}</p>}
    <dl className="grid gap-x-4 gap-y-1 sm:grid-cols-2"><div className="flex flex-wrap gap-x-2"><dt className="text-muted-foreground">{zh ? '角色' : 'Role'}</dt><dd>{role}</dd></div><div className="flex flex-wrap gap-x-2"><dt className="text-muted-foreground">{zh ? '截止会话' : 'Cutoff session'}</dt><dd>{report.window.score_end}</dd></div></dl>
    <p className="text-muted-foreground">{zh ? '结构' : 'Structure'}: {structural} · {zh ? '来源与 PIT 另述' : 'source and PIT are separate'}</p>
    <p className="text-muted-foreground">{zh ? '读取时新鲜度' : 'Read-time freshness'}: {view ? freshnessReasons[view.reason] : (zh ? '未知 · 缺少绑定的读取视图' : 'Unknown · no bound read-time view')}{view?.latest_complete_session && <span className="ml-2">{zh ? '最新完整会话' : 'Latest completed session'}: {view.latest_complete_session}</span>}</p>
    <details><summary className="min-h-11 cursor-pointer py-3 text-muted-foreground">{zh ? '样本身份与证据' : 'Sample identity and evidence'}</summary><dl className="grid gap-x-6 gap-y-2 pb-2 sm:grid-cols-2">{facts.map(([label, value]) => <div key={label}><dt className="text-muted-foreground">{label}</dt><dd className="break-all">{value}</dd></div>)}</dl>
      {sample && <details><summary className="min-h-11 cursor-pointer py-3 text-muted-foreground">{zh ? '原始证据引用（仅哈希）' : 'Original evidence references (hashes only)'}</summary><dl className="space-y-2 pb-2">{Object.entries(sample.refs).map(([label, value]) => <div key={label}><dt className="text-muted-foreground">{label}</dt><dd className="break-all">{value?.digest ?? (synthetic ? (zh ? 'N/A · 合成样本' : 'N/A · synthetic') : unknown)}</dd></div>)}</dl></details>}
    </details>
  </section>
}

function ReportView({ artifact, job, locale, scenario, onScenario }: { artifact: ReplayArtifact; job: ReplayJob; locale: 'en' | 'zh-CN'; scenario: Scenario; onScenario: (value: Scenario) => void }) {
  const r = replayReport(artifact.value, job); const zh = locale === 'zh-CN'; const u = flow[locale]
  const unavailable = zh ? '不可用' : 'Unavailable'
  const number = (v: number | null, percent = false) => v === null ? unavailable : percent ? new Intl.NumberFormat(locale, { style: 'percent', maximumFractionDigits: 2 }).format(v) : new Intl.NumberFormat(locale, { maximumFractionDigits: 2 }).format(v)
  const usd = (v: number) => new Intl.NumberFormat(locale, { style: 'currency', currency: 'USD', maximumFractionDigits: 2 }).format(v)
  return <div className="space-y-4">
    <div aria-label={zh ? '成本场景' : 'Cost scenario'} className="flex flex-wrap gap-1">{(['base5','stress10'] as const).map(key => <Button key={key} className="min-h-11" variant={scenario === key ? 'secondary' : 'ghost'} aria-pressed={scenario === key} onClick={() => onScenario(key)}>{key === 'base5' ? u.base : u.stress}</Button>)}</div>
    {(() => { const s = r.calculation.scenarios[scenario]; return <section className="space-y-2">
      <div className="overflow-x-auto"><table className="w-full text-left text-sm tabular-nums"><caption className="sr-only">{scenario === 'base5' ? (zh ? '基准成本结果' : 'Base cost results') : (zh ? '压力成本结果' : 'Stress cost results')}</caption><thead className="text-xs text-muted-foreground"><tr><th className="py-2 pr-4 font-normal">{zh ? '结果' : 'Result'}</th><th className="py-2 pr-4 text-right font-normal">SMA100</th><th className="py-2 text-right font-normal">{zh ? '买入持有' : 'Buy-and-hold'}</th></tr></thead><tbody>
        {[[zh ? '净收益率' : 'Net return', 'total_return', 'percent'], [zh ? '期末资金' : 'Terminal equity', 'terminal_equity', 'usd'], [zh ? '最大回撤' : 'Max drawdown', 'max_drawdown', 'percent'], [zh ? '综合摩擦成本' : 'Combined friction', 'friction_usd', 'usd'], [zh ? '成交笔数' : 'Fills', 'fills', 'number']].map(([label, metric, format]) => <tr key={metric} className="border-t"><th className="py-2 pr-4 font-normal">{label}</th>{(['strategy','buyhold'] as const).map(track => { const v = s[track].metrics[metric as keyof typeof s.strategy.metrics]; return <td key={track} className="py-2 text-right whitespace-nowrap">{format === 'usd' ? usd(v as number) : number(v, format === 'percent')}</td> })}</tr>)}
      </tbody></table></div>
      <p className="text-xs tabular-nums">{zh ? 'SMA100 入场次数' : 'Long entries'}: {s.strategy.metrics.long_entries == null ? unavailable : number(s.strategy.metrics.long_entries)} · {zh ? '成交名义额 / 初始资金' : 'Traded notional / initial capital'}: {s.strategy.metrics.gross_traded_notional_over_initial_capital == null ? unavailable : `${number(s.strategy.metrics.gross_traded_notional_over_initial_capital)}×`} ({zh ? '非年化' : 'not annualized'})</p>
      <p className="text-xs text-muted-foreground">{zh ? '成交笔数不等于完整交易轮数或独立机会数。' : 'Fills are not round trips or independent opportunities.'}</p>
      <p className="text-sm text-muted-foreground">{zh ? '策略相对买入持有' : 'Strategy minus buy-and-hold'}: {usd(s.comparison.terminal_equity_difference_usd)} · {number(s.comparison.total_return_difference * 100)} {zh ? '个百分点' : 'percentage points'}</p>
      <p className="text-xs text-muted-foreground">{zh ? '综合成本代理；费用 / 价差 / 滑点拆分未经校准。' : 'Combined cost proxy; fee / spread / slippage split is uncalibrated.'}</p>
      <details className="text-xs"><summary className="min-h-11 cursor-pointer py-3 text-muted-foreground">{u.metrics}</summary><p className="mb-3 text-muted-foreground">{zh ? '仅 21 个观察日，年化比率估计不稳定，不构成策略有效性证据；不可用值不按零处理。费用 / 价差 / 滑点拆分未经校准。' : 'Only 21 observation sessions: annualized ratios are unstable diagnostics, not strategy-validity evidence. Undefined values are not zero; fee / spread / slippage split is uncalibrated.'}</p><dl className="mb-3 grid grid-cols-2 gap-x-4 gap-y-2">{[['CAGR', 'cagr', true], [zh ? '年化波动' : 'Annualized volatility', 'annualized_volatility', true], ['Sharpe (rf=0)', 'naive_sharpe_rf_zero', false], ['Sortino (target=0)', 'sortino_target_zero', false], ['Calmar', 'calmar', false]].map(([label, metric, percent]) => <div key={String(metric)}><dt className="text-muted-foreground">{label}</dt><dd>{number(s.strategy.metrics[metric as keyof typeof s.strategy.metrics], !!percent)}</dd></div>)}</dl>{r.limitations.map((limitation, i) => <p key={i} className="mb-2 text-muted-foreground">{limitation}</p>)}</details>
    </section> })()}
    <p className="border-t pt-3 text-sm">{zh ? '现金基准（利息 0%）' : 'Cash benchmark (0% interest)'}: {usd(r.calculation.cash_benchmark.terminal_equity)} · {number(r.calculation.cash_benchmark.total_return, true)} · {zh ? '回撤' : 'drawdown'} {number(r.calculation.cash_benchmark.max_drawdown, true)}</p>
  </div>
}
