import { useCallback } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useParams, useSearchParams } from 'react-router-dom'

import { Button } from '@/components/ui/button'
import { WorkspaceLoading } from '@/components/workspace-loading'
import {
  api,
  type HistoricalVenue,
  type HistoryRange,
} from '@/lib/api'
import { money, quantity } from '@/lib/format'
import { useLiveConnection } from '@/lib/live'
import { usePreferences } from '@/lib/preferences'
import { WorkspaceHeader } from './instrument/WorkspaceHeader'
import { ComparisonPicker } from './instrument/ComparisonPicker'
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

export function InstrumentWorkspaceScreen() {
  const { t } = usePreferences()
  const { symbol = '', venue = '' } = useParams<{ symbol: string; venue: string }>()
  const [search, setSearch] = useSearchParams()
  const range = historyRange(search.get('range'))
  const compare = search.getAll('compare').filter(Boolean).slice(0, 3)
  const mode = search.get('mode') === 'line' ? 'line' : 'candles'
  const volume = search.get('volume') === '1'
  const showSma20 = search.get('sma20') === '1'
  const showSma50 = search.get('sma50') === '1'
  const validVenue = isVenue(venue)
  const stream = useLiveConnection(useCallback(() => {}, []))
  const query = useQuery({
    enabled: validVenue && symbol.length > 0,
    queryKey: ['instrument-workspace', venue, symbol, range, compare],
    queryFn: () => api.instrumentWorkspace(venue as HistoricalVenue, symbol, range, compare),
    retry: false,
  })

  if (!validVenue || symbol.length === 0) {
    return <WorkspaceError error={new Error(t('screen.workspace.invalidRoute'))} symbol={symbol} venue={venue} />
  }
  if (query.isPending) return <WorkspaceLoading />
  if (query.isError) return <WorkspaceError error={query.error} symbol={symbol} venue={venue} />
  const workspace = query.data
  const forecastPath = workspace.forecast?.paths.find((path) => path.sessions === 30)
    ?? workspace.forecast?.paths[0]
    ?? null
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
          <div className="space-y-1 px-3">
            <h2 className="text-xs font-semibold uppercase tracking-widest text-muted-foreground">
              {t('screen.workspace.forecast')}
            </h2>
            <p className="text-xs">
              {workspace.forecast === null
                ? workspace.forecast_unavailable_reason ?? t('screen.workspace.noForecast')
                : workspace.forecast.eligible
                  ? t('screen.workspace.forecastEligible')
                  : t('screen.workspace.forecastBlocked')}
            </p>
          </div>
        </section>

        <aside className="space-y-5 border-y border-border py-4" aria-label={t('screen.workspace.decision')}>
          <div className="space-y-1 px-4">
            <h2 className="text-xs font-semibold uppercase tracking-widest text-muted-foreground">
              {t('screen.workspace.decision')}
            </h2>
            <p className="text-sm font-medium">{t('screen.workspace.paperOnly')}</p>
          </div>
          <dl className="grid grid-cols-2 gap-x-4 gap-y-3 px-4 text-xs">
            <div>
              <dt className="text-muted-foreground">{t('screen.workspace.cash')}</dt>
              <dd className="font-mono tabular-nums">{money(workspace.risk.cash)}</dd>
            </div>
            <div>
              <dt className="text-muted-foreground">{t('screen.workspace.position')}</dt>
              <dd className="font-mono tabular-nums">
                {workspace.position === null ? t('screen.workspace.noPosition') : quantity(workspace.position.quantity)}
              </dd>
            </div>
          </dl>
          {workspace.proposal.blockers.length > 0 && (
            <ul className="space-y-1 border-y border-border px-4 py-3 text-xs text-muted-foreground">
              {workspace.proposal.blockers.map((blocker) => <li key={blocker}>{blocker}</li>)}
            </ul>
          )}
          <div className="px-4">
            <Button className="w-full" disabled={!workspace.proposal.allowed} type="button">
              {t('screen.workspace.createProposal')}
            </Button>
          </div>
        </aside>
      </div>
    </div>
  )
}

export default InstrumentWorkspaceScreen
