import { Link } from 'react-router-dom'
import { Activity } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { LiveMarketList } from '@/components/live-market-list'
import { Page } from '@/components/page'
import { InstrumentEntry } from '@/components/instrument-entry'
import { Surface, useSurface } from '@/components/state'
import { api } from '@/lib/api'
import { chartEntryPath } from '@/lib/instrument-route'
import { money, venueLabel } from '@/lib/format'
import { usePreferences } from '@/lib/preferences'
import { cn } from '@/lib/utils'

/**
 * Market evidence (市场证据): the cross-venue board from the seeded
 * demo universe — 6 equities on moomoo, 4 perps on hyperliquid, every
 * mark a deterministic seed. Each instrument is one click from the
 * instrument chart, with a separate explicit paper order action.
 */
export function MarketsScreen() {
  const query = useSurface(['markets'], api.markets)
  const venues = useSurface(['overview'], api.overview)
  const { t } = usePreferences()
  const health = useSurface(['health'], api.health)
  if (health.data?.runtime_mode === 'live') return (
    <Page title={t('screen.markets.title')} description={t('liveMarkets.description')}>
      <LiveMarketList />
    </Page>
  )

  return (
    <Page
      title={t('screen.markets.title')}
      description={t('screen.markets.description')}
      actions={
        <Button nativeButton={false} variant="outline" size="sm" render={<Link to="/trading/order" />}>
          <Activity className="size-3.5" aria-hidden /> {t('screen.markets.paperOrder')}
        </Button>
      }
    >
      <InstrumentEntry />
      <Surface
        query={query}
        title={t('screen.markets.title')}
        empty={
          <Card>
            <CardHeader>
              <CardTitle className="text-base">{t('screen.markets.empty.title')}</CardTitle>
              <CardDescription>{t('screen.markets.empty.description')}</CardDescription>
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
                      {t('screen.markets.instruments', { count: String(entry.instruments.length) })}
                    </Badge>
                  </CardTitle>
                  <CardDescription>
                    {entry.venue === 'hyperliquid'
                      ? t('screen.markets.hyperliquid.description')
                      : t('screen.markets.equities.description')}
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="border-b border-border text-left text-xs text-muted-foreground">
                          <th className="py-2 pr-4 font-medium">{t('table.symbol')}</th>
                          <th className="py-2 pr-4 text-right font-medium">{t('table.mark')}</th>
                          <th className="py-2 pr-4 font-medium">{t('table.venue')}</th>
                          <th className="py-2 text-right font-medium">{t('table.action')}</th>
                        </tr>
                      </thead>
                      <tbody>
                        {markets.instruments
                          .filter((instrument) => instrument.venue === entry.venue)
                          .map((instrument) => (
                            <tr key={`${instrument.venue}:${instrument.symbol}`} className="border-b border-border/60 last:border-0">
                              <td className="py-2 pr-4 font-mono font-medium">
                                <Link
                                  className="underline-offset-4 hover:text-primary hover:underline focus-visible:rounded-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                                  to={chartEntryPath(instrument.venue, instrument.symbol)}
                                >
                                  {instrument.symbol}
                                </Link>
                              </td>
                              <td className="py-2 pr-4 text-right font-mono tabular-nums">{money(instrument.mark)}</td>
                              <td className="py-2 pr-4 font-mono text-xs text-muted-foreground">{instrument.venue}</td>
                              <td className="py-2 text-right">
                                <Button
                                  nativeButton={false}
                                  size="sm"
                                  variant="outline"
                                  render={
                                    <Link
                                      to={`/trading/order?venue=${encodeURIComponent(instrument.venue)}&symbol=${encodeURIComponent(instrument.symbol)}`}
                                    />
                                  }
                                  className={cn('font-mono text-[11px]')}
                                >
                                  {t('table.trade')}
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
