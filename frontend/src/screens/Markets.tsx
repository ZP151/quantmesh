import { Link } from 'react-router-dom'
import { Activity } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Page } from '@/components/page'
import { Surface, useSurface } from '@/components/state'
import { api } from '@/lib/api'
import { money, venueLabel } from '@/lib/format'
import { cn } from '@/lib/utils'

/**
 * Market evidence (市场证据): the cross-venue board from the seeded
 * demo universe — 6 equities on moomoo, 4 perps on hyperliquid, every
 * mark a deterministic seed. Each instrument is one click from the
 * paper order form.
 */
export function MarketsScreen() {
  const query = useSurface(['markets'], api.markets)
  const venues = useSurface(['overview'], api.overview)

  return (
    <Page
      title="Markets"
      description="Cross-venue instrument board — the market evidence the paper-order loop starts from. Every row carries its demo provenance; nothing here is live market data."
      actions={
        <Button variant="outline" size="sm" render={<Link to="/trading/order" />}>
          <Activity className="size-3.5" aria-hidden /> Paper order
        </Button>
      }
    >
      <Surface
        query={query}
        title="Markets"
        empty={
          <Card>
            <CardHeader>
              <CardTitle className="text-base">No instruments mounted</CardTitle>
              <CardDescription>
                The demo universe is empty — the workstation has no venues to render.
              </CardDescription>
            </CardHeader>
          </Card>
        }
      >
        {(markets) => (
          <div className="space-y-5">
            {venues.data?.venues.map((entry) => (
              <Card key={entry.venue}>
                <CardHeader className="pb-2">
                  <CardTitle className="flex items-center gap-2 text-base">
                    {venueLabel(entry.venue)}
                    <Badge variant="outline" className="font-mono text-[10px]">
                      {entry.instruments.length} instruments
                    </Badge>
                  </CardTitle>
                  <CardDescription>
                    {entry.venue === 'hyperliquid'
                      ? 'Perpetual futures — synthetic marks from the seeded walk.'
                      : 'Equities — synthetic marks from the seeded walk.'}
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="border-b border-border text-left text-xs text-muted-foreground">
                          <th className="py-2 pr-4 font-medium">Symbol</th>
                          <th className="py-2 pr-4 text-right font-medium">Mark</th>
                          <th className="py-2 pr-4 font-medium">Venue</th>
                          <th className="py-2 text-right font-medium">Action</th>
                        </tr>
                      </thead>
                      <tbody>
                        {markets.instruments
                          .filter((instrument) => instrument.venue === entry.venue)
                          .map((instrument) => (
                            <tr key={`${instrument.venue}:${instrument.symbol}`} className="border-b border-border/60 last:border-0">
                              <td className="py-2 pr-4 font-mono font-medium">{instrument.symbol}</td>
                              <td className="py-2 pr-4 text-right font-mono tabular-nums">{money(instrument.mark)}</td>
                              <td className="py-2 pr-4 font-mono text-xs text-muted-foreground">{instrument.venue}</td>
                              <td className="py-2 text-right">
                                <Button
                                  size="sm"
                                  variant="outline"
                                  render={
                                    <Link
                                      to={`/trading/order?venue=${encodeURIComponent(instrument.venue)}&symbol=${encodeURIComponent(instrument.symbol)}`}
                                    />
                                  }
                                  className={cn('font-mono text-[11px]')}
                                >
                                  Trade
                                </Button>
                              </td>
                            </tr>
                          ))}
                      </tbody>
                    </table>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        )}
      </Surface>
    </Page>
  )
}
