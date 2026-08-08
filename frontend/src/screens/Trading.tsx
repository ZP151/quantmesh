import { Link } from 'react-router-dom'
import { Send } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Page } from '@/components/page'
import { Surface, useSurface } from '@/components/state'
import { api, type OrderSummary } from '@/lib/api'
import { dateTime, money, moneyPrecise, pnlClass, quantity } from '@/lib/format'

const orderAction = (
  <Button variant="outline" size="sm" render={<Link to="/trading/order" />}>
    <Send className="size-3.5" aria-hidden /> Paper order
  </Button>
)

// --- Positions -----------------------------------------------------------

export function PositionsScreen() {
  const query = useSurface(['positions'], api.positions)
  const marks = useSurface(['pnl'], api.pnl)

  return (
    <Page
      title="Positions"
      description="Paper positions after the seeded replay — every fill that lands on the order screen appears here immediately, because both read the same account object."
      actions={orderAction}
    >
      <Surface query={query} title="Positions">
        {(positions) => (
          <Card>
            <CardContent className="p-0">
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-border text-left text-xs text-muted-foreground">
                      <th className="px-4 py-2.5 font-medium">Instrument</th>
                      <th className="px-4 py-2.5 text-right font-medium">Quantity</th>
                      <th className="px-4 py-2.5 text-right font-medium">Avg cost</th>
                      <th className="px-4 py-2.5 text-right font-medium">Mark</th>
                      <th className="px-4 py-2.5 text-right font-medium">Unrealized</th>
                      <th className="px-4 py-2.5 text-right font-medium">Realized</th>
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

  return (
    <Page
      title="Orders"
      description="The paper order journal — the account's own order book, including the resting seeded limit and every order the browser submits."
      actions={orderAction}
    >
      <Surface query={query} title="Orders">
        {(orders) => (
          <Card>
            <CardContent className="p-0">
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-border text-left text-xs text-muted-foreground">
                      <th className="px-4 py-2.5 font-medium">Order</th>
                      <th className="px-4 py-2.5 font-medium">Instrument</th>
                      <th className="px-4 py-2.5 font-medium">Side</th>
                      <th className="px-4 py-2.5 font-medium">Type</th>
                      <th className="px-4 py-2.5 text-right font-medium">Avg fill</th>
                      <th className="px-4 py-2.5 text-right font-medium">Status</th>
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

  return (
    <Page
      title="P&L"
      description="Performance over the paper account — realized from the seeded fills, unrealized against the seeded marks."
      actions={orderAction}
    >
      <Surface query={query} title="P&L">
        {(pnl) => (
          <div className="space-y-5">
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
              <Card>
                <CardHeader className="pb-1">
                  <CardTitle className="text-xs font-medium text-muted-foreground">Equity</CardTitle>
                </CardHeader>
                <CardContent className="font-mono text-lg tabular-nums">{money(pnl.equity)}</CardContent>
              </Card>
              <Card>
                <CardHeader className="pb-1">
                  <CardTitle className="text-xs font-medium text-muted-foreground">Total P&L</CardTitle>
                </CardHeader>
                <CardContent className={`font-mono text-lg tabular-nums ${pnlClass(pnl.total_pnl)}`}>
                  {money(pnl.total_pnl)}
                </CardContent>
              </Card>
              <Card>
                <CardHeader className="pb-1">
                  <CardTitle className="text-xs font-medium text-muted-foreground">Realized</CardTitle>
                </CardHeader>
                <CardContent className={`font-mono text-lg tabular-nums ${pnlClass(pnl.realized_pnl)}`}>
                  {money(pnl.realized_pnl)}
                </CardContent>
              </Card>
              <Card>
                <CardHeader className="pb-1">
                  <CardTitle className="text-xs font-medium text-muted-foreground">Unrealized</CardTitle>
                </CardHeader>
                <CardContent className={`font-mono text-lg tabular-nums ${pnlClass(pnl.unrealized_pnl)}`}>
                  {money(pnl.unrealized_pnl)}
                </CardContent>
              </Card>
            </div>
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-base">Marked to seeded marks</CardTitle>
                <CardDescription>
                  {Object.keys(pnl.marks).length} instruments ·{' '}
                  {pnl.missing_marks.length > 0 ? `${pnl.missing_marks.length} missing` : 'no missing marks'}
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
