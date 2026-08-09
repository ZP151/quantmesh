import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { ArrowLeftRight } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Page } from '@/components/page'
import { ErrorState, LoadingState } from '@/components/state'
import { api, type PredictionRow, type PredictionVenueRow } from '@/lib/api'
import { LABEL_TEXT, labelTone } from '@/lib/live'
import { money } from '@/lib/format'
import { usePreferences } from '@/lib/preferences'

// The prediction comparison board (iteration 0015 Phase E): the same
// event priced on Polymarket and Kalshi, side by side — implied
// probability (each venue's own mid), spread, touch depth, book
// liquidity and the feed's freshness label, plus the cross-venue
// difference in percentage points. The screen renders only what the
// server folded from real quotes: a quiet or unconfigured venue shows
// "—" with its label, never a fabricated number. Calibration is the
// existing forecast surface, linked — never re-fabricated here.

const REFRESH_MS = 10_000

function diffText(diff: number | null): string {
  if (diff === null) return '—'
  return `${diff > 0 ? '+' : ''}${diff.toFixed(1)} pp`
}

/** Differences of a full point get the eye; sub-point noise stays muted. */
function diffTone(diff: number | null): string {
  if (diff === null) return 'text-muted-foreground'
  return Math.abs(diff) >= 1
    ? 'font-semibold tabular-nums text-amber-600 dark:text-amber-400'
    : 'font-semibold tabular-nums text-muted-foreground'
}

function VenueBlock({ row }: { row: PredictionVenueRow }) {
  const { t } = usePreferences()
  return (
    <div className="rounded-lg border border-border p-4">
      <div className="flex items-center justify-between gap-2">
        <span className="text-sm font-medium capitalize">{row.venue}</span>
        <Badge className={labelTone(row.label)}>{t(LABEL_TEXT[row.label])}</Badge>
      </div>
      <p className="mt-2 text-2xl font-semibold tabular-nums">
        {row.probability !== null ? `${row.probability.toFixed(1)}%` : '—'}
      </p>
      <dl className="mt-3 grid grid-cols-2 gap-x-4 gap-y-1.5 text-xs text-muted-foreground">
        <div className="flex items-baseline justify-between gap-2">
          <dt>Bid / Ask</dt>
          <dd className="font-mono tabular-nums text-foreground">
            {row.bid !== null && row.ask !== null
              ? `${money(row.bid)} / ${money(row.ask)}`
              : '—'}
          </dd>
        </div>
        <div className="flex items-baseline justify-between gap-2">
          <dt>Spread</dt>
          <dd className="font-mono tabular-nums text-foreground">
            {row.spread_bps !== null ? `${row.spread_bps.toFixed(1)} bps` : '—'}
          </dd>
        </div>
        <div className="flex items-baseline justify-between gap-2">
          <dt>Touch depth</dt>
          <dd className="font-mono tabular-nums text-foreground">
            {row.depth !== null ? row.depth.toFixed(0) : '—'}
          </dd>
        </div>
        <div className="flex items-baseline justify-between gap-2">
          <dt>Liquidity</dt>
          <dd className="font-mono tabular-nums text-foreground">
            {row.liquidity !== null ? row.liquidity.toFixed(0) : '—'}
          </dd>
        </div>
      </dl>
    </div>
  )
}

function PairCard({ pair }: { pair: PredictionRow }) {
  return (
    <Card>
      <CardHeader>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="space-y-1">
            <CardTitle className="text-base">{pair.title}</CardTitle>
            <CardDescription>
              {pair.expiry !== null ? `Expires ${pair.expiry.slice(0, 10)}` : 'No expiry listed'}
            </CardDescription>
          </div>
          <span className="flex items-center gap-1.5 text-sm">
            <ArrowLeftRight className="size-3.5 text-muted-foreground" aria-hidden />
            <span className="text-muted-foreground">Polymarket − Kalshi</span>
            <span className={diffTone(pair.diff)}>{diffText(pair.diff)}</span>
          </span>
        </div>
      </CardHeader>
      <CardContent>
        <div className="grid gap-3 sm:grid-cols-2">
          {pair.venues.map((row) => (
            <VenueBlock key={row.venue} row={row} />
          ))}
        </div>
      </CardContent>
    </Card>
  )
}

export function PredictionScreen() {
  const query = useQuery({
    queryKey: ['live', 'prediction'],
    queryFn: api.prediction,
    refetchInterval: REFRESH_MS,
  })

  if (query.isPending) return <LoadingState rows={3} />
  if (query.isError) {
    const detail = query.error instanceof Error ? query.error.message : String(query.error)
    return (
      <Page
        title="Prediction markets"
        description="The same event priced on Polymarket and Kalshi — implied probability, spread, depth and liquidity from the attached read-only feed."
      >
        <ErrorState
          title="Prediction board unavailable"
          detail={`${detail} — start the workstation with --live and a QUANTMESH_PREDICTION_WATCHLIST.`}
        />
      </Page>
    )
  }

  return (
    <Page
      title="Prediction markets"
      description="The same event priced on Polymarket and Kalshi — implied probability, spread, depth and liquidity from the attached read-only feed."
      actions={
        <Link
          to="/research/forecasts"
          className="text-sm font-medium text-primary hover:underline"
        >
          Calibration & forecast history
        </Link>
      }
    >
      <div className="space-y-4">
        {query.data.map((pair) => (
          <PairCard key={pair.event_key} pair={pair} />
        ))}
      </div>
    </Page>
  )
}
