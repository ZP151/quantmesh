import { Link } from 'react-router-dom'
import { ShieldAlert } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Page } from '@/components/page'
import { Surface, useSurface } from '@/components/state'
import { api } from '@/lib/api'
import { dateTime, quantity } from '@/lib/format'
import { usePreferences } from '@/lib/preferences'

const KIND_VARIANT: Record<string, 'default' | 'outline' | 'destructive' | 'secondary'> = {
  failure: 'destructive',
  staleness: 'secondary',
  feature_drift: 'outline',
  prediction_drift: 'outline',
  reliability: 'outline',
}

/** Risk: the paper limits, the (absent) live posture, and the alert
 * ledger. The kill-switch verdict the order form shows comes from the
 * same account object this screen mirrors. */
export function RiskScreen() {
  const query = useSurface(['risk'], api.risk)
  const { t } = usePreferences()

  return (
    <Page
      title={t('screen.risk.title')}
      description={t('screen.risk.description')}
      actions={
        <Button variant="outline" size="sm" render={<Link to="/ops/kill-switch" />}>
          <ShieldAlert className="size-3.5" aria-hidden /> {t('nav.killSwitch')}
        </Button>
      }
    >
      <Surface query={query} title={t('screen.risk.title')}>
        {(risk) => (
          <div className="space-y-5">
            <div className="grid gap-4 sm:grid-cols-2">
              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-base">{t('screen.risk.limits.title')}</CardTitle>
                  <CardDescription>{t('screen.risk.limits.description')}</CardDescription>
                </CardHeader>
                <CardContent className="space-y-2 text-sm">
                  <div className="flex items-center justify-between gap-4">
                    <span className="text-muted-foreground">{t('nav.killSwitch')}</span>
                    <Badge variant={risk.paper_limits.kill_switch ? 'destructive' : 'outline'}>
                      {risk.paper_limits.kill_switch
                        ? t('screen.overview.account.engaged')
                        : t('screen.overview.account.disarmed')}
                    </Badge>
                  </div>
                  {(
                    [
                      ['screen.risk.limit.orderQuantity', risk.paper_limits.max_order_quantity],
                      ['screen.risk.limit.notional', risk.paper_limits.max_notional],
                      ['screen.risk.limit.positionQuantity', risk.paper_limits.max_position_quantity],
                    ] as const
                  ).map(([key, value]) => (
                    <div key={key} className="flex items-center justify-between gap-4">
                      <span className="text-muted-foreground">{t(key)}</span>
                      <span className="font-mono tabular-nums">{value === null ? t('screen.risk.unset') : quantity(value)}</span>
                    </div>
                  ))}
                </CardContent>
              </Card>
              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-base">{t('screen.risk.posture.title')}</CardTitle>
                  <CardDescription>{t('screen.risk.posture.description')}</CardDescription>
                </CardHeader>
                <CardContent>
                  {risk.hl_posture === null ? (
                    <p className="text-sm text-muted-foreground">{t('screen.risk.posture.none')}</p>
                  ) : (
                    <pre className="overflow-x-auto rounded-lg bg-muted/40 p-3 text-xs">
                      {JSON.stringify(risk.hl_posture, null, 2)}
                    </pre>
                  )}
                </CardContent>
              </Card>
            </div>

            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="flex items-center gap-2 text-base">
                  <ShieldAlert className="size-4" aria-hidden /> {t('screen.risk.alerts.title')}
                  {!risk.alerts_bound && (
                    <Badge variant="outline" className="text-[10px]">
                      {t('screen.risk.alerts.notBound')}
                    </Badge>
                  )}
                </CardTitle>
                <CardDescription>{t('screen.risk.alerts.description')}</CardDescription>
              </CardHeader>
              <CardContent className="space-y-2">
                {risk.alerts.map((alert) => (
                  <div key={alert.id} className="flex items-start justify-between gap-3 rounded-lg border border-border/70 px-3 py-2">
                    <div className="min-w-0">
                      <p className="text-sm">{alert.message}</p>
                      <p className="mt-0.5 font-mono text-[10px] text-muted-foreground">
                        {alert.source} · {dateTime(alert.detected_at)}
                      </p>
                    </div>
                    <div className="flex shrink-0 items-center gap-2">
                      {Object.entries(alert.observed).map(([key, value]) => (
                        <span key={key} className="font-mono text-[10px] text-muted-foreground">
                          {key}={value}
                        </span>
                      ))}
                      <Badge variant={KIND_VARIANT[alert.kind] ?? 'outline'} className="font-mono text-[10px]">
                        {alert.kind}
                      </Badge>
                    </div>
                  </div>
                ))}
              </CardContent>
            </Card>
          </div>
        )}
      </Surface>
    </Page>
  )
}
