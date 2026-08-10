import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { Radio } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Page } from '@/components/page'
import { ErrorState, LoadingState } from '@/components/state'
import { useQuery } from '@tanstack/react-query'
import {
  ageText,
  instrumentLabel,
  LABEL_TEXT,
  labelTone,
  mergeUpdate,
  midOf,
  quoteNumbers,
  spreadBps,
  useLiveConnection,
} from '@/lib/live'
import { api, type LiveInstrumentState, type LiveSourceState, type LiveStatus, type ReplayWindow } from '@/lib/api'
import { dateTime, money, timeOfDay } from '@/lib/format'
import { usePreferences } from '@/lib/preferences'

// The Live Market Cockpit watchlist (iteration 0015 Phase C): every
// instrument the feed knows, with the provenance+age label the server
// derives (real/delayed/stale/synthetic/unavailable), the current
// quote and last trade, and a stream banner that says which transport
// is carrying the updates. Below the board sits the connector-health
// panel driven by the supervisors' STATUS transitions. The browser
// never touches the venues — everything arrives via the local feed.

const SNAPSHOT_INTERVAL_MS = 10_000

function sourceTone(state: LiveSourceState): string {
  switch (state) {
    case 'connected':
      return 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400'
    case 'lagging':
      return 'bg-amber-500/10 text-amber-600 dark:text-amber-400'
    case 'stale':
      return 'bg-orange-500/10 text-orange-600 dark:text-orange-400'
    case 'disconnected':
      return 'bg-destructive/10 text-destructive'
    case 'unavailable':
      return 'bg-muted text-muted-foreground'
  }
}

function ConnectorPanel({ venues }: { venues: LiveStatus['venues'] }) {
  const { t } = usePreferences()
  if (venues.length === 0) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="text-base">{t('screen.cockpit.connectorHealth')}</CardTitle>
          <CardDescription>{t('screen.cockpit.connectorEmpty')}</CardDescription>
        </CardHeader>
      </Card>
    )
  }
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">{t('screen.cockpit.connectorHealth')}</CardTitle>
        <CardDescription>{t('screen.cockpit.connectorDesc')}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {venues.map((venue) => (
          <div key={venue.venue} className="space-y-2">
            <div className="flex items-center gap-2">
              <span className="text-sm font-medium capitalize">{venue.venue}</span>
              <Badge
                className={venue.connected ? 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400' : 'bg-destructive/10 text-destructive'}
              >
                {venue.connected ? t('screen.cockpit.connected') : t('screen.cockpit.disconnected')}
              </Badge>
            </div>
            <div className="flex flex-wrap gap-1.5">
              {venue.sources.map((source) => (
                <span
                  key={source.instrument}
                  className="inline-flex items-center gap-1.5 rounded-4xl border border-border px-2 py-0.5 text-xs"
                >
                  <span className="font-mono">{source.instrument}</span>
                  <Badge className={sourceTone(source.state)}>{source.state}</Badge>
                  {source.age_ms !== null && (
                    <span className="text-muted-foreground">{ageText(source.age_ms)}</span>
                  )}
                </span>
              ))}
            </div>
          </div>
        ))}
      </CardContent>
    </Card>
  )
}

/** The most informative payload number of one update, compactly. */
function payloadSummary(update: ReplayWindow['updates'][number]): string {
  const payload = update.payload
  if (typeof payload.bid === 'number' && typeof payload.ask === 'number') {
    return `${money(payload.bid)} / ${money(payload.ask)}`
  }
  const single =
    payload.price ?? payload.close ?? payload.last ?? payload.mark_price
  if (typeof single === 'number') return money(single)
  if (update.kind === 'l2_snapshot' && Array.isArray(payload.levels)) {
    return String(payload.levels.length)
  }
  return '—'
}

/** The recorded replay workflow (iteration 0019 slice 4): pick a window
 * over the local lake, replay it below a visible provenance banner, and
 * clear it again — a read-only display that never folds into the live
 * cache or the paper surface. */
function ReplayPanel() {
  const { t } = usePreferences()
  const [replay, setReplay] = useState<ReplayWindow | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const extent = useQuery({
    queryKey: ['live', 'replay', 'extent'],
    queryFn: api.replayExtent,
    refetchInterval: SNAPSHOT_INTERVAL_MS,
    retry: false,
  })

  const runWindow = async (start: string | null, end: string | null) => {
    setLoading(true)
    setError(null)
    try {
      const params: { start?: string; end?: string } = {}
      if (start !== null) params.start = start
      if (end !== null) params.end = end
      setReplay(await api.replayWindow(params))
    } catch (cause) {
      setReplay(null)
      setError(cause instanceof Error ? cause.message : String(cause))
    } finally {
      setLoading(false)
    }
  }

  const extentBody = extent.data
  const noLake = extent.isError
  const empty = extent.isSuccess && !extentBody
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">{t('screen.cockpit.replay')}</CardTitle>
        <CardDescription>{t('screen.cockpit.replayDesc')}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {noLake || empty ? (
          <p className="text-sm text-muted-foreground">
            {noLake
              ? t('screen.cockpit.replayNoLake')
              : t('screen.cockpit.replayEmpty')}
          </p>
        ) : (
          <div className="space-y-4">
            {extentBody && (
              <p className="text-xs text-muted-foreground">
                {t('screen.cockpit.replayExtent', {
                  count: String(extentBody.count),
                  earliest: dateTime(extentBody.earliest ?? ''),
                  latest: dateTime(extentBody.latest ?? ''),
                  venues: extentBody.venues.join(', '),
                })}
              </p>
            )}
            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                disabled={loading}
                onClick={() =>
                  extentBody &&
                  runWindow(
                    new Date(new Date(extentBody.latest ?? Date.now()).getTime() - 5 * 60_000).toISOString(),
                    extentBody.latest,
                  )
                }
                className="rounded-md border border-border px-2.5 py-1 text-xs hover:bg-muted"
              >
                {t('screen.cockpit.replayWindow5m')}
              </button>
              <button
                type="button"
                disabled={loading}
                onClick={() =>
                  extentBody &&
                  runWindow(
                    new Date(new Date(extentBody.latest ?? Date.now()).getTime() - 15 * 60_000).toISOString(),
                    extentBody.latest,
                  )
                }
                className="rounded-md border border-border px-2.5 py-1 text-xs hover:bg-muted"
              >
                {t('screen.cockpit.replayWindow15m')}
              </button>
              <button
                type="button"
                disabled={loading}
                onClick={() =>
                  extentBody && runWindow(extentBody.earliest, extentBody.latest)
                }
                className="rounded-md border border-border px-2.5 py-1 text-xs hover:bg-muted"
              >
                {t('screen.cockpit.replayWindowAll')}
              </button>
              {loading && (
                <span className="text-xs text-muted-foreground">
                  {t('screen.cockpit.replayLoading')}
                </span>
              )}
            </div>
            {error && <p className="text-xs text-destructive">{error}</p>}
            {replay && (
              <div className="space-y-2">
                <div className="flex flex-wrap items-center gap-2 rounded-lg border border-border bg-muted/40 px-3 py-2">
                  <Badge className="bg-violet-500/10 text-violet-600 dark:text-violet-400">
                    {t('screen.cockpit.replayMode')}
                  </Badge>
                  <span className="text-xs text-muted-foreground">
                    {t('screen.cockpit.replayBanner', {
                      start: dateTime(replay.window.start ?? ''),
                      end: dateTime(replay.window.end ?? ''),
                      count: String(replay.window.count),
                    })}
                  </span>
                  <button
                    type="button"
                    onClick={() => setReplay(null)}
                    className="ml-auto text-xs text-muted-foreground underline-offset-4 hover:underline"
                  >
                    {t('screen.cockpit.replayClear')}
                  </button>
                </div>
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-border text-left text-xs text-muted-foreground">
                        <th className="px-3 py-2 font-medium">{t('screen.cockpit.replayCol.time')}</th>
                        <th className="px-3 py-2 font-medium">{t('table.venue')}</th>
                        <th className="px-3 py-2 font-medium">{t('table.symbol')}</th>
                        <th className="px-3 py-2 font-medium">{t('screen.cockpit.replayCol.kind')}</th>
                        <th className="px-3 py-2 text-right font-medium">{t('screen.cockpit.col.seq')}</th>
                        <th className="px-3 py-2 font-medium">{t('screen.cockpit.replayCol.provenance')}</th>
                        <th className="px-3 py-2 text-right font-medium">{t('screen.cockpit.replayCol.value')}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {replay.updates.map((update, index) => (
                        <tr key={index} className="border-b border-border/60 last:border-0">
                          <td className="px-3 py-1.5 font-mono text-xs text-muted-foreground">
                            {timeOfDay(update.received_at)}
                          </td>
                          <td className="px-3 py-1.5 text-xs capitalize text-muted-foreground">
                            {update.venue}
                          </td>
                          <td className="px-3 py-1.5 font-mono text-xs">{update.instrument}</td>
                          <td className="px-3 py-1.5 text-xs">{update.kind}</td>
                          <td className="px-3 py-1.5 text-right font-mono text-xs">
                            <span className={update.sequence_gap ? 'text-destructive' : ''}>
                              {update.sequence ?? '—'}
                              {update.sequence_gap ? ` ${t('screen.cockpit.gap')}` : ''}
                            </span>
                          </td>
                          <td className="px-3 py-1.5 text-xs">{update.provenance}</td>
                          <td className="px-3 py-1.5 text-right font-mono text-xs tabular-nums">
                            {payloadSummary(update)}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  )
}

export function CockpitScreen() {
  const { t } = usePreferences()
  const snapshot = useQuery({
    queryKey: ['live', 'state'],
    queryFn: api.liveState,
    refetchInterval: SNAPSHOT_INTERVAL_MS,
  })
  const [instruments, setInstruments] = useState<Record<string, LiveInstrumentState>>({})
  useEffect(() => {
    if (snapshot.data) setInstruments(snapshot.data.instruments)
  }, [snapshot.data])

  const statusQuery = useQuery({
    queryKey: ['live', 'status'],
    queryFn: api.liveStatus,
    refetchInterval: SNAPSHOT_INTERVAL_MS,
  })

  const streamStatus = useLiveConnection((update) => {
    setInstruments((previous) => mergeUpdate(previous, update))
  })

  const rows = useMemo(
    () =>
      Object.entries(instruments)
        .map(([symbol, instrument]) => ({ symbol, instrument }))
        .sort((a, b) => a.symbol.localeCompare(b.symbol)),
    [instruments],
  )

  if (snapshot.isPending) return <LoadingState rows={4} />
  if (snapshot.isError) {
    const detail =
      snapshot.error instanceof Error ? snapshot.error.message : String(snapshot.error)
    return (
      <Page
        title={t('screen.cockpit.title')}
        description={t('screen.cockpit.description')}
      >
        <ErrorState
          title={t('surface.unavailable', { title: t('screen.cockpit.title') })}
          detail={t('screen.cockpit.liveHint', { detail })}
        />
      </Page>
    )
  }

  const banner =
    streamStatus === 'live'
      ? t('screen.cockpit.banner.live')
      : streamStatus === 'fallback'
        ? t('screen.cockpit.banner.fallback')
        : streamStatus === 'down'
          ? t('screen.cockpit.banner.down')
          : t('screen.cockpit.banner.connecting')

  return (
    <Page
      title={t('screen.cockpit.title')}
      description={t('screen.cockpit.description')}
      actions={
        <span className="flex items-center gap-2 text-xs text-muted-foreground">
          <Radio className="size-3.5" aria-hidden />
          {banner}
        </span>
      }
    >
      <Card>
        <CardContent className="p-0">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border text-left text-xs text-muted-foreground">
                  <th className="px-4 py-2.5 font-medium">{t('table.symbol')}</th>
                  <th className="px-4 py-2.5 font-medium">{t('table.venue')}</th>
                  <th className="px-4 py-2.5 font-medium">{t('screen.cockpit.col.state')}</th>
                  <th className="px-4 py-2.5 text-right font-medium">{t('screen.cockpit.col.bid')}</th>
                  <th className="px-4 py-2.5 text-right font-medium">{t('screen.cockpit.col.ask')}</th>
                  <th className="px-4 py-2.5 text-right font-medium">{t('screen.cockpit.col.mid')}</th>
                  <th className="px-4 py-2.5 text-right font-medium">{t('screen.cockpit.col.spreadBps')}</th>
                  <th className="px-4 py-2.5 text-right font-medium">{t('screen.cockpit.col.last')}</th>
                  <th className="px-4 py-2.5 text-right font-medium">{t('screen.cockpit.col.eventTime')}</th>
                  <th className="px-4 py-2.5 text-right font-medium">{t('screen.cockpit.col.received')}</th>
                  <th className="px-4 py-2.5 text-right font-medium">{t('screen.cockpit.col.seq')}</th>
                  <th className="px-4 py-2.5 text-right font-medium">{t('screen.cockpit.col.age')}</th>
                </tr>
              </thead>
              <tbody>
                {rows.map(({ symbol, instrument }) => {
                  const quote = quoteNumbers(instrument.kinds.quote)
                  const trade = instrument.kinds.trade
                  const label = instrumentLabel(instrument)
                  const mid = midOf(quote)
                  const spread = spreadBps(quote)
                  const worst = instrument.kinds.quote ?? instrument.kinds.trade
                  return (
                    <tr key={symbol} className="border-b border-border/60 last:border-0">
                      <td className="px-4 py-2.5">
                        <Link
                          to={`/cockpit/${encodeURIComponent(symbol)}`}
                          className="font-mono font-medium hover:underline"
                        >
                          {symbol}
                        </Link>
                      </td>
                      <td className="px-4 py-2.5 capitalize text-muted-foreground">
                        {instrument.venue}
                      </td>
                      <td className="px-4 py-2.5">
                        <Badge className={labelTone(label)}>{t(LABEL_TEXT[label])}</Badge>
                      </td>
                      <td className="px-4 py-2.5 text-right font-mono tabular-nums">
                        {quote.bid !== undefined ? money(quote.bid) : '—'}
                      </td>
                      <td className="px-4 py-2.5 text-right font-mono tabular-nums">
                        {quote.ask !== undefined ? money(quote.ask) : '—'}
                      </td>
                      <td className="px-4 py-2.5 text-right font-mono tabular-nums">
                        {mid !== undefined ? money(mid) : '—'}
                      </td>
                      <td className="px-4 py-2.5 text-right font-mono tabular-nums">
                        {spread !== undefined ? spread.toFixed(1) : '—'}
                      </td>
                      <td className="px-4 py-2.5 text-right font-mono tabular-nums">
                        {trade && typeof trade.payload.price === 'number'
                          ? money(trade.payload.price)
                          : '—'}
                      </td>
                      <td className="px-4 py-2.5 text-right font-mono text-xs tabular-nums text-muted-foreground">
                        {worst ? timeOfDay(worst.data_time) : '—'}
                      </td>
                      <td className="px-4 py-2.5 text-right font-mono text-xs tabular-nums text-muted-foreground">
                        {worst ? timeOfDay(worst.received_at) : '—'}
                      </td>
                      <td className="px-4 py-2.5 text-right font-mono tabular-nums">
                        <span
                          className={
                            worst?.sequence_gap
                              ? 'text-destructive'
                              : 'text-muted-foreground'
                          }
                          title={
                            worst?.sequence_gap
                              ? t('screen.cockpit.gap')
                              : undefined
                          }
                        >
                          {worst?.sequence ?? '—'}
                          {worst?.sequence_gap ? ` ${t('screen.cockpit.gap')}` : ''}
                        </span>
                      </td>
                      <td className="px-4 py-2.5 text-right font-mono tabular-nums">
                        <span
                          className={
                            worst?.sequence_gap
                              ? 'text-destructive'
                              : label === 'stale'
                                ? 'text-orange-600 dark:text-orange-400'
                                : 'text-muted-foreground'
                          }
                        >
                          {worst ? ageText(worst.age_ms) : '—'}
                        </span>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>
      <ConnectorPanel venues={statusQuery.data?.venues ?? []} />
      <ReplayPanel />
    </Page>
  )
}
