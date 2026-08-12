import { Link } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Page } from '@/components/page'
import { Surface, useSurface } from '@/components/state'
import { api } from '@/lib/api'
import { instrumentPath } from '@/lib/instrument-route'
import { money } from '@/lib/format'
import { usePreferences } from '@/lib/preferences'

/** The watchlist: venue-scoped favorites with their marks. Every action
 * consumes the identity carried by its own API row; symbols are never
 * resolved by a first-match lookup across venues. */
export function WatchlistScreen() {
  const query = useSurface(['watchlist'], api.watchlist)
  const { t } = usePreferences()

  return (
    <Page
      title={t('screen.watchlist.title')}
      description={t('screen.watchlist.description')}
    >
      <Surface
        query={query}
        title={t('screen.watchlist.title')}
        empty={
          <Card>
            <CardHeader>
              <CardTitle className="text-base text-muted-foreground">{t('screen.watchlist.empty')}</CardTitle>
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
                      <th className="px-4 py-2.5 font-medium">{t('table.symbol')}</th>
                      <th className="px-4 py-2.5 font-medium">{t('table.venue')}</th>
                      <th className="px-4 py-2.5 text-right font-medium">{t('table.mark')}</th>
                      <th className="px-4 py-2.5 text-right font-medium">{t('table.action')}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {watchlist.entries.map((entry) => {
                      const venue = typeof entry.venue === 'string' && entry.venue.trim().length > 0
                        ? entry.venue
                        : null
                      return (
                        <tr key={`${entry.venue ?? 'unknown'}:${entry.symbol}`} className="border-b border-border/60 last:border-0">
                          <td className="px-4 py-2.5 font-mono font-medium">
                            {venue !== null ? (
                              <Link
                                className="underline-offset-4 hover:text-primary hover:underline focus-visible:rounded-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                                to={instrumentPath(venue, entry.symbol)}
                              >
                                {entry.symbol}
                              </Link>
                            ) : entry.symbol}
                          </td>
                          <td className="px-4 py-2.5 font-mono text-xs text-muted-foreground">
                            {venue ?? '—'}
                          </td>
                          <td className="px-4 py-2.5 text-right font-mono tabular-nums">{money(entry.mark)}</td>
                          <td className="px-4 py-2.5 text-right">
                            {venue !== null ? <Button
                              nativeButton={false}
                              size="sm"
                              variant="ghost"
                              className="font-mono text-[11px]"
                              render={
                                <Link
                                  to={`/trading/order?venue=${encodeURIComponent(venue)}&symbol=${encodeURIComponent(entry.symbol)}`}
                                />
                              }
                            >
                              {t('table.trade')}
                            </Button> : (
                              <span className="text-xs text-muted-foreground">
                                {t('screen.watchlist.notInUniverse')}
                              </span>
                            )}
                          </td>
                        </tr>
                      )})}
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
