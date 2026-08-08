import { Link } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Page } from '@/components/page'
import { Surface, useSurface } from '@/components/state'
import { api } from '@/lib/api'
import { money } from '@/lib/format'

/** The watchlist: the seeded favorites with their marks. The venue for
 * a "Trade" link is resolved from the overview board — never guessed. */
export function WatchlistScreen() {
  const query = useSurface(['watchlist'], api.watchlist)
  const venues = useSurface(['overview'], api.overview)

  const venueOf = (symbol: string): string | undefined => {
    for (const entry of venues.data?.venues ?? []) {
      if (entry.instruments.some((instrument) => instrument.symbol === symbol)) return entry.venue
    }
    return undefined
  }

  return (
    <Page
      title="Watchlist"
      description="Seeded favorites — AAPL, BTC-USD, NVDA, SOL-USD — with their deterministic marks."
    >
      <Surface
        query={query}
        title="Watchlist"
        empty={
          <Card>
            <CardHeader>
              <CardTitle className="text-base text-muted-foreground">Watchlist empty</CardTitle>
            </CardHeader>
          </Card>
        }
      >
        {(watchlist) => (
          <Card>
            <CardContent className="p-0">
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-border text-left text-xs text-muted-foreground">
                      <th className="px-4 py-2.5 font-medium">Symbol</th>
                      <th className="px-4 py-2.5 text-right font-medium">Mark</th>
                      <th className="px-4 py-2.5 text-right font-medium">Action</th>
                    </tr>
                  </thead>
                  <tbody>
                    {watchlist.entries.map((entry) => {
                      const venue = venueOf(entry.symbol)
                      return (
                        <tr key={entry.symbol} className="border-b border-border/60 last:border-0">
                          <td className="px-4 py-2.5 font-mono font-medium">{entry.symbol}</td>
                          <td className="px-4 py-2.5 text-right font-mono tabular-nums">{money(entry.mark)}</td>
                          <td className="px-4 py-2.5 text-right">
                            {venue ? (
                              <Button
                                size="sm"
                                variant="ghost"
                                className="font-mono text-[11px]"
                                render={
                                  <Link
                                    to={`/trading/order?venue=${encodeURIComponent(venue)}&symbol=${encodeURIComponent(entry.symbol)}`}
                                  />
                                }
                              >
                                Trade
                              </Button>
                            ) : (
                              <span className="text-xs text-muted-foreground">not in universe</span>
                            )}
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            </CardContent>
          </Card>
        )}
      </Surface>
    </Page>
  )
}
