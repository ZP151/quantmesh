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
import { api, type LiveInstrumentState, type LiveSourceState, type LiveStatus } from '@/lib/api'
import { money } from '@/lib/format'
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
                          {worst?.sequence_gap ? ` ${t('screen.cockpit.gap')}` : ''}
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
    </Page>
  )
}
