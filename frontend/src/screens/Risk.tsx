import { Link } from 'react-router-dom'
import { ShieldAlert } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Page } from '@/components/page'
import { Surface, useSurface } from '@/components/state'
import { api } from '@/lib/api'
import { dateTime, quantity } from '@/lib/format'

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

  return (
    <Page
      title="Risk"
      description="Paper limits and the alert ledger — everything the kernel gate reads, mirrored read-only."
      actions={
        <Button variant="outline" size="sm" render={<Link to="/ops/kill-switch" />}>
          <ShieldAlert className="size-3.5" aria-hidden /> Kill switch
        </Button>
      }
    >
      <Surface query={query} title="Risk">
        {(risk) => (
          <div className="space-y-5">
            <div className="grid gap-4 sm:grid-cols-2">
              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-base">Paper limits</CardTitle>
                  <CardDescription>Enforced by the accounting risk gate on every submit.</CardDescription>
                </CardHeader>
                <CardContent className="space-y-2 text-sm">
                  <div className="flex items-center justify-between gap-4">
                    <span className="text-muted-foreground">Kill switch</span>
                    <Badge variant={risk.paper_limits.kill_switch ? 'destructive' : 'outline'}>
                      {risk.paper_limits.kill_switch ? 'engaged' : 'disarmed'}
                    </Badge>
                  </div>
                  {(
                    [
                      ['Max order quantity', risk.paper_limits.max_order_quantity],
                      ['Max notional', risk.paper_limits.max_notional],
                      ['Max position quantity', risk.paper_limits.max_position_quantity],
                    ] as const
                  ).map(([label, value]) => (
                    <div key={label} className="flex items-center justify-between gap-4">
                      <span className="text-muted-foreground">{label}</span>
                      <span className="font-mono tabular-nums">{value === null ? 'unset' : quantity(value)}</span>
                    </div>
                  ))}
                </CardContent>
              </Card>
              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-base">Live posture</CardTitle>
                  <CardDescription>Read-only; live enablement is operator-owned.</CardDescription>
                </CardHeader>
                <CardContent>
                  {risk.hl_posture === null ? (
                    <p className="text-sm text-muted-foreground">
                      No Hyperliquid live risk posture is attached — live trading is not enabled for
                      this session.
                    </p>
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
                  <ShieldAlert className="size-4" aria-hidden /> Alerts
                  {!risk.alerts_bound && (
                    <Badge variant="outline" className="text-[10px]">
                      ledger not bound
                    </Badge>
                  )}
                </CardTitle>
                <CardDescription>The seeded alert ledger — drift, staleness, failure, reliability.</CardDescription>
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
