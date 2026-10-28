import { useEffect, useState, type ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { ChevronLeft, ChevronRight } from 'lucide-react'
import { Page } from '@/components/page'
import { Button } from '@/components/ui/button'
import { usePreferences } from '@/lib/preferences'
import { trendCases, trendOverlayApi, type TrendCase, type TrendRow, type TrendTrace } from '@/lib/trend-overlay-api'
import { trendCopy } from '@/lib/trend-overlay-copy'

// Operate extension: one supplied step, two arms, critical evidence boundary always
// visible. Long rules/input series disclose inline; no client-side strategy math.
const focus = 'rounded-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2'
type Copy = typeof trendCopy.en
function Datum({ label, children }: { label: string; children: ReactNode }) {
  return <div className="min-w-0 space-y-1"><dt className="text-xs text-muted-foreground">{label}</dt><dd className="break-words text-sm tabular-nums">{children}</dd></div>
}

function Arm({ row, title, c }: { row: TrendRow; title: string; c: Copy }) {
  const term = (value: string | null) => value ? c.terms[value] ?? value : c.none
  const list = (values: string[]) => values.map(term).join(', ') || c.none
  const sized = row.sizing
  const before = row.campaign_before, after = row.campaign_after
  return <section aria-label={title} className="min-w-0 space-y-4 rounded-lg border border-border p-4">
    <h3 className="font-semibold">{title}</h3>
    <dl className="grid grid-cols-2 gap-x-4 gap-y-4">
      <Datum label={c.signal}>{term(row.action.signal)}</Datum>
      <Datum label={c.action}>{term(row.action.kind)}</Datum>
      <div className="col-span-2"><Datum label={c.quantities}>{sized ? `${sized.requested} / ${sized.allowed} / ${row.supplied_fill?.quantity ?? c.none}` : c.noFill}</Datum></div>
      <div className="col-span-2"><Datum label={c.why}>
        <p>{term(row.action.reason)}</p>
        {sized && sized.constraints.length > 0 && <ul className="mt-1 list-inside list-disc text-muted-foreground">{sized.constraints.map(item => <li key={item}>{term(item)}</li>)}</ul>}
        {row.action.stages.length > 0 && <p className="mt-1">{list(row.action.stages)}</p>}
      </Datum></div>
      <Datum label={c.shares}>{before.shares} → {after.shares}</Datum>
      <Datum label={c.cash}>{row.supplied_account.cash}</Datum>
      <Datum label={c.receivable}>{row.supplied_account.receivable}</Datum>
      {sized && <Datum label={c.cancelled}>{row.cancelled_remainder}</Datum>}
      {after.pending_full_exit && <div className="col-span-2"><Datum label={c.pending}>{term(after.pending_full_exit)}</Datum></div>}
    </dl>
    <details className="border-t border-border pt-3">
      <summary className={`min-h-9 cursor-pointer text-sm underline-offset-4 hover:underline ${focus}`}>{c.conditions}</summary>
      <dl className="mt-3 grid grid-cols-2 gap-4">
        <Datum label={c.close}>{row.close_input.closes.at(-1)}</Datum>
        <Datum label={c.open}>{row.open_input?.price ?? c.none}</Datum>
        <Datum label={c.anchors}>{before.initial_price ?? c.none} / {before.initial_quantity}</Datum>
        <Datum label={c.averages}>{row.action.averages.slice(0, 2).join(' / ') || c.none}</Datum>
        <Datum label={c.prior}>{row.action.averages.slice(2).join(' / ') || c.none}</Datum>
        <Datum label={c.friction}>{row.friction_for_supplied_fill ?? c.none}</Datum>
        <div className="col-span-2"><Datum label={c.consumed}>{list(before.consumed)} → {list(after.consumed)}</Datum></div>
        {sized && <><Datum label={c.volume}>{sized.participation_cap}</Datum><Datum label={c.cost}>{sized.cost_bps}</Datum></>}
      </dl>
    </details>
  </section>
}

export function TrendOverlayScreen() {
  const { locale } = usePreferences()
  const c = trendCopy[locale]
  const [caseId, setCaseId] = useState<TrendCase>('campaign')
  const [trace, setTrace] = useState<TrendTrace | null>(null)
  const [step, setStep] = useState(0)
  const [mobileArm, setMobileArm] = useState<'overlay_off' | 'overlay_on'>('overlay_on')
  const [retry, setRetry] = useState(0)
  const [status, setStatus] = useState<'loading' | 'ready' | 'error'>('loading')
  useEffect(() => {
    let current = true
    const controller = new AbortController()
    trendOverlayApi.get(caseId, controller.signal).then(value => {
      if (current) { setTrace(value); setStatus('ready') }
    }).catch(() => { if (current) setStatus('error') })
    return () => { current = false; controller.abort() }
  }, [caseId, retry])
  function select(value: TrendCase) {
    if (value === caseId) return
    setCaseId(value); setTrace(null); setStep(0); setStatus('loading')
  }
  const visible = status === 'ready' && trace?.case === caseId ? trace : null
  const total = visible?.arms.overlay_on.length ?? 0
  const row = visible?.arms.overlay_on[step]
  const episodes = c.episodes as Record<string, string>
  return <Page title={c.title} description={c.subtitle} actions={<Button variant="outline" size="sm" render={<Link to="/research/jobs" />}>{c.back}</Button>}>
    <div className="space-y-1 rounded-md bg-muted/50 p-3 text-sm">
      <p className="font-semibold">{c.synthetic}</p><p className="max-w-3xl text-muted-foreground">{c.boundary}</p>
    </div>
    <div className="space-y-2">
      <label htmlFor="trend-case" className="block text-sm font-medium">{c.fixedCase}</label>
      <select id="trend-case" value={caseId} onChange={event => select(event.target.value as TrendCase)} className="min-h-11 w-full max-w-lg rounded-md border border-input bg-background px-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
        {trendCases.map(id => <option key={id} value={id}>{c.cases[id]}</option>)}
      </select>
      <p className="max-w-3xl text-sm text-muted-foreground">{c.descriptions[caseId]}</p>
    </div>
    {status === 'loading' && <p role="status" className="min-h-24 text-sm text-muted-foreground">{c.loading}</p>}
    {status === 'error' && <div role="alert" className="space-y-3 text-sm"><p>{c.error}</p><Button variant="outline" onClick={() => { setTrace(null); setStatus('loading'); setRetry(value => value + 1) }}>{c.retry}</Button></div>}
    {visible && row && <>
      <div className="sticky top-14 z-10 space-y-3 border-y border-border bg-background py-3 lg:static lg:border-b-0">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <p role="status" aria-live="polite" className="text-sm font-semibold">{c.step(step + 1, total)}</p>
          <div className="flex gap-2"><Button variant="outline" className="min-h-11" disabled={step === 0} onClick={() => setStep(value => value - 1)}><ChevronLeft className="size-4" aria-hidden />{c.previous}</Button>
            <Button variant="outline" className="min-h-11" disabled={step + 1 === total} onClick={() => setStep(value => value + 1)}>{c.next}<ChevronRight className="size-4" aria-hidden /></Button></div>
        </div>
        <div role="group" aria-label={c.compare} className="grid grid-cols-2 gap-2 lg:hidden">
          {(['overlay_off', 'overlay_on'] as const).map(arm => <Button key={arm} className="min-h-11" variant={mobileArm === arm ? 'default' : 'outline'} aria-pressed={mobileArm === arm} onClick={() => setMobileArm(arm)}>{c.arms[arm]}</Button>)}
        </div>
      </div>
      <div className="space-y-1"><h3 className="text-sm font-medium">{episodes[row.episode] ?? row.episode}</h3>
        <p className="text-xs text-muted-foreground">{c.close} {row.close_session}{row.open_input ? ` · ${c.open} ${row.open_input.session}` : ''} · {c.ordinal}</p></div>
      <div className="grid min-w-0 gap-4 lg:grid-cols-2">
        <div className={mobileArm === 'overlay_off' ? 'min-w-0' : 'hidden min-w-0 lg:block'}><Arm row={visible.arms.overlay_off[step]} title={c.arms.overlay_off} c={c} /></div>
        <div className={mobileArm === 'overlay_on' ? 'min-w-0' : 'hidden min-w-0 lg:block'}><Arm row={row} title={c.arms.overlay_on} c={c} /></div>
      </div>
      <p className="max-w-3xl text-xs text-muted-foreground">{c.cashNote}</p>
      <details key={caseId} className="min-w-0 border-t border-border pt-4">
        <summary className={`min-h-11 cursor-pointer text-sm font-medium ${focus}`}>{c.details}</summary>
        <div className="mt-2 max-w-4xl space-y-4 text-sm">
          <p>{c.rule}</p><p>{c.stages}</p>
          <div><h3 className="mb-2 font-semibold">{c.assumptions}</h3><ul className="list-inside list-disc space-y-1 text-muted-foreground">{visible.assumptions.map(value => <li key={value}>{value}</li>)}</ul></div>
          <dl className="space-y-3"><Datum label={c.identity}><span className="break-all font-mono text-xs">{visible.trace_sha256}</span></Datum><Datum label={c.fixture}><span className="break-all font-mono text-xs">{visible.fixture_sha256}</span></Datum></dl>
          <a href={`data:application/json;charset=utf-8,${encodeURIComponent(JSON.stringify(visible))}`} download={`trend-${caseId}.json`} className={`inline-flex min-h-11 items-center underline underline-offset-4 ${focus}`}>{c.download}</a>
          <details><summary className={`min-h-11 cursor-pointer ${focus}`}>{c.raw}</summary><pre className="max-h-96 overflow-auto whitespace-pre-wrap break-all rounded-md bg-muted/50 p-3 text-xs">{JSON.stringify(visible, null, 2)}</pre></details>
        </div>
      </details>
    </>}
  </Page>
}
