import { useEffect, useState, type ReactNode } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useParams, useSearchParams } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { WorkspaceLoading } from '@/components/workspace-loading'
import { api, type DecisionPacket, type DecisionPacketActionResult } from '@/lib/api'
import { moneyPrecise, number, percent } from '@/lib/format'
import { usePreferences } from '@/lib/preferences'
import { DecisionRail } from './DecisionRail'
import { evidenceText } from './evidence-copy'
import { MarketCanvas } from './MarketCanvas'
import { PacketCopilot } from './PacketCopilot'
import { PacketMonitoring } from './PacketMonitoring'
import { PacketOutcomeReview } from './PacketOutcomeReview'
import { PacketEvidenceSummary, ScenarioEvidence } from './ScenarioEvidence'

const PACKET_ID = /^packet-[0-9a-f]{24}$/
const workspaceKey = (symbol: string, horizon: 7 | 30, artifact?: string) => ['scenario-lab', symbol, horizon, artifact] as const

/** Lab evidence is immutable once selected; refresh is an explicit new analysis. */
export function ScenarioLabWorkspace() {
  const { symbol = '', venue = '' } = useParams()
  const [search, setSearch] = useSearchParams()
  const { t } = usePreferences()
  const client = useQueryClient()
  const [riskOpen, setRiskOpen] = useState(false)
  const requestedPacket = search.get('packet')
  const artifact = search.get('forecast') ?? undefined
  const horizon = search.get('horizon') === '7' ? 7 : 30
  const supported = venue === 'moomoo' && ['AAPL', 'NVDA'].includes(symbol)
  const saved = useQuery({
    queryKey: ['decision-packet', requestedPacket],
    queryFn: () => api.decisionPacket(requestedPacket!),
    enabled: supported && requestedPacket !== null && PACKET_ID.test(requestedPacket),
    retry: false, staleTime: Infinity,
  })
  const fresh = useQuery({
    queryKey: workspaceKey(symbol, horizon, artifact),
    queryFn: () => api.instrumentWorkspace('moomoo', symbol, '6m', [], horizon, artifact),
    enabled: supported && requestedPacket === null,
    retry: false, staleTime: Infinity, refetchOnWindowFocus: false,
  })
  const packet = requestedPacket !== null ? saved.data : fresh.data?.decision.draft
  const snapshot = packet?.scenario_lab
  const savedArtifact = packet?.evidence.forecast_artifact_id ?? undefined
  const selectedHorizon = snapshot?.selected_horizon ?? horizon
  const currentRisk = useQuery({
    queryKey: ['scenario-lab-risk', requestedPacket],
    queryFn: () => api.instrumentWorkspace('moomoo', symbol, '6m', [], selectedHorizon, savedArtifact),
    enabled: supported && requestedPacket !== null && snapshot != null && riskOpen,
    retry: false, refetchOnWindowFocus: false,
  })
  useEffect(() => {
    const id = fresh.data?.decision.draft.evidence.forecast_artifact_id
    if (requestedPacket !== null || artifact || !id || !fresh.data) return
    client.setQueryData(workspaceKey(symbol, horizon, id), fresh.data)
    setSearch((previous) => { const next = new URLSearchParams(previous); next.set('forecast', id); return next }, { replace: true })
  }, [artifact, client, fresh.data, horizon, requestedPacket, setSearch, symbol])

  function update(key: string, value: string) {
    setSearch((previous) => { const next = new URLSearchParams(previous); next.set(key, value); return next }, { replace: true })
  }
  function newAnalysis(nextHorizon: 7 | 30, retainArtifact: boolean) {
    setRiskOpen(false)
    const next = new URLSearchParams(search)
    next.delete('packet')
    next.set('analysis', 'fresh')
    next.set('horizon', String(nextHorizon))
    if (retainArtifact && savedArtifact) next.set('forecast', savedArtifact)
    else next.delete('forecast')
    if (!retainArtifact) client.removeQueries({ queryKey: workspaceKey(symbol, nextHorizon) })
    setSearch(next)
  }
  function saveResult(result: DecisionPacketActionResult) {
    client.setQueryData(['decision-packet', result.packet.packet_id], result.packet)
    const next = new URLSearchParams(search)
    next.delete('analysis')
    next.set('packet', result.packet.packet_id)
    next.set('horizon', String(result.packet.scenario_lab?.selected_horizon ?? selectedHorizon))
    setSearch(next)
  }

  if (!supported || (requestedPacket !== null && !PACKET_ID.test(requestedPacket))) return <LabError text={t('screen.workspace.invalidRoute')} />
  const heading = <LabHeading symbol={symbol} horizon={selectedHorizon} saved={requestedPacket !== null}
    onNewAnalysis={() => newAnalysis(selectedHorizon, false)} onHorizon={(value) => value !== selectedHorizon && newAnalysis(value, true)} />
  if ((requestedPacket !== null ? saved.isPending : fresh.isPending)) return <div className="mx-auto max-w-[1600px] space-y-5 pb-12" data-testid="scenario-lab">{heading}<WorkspaceLoading /></div>
  if ((requestedPacket !== null ? saved.isError : fresh.isError) || !packet || !snapshot) return <LabError text={t('lab.unavailable')} />
  if (packet.instrument.venue !== venue || packet.instrument.symbol !== symbol || snapshot.history.instrument.symbol !== symbol
    || (requestedPacket !== null && packet.packet_id !== requestedPacket)
    || (requestedPacket === null && (snapshot.selected_horizon !== horizon || (artifact && packet.evidence.forecast_artifact_id !== artifact)))) {
    return <LabError text={t('lab.mismatch')} />
  }
  const forecast = packet.evidence.forecast_paths?.find((path) => path.sessions === selectedHorizon) ?? null
  const riskWorkspace = requestedPacket !== null ? currentRisk.data : fresh.data
  const contextKey = `${venue}:${symbol}:${packet.packet_id}:${selectedHorizon}`
  return <div className="mx-auto max-w-[1600px] space-y-5 pb-12" data-testid="scenario-lab">
    {heading}
    <section className="min-w-0 space-y-3" aria-label={t('lab.canvas')}>
      <p className="text-xs text-muted-foreground">{snapshot.history.source === 'demo-synthetic' ? t('lab.demo') : snapshot.history.source} · {t(`lab.${snapshot.confidence}`)}</p>
      {requestedPacket !== null && <p className="text-xs text-muted-foreground">{t('lab.replayNote')}</p>}
      <MarketCanvas chartFirst history={snapshot.history} forecast={forecast} comparison={null} range={packet.selected_range}
        mode={search.get('mode') === 'line' ? 'line' : 'candles'} volume={search.get('volume') !== '0'} showSma20={search.get('sma20') !== '0'} showSma50={search.get('sma50') !== '0'}
        onRangeChange={() => {}} onModeChange={(value) => update('mode', value)} onVolumeChange={(value) => update('volume', value ? '1' : '0')}
        onSma20Change={(value) => update('sma20', value ? '1' : '0')} onSma50Change={(value) => update('sma50', value ? '1' : '0')} />
    </section>
    <LabEvidence packet={packet} />
    <Disclosure title={t('lab.evidence')}>
      {packet.evidence.forecast_model_version === 'demo-drift-conformal-xnys-v2' && <p className="mb-4 px-3 text-sm text-muted-foreground">{t('lab.modelConfig')}</p>}
      <PacketEvidenceSummary packet={packet} archived={requestedPacket !== null} />
    </Disclosure>
    <details className="border-y border-border py-4" open={riskOpen} onToggle={(event) => setRiskOpen(event.currentTarget.open)}>
      <summary className="cursor-pointer font-semibold focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">{t('lab.decision')}</summary>
      {riskOpen && <div className="mt-4 grid min-w-0 gap-6 lg:grid-cols-[minmax(0,1fr)_24rem]">
        <ScenarioEvidence packet={packet} />
        <DecisionRail workspace={riskWorkspace} packet={packet} packetSource={requestedPacket !== null ? 'persisted' : 'fresh'} contextKey={contextKey} onActionResult={saveResult} onNewAnalysis={() => newAnalysis(selectedHorizon, false)} />
      </div>}
    </details>
    {requestedPacket !== null && <>
      <Disclosure title={t('screen.workspace.copilot')}><PacketCopilot contextKey={contextKey} packetId={packet.packet_id} /></Disclosure>
      <Disclosure title={t('lab.followThrough')}><PacketMonitoring contextKey={contextKey} packetId={packet.packet_id} /><PacketOutcomeReview contextKey={contextKey} packetId={packet.packet_id} /></Disclosure>
    </>}
  </div>
}

function LabHeading({ symbol, horizon, saved, onNewAnalysis, onHorizon }: {
  symbol: string; horizon: 7 | 30; saved: boolean; onNewAnalysis: () => void; onHorizon: (value: 7 | 30) => void
}) {
  const { t } = usePreferences()
  return <header className="space-y-3 border-b border-border pb-3">
    <div className="flex flex-wrap items-center justify-between gap-3">
      <div><p className="text-xs text-muted-foreground">{t('lab.title')} · Moomoo</p><h1 className="text-2xl font-semibold tracking-tight">{symbol} <span className="text-sm font-normal text-muted-foreground">USD · {t('lab.daily')}</span></h1></div>
      <div className="flex flex-wrap items-center gap-2"><span className="text-xs text-muted-foreground">{t(saved ? 'lab.saved' : 'lab.draft')}</span><Button onClick={onNewAnalysis} variant="outline">{t('screen.workspace.newAnalysis')}</Button></div>
    </div>
    <div className="flex gap-1" aria-label={t('lab.horizon')}>
      {([7, 30] as const).map((value) => <Button key={value} aria-pressed={horizon === value} variant={horizon === value ? 'secondary' : 'ghost'} onClick={() => onHorizon(value)}>{t('lab.sessions', { count: String(value) })}</Button>)}
    </div>
  </header>
}

function LabEvidence({ packet }: { packet: DecisionPacket }) {
  const { t, locale } = usePreferences()
  const lab = packet.scenario_lab!
  const path = packet.evidence.forecast_paths?.find((item) => item.sessions === lab.selected_horizon)
  const metric = packet.evidence.forecast_metrics?.find((item) => item.sessions === lab.selected_horizon)
  const target = path?.points.at(-1)
  const available = t('screen.workspace.unavailable')
  return <section aria-label={t('lab.summary')} className="space-y-3 border-t border-border pt-4">
    <dl className="grid grid-cols-2 gap-x-5 gap-y-4 lg:grid-cols-4">
      <Fact label={t('lab.median')} value={target ? moneyPrecise(target.p50, locale) : available} />
      <Fact label={t('lab.band')} value={target ? `${moneyPrecise(target.p10, locale)} – ${moneyPrecise(target.p90, locale)}` : available} />
      <Fact label={t('lab.mae')} value={metric && metric.residual_count > 0 ? `${number(metric.mae, locale)} / ${number(metric.benchmark_mae, locale)}` : available} />
      <Fact label={t('lab.coverage')} value={metric && metric.interval_test_count > 0 ? `${percent(metric.coverage_80, locale)} · n=${number(metric.interval_test_count, locale)}` : available} />
    </dl>
    <p className="text-xs text-muted-foreground">{t('lab.noProbability')}</p>
    <div role="note" className="border-l-2 border-muted-foreground pl-3 text-sm">
      <p className="font-medium">{t(`lab.${lab.confidence}`)}</p>
      <ul className="mt-1 space-y-1 text-xs text-muted-foreground">{lab.reasons.map((reason) => <li key={reason}>{evidenceText(reason, locale, t)}</li>)}</ul>
    </div>
  </section>
}
function Fact({ label, value }: { label: string; value: string }) {
  return <div className="min-w-0"><dt className="text-xs text-muted-foreground">{label}</dt><dd className="mt-1 break-words font-mono text-sm tabular-nums">{value}</dd></div>
}
function LabError({ text }: { text: string }) { return <p role="alert" className="border-l-2 border-destructive p-4">{text}</p> }
function Disclosure({ title, children }: { title: string; children: ReactNode }) {
  const [open, setOpen] = useState(false)
  return <details className="min-w-0 border-b border-border py-3" onToggle={(event) => setOpen(event.currentTarget.open)}>
    <summary className="cursor-pointer font-medium focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">{title}</summary>
    {open && <div className="mt-4 min-w-0">{children}</div>}
  </details>
}
