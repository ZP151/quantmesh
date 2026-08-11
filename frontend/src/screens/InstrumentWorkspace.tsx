import { useCallback, useEffect, useRef } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useParams, useSearchParams } from 'react-router-dom'

import { WorkspaceLoading } from '@/components/workspace-loading'
import {
  api,
  type HistoricalVenue,
  type HistoryRange,
  type MarketUpdate,
} from '@/lib/api'
import { useLiveConnection } from '@/lib/live'
import { usePreferences } from '@/lib/preferences'
import { WorkspaceHeader } from './instrument/WorkspaceHeader'
import { ComparisonPicker } from './instrument/ComparisonPicker'
import { DecisionRail } from './instrument/DecisionRail'
import { ForecastEvidence, type ForecastHorizon } from './instrument/ForecastEvidence'
import { MarketCanvas } from './instrument/MarketCanvas'
import { WorkspaceDegraded, WorkspaceError } from './instrument/WorkspaceStates'

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

export function InstrumentWorkspaceScreen() {
  const { t } = usePreferences()
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
  const stream = useLiveConnection(onLiveUpdate)
  const query = useQuery({
    enabled: validVenue && symbol.length > 0,
    queryKey: ['instrument-workspace', venue, symbol, range, compare],
    queryFn: () => api.instrumentWorkspace(venue as HistoricalVenue, symbol, range, compare),
    refetchInterval: 5_000,
    retry: false,
  })

  if (!validVenue || symbol.length === 0) {
    return <WorkspaceError error={new Error(t('screen.workspace.invalidRoute'))} symbol={symbol} venue={venue} />
  }
  if (query.isPending) return <WorkspaceLoading />
  if (query.isError) return <WorkspaceError error={query.error} symbol={symbol} venue={venue} />
  const workspace = query.data
  const forecastPath = workspace.forecast?.paths.find((path) => path.sessions === horizon)
    ?? workspace.forecast?.paths[0]
    ?? null
  const syntheticForecast = [
    workspace.history.source,
    workspace.history.license,
    ...(workspace.forecast?.limitations ?? []),
  ].some((value) => value.toLowerCase().includes('synthetic'))
  const liveReason = workspace.live.reason
    ?? workspace.proposal.blockers[0]
    ?? t('screen.workspace.staleReason')
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
      {workspace.live.status !== 'available' && <WorkspaceDegraded reason={liveReason} />}
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
            comparison={workspace.comparison}
            forecast={forecastPath}
            history={workspace.history}
            mode={mode}
            onModeChange={(next) => updateParam('mode', next === 'candles' ? null : next)}
            onRangeChange={(next) => updateParam('range', next)}
            onSma20Change={(enabled) => updateParam('sma20', enabled ? '1' : null)}
            onSma50Change={(enabled) => updateParam('sma50', enabled ? '1' : null)}
            onVolumeChange={(enabled) => updateParam('volume', enabled ? '1' : null)}
            range={range}
            showSma20={showSma20}
            showSma50={showSma50}
            volume={volume}
          />
        </section>

        <section className="space-y-5 border-y border-border py-4" aria-label={t('screen.workspace.evidence')}>
          <div className="space-y-1 px-3">
            <h2 className="text-xs font-semibold uppercase tracking-widest text-muted-foreground">
              {t('screen.workspace.evidence')}
            </h2>
            <p className="font-mono text-xs">{workspace.history.dataset_id}</p>
            <p className="text-xs text-muted-foreground">
              {t('screen.workspace.revision', { revision: String(workspace.history.dataset_revision) })}
            </p>
          </div>
          <ComparisonPicker
            onChange={updateComparisons}
            primary={`${workspace.instrument.venue}:${workspace.instrument.symbol}`}
            selected={compare}
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
              <dd className="max-w-36 truncate font-mono">{workspace.history.license}</dd>
            </div>
          </dl>
          <ForecastEvidence
            forecast={workspace.forecast}
            horizon={horizon}
            onHorizonChange={(next) => updateParam('horizon', next === 30 ? null : String(next))}
            synthetic={syntheticForecast}
            unavailableReason={workspace.forecast_unavailable_reason}
          />
        </section>

        <aside className="space-y-5 border-y border-border py-4" aria-label={t('screen.workspace.decision')}>
          <DecisionRail
            key={`${workspace.instrument.venue}:${workspace.instrument.symbol}`}
            workspace={workspace}
          />
        </aside>
      </div>
    </div>
  )
}

export default InstrumentWorkspaceScreen
