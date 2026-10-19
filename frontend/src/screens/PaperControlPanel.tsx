/** Operate: extend existing Ops primitives. Current authority precedes evidence and
 * original receipts; local confirmation never claims authenticated identity. */
import { useCallback, useEffect, useRef, useState } from 'react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Notice } from '@/components/state'
import { usePreferences } from '@/lib/preferences'
import { paperControlsApi, type PaperStatus, type PaperTransition, type Transition, type Venue } from '@/lib/paper-controls-api'
import { paperControlsCopy } from '@/lib/paper-controls-copy'

export type PaperAvailability = 'loading' | 'configured' | 'unavailable' | 'error'
type Props = { onAvailabilityChange: (value: PaperAvailability) => void; onStateChange?: (state: PaperStatus) => void }
export function PaperControlPanel({ onAvailabilityChange, onStateChange }: Props) {
  const { locale } = usePreferences(), c = paperControlsCopy[locale]
  const [state, setState] = useState<PaperStatus | null>(null)
  const [availability, setAvailability] = useState<PaperAvailability>('loading')
  const [busy, setBusy] = useState<keyof typeof c | null>('loading')
  const busyRef = useRef(false), mounted = useRef(true)
  const [error, setError] = useState<string | null>(null)
  const [reason, setReason] = useState(''), [confirmed, setConfirmed] = useState(false)
  const [target, setTarget] = useState<Venue | null>(null)
  const [prepared, setPrepared] = useState<PaperStatus | null>(null)
  const [result, setResult] = useState<PaperTransition | null>(null)
  const pending = useRef<{ action: 'pause' | 'resume'; payload: Transition } | null>(null)
  const invalidate = useCallback(() => { setPrepared(null); setConfirmed(false) }, [])
  const message = (code: string) => c[code as keyof typeof c] ?? c.request_failed
  const reportError = useCallback((failure: unknown) => {
    const code = typeof failure === 'object' && failure !== null && 'code' in failure ? String(failure.code) : 'request_failed'
    setError(code); invalidate()
    return code
  }, [invalidate])
  const refresh = useCallback(async () => {
    if (busyRef.current) return
    busyRef.current = true; setBusy('loading'); setError(null); invalidate(); setTarget(null)
    try {
      const next = await paperControlsApi.status()
      if (!mounted.current) return
      setState(next); onStateChange?.(next); setAvailability('configured'); onAvailabilityChange('configured')
    } catch (failure) {
      if (!mounted.current) return
      const code = reportError(failure)
      const next = code === 'unavailable' ? 'unavailable' : 'error'
      setAvailability(next); onAvailabilityChange(next)
    } finally { busyRef.current = false; if (mounted.current) setBusy(null) }
  }, [invalidate, onAvailabilityChange, onStateChange, reportError])
  useEffect(() => {
    mounted.current = true
    void refresh()
    return () => { mounted.current = false }
  }, [refresh])

  async function check() {
    if (busyRef.current) return
    busyRef.current = true; setBusy('checking'); setError(null); invalidate()
    try {
      const next = await paperControlsApi.preflight(target)
      setState(next); onStateChange?.(next); setPrepared(next.blocked ? null : next)
    } catch (failure) { reportError(failure) }
    finally { busyRef.current = false; setBusy(null) }
  }
  async function transition(action: 'pause' | 'resume') {
    if (busyRef.current || !reason.trim() || (action === 'resume' && (!prepared || !confirmed))) return
    busyRef.current = true; setBusy(action === 'pause' ? 'pausing' : 'resuming'); setError(null); setResult(null)
    const fields: Omit<Transition, 'key'> = { reason: reason.trim(), ...(action === 'resume'
      ? { revision: prepared!.revision, confirmation: true, target } : {}) }
    const previous = pending.current
    const same = previous?.action === action && JSON.stringify({ ...previous.payload, key: undefined }) === JSON.stringify(fields)
    const payload: Transition = same ? previous.payload : { ...fields, key: crypto.randomUUID() }
    pending.current = { action, payload }
    try {
      const response = await paperControlsApi.transition(action, payload)
      setState(response.status); onStateChange?.(response.status); setResult(response); pending.current = null; invalidate(); setTarget(null)
    } catch (failure) { reportError(failure) }
    finally { busyRef.current = false; setBusy(null) }
  }
  async function download(id?: string) {
    if (busyRef.current) return
    busyRef.current = true; setBusy('downloading'); setError(null)
    try {
      const blob = await paperControlsApi.download(id ? 'receipt' : 'audit', id)
      const href = URL.createObjectURL(blob), anchor = document.createElement('a')
      anchor.href = href; anchor.download = id ? `paper-receipt-${id}.json` : 'synthetic-paper-audit.jsonl'
      anchor.click(); URL.revokeObjectURL(href)
    } catch (failure) { reportError(failure) }
    finally { busyRef.current = false; setBusy(null) }
  }
  const stops = state ? Object.entries(state.venue_stops).filter(([, value]) => value) : []
  return <section aria-label={c.title} className="space-y-5">
    <Card>
      <CardHeader>
        <CardTitle className="text-lg">{c.title}</CardTitle>
        <CardDescription className="max-w-prose">{c.scope}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-5">
        {busy && <p role="status" aria-live="polite" className="text-sm text-muted-foreground">{c[busy]}</p>}
        {availability === 'unavailable' && <Notice>{c.unavailable}</Notice>}
        {error && error !== 'unavailable' && <p role="alert" className="text-sm">{message(error)}</p>}
        {state && availability !== 'unavailable' && <>
          <div className="space-y-2" aria-live="polite">
            <div className="flex flex-wrap items-center gap-3">
              <h2 className="text-base font-semibold">{state.blocked ? c.ordersBlocked : state.paused ? c.paused : c.allowed}</h2>
              {state.blocked && <Badge variant="outline">{c.blocked}</Badge>}
            </div>
            <p className="text-sm text-muted-foreground">{state.paused ? c.globalStopped : c.globalRunning}</p>
            <p className="break-words text-sm text-muted-foreground">{c.reason}: {message(state.pause_reason) === c.request_failed ? state.pause_reason : message(state.pause_reason)}</p>
          </div>
          {result && <p role="status" className="text-sm">{result.replay ? c.replay : c.completed}</p>}
          <div className="space-y-2">
            <label htmlFor="paper-control-reason" className="block text-sm font-medium">{c.reasonLabel}</label>
            <input id="paper-control-reason" value={reason} maxLength={240} disabled={!!busy}
              placeholder={c.reasonHint} onChange={e => setReason(e.target.value)}
              className="w-full min-w-0 rounded-md border border-input bg-background px-3 py-2 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50" />
          </div>
          <div className="flex flex-wrap gap-2">
            <Button variant="destructive" disabled={!!busy || !reason.trim()} onClick={() => void transition('pause')}>{c.pause}</Button>
            <Button variant="outline" disabled={!!busy} onClick={() => void refresh()}>{c.refresh}</Button>
          </div>
          {stops.length > 0 && <div className="space-y-2 text-sm">
            <h3 className="font-medium">{c.stops}</h3>
            {stops.map(([venue]) => <p key={venue}>{venue}: {c.venuePaused}</p>)}
            <p className="max-w-prose text-muted-foreground">{c.stopsHint}</p>
          </div>}
          <div className="space-y-3 border-t pt-4">
            <label htmlFor="paper-control-target" className="block text-sm font-medium">{c.target}</label>
            <select id="paper-control-target" value={target ?? ''} disabled={!!busy}
              onChange={e => { setTarget(e.target.value ? e.target.value as Venue : null); invalidate() }}
              className="max-w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus-visible:outline-2 focus-visible:outline-ring">
              <option value="">{c.global}</option>
              {stops.map(([venue]) => <option key={venue} value={venue}>{venue}</option>)}
            </select>
            <div><Button variant="outline" disabled={!!busy} onClick={() => void check()}>{c.preflight}</Button></div>
            {prepared && <div className="space-y-1 text-sm"><p>{c.prepared}</p><p className="break-all font-mono text-xs text-muted-foreground">{prepared.revision}</p></div>}
            <label className="flex max-w-prose items-start gap-2 text-sm">
              <input type="checkbox" checked={confirmed} disabled={!!busy || !prepared || state.blocked}
                onChange={e => setConfirmed(e.target.checked)} className="mt-1 size-4 shrink-0 accent-primary focus-visible:outline-2 focus-visible:outline-ring" />
              <span>{c.confirm}</span>
            </label>
            <Button disabled={!!busy || !prepared || !confirmed || !reason.trim() || state.blocked}
              onClick={() => void transition('resume')}>{c.resume}</Button>
          </div>
        </>}
        {!state && !busy && <Button variant="outline" onClick={() => void refresh()}>{c.refresh}</Button>}
      </CardContent>
    </Card>
    {state && <>
      <section aria-label={c.evidence} className="space-y-3">
        <h2 className="text-base font-semibold">{c.evidence}</h2>
        {state.checks.length ? <ul className="list-disc space-y-2 pl-5 text-sm">{state.checks.map(code => <li key={code}>{message(code)}</li>)}</ul>
          : <p className="text-sm text-muted-foreground">{c.checksPass}</p>}
        <div className="grid gap-5 sm:grid-cols-2">
          <div><h3 className="mb-2 text-sm font-medium">{c.limits}</h3>
            {state.limits ? <dl className="space-y-2 text-sm">{[
              [c.quantity, state.limits.max_order_quantity], [c.notional, state.limits.max_notional], [c.position, state.limits.max_position_quantity],
            ].map(([label, value]) => <div key={label} className="flex flex-wrap justify-between gap-x-3"><dt className="text-muted-foreground">{label}</dt><dd className="tabular-nums">{value}</dd></div>)}</dl>
              : <p className="text-sm text-muted-foreground">{c.blocked}</p>}</div>
          <div><h3 className="mb-2 text-sm font-medium">{c.costs}</h3><dl className="space-y-2 text-sm">{[
            [c.fee, state.costs.fee_bps], [c.minimum, state.costs.min_fee], [c.slippage, state.costs.slippage_bps],
          ].map(([label, value]) => <div key={label} className="flex flex-wrap justify-between gap-x-3"><dt className="text-muted-foreground">{label}</dt><dd className="tabular-nums">{value}</dd></div>)}</dl></div>
        </div>
      </section>
      <section aria-label={c.history} className="space-y-3 border-t pt-4">
        <div className="flex flex-wrap items-center justify-between gap-3"><h2 className="text-base font-semibold">{c.history}</h2>
          <Button variant="outline" size="sm" disabled={!!busy} onClick={() => void download()}>{c.downloadAudit}</Button></div>
        <ol className="space-y-4">{state.history.slice().reverse().map(receipt => <li key={receipt.id} className="space-y-1 text-sm">
          <p className="flex flex-wrap gap-x-2 font-medium"><span>{receipt.action === 'startup' ? c.startupAction : receipt.action === 'pause' ? c.pauseAction : c.resumeAction}</span>
            <time dateTime={receipt.recorded_at} className="font-normal text-muted-foreground">{receipt.recorded_at}</time></p>
          <p className="break-words">{receipt.reason === 'cold_start' ? c.cold_start : receipt.reason}</p>
          <p className="break-all font-mono text-xs text-muted-foreground">{receipt.id}</p>
          <Button variant="link" size="sm" disabled={!!busy} onClick={() => void download(receipt.id)}>{c.downloadReceipt}</Button>
        </li>)}</ol>
        {result && !state.history.some(r => r.id === result.receipt.id) && <div className="space-y-1 text-sm">
          <p>{c.original}</p><p className="break-all font-mono text-xs">{result.receipt.id}</p>
          <Button variant="link" size="sm" disabled={!!busy} onClick={() => void download(result.receipt.id)}>{c.downloadReceipt}</Button>
        </div>}
      </section>
    </>}
  </section>
}
