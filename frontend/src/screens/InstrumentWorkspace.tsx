import { useCallback, useEffect, useRef, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useParams, useSearchParams } from 'react-router-dom'

import { WorkspaceLoading } from '@/components/workspace-loading'
import {
  ApiError,
  api,
  type HistoricalVenue,
  type HistoryRange,
  type MarketUpdate,
} from '@/lib/api'
import { useLiveConnection } from '@/lib/live'
import { usePreferences } from '@/lib/preferences'
import { WorkspaceHeader } from './instrument/WorkspaceHeader'
import { CockpitDetailScreen } from './CockpitDetail'
import { ComparisonPicker } from './instrument/ComparisonPicker'
import { DecisionRail } from './instrument/DecisionRail'
import { evidenceText } from './instrument/evidence-copy'
import { ForecastEvidence, type ForecastHorizon } from './instrument/ForecastEvidence'
import { MarketCanvas } from './instrument/MarketCanvas'
import { PacketEvidenceSummary, ScenarioEvidence } from './instrument/ScenarioEvidence'
import { WorkspaceDegraded, WorkspaceError, WorkspaceRefreshWarning } from './instrument/WorkspaceStates'
import { retainSameInstrument } from './instrument/workspace-query'

const VENUES: readonly HistoricalVenue[] = ['internal', 'moomoo', 'hyperliquid', 'polymarket', 'kalshi']
const RANGES: readonly HistoryRange[] = ['1d', '5d', '1m', '3m', '6m', '1y']

function isVenue(value: string): value is HistoricalVenue {
  return VENUES.includes(value as HistoricalVenue)
}

function historyRange(value: string | null): HistoryRange {
  return value !== null && RANGES.includes(value as HistoryRange) ? value as HistoryRange : '6m'
}

function forecastHorizon(value: string | null): ForecastHorizon {
  return value === '7' || value === '126' ? Number(value) as ForecastHorizon : 30
}

interface PacketSelection {
  contextKey: string
  mode: 'fresh' | 'persisted'
  revision: number
}

export function InstrumentWorkspaceScreen() {
  const { locale, t } = usePreferences()
  const { symbol = '', venue = '' } = useParams<{ symbol: string; venue: string }>()
  const [search, setSearch] = useSearchParams()
  const range = historyRange(search.get('range'))
  const horizon = forecastHorizon(search.get('horizon'))
  const compare = search.getAll('compare').filter(Boolean).slice(0, 3)
  const mode = search.get('mode') === 'line' ? 'line' : 'candles'
  const volume = search.get('volume') === '1'
  const showSma20 = search.get('sma20') === '1'
  const showSma50 = search.get('sma50') === '1'
  const validVenue = isVenue(venue)
  const queryClient = useQueryClient()
  const [packetSelection, setPacketSelection] = useState<PacketSelection | null>(null)
  const lastLiveRefresh = useRef(0)
  const trailingLiveRefresh = useRef<ReturnType<typeof setTimeout> | null>(null)
  const refreshWorkspace = useCallback(() => {
    lastLiveRefresh.current = Date.now()
    trailingLiveRefresh.current = null
    void queryClient.invalidateQueries({
      queryKey: ['instrument-workspace', venue, symbol],
      refetchType: 'active',
    }, { cancelRefetch: false })
  }, [queryClient, symbol, venue])
  const onLiveUpdate = useCallback((update: MarketUpdate) => {
    if (update.venue !== venue || update.instrument !== symbol) return
    const remaining = 500 - (Date.now() - lastLiveRefresh.current)
    if (remaining <= 0) {
      if (trailingLiveRefresh.current !== null) clearTimeout(trailingLiveRefresh.current)
      refreshWorkspace()
      return
    }
    if (trailingLiveRefresh.current === null) {
      trailingLiveRefresh.current = setTimeout(refreshWorkspace, remaining)
    }
  }, [refreshWorkspace, symbol, venue])
  useEffect(() => () => {
    if (trailingLiveRefresh.current !== null) clearTimeout(trailingLiveRefresh.current)
  }, [refreshWorkspace])
  const health = useQuery({
    queryKey: ['health'],
    queryFn: api.health,
    retry: false,
  })
  const query = useQuery({
    enabled: validVenue && symbol.length > 0,
    queryKey: ['instrument-workspace', venue, symbol, range, compare],
    queryFn: () => api.instrumentWorkspace(venue as HistoricalVenue, symbol, range, compare),
    placeholderData: (previous, previousQuery) => retainSameInstrument(
      previous,
      previousQuery?.queryKey,
      venue,
      symbol,
    ),
    refetchInterval: 5_000,
    retry: false,
  })
  const liveRuntime = health.data?.runtime_mode === 'live'
  const stream = useLiveConnection(onLiveUpdate, liveRuntime && query.data !== undefined)

  if (!validVenue || symbol.length === 0) {
    return <WorkspaceError error={new Error(t('screen.workspace.invalidRoute'))} symbol={symbol} venue={venue} />
  }
  if (query.isPending) return <WorkspaceLoading />
  if (query.isError && query.data === undefined) {
    if (liveRuntime && query.error instanceof ApiError && query.error.status === 404) {
      return <CockpitDetailScreen showWorkspaceLink={false} />
    }
    return <WorkspaceError error={query.error} symbol={symbol} venue={venue} />
  }
  const workspace = query.data
  const displayedRange = query.isPlaceholderData ? workspace.history.range : range
  const decisionContextKey = `${workspace.instrument.venue}:${workspace.instrument.symbol}:${displayedRange}`
  const defaultPacketMode = workspace.decision.latest === null || workspace.decision.latest === undefined
    ? 'fresh'
    : 'persisted'
  const activeSelection: PacketSelection = packetSelection?.contextKey === decisionContextKey
    ? packetSelection
    : { contextKey: decisionContextKey, mode: defaultPacketMode, revision: 0 }
  if (packetSelection === null || packetSelection.contextKey !== decisionContextKey) {
    setPacketSelection(activeSelection)
  }
  const persistedPacket = activeSelection.mode === 'persisted' ? workspace.decision.latest : null
  const packetSource = persistedPacket === null || persistedPacket === undefined ? 'fresh' : 'persisted'
  const displayedPacket = persistedPacket ?? workspace.decision.draft
  const displayedComparisons = query.isPlaceholderData
    ? (workspace.comparison?.keys ?? []).filter(
        (key) => key !== `${workspace.instrument.venue}:${workspace.instrument.symbol}`,
      )
    : compare
  const forecastPath = workspace.forecast?.paths.find((path) => path.sessions === horizon)
    ?? workspace.forecast?.paths[0]
    ?? null
  const syntheticForecast = workspace.forecast?.synthetic === true
  const liveReasonRaw = workspace.live.reason
    ?? workspace.proposal.blockers[0]
    ?? t('screen.workspace.staleReason')
  const liveReason = evidenceText(liveReasonRaw, locale, t)
  const historyGaps = workspace.history.gaps ?? []
  const historyDuplicates = workspace.history.duplicates ?? []
  const qualityWarnings = [
    workspace.history.resolution_fallback === null || workspace.history.resolution_fallback === undefined
      ? null
      : t('screen.workspace.resolutionFallback', { detail: workspace.history.resolution_fallback }),
    historyGaps.length === 0
      ? null
      : t('screen.workspace.historyGaps', {
          count: String(historyGaps.length),
          detail: historyGaps.join(', '),
        }),
    historyDuplicates.length === 0
      ? null
      : t('screen.workspace.historyDuplicates', {
          count: String(historyDuplicates.length),
          detail: historyDuplicates.join(', '),
        }),
    workspace.live.sequence_gap ? t('screen.workspace.sequenceGap') : null,
    ...workspace.history.limitations.map((detail) => t('screen.workspace.historyLimitation', {
      detail: evidenceText(detail, locale, t),
    })),
    ...(workspace.comparison?.limitations ?? []).map((detail) => t(
      'screen.workspace.comparisonLimitation',
      { detail: evidenceText(detail, locale, t) },
    )),
  ].filter((warning): warning is string => warning !== null)
  const updateParam = (key: string, value: string | null) => {
    const next = new URLSearchParams(search)
    if (value === null) next.delete(key)
    else next.set(key, value)
    setSearch(next)
  }
  const updateComparisons = (peers: string[]) => {
    const next = new URLSearchParams(search)
    next.delete('compare')
    for (const peer of peers) next.append('compare', peer)
    setSearch(next)
  }

  return (
    <div className="space-y-4">
      <WorkspaceHeader stream={stream} workspace={workspace} />
      {query.isRefetchError && <WorkspaceRefreshWarning error={query.error} />}
      {query.isPlaceholderData && (
        <p className="border-l-2 border-sky-600 bg-sky-500/5 px-3 py-2 text-xs" role="status">
          {t('screen.workspace.updatingEvidence')}
        </p>
      )}
      {workspace.live.status !== 'available' && (
        <WorkspaceDegraded rawReason={liveReasonRaw} reason={liveReason} />
      )}
      {qualityWarnings.length > 0 && (
        <section
          aria-label={t('screen.workspace.dataQuality')}
          className="border-l-2 border-sky-500 bg-sky-500/5 px-3 py-2"
          role="status"
        >
          <ul className="space-y-1 font-mono text-xs text-muted-foreground">
            {qualityWarnings.map((warning) => <li key={warning}>{warning}</li>)}
          </ul>
        </section>
      )}
      <div
        className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_18rem_22rem]"
        data-testid="workspace-grid"
      >
        <section
          aria-label={t('screen.workspace.marketCanvas')}
          className="min-w-0 border-y border-border py-3"
        >
          <MarketCanvas
            archivedPacket={packetSource === 'persisted'}
            comparison={workspace.comparison}
            forecast={forecastPath}
            history={workspace.history}
            marketState={displayedPacket.market_state}
            mode={mode}
            onModeChange={(next) => updateParam('mode', next === 'candles' ? null : next)}
            onRangeChange={(next) => updateParam('range', next)}
            onSma20Change={(enabled) => updateParam('sma20', enabled ? '1' : null)}
            onSma50Change={(enabled) => updateParam('sma50', enabled ? '1' : null)}
            onVolumeChange={(enabled) => updateParam('volume', enabled ? '1' : null)}
            range={displayedRange}
            showSma20={showSma20}
            showSma50={showSma50}
            volume={volume}
          />
        </section>

        <section className="space-y-5 border-y border-border py-4" aria-label={t('screen.workspace.evidence')}>
          {packetSource === 'persisted' ? (
            <PacketEvidenceSummary packet={displayedPacket} />
          ) : (
            <>
              <div className="min-w-0 space-y-1 px-3">
                <h2 className="text-xs font-semibold uppercase tracking-widest text-muted-foreground">
                  {t('screen.workspace.evidence')}
                </h2>
                <p className="break-all font-mono text-xs [overflow-wrap:anywhere]">{workspace.history.dataset_id}</p>
                <p className="text-xs text-muted-foreground">
                  {t('screen.workspace.revision', { revision: String(workspace.history.dataset_revision) })}
                </p>
              </div>
              <ComparisonPicker
                onChange={updateComparisons}
                primary={`${workspace.instrument.venue}:${workspace.instrument.symbol}`}
                selected={displayedComparisons}
              />
              <dl className="divide-y divide-border border-y border-border text-xs">
                <div className="flex justify-between gap-3 px-3 py-2">
                  <dt className="text-muted-foreground">{t('screen.workspace.rows')}</dt>
                  <dd className="font-mono tabular-nums">{workspace.history.coverage.rows}</dd>
                </div>
                <div className="flex justify-between gap-3 px-3 py-2">
                  <dt className="text-muted-foreground">{t('screen.workspace.calendar')}</dt>
                  <dd className="font-mono">{workspace.history.calendar}</dd>
                </div>
                <div className="flex justify-between gap-3 px-3 py-2">
                  <dt className="text-muted-foreground">{t('screen.workspace.license')}</dt>
                  <dd
                    className="max-w-40 break-words text-right font-mono"
                    title={workspace.history.license}
                  >
                    {workspace.history.license}
                  </dd>
                </div>
              </dl>
            </>
          )}
          <ScenarioEvidence packet={displayedPacket} />
          {packetSource === 'fresh' && (
            <ForecastEvidence
              forecast={workspace.forecast}
              horizon={horizon}
              onHorizonChange={(next) => updateParam('horizon', next === 30 ? null : String(next))}
              synthetic={syntheticForecast}
              unavailableReason={workspace.forecast_unavailable_reason}
            />
          )}
        </section>

        <aside className="space-y-5 border-y border-border py-4" aria-label={t('screen.workspace.decision')}>
          <DecisionRail
            contextKey={decisionContextKey}
            evidenceUpdating={query.isPlaceholderData}
            key={`${decisionContextKey}:${packetSource}:${activeSelection.revision}`}
            onNewAnalysis={workspace.decision.latest
              ? () => setPacketSelection({
                  contextKey: decisionContextKey,
                  mode: 'fresh',
                  revision: activeSelection.revision + 1,
                })
              : undefined}
            packet={displayedPacket}
            packetSource={packetSource}
            workspace={workspace}
          />
        </aside>
      </div>
    </div>
  )
}

export default InstrumentWorkspaceScreen
