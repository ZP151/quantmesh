import { useEffect, useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link, useParams } from 'react-router-dom'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Page } from '@/components/page'
import {
  bookSide,
  candleCloses,
  LABEL_TEXT,
  instrumentLabel,
  labelTone,
  mergeUpdate,
  midOf,
  quoteNumbers,
  spreadBps,
  useLiveConnection,
} from '@/lib/live'
import { api } from '@/lib/api'
import type { LiveInstrumentState, LiveView, MarketUpdate } from '@/lib/api'
import { dateTime, money, quantity } from '@/lib/format'

// Instrument detail (iteration 0015 Phase C): the live chart (candle
// closes, hand-drawn SVG — no chart dependency), the order book (the
// latest per-side L2 snapshots) and the trade tape, all driven by the
// one stream this screen subscribes to. Everything shown is labeled by
// the source+age badge in the header; a gap flag or a stale badge is
// the visible reason an order on this instrument would be blocked.

const TAPE_LIMIT = 40
const CHART_LIMIT = 120
const SNAPSHOT_INTERVAL_MS = 10_000

function snapshotUpdate(
  symbol: string,
  venue: string,
  view: LiveView,
): MarketUpdate {
  return {
    venue,
    instrument: symbol,
    kind: view.kind,
    provenance: view.provenance,
    data_time: view.data_time,
    received_at: view.received_at,
    sequence: view.sequence,
    sequence_gap: view.sequence_gap,
    payload: view.payload,
    state: null,
    state_note: null,
  }
}

function Sparkline({ closes }: { closes: number[] }) {
  if (closes.length < 2) {
    return (
      <p className="text-sm text-muted-foreground">
        No candles yet — the chart draws once two closes arrive.
      </p>
    )
  }
  const width = 640
  const height = 160
  const min = Math.min(...closes)
  const max = Math.max(...closes)
  const span = max - min || 1
  const points = closes.map((close, index) => {
    const x = (index / (closes.length - 1)) * width
    const y = height - ((close - min) / span) * (height - 8) - 4
    return `${x.toFixed(1)},${y.toFixed(1)}`
  })
  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      className="h-40 w-full"
      role="img"
      aria-label={`Price chart of the latest ${closes.length} candle closes`}
    >
      <polyline
        points={points.join(' ')}
        fill="none"
        stroke="currentColor"
        strokeWidth="1.5"
        className="text-emerald-500"
      />
    </svg>
  )
}

export function CockpitDetailScreen() {
  const { symbol = '' } = useParams<{ symbol: string }>()
  const [updates, setUpdates] = useState<MarketUpdate[]>([])
  const [instruments, setInstruments] = useState<Record<string, LiveInstrumentState>>({})
  const snapshot = useQuery({
    queryKey: ['live', 'state'],
    queryFn: api.liveState,
    refetchInterval: SNAPSHOT_INTERVAL_MS,
  })

  useEffect(() => {
    const instrument = snapshot.data?.instruments[symbol]
    if (!instrument) return
    setInstruments((previous) => ({ ...previous, [symbol]: instrument }))
    const seeded = Object.values(instrument.kinds).map((view) =>
      snapshotUpdate(symbol, instrument.venue, view),
    )
    setUpdates((previous) => {
      const known = new Set(
        previous.map((update) => `${update.kind}:${update.received_at}:${update.sequence ?? ''}`),
      )
      const missing = seeded.filter(
        (update) => !known.has(`${update.kind}:${update.received_at}:${update.sequence ?? ''}`),
      )
      const next = [...previous, ...missing]
      return next.slice(-(TAPE_LIMIT + CHART_LIMIT))
    })
  }, [snapshot.data, symbol])

  const streamStatus = useLiveConnection((update) => {
    if (update.instrument !== symbol) return
    setUpdates((previous) => {
      const next = [...previous, update]
      return next.length > TAPE_LIMIT + CHART_LIMIT ? next.slice(-(TAPE_LIMIT + CHART_LIMIT)) : next
    })
    // The same reconciliation the watchlist uses, so the badge agrees.
    setInstruments((previous) => mergeUpdate(previous, update))
  })

  const instrument = instruments[symbol]
  const badgeLabel = instrument ? instrumentLabel(instrument) : 'unavailable'

  const byKind = useMemo(() => {
    const latest: Record<string, MarketUpdate | undefined> = {}
    for (const update of updates) latest[update.kind] = update
    return latest
  }, [updates])

  const l2Sides = useMemo(() => {
    let bid: MarketUpdate | undefined
    let ask: MarketUpdate | undefined
    for (const update of updates) {
      if (update.kind !== 'l2_snapshot') continue
      if (update.payload.side === 'bid') bid = update
      else if (update.payload.side === 'ask') ask = update
    }
    return { bid, ask }
  }, [updates])

  const quote = quoteNumbers(byKind.quote)
  const mid = midOf(quote)
  const spread = spreadBps(quote)
  const closes = useMemo(() => candleCloses(updates.slice(-CHART_LIMIT)), [updates])
  const bids = bookSide(l2Sides.bid)
  const asks = bookSide(l2Sides.ask)
  const tape = useMemo(
    () =>
      updates
        .filter((update) => update.kind === 'trade')
        .reverse()
        .slice(0, 12),
    [updates],
  )
  const newest = updates[updates.length - 1]

  if (streamStatus === 'connecting' && updates.length === 0) {
    return (
      <Page
        title={symbol}
        description="Connecting to the live stream for this instrument…"
      >
        <p className="text-sm text-muted-foreground">Waiting for the first update.</p>
      </Page>
    )
  }

  return (
    <Page
      title={symbol}
      description={
        instrument?.venue
          ? `${instrument.venue} — latest local ${quote.bid !== undefined || quote.ask !== undefined ? 'quote' : 'data'} snapshot; freshness is shown below.`
          : 'Waiting for the first update for this instrument.'
      }
      actions={
        <Link
          to="/cockpit"
          className="text-xs text-muted-foreground underline-offset-4 hover:underline"
        >
          Back to watchlist
        </Link>
      }
    >
      <div className="flex flex-wrap items-center gap-3">
        <Badge className={labelTone(badgeLabel)}>{LABEL_TEXT[badgeLabel]}</Badge>
        <span className="text-xs text-muted-foreground">
          {newest ? `last update ${dateTime(newest.received_at)}` : 'no update yet'}
          {newest?.sequence_gap ? ' — ⚠ sequence gap' : ''}
        </span>
        <span className="text-xs text-muted-foreground">
          {mid !== undefined ? `mid ${money(mid)}` : ''}
          {spread !== undefined ? ` · ${spread.toFixed(1)} bps` : ''}
        </span>
      </div>

      <div className="grid gap-5 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Chart</CardTitle>
            <CardDescription>Candle closes, newest right — {closes.length} points.</CardDescription>
          </CardHeader>
          <CardContent>
            <Sparkline closes={closes} />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">Order book</CardTitle>
            <CardDescription>Latest per-side L2 snapshot from the feed.</CardDescription>
          </CardHeader>
          <CardContent>
            {bids.length === 0 && asks.length === 0 ? (
              <p className="text-sm text-muted-foreground">No book depth yet.</p>
            ) : (
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <p className="mb-1 text-xs font-medium text-emerald-600 dark:text-emerald-400">Bids</p>
                  <ul className="space-y-0.5 font-mono text-xs">
                    {bids.map((level, index) => (
                      <li key={index} className="flex justify-between tabular-nums">
                        <span>{money(level.price)}</span>
                        <span className="text-muted-foreground">{quantity(level.size)}</span>
                      </li>
                    ))}
                  </ul>
                </div>
                <div>
                  <p className="mb-1 text-xs font-medium text-destructive">Asks</p>
                  <ul className="space-y-0.5 font-mono text-xs">
                    {asks.map((level, index) => (
                      <li key={index} className="flex justify-between tabular-nums">
                        <span>{money(level.price)}</span>
                        <span className="text-muted-foreground">{quantity(level.size)}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              </div>
            )}
          </CardContent>
        </Card>

        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle className="text-base">Trade tape</CardTitle>
            <CardDescription>Most recent trades first, from the local feed.</CardDescription>
          </CardHeader>
          <CardContent className="p-0">
            {tape.length === 0 ? (
              <p className="px-4 pb-4 text-sm text-muted-foreground">No trades yet.</p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-border text-left text-xs text-muted-foreground">
                      <th className="px-4 py-2 font-medium">Time</th>
                      <th className="px-4 py-2 text-right font-medium">Price</th>
                      <th className="px-4 py-2 text-right font-medium">Size</th>
                      <th className="px-4 py-2 text-right font-medium">Side</th>
                      <th className="px-4 py-2 text-right font-medium">Seq</th>
                    </tr>
                  </thead>
                  <tbody>
                    {tape.map((update, index) => (
                      <tr key={update.sequence ?? `${update.received_at}-${index}`} className="border-b border-border/60 last:border-0">
                        <td className="px-4 py-1.5 font-mono text-xs text-muted-foreground">
                          {dateTime(update.received_at)}
                        </td>
                        <td className="px-4 py-1.5 text-right font-mono tabular-nums">
                          {typeof update.payload.price === 'number' ? money(update.payload.price) : '—'}
                        </td>
                        <td className="px-4 py-1.5 text-right font-mono tabular-nums">
                          {typeof update.payload.size === 'number' ? quantity(update.payload.size) : '—'}
                        </td>
                        <td className="px-4 py-1.5 text-right">
                          {update.payload.side === 'buy' ? (
                            <span className="text-emerald-600 dark:text-emerald-400">buy</span>
                          ) : update.payload.side === 'sell' ? (
                            <span className="text-destructive">sell</span>
                          ) : (
                            <span className="text-muted-foreground">—</span>
                          )}
                        </td>
                        <td className="px-4 py-1.5 text-right font-mono text-xs text-muted-foreground">
                          {update.sequence ?? '—'}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </Page>
  )
}
