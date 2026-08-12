import { Link } from 'react-router-dom'
import { LayoutGrid, Star, Wallet } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Separator } from '@/components/ui/separator'
import { Page } from '@/components/page'
import { Surface, useSurface } from '@/components/state'
import { api } from '@/lib/api'
import { money, venueLabel } from '@/lib/format'
import { usePreferences } from '@/lib/preferences'

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
  const health = useSurface(['health'], api.health)
  const liveMode = health.data?.runtime_mode === 'live'
  const { t } = usePreferences()

  return (
    <Page
      title={t('screen.overview.title')}
      description={
        liveMode ? t('screen.overview.description.live') : t('screen.overview.description.demo')
      }
    >
      <Surface query={query} title={t('screen.overview.title')}>
        {(overview) => {
          const valuationComplete = overview.valuation_complete
            ?? (overview.missing_marks.length === 0
              && typeof overview.account.equity === 'number'
              && Number.isFinite(overview.account.equity))
          const equityAvailable = valuationComplete
            && overview.missing_marks.length === 0
            && typeof overview.account.equity === 'number'
            && Number.isFinite(overview.account.equity)
          return (
            <div className="space-y-5">
            {liveMode && (
              <Card className="border-emerald-500/30 bg-emerald-500/5">
                <CardHeader>
                  <CardTitle className="text-base">{t('screen.overview.liveCard.title')}</CardTitle>
                  <CardDescription>{t('screen.overview.liveCard.description')}</CardDescription>
                </CardHeader>
                <CardContent>
                  <Link to="/cockpit" className="text-sm font-medium text-primary hover:underline">
                    {t('screen.overview.liveCard.cta')}
                  </Link>
                </CardContent>
              </Card>
            )}
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="flex items-center gap-2 text-base">
                  <Wallet className="size-4" aria-hidden /> {t('screen.overview.account.title')}
                </CardTitle>
                <CardDescription>{t('screen.overview.account.description')}</CardDescription>
              </CardHeader>
              <CardContent className="space-y-2 text-sm">
                <StatRow label={t('screen.overview.account.cash')}>{money(overview.account.cash)}</StatRow>
                <StatRow label={t('screen.overview.account.startingCash')}>{money(overview.account.starting_cash)}</StatRow>
                <StatRow label={t('screen.overview.account.equity')}>
                  {equityAvailable
                    ? money(overview.account.equity)
                    : t('screen.workspace.valueUnavailable')}
                </StatRow>
                {!equityAvailable && overview.valuation_reason && (
                  <p className="text-xs text-destructive" role="status">
                    {overview.valuation_reason}
                  </p>
                )}
                <Separator className="my-2" />
                <div className="flex items-center justify-between gap-4">
                  <span className="text-muted-foreground">{t('screen.overview.account.killSwitch')}</span>
                  <Badge variant={overview.account.kill_switch ? 'destructive' : 'outline'}>
                    {overview.account.kill_switch
                      ? t('screen.overview.account.engaged')
                      : t('screen.overview.account.disarmed')}
                  </Badge>
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="flex items-center gap-2 text-base">
                  <LayoutGrid className="size-4" aria-hidden /> {t('screen.overview.boards.title')}
                </CardTitle>
                <CardDescription>{t('screen.overview.boards.description')}</CardDescription>
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
                {overview.venues.length === 0 && (
                  <p className="text-sm text-muted-foreground">{t('screen.overview.boards.empty')}</p>
                )}
                {overview.missing_marks.length > 0 && (
                  <p className="text-xs text-destructive">
                    {t('screen.overview.boards.missing', { symbols: overview.missing_marks.join(', ') })}
                  </p>
                )}
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="flex items-center gap-2 text-base">
                  <Star className="size-4" aria-hidden /> {t('screen.overview.watchlist.title')}
                </CardTitle>
                <CardDescription>
                  <Link to="/markets/watchlist" className="text-primary hover:underline">
                    {t('screen.overview.watchlist.open')}
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
                  {overview.watchlist.length === 0 && (
                    <p className="text-sm text-muted-foreground">{t('screen.overview.watchlist.empty')}</p>
                  )}
                </div>
              </CardContent>
            </Card>
            </div>
          )
        }}
      </Surface>
    </Page>
  )
}
