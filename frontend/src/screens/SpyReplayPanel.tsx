import { useEffect, useRef, useState } from 'react'
import { Page } from '@/components/page'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { usePreferences } from '@/lib/preferences'
import { spyReplayApi, replayUuid, replayReport, SpyReplayError, type ReplayOptions, type ReplayRequest, type ReplayJob, type ReplayArtifact, type ReplayDecisionRequest } from '@/lib/spy-replay-api'

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
function issue(cause: unknown): ErrorKind { return cause instanceof SpyReplayError && cause.status === 409 ? 'conflict' : cause instanceof SpyReplayError && cause.status === 404 ? 'notfound' : 'error' }
function download(value: ReplayArtifact, name: string) { const url = URL.createObjectURL(new Blob([value.bytes], { type: 'application/json' })); const link = document.createElement('a'); link.href = url; link.download = name; link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000) }

export function SpyReplayPanel() {
  const { locale } = usePreferences(); const w = words[locale]
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
    try { accept(await spyReplayApi.submit(saved.key, saved.request), token) } catch (cause) {
      if (alive.current && token === generation.current) {
        if (cause instanceof SpyReplayError && cause.status === 422 && ['input_pin_mismatch','input_not_qualified','invalid_request'].includes(cause.code)) retain({ ...pending, refused: cause.code as Intent['refused'] })
        setError(issue(cause))
      }
    }
    finally { locked.current = false; if (alive.current) setBusy(false) }
  }
  function start() {
    if (!options?.configured || !options.input || locked.current) return
    const next: Intent = { key: crypto.randomUUID(), request: { snapshot_digest: options.input.snapshot_digest, protocol_digest: options.input.protocol_digest } }
    if (!retain(next)) return
    generation.current++; currentJob.current = null; setJob(null); setReport(null); setDecisionArtifact(null); setPaused(false)
    void submit(next)
  }
  async function record(retry = false) {
    if (locked.current || !job || !report || report.digest !== job.report?.digest || job.decision || intent?.key !== job.job_id) return
    const proposal = retry ? intent.decision : { key: crypto.randomUUID(), body: { request_digest: job.request_digest, report_digest: report.digest, disposition, reason: reason.trim() } }
    if (!proposal || !proposal.body.reason || proposal.body.reason.length > 1000) return
    if (!retain({ ...intent, decision: proposal })) return
    locked.current = true; setBusy(true); setError(null); const token = generation.current
    try { accept(await spyReplayApi.decide(job, proposal.key, proposal.body), token) } catch (cause) { if (alive.current && token === generation.current) setError(issue(cause)) }
    finally { locked.current = false; if (alive.current) setBusy(false) }
  }
  function open() {
    if (!replayUuid(openId)) { setError('invalidId'); return }
    generation.current++; currentJob.current = null; setJob(null); setReport(null); setDecisionArtifact(null); setPaused(false)
    void read(openId, intent?.key === openId ? intent.request : undefined)
  }
  const state = job ? w[job.state] : busy ? w.waiting : w.nojob
  return <Page title={w.title} description={w.subtitle}>
    <div className="flex flex-wrap items-center gap-2"><Badge variant="outline" className="h-auto whitespace-normal border-amber-500/40 text-amber-600 dark:text-amber-400">{w.insufficient}</Badge><span className="text-sm text-muted-foreground">{w.guard}</span></div>
    {error && <p role="alert" className="border-l-2 border-destructive py-2 pl-3 text-sm">{w[error]}</p>}
    <div className="grid gap-8 xl:grid-cols-[minmax(16rem,0.8fr)_minmax(0,1.5fr)]">
      <section aria-labelledby="spy-input" className="space-y-4">
        <h3 id="spy-input" className="text-base font-semibold">{job ? (locale === 'zh-CN' ? '下一轮回放的配置' : 'Configuration for the next replay') : w.input}</h3>
        {job && <p className="text-sm text-muted-foreground">{locale === 'zh-CN' ? '已打开的报告保留原来的输入与日期。' : 'The opened report keeps its original input and dates.'}</p>}
        <p className="text-lg font-medium">{w.model}</p>
        <ul className="space-y-2 text-sm text-muted-foreground"><li>{w.window}</li><li>{w.capital}</li><li>{w.costs}</li><li>{w.compare}</li></ul>
        {options?.input ? <div className="space-y-3 border-y py-4 text-sm">
          <Badge variant="outline" className="h-auto whitespace-normal">{options.input.evidence_kind === 'engineering_fixture' ? w.engineering : w.reviewed}</Badge>
          <p>{w.dates}<br /><span className="font-mono">{options.input.observation_start} → {options.input.observation_end}</span></p>
          <p className="break-words text-muted-foreground">{w.asof}: {options.input.as_of_utc}<br />{w.frozen}: {options.input.frozen_at_utc}</p>
          {options.input.limitations.map((v, i) => <p key={i} className="text-muted-foreground">{v}</p>)}
        </div> : <p className="text-sm text-muted-foreground">{options ? w.unavailable : w.loading}</p>}
        {!intent && <Button className="min-h-11" disabled={!options?.configured || busy} onClick={start}>{w.start}</Button>}
        {intent && !job && <div className="space-y-3"><p className="text-sm text-muted-foreground">{w.retained}</p><code className="block break-all text-xs">{intent.key}</code>
          <Button className="min-h-11" variant="outline" disabled={busy} onClick={() => void read(intent.key, intent.request)}>{w.recover}</Button>
          {!busy && <Button className="min-h-11" variant="outline" onClick={() => void submit(intent)}>{w.retry}</Button>}
          {intent.refused && <Button className="min-h-11" variant="outline" disabled={busy || !options?.configured} onClick={start}>{locale === 'zh-CN' ? '使用当前配置的输入开始' : 'Start with current configured input'}</Button>}</div>}
        {job && (job.state === 'failed' || job.state === 'interrupted' || !!job.decision) && !busy && <Button className="min-h-11" variant="outline" disabled={!options?.configured} onClick={start}>{w.newJob}</Button>}
        <form className="space-y-2 border-t pt-4" onSubmit={e => { e.preventDefault(); open() }}><label className="block text-sm" htmlFor="spy-open">{w.reopen}</label><input id="spy-open" value={openId} onChange={e => setOpenId(e.target.value.trim())} className={`${control} font-mono`} autoCapitalize="none" spellCheck={false} /><Button className="min-h-11" variant="outline" disabled={busy} type="submit">{w.open}</Button></form>
      </section>
      <section aria-labelledby="spy-status" className="min-w-0 space-y-5 border-t pt-5 xl:border-l xl:border-t-0 xl:pl-8 xl:pt-0">
        <div className="flex flex-wrap items-center justify-between gap-3"><div><h3 id="spy-status" className="text-base font-semibold">{w.job}</h3><p role="status" aria-live="polite" className="mt-1 text-sm">{state}</p></div>{job && <Button className="min-h-11" variant="outline" disabled={busy} onClick={() => { setPaused(false); void read(job.job_id, job.request) }}>{w.recover}</Button>}</div>
        {busy && job && <p className="text-sm text-muted-foreground">{w.busy}</p>}
        {job && <p className="break-all font-mono text-xs text-muted-foreground">{job.job_id}</p>}
        {paused && job?.state === 'running' && <p className="text-sm text-muted-foreground">{w.polling}</p>}
        {job?.state === 'succeeded' && <>
          <section aria-labelledby="spy-report" className="space-y-3 border-t pt-4"><h3 id="spy-report" className="font-semibold">{w.report}</h3>
            {artifactError ? <><p role="alert" className="text-sm">{w.artifact}</p><Button variant="outline" onClick={() => void fetchArtifacts(job, generation.current)}>{w.retryReport}</Button></> : !report ? <p className="text-sm text-muted-foreground">{w.verify}</p> : <><ReportView artifact={report} job={job} locale={locale} /><Button variant="outline" className="min-h-11" onClick={() => download(report, `${job.job_id}-report.json`)}>{w.download}</Button></>}
          </section>
          <section aria-labelledby="spy-decision" className="space-y-3 border-t pt-4"><h3 id="spy-decision" className="font-semibold">{w.decision}</h3>
            {job.decision ? <><p className="text-sm font-medium">{w.final} · {w[job.decision.disposition]}</p><p className="whitespace-pre-wrap break-words text-sm">{job.decision.reason}</p><p className="text-xs text-muted-foreground">{job.decision.created_at}</p>{decisionArtifact && <Button variant="outline" className="min-h-11" onClick={() => download(decisionArtifact, `${job.job_id}-decision.json`)}>{w.downloadDecision}</Button>}</> : <>
              <p className="text-sm text-muted-foreground">{w.decisionHelp}</p>
              {intent?.decision ? <><p className="text-sm">{w.pendingDecision}</p><p className="whitespace-pre-wrap break-words text-sm">{w[intent.decision.body.disposition]} · {intent.decision.body.reason}</p><Button className="min-h-11" disabled={busy || !report || artifactError} onClick={() => void record(true)}>{w.retryDecision}</Button></> : <form className="space-y-3" onSubmit={e => { e.preventDefault(); void record() }}>
                <fieldset disabled={busy || !report || artifactError} className="flex gap-5"><legend className="sr-only">{w.decision}</legend>{(['reject', 'watch'] as const).map(v => <label key={v} className="flex min-h-11 items-center gap-2 text-sm"><input type="radio" name="spy-disposition" value={v} checked={disposition === v} onChange={() => setDisposition(v)} />{w[v]}</label>)}</fieldset>
                <label htmlFor="spy-reason" className="block text-sm">{w.reason}</label><textarea id="spy-reason" maxLength={1000} rows={3} value={reason} onChange={e => setReason(e.target.value)} disabled={busy || !report || artifactError} className={control} />
                <Button className="min-h-11" type="submit" disabled={busy || !report || artifactError || !reason.trim()}>{w.record}</Button>
              </form>}
            </>}
          </section>
        </>}
        {(job || options?.input) && <details className="border-t pt-4 text-xs"><summary className="min-h-11 cursor-pointer text-sm">{w.lineage}</summary><dl className="space-y-3">{[[w.snapshot, job?.request.snapshot_digest ?? options?.input?.snapshot_digest], [w.protocol, job?.request.protocol_digest ?? options?.input?.protocol_digest], [w.request, job?.request_digest], [w.digest, job?.report?.digest]].filter(([,v]) => v).map(([label,value]) => <div key={label}><dt className="text-muted-foreground">{label}</dt><dd className="break-all font-mono">{value}</dd></div>)}</dl></details>}
      </section>
    </div>
  </Page>
}

function ReportView({ artifact, job, locale }: { artifact: ReplayArtifact; job: ReplayJob; locale: 'en' | 'zh-CN' }) {
  const r = replayReport(artifact.value, job); const zh = locale === 'zh-CN'; const w = words[locale]
  const unavailable = zh ? '不可用' : 'Unavailable'
  const number = (v: number | null, percent = false) => v === null ? unavailable : percent ? new Intl.NumberFormat(locale, { style: 'percent', maximumFractionDigits: 2 }).format(v) : new Intl.NumberFormat(locale, { maximumFractionDigits: 2 }).format(v)
  const usd = (v: number) => new Intl.NumberFormat(locale, { style: 'currency', currency: 'USD', maximumFractionDigits: 2 }).format(v)
  return <div className="space-y-4">
    <Badge variant="outline" className="h-auto whitespace-normal">{r.evidence_kind === 'engineering_fixture' ? w.engineering : w.reviewed}</Badge>
    <p className="text-sm text-muted-foreground">{r.window.score_start} → {r.window.score_end} · {w.noSplit}</p>
    {(['base5', 'stress10'] as const).map(key => { const s = r.calculation.scenarios[key]; return <section key={key} className="space-y-2">
      <h4 className="text-sm font-semibold">{key === 'base5' ? (zh ? '基准 · 单边 5 bps' : 'Base · 5 bps one way') : (zh ? '压力 · 单边 10 bps' : 'Stress · 10 bps one way')}</h4>
      <div className="overflow-x-auto"><table className="w-full text-left text-sm tabular-nums"><caption className="sr-only">{key === 'base5' ? (zh ? '基准成本结果' : 'Base cost results') : (zh ? '压力成本结果' : 'Stress cost results')}</caption><thead className="text-xs text-muted-foreground"><tr><th className="py-2 pr-4 font-normal">{zh ? '结果' : 'Result'}</th><th className="py-2 pr-4 text-right font-normal">SMA100</th><th className="py-2 text-right font-normal">{zh ? '买入持有' : 'Buy-and-hold'}</th></tr></thead><tbody>
        {[[zh ? '净收益率' : 'Net return', 'total_return', 'percent'], [zh ? '期末资金' : 'Terminal equity', 'terminal_equity', 'usd'], [zh ? '最大回撤' : 'Max drawdown', 'max_drawdown', 'percent'], [zh ? '综合摩擦成本' : 'Combined friction', 'friction_usd', 'usd'], [zh ? '成交笔数' : 'Fills', 'fills', 'number']].map(([label, metric, format]) => <tr key={metric} className="border-t"><th className="py-2 pr-4 font-normal">{label}</th>{(['strategy','buyhold'] as const).map(track => { const v = s[track].metrics[metric as keyof typeof s.strategy.metrics]; return <td key={track} className="py-2 text-right whitespace-nowrap">{format === 'usd' ? usd(v as number) : number(v, format === 'percent')}</td> })}</tr>)}
      </tbody></table></div>
      <p className="text-sm text-muted-foreground">{zh ? '策略相对买入持有' : 'Strategy minus buy-and-hold'}: {usd(s.comparison.terminal_equity_difference_usd)} · {number(s.comparison.total_return_difference * 100)} {zh ? '个百分点' : 'percentage points'}</p>
      <details className="text-xs"><summary className="min-h-11 cursor-pointer text-muted-foreground">{zh ? '年化指标（仅 21 个观察日）' : 'Annualized metrics (only 21 observation sessions)'}</summary><dl className="grid grid-cols-2 gap-x-4 gap-y-2">{[['CAGR', 'cagr', true], [zh ? '年化波动' : 'Annualized volatility', 'annualized_volatility', true], ['Sharpe (rf=0)', 'naive_sharpe_rf_zero', false], ['Sortino (target=0)', 'sortino_target_zero', false], ['Calmar', 'calmar', false]].map(([label, metric, percent]) => <div key={String(metric)}><dt className="text-muted-foreground">{label}</dt><dd>{number(s.strategy.metrics[metric as keyof typeof s.strategy.metrics], !!percent)}</dd></div>)}</dl></details>
    </section> })}
    <p className="border-t pt-3 text-sm">{zh ? '现金基准（利息 0%）' : 'Cash benchmark (0% interest)'}: {usd(r.calculation.cash_benchmark.terminal_equity)} · {number(r.calculation.cash_benchmark.total_return, true)} · {zh ? '回撤' : 'drawdown'} {number(r.calculation.cash_benchmark.max_drawdown, true)}</p>
    {r.limitations.map((limitation, i) => <p key={i} className="text-xs text-muted-foreground">{limitation}</p>)}
  </div>
}
