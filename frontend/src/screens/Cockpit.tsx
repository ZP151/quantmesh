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
  if (venues.length === 0) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Connector health</CardTitle>
          <CardDescription>No venue reported a status yet.</CardDescription>
        </CardHeader>
      </Card>
    )
  }
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Connector health</CardTitle>
        <CardDescription>
          Per-source connection and freshness states from the supervisors' STATUS transitions.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {venues.map((venue) => (
          <div key={venue.venue} className="space-y-2">
            <div className="flex items-center gap-2">
              <span className="text-sm font-medium capitalize">{venue.venue}</span>
              <Badge
                className={venue.connected ? 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400' : 'bg-destructive/10 text-destructive'}
              >
                {venue.connected ? 'connected' : 'disconnected'}
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
        title="Live cockpit"
        description="A bounded watchlist of real, sourced, freshness-labeled quotes from the attached live feed."
      >
        <ErrorState
          title="Live cockpit unavailable"
          detail={`${detail} — start the workstation with --live and a QUANTMESH_LIVE_WATCHLIST.`}
        />
      </Page>
    )
  }

  const banner =
    streamStatus === 'live'
      ? 'Local stream connected over WebSocket — venue freshness is shown below.'
      : streamStatus === 'fallback'
        ? 'WebSocket unavailable — streaming over the SSE fallback.'
        : streamStatus === 'down'
          ? 'Stream down — showing the latest snapshot, refreshed every 10 s.'
          : 'Connecting to the live stream…'

  return (
    <Page
      title="Live cockpit"
      description="A bounded watchlist of real, sourced, freshness-labeled quotes from the attached live feed."
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
                  <th className="px-4 py-2.5 font-medium">Symbol</th>
                  <th className="px-4 py-2.5 font-medium">Venue</th>
                  <th className="px-4 py-2.5 font-medium">State</th>
                  <th className="px-4 py-2.5 text-right font-medium">Bid</th>
                  <th className="px-4 py-2.5 text-right font-medium">Ask</th>
                  <th className="px-4 py-2.5 text-right font-medium">Mid</th>
                  <th className="px-4 py-2.5 text-right font-medium">Spread bps</th>
                  <th className="px-4 py-2.5 text-right font-medium">Last</th>
                  <th className="px-4 py-2.5 text-right font-medium">Age</th>
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
                        <Badge className={labelTone(label)}>{LABEL_TEXT[label]}</Badge>
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
                          {worst?.sequence_gap ? ' ⚠ gap' : ''}
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
