import { Link } from 'react-router-dom'
import { Send } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Page } from '@/components/page'
import { Surface, useSurface } from '@/components/state'
import { api, type OrderSummary } from '@/lib/api'
import { dateTime, money, moneyPrecise, pnlClass, quantity } from '@/lib/format'
import { usePreferences } from '@/lib/preferences'

function OrderAction() {
  const { t } = usePreferences()
  return (
    <Button variant="outline" size="sm" render={<Link to="/trading/order" />}>
      <Send className="size-3.5" aria-hidden /> {t('nav.paperOrder')}
    </Button>
  )
}

// --- Positions -----------------------------------------------------------

export function PositionsScreen() {
  const query = useSurface(['positions'], api.positions)
  const marks = useSurface(['pnl'], api.pnl)
  const { t } = usePreferences()

  return (
    <Page
      title={t('screen.positions.title')}
      description={t('screen.positions.description')}
      actions={<OrderAction />}
    >
      <Surface query={query} title={t('screen.positions.title')}>
        {(positions) => (
          <Card>
            <CardContent className="p-0">
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-border text-left text-xs text-muted-foreground">
                      <th className="px-4 py-2.5 font-medium">{t('screen.positions.col.instrument')}</th>
                      <th className="px-4 py-2.5 text-right font-medium">{t('screen.positions.col.quantity')}</th>
                      <th className="px-4 py-2.5 text-right font-medium">{t('screen.positions.col.avgCost')}</th>
                      <th className="px-4 py-2.5 text-right font-medium">{t('screen.positions.col.mark')}</th>
                      <th className="px-4 py-2.5 text-right font-medium">{t('screen.positions.col.unrealized')}</th>
                      <th className="px-4 py-2.5 text-right font-medium">{t('screen.positions.col.realized')}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {positions.map((position) => {
                      const mark = marks.data?.marks[position.key] ?? null
                      return (
                        <tr key={position.key} className="border-b border-border/60 last:border-0">
                          <td className="px-4 py-2.5">
                            <p className="font-mono font-medium">{position.instrument.symbol}</p>
                            <p className="font-mono text-[10px] text-muted-foreground">{position.key}</p>
                          </td>
                          <td className="px-4 py-2.5 text-right font-mono tabular-nums">{quantity(position.quantity)}</td>
                          <td className="px-4 py-2.5 text-right font-mono tabular-nums">{moneyPrecise(position.average_cost)}</td>
                          <td className="px-4 py-2.5 text-right font-mono tabular-nums">{mark === null ? '—' : money(mark)}</td>
                          <td className={`px-4 py-2.5 text-right font-mono tabular-nums ${pnlClass(position.unrealized_pnl)}`}>
                            {money(position.unrealized_pnl)}
                          </td>
                          <td className={`px-4 py-2.5 text-right font-mono tabular-nums ${pnlClass(position.realized_pnl)}`}>
                            {money(position.realized_pnl)}
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

// --- Orders --------------------------------------------------------------

const STATUS_VARIANT: Record<string, 'default' | 'outline' | 'destructive' | 'secondary'> = {
  filled: 'default',
  accepted: 'secondary',
  pending: 'outline',
  rejected: 'destructive',
  cancelled: 'outline',
}

function OrderRow({ order }: { order: OrderSummary }) {
  return (
    <tr className="border-b border-border/60 last:border-0">
      <td className="px-4 py-2.5">
        <p className="font-mono font-medium">{order.order_id}</p>
        <p className="font-mono text-[10px] text-muted-foreground">{dateTime(order.created_at)}</p>
      </td>
      <td className="px-4 py-2.5">
        <p className="font-mono font-medium">{order.instrument.symbol}</p>
        <p className="font-mono text-[10px] text-muted-foreground">{order.instrument.venue}</p>
      </td>
      <td className="px-4 py-2.5">
        <span className={order.side === 'buy' ? 'text-emerald-500' : 'text-destructive'}>
          {order.side.toUpperCase()}
        </span>{' '}
        <span className="font-mono tabular-nums">{quantity(order.quantity)}</span>
      </td>
      <td className="px-4 py-2.5 font-mono text-xs">{order.order_type}</td>
      <td className="px-4 py-2.5 text-right font-mono tabular-nums">{moneyPrecise(order.average_fill_price)}</td>
      <td className="px-4 py-2.5 text-right">
        <Badge variant={STATUS_VARIANT[order.status] ?? 'outline'} className="font-mono text-[10px]">
          {order.status}
        </Badge>
      </td>
    </tr>
  )
}

export function OrdersScreen() {
  const query = useSurface(['orders'], api.orders)
  const { t } = usePreferences()

  return (
    <Page
      title={t('screen.orders.title')}
      description={t('screen.orders.description')}
      actions={<OrderAction />}
    >
      <Surface query={query} title={t('screen.orders.title')}>
        {(orders) => (
          <Card>
            <CardContent className="p-0">
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-border text-left text-xs text-muted-foreground">
                      <th className="px-4 py-2.5 font-medium">{t('screen.orders.col.order')}</th>
                      <th className="px-4 py-2.5 font-medium">{t('screen.orders.col.instrument')}</th>
                      <th className="px-4 py-2.5 font-medium">{t('screen.orders.col.side')}</th>
                      <th className="px-4 py-2.5 font-medium">{t('screen.orders.col.type')}</th>
                      <th className="px-4 py-2.5 text-right font-medium">{t('screen.orders.col.avgFill')}</th>
                      <th className="px-4 py-2.5 text-right font-medium">{t('screen.orders.col.status')}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {orders.map((order) => (
                      <OrderRow key={order.order_id} order={order} />
                    ))}
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

// --- P&L ------------------------------------------------------------------

export function PnLScreen() {
  const query = useSurface(['pnl'], api.pnl)
  const { t } = usePreferences()

  return (
    <Page
      title={t('screen.pnl.title')}
      description={t('screen.pnl.description')}
      actions={<OrderAction />}
    >
      <Surface query={query} title={t('screen.pnl.title')}>
        {(pnl) => (
          <div className="space-y-5">
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
              <Card>
                <CardHeader className="pb-1">
                  <CardTitle className="text-xs font-medium text-muted-foreground">{t('screen.overview.account.equity')}</CardTitle>
                </CardHeader>
                <CardContent className="font-mono text-lg tabular-nums">{money(pnl.equity)}</CardContent>
              </Card>
              <Card>
                <CardHeader className="pb-1">
                  <CardTitle className="text-xs font-medium text-muted-foreground">{t('screen.pnl.total')}</CardTitle>
                </CardHeader>
                <CardContent className={`font-mono text-lg tabular-nums ${pnlClass(pnl.total_pnl)}`}>
                  {money(pnl.total_pnl)}
                </CardContent>
              </Card>
              <Card>
                <CardHeader className="pb-1">
                  <CardTitle className="text-xs font-medium text-muted-foreground">{t('screen.pnl.realized')}</CardTitle>
                </CardHeader>
                <CardContent className={`font-mono text-lg tabular-nums ${pnlClass(pnl.realized_pnl)}`}>
                  {money(pnl.realized_pnl)}
                </CardContent>
              </Card>
              <Card>
                <CardHeader className="pb-1">
                  <CardTitle className="text-xs font-medium text-muted-foreground">{t('screen.pnl.unrealized')}</CardTitle>
                </CardHeader>
                <CardContent className={`font-mono text-lg tabular-nums ${pnlClass(pnl.unrealized_pnl)}`}>
                  {money(pnl.unrealized_pnl)}
                </CardContent>
              </Card>
            </div>
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-base">{t('screen.pnl.marks.title')}</CardTitle>
                <CardDescription>
                  {t('screen.pnl.marks.instruments', { count: String(Object.keys(pnl.marks).length) })} ·{' '}
                  {pnl.missing_marks.length > 0
                    ? t('screen.pnl.marks.missingCount', { count: String(pnl.missing_marks.length) })
                    : t('screen.pnl.marks.noMissing')}
                </CardDescription>
              </CardHeader>
              <CardContent className="flex flex-wrap gap-2">
                {Object.entries(pnl.marks).map(([key, mark]) => (
                  <span key={key} className="flex items-center gap-2 rounded-lg border border-border px-2.5 py-1.5 text-xs">
                    <span className="font-mono">{key}</span>
                    <span className="font-mono text-muted-foreground">{money(mark)}</span>
                  </span>
                ))}
              </CardContent>
            </Card>
          </div>
        )}
      </Surface>
    </Page>
  )
}
