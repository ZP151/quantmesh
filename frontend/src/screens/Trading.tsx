import { Link } from 'react-router-dom'
import { Send } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Page } from '@/components/page'
import { Surface, useSurface } from '@/components/state'
import { api, type OrderSummary } from '@/lib/api'
import { instrumentPath } from '@/lib/instrument-route'
import { dateTime, money, moneyPrecise, pnlClass, quantity } from '@/lib/format'
import { usePreferences } from '@/lib/preferences'

function OrderAction() {
  const { t } = usePreferences()
  return (
    <Button nativeButton={false} variant="outline" size="sm" render={<Link to="/trading/order" />}>
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
                      const evidence = position.mark_status ?? marks.data?.mark_statuses?.[position.key]
                      const candidateMark = marks.data?.marks[position.key]
                      const validAvailableMark = evidence?.status === 'available'
                        && typeof candidateMark === 'number'
                        && Number.isFinite(candidateMark)
                      const status = validAvailableMark
                        ? 'available'
                        : evidence?.status === 'stale' ? 'stale' : 'unavailable'
                      const reason = evidence?.reason
                        ?? (evidence === undefined
                          ? t('screen.valuation.legacyReason')
                          : validAvailableMark ? null : t('screen.valuation.invalidMark'))
                      const mark = validAvailableMark ? candidateMark : null
                      const unrealized = status === 'available' ? position.unrealized_pnl : null
                      return (
                        <tr key={position.key} className="border-b border-border/60 last:border-0">
                          <td className="px-4 py-2.5">
                            <Link
                              className="font-mono font-medium underline-offset-4 hover:text-primary hover:underline focus-visible:rounded-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                              to={instrumentPath(position.instrument.venue, position.instrument.symbol)}
                            >
                              {position.instrument.symbol}
                            </Link>
                            <p className="font-mono text-[10px] text-muted-foreground">{position.key}</p>
                          </td>
                          <td className="px-4 py-2.5 text-right font-mono tabular-nums">{quantity(position.quantity)}</td>
                          <td className="px-4 py-2.5 text-right font-mono tabular-nums">{moneyPrecise(position.average_cost)}</td>
                          <td className="px-4 py-2.5 text-right">
                            <div className="flex flex-col items-end gap-1">
                              <span className="font-mono tabular-nums">{mark === null ? '—' : money(mark)}</span>
                              <Badge
                                variant={status === 'available' ? 'outline' : 'destructive'}
                                className="font-mono text-[10px]"
                              >
                                {t(`screen.pnl.marks.status.${status}`)}
                              </Badge>
                              {reason && (
                                <span className="max-w-64 text-right text-[10px] leading-snug text-muted-foreground">
                                  {reason}
                                </span>
                              )}
                            </div>
                          </td>
                          <td className={`px-4 py-2.5 text-right font-mono tabular-nums ${pnlClass(unrealized)}`}>
                            {money(unrealized)}
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
  const positions = useSurface(['positions'], api.positions)
  const { t } = usePreferences()

  return (
    <Page
      title={t('screen.pnl.title')}
      description={t('screen.pnl.description')}
      actions={<OrderAction />}
    >
      <Surface query={query} title={t('screen.pnl.title')}>
        {(pnl) => {
          const heldPositions = positions.data
          const positionsKnown = heldPositions !== undefined
          const statuses = pnl.mark_statuses ?? {}
          const heldMarksAvailable = positionsKnown && heldPositions.every((position) => (
            (position.mark_status ?? statuses[position.key])?.status === 'available'
            && typeof pnl.marks[position.key] === 'number'
            && Number.isFinite(pnl.marks[position.key])
            && !pnl.missing_marks.includes(position.key)
          ))
          const totalsAvailable = typeof pnl.equity === 'number'
            && Number.isFinite(pnl.equity)
            && typeof pnl.total_pnl === 'number'
            && Number.isFinite(pnl.total_pnl)
            && typeof pnl.unrealized_pnl === 'number'
            && Number.isFinite(pnl.unrealized_pnl)
          const valuationComplete = pnl.valuation_complete === false
            ? false
            : pnl.valuation_complete === true
              ? heldMarksAvailable && totalsAvailable
              : positionsKnown && heldPositions.length === 0
          const valuationReason = pnl.valuation_reason
            ?? (!positionsKnown
              ? t('screen.valuation.positionStateMissing')
              : heldPositions.length > 0
                ? pnl.valuation_complete === undefined
                  ? t('screen.valuation.legacyReason')
                  : t('screen.valuation.invalidMark')
                : null)

          return <div className="space-y-5">
            {!valuationComplete && (
              <div
                className="rounded-lg border border-amber-500/40 bg-amber-500/5 px-3 py-2 text-sm"
                role="status"
              >
                <p className="font-medium text-amber-700 dark:text-amber-300">
                  {t('screen.valuation.incomplete')}
                </p>
                {valuationReason && (
                  <p className="mt-1 text-xs text-muted-foreground">{valuationReason}</p>
                )}
              </div>
            )}
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
              <Card>
                <CardHeader className="pb-1">
                  <CardTitle className="text-xs font-medium text-muted-foreground">{t('screen.overview.account.equity')}</CardTitle>
                </CardHeader>
                <CardContent className="font-mono text-lg tabular-nums">
                  {valuationComplete && pnl.equity !== null
                    ? money(pnl.equity)
                    : t('screen.workspace.valueUnavailable')}
                </CardContent>
              </Card>
              <Card>
                <CardHeader className="pb-1">
                  <CardTitle className="text-xs font-medium text-muted-foreground">{t('screen.pnl.total')}</CardTitle>
                </CardHeader>
                <CardContent className={`font-mono text-lg tabular-nums ${pnlClass(valuationComplete ? pnl.total_pnl : null)}`}>
                  {valuationComplete && pnl.total_pnl !== null
                    ? money(pnl.total_pnl)
                    : t('screen.workspace.valueUnavailable')}
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
                <CardContent className={`font-mono text-lg tabular-nums ${pnlClass(valuationComplete ? pnl.unrealized_pnl : null)}`}>
                  {valuationComplete && pnl.unrealized_pnl !== null
                    ? money(pnl.unrealized_pnl)
                    : t('screen.workspace.valueUnavailable')}
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
                {Array.from(new Set([...Object.keys(pnl.marks), ...pnl.missing_marks])).map((key) => {
                  const mark = pnl.marks[key]
                  const evidence = statuses[key]
                  const displayMark = evidence?.status === 'available' ? mark : undefined
                  return (
                    <span
                      key={key}
                      className="flex items-center gap-2 rounded-lg border border-border px-2.5 py-1.5 text-xs"
                      title={evidence?.reason ?? undefined}
                    >
                      <span className="font-mono">{key}</span>
                      <span className="font-mono text-muted-foreground">
                        {displayMark === undefined ? '—' : money(displayMark)}
                      </span>
                      {evidence && (
                        <Badge
                          variant={evidence.status === 'available' ? 'outline' : 'destructive'}
                          className="font-mono text-[10px]"
                        >
                          {t(`screen.pnl.marks.status.${evidence.status}`)}
                        </Badge>
                      )}
                      {evidence?.reason && (
                        <span className="max-w-64 text-muted-foreground">{evidence.reason}</span>
                      )}
                    </span>
                  )
                })}
              </CardContent>
            </Card>
          </div>
        }}
      </Surface>
    </Page>
  )
}
