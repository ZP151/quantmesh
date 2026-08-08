import { Link } from 'react-router-dom'
import { LayoutGrid, Star, Wallet } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Separator } from '@/components/ui/separator'
import { Page } from '@/components/page'
import { Surface, useSurface } from '@/components/state'
import { api } from '@/lib/api'
import { money, venueLabel } from '@/lib/format'

function StatRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-4">
      <span className="text-muted-foreground">{label}</span>
      <span className="font-mono tabular-nums">{children}</span>
    </div>
  )
}

/** The workstation home: account + the per-venue boards + watchlist. */
export function OverviewScreen() {
  const query = useSurface(['overview'], api.overview)

  return (
    <Page
      title="Overview"
      description="The paper workstation at a glance — account, cross-venue marks, watchlist. All synthetic, all labeled, all deterministic."
    >
      <Surface query={query} title="Overview">
        {(overview) => (
          <div className="space-y-5">
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="flex items-center gap-2 text-base">
                  <Wallet className="size-4" aria-hidden /> Account
                </CardTitle>
                <CardDescription>Paper account bound to this workstation.</CardDescription>
              </CardHeader>
              <CardContent className="space-y-2 text-sm">
                <StatRow label="Cash">{money(overview.account.cash)}</StatRow>
                <StatRow label="Starting cash">{money(overview.account.starting_cash)}</StatRow>
                <StatRow label="Equity">{money(overview.account.equity)}</StatRow>
                <Separator className="my-2" />
                <div className="flex items-center justify-between gap-4">
                  <span className="text-muted-foreground">Kill switch</span>
                  <Badge variant={overview.account.kill_switch ? 'destructive' : 'outline'}>
                    {overview.account.kill_switch ? 'engaged' : 'disarmed'}
                  </Badge>
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="flex items-center gap-2 text-base">
                  <LayoutGrid className="size-4" aria-hidden /> Venue boards
                </CardTitle>
                <CardDescription>
                  The same board the Markets screen renders, with provenance per surface.
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                {overview.venues.map((entry) => (
                  <div key={entry.venue}>
                    <p className="mb-1.5 text-xs font-medium text-muted-foreground">{venueLabel(entry.venue)}</p>
                    <div className="flex flex-wrap gap-2">
                      {entry.instruments.map((instrument) => (
                        <Link
                          key={instrument.symbol}
                          to={`/trading/order?venue=${encodeURIComponent(entry.venue)}&symbol=${encodeURIComponent(instrument.symbol)}`}
                          className="flex items-center gap-2 rounded-lg border border-border px-2.5 py-1.5 text-xs hover:bg-muted"
                        >
                          <span className="font-mono font-medium">{instrument.symbol}</span>
                          <span className="font-mono text-muted-foreground">{money(instrument.mark)}</span>
                        </Link>
                      ))}
                    </div>
                  </div>
                ))}
                {overview.missing_marks.length > 0 && (
                  <p className="text-xs text-destructive">
                    Missing marks: {overview.missing_marks.join(', ')}
                  </p>
                )}
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="flex items-center gap-2 text-base">
                  <Star className="size-4" aria-hidden /> Watchlist
                </CardTitle>
                <CardDescription>
                  <Link to="/markets/watchlist" className="text-primary hover:underline">
                    Open the watchlist screen →
                  </Link>
                </CardDescription>
              </CardHeader>
              <CardContent>
                <div className="flex flex-wrap gap-2">
                  {overview.watchlist.map((entry) => (
                    <span
                      key={entry.symbol}
                      className="flex items-center gap-2 rounded-lg border border-border px-2.5 py-1.5 text-xs"
                    >
                      <span className="font-mono font-medium">{entry.symbol}</span>
                      <span className="font-mono text-muted-foreground">{money(entry.mark)}</span>
                    </span>
                  ))}
                </div>
              </CardContent>
            </Card>
          </div>
        )}
      </Surface>
    </Page>
  )
}
