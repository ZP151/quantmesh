import { useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { CircleCheck, CircleX, Send } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Page } from '@/components/page'
import { Notice, useSurface } from '@/components/state'
import { api, ApiError, type DemoOrderInput } from '@/lib/api'
import { money, moneyPrecise, quantity as formatQuantity, venueLabel } from '@/lib/format'
import { usePreferences } from '@/lib/preferences'
import { cn } from '@/lib/utils'

/**
 * The tracer-bullet paper order (iteration 0014 Phase C): the browser's
 * simulated submit. The order goes through the real pipeline — quote
 * from the seeded book touch, the paper account's own risk gate, the
 * journal, the accounting engine — so the result is exactly what every
 * other surface (positions, P&L, audit, risk) will show afterwards.
 * Kill-switch refusals come back as the gate's own message.
 */
export function OrderScreen() {
  const [params] = useSearchParams()
  const queryClient = useQueryClient()

  const overview = useSurface(['overview'], api.overview)
  const killSwitch = useSurface(['kill-switch'], api.killSwitch)

  const { t } = usePreferences()

  const [venue, setVenue] = useState(params.get('venue') ?? '')
  const [symbol, setSymbol] = useState(params.get('symbol') ?? '')
  const [side, setSide] = useState<'BUY' | 'SELL'>('BUY')
  const [quantity, setQuantity] = useState('1')
  const [limitPrice, setLimitPrice] = useState('')
  const [idempotencyKey, setIdempotencyKey] = useState('')
  const [result, setResult] = useState<Awaited<ReturnType<typeof api.demoOrder>> | null>(null)
  const [rejection, setRejection] = useState<string | null>(null)

  // One key per submit attempt: a retry of the same attempt replays the
  // original order instead of duplicating it (the M10 contract).
  const [attemptKey, setAttemptKey] = useState<string | null>(null)
  const [lastSent, setLastSent] = useState<string | null>(null)

  const venues = useMemo(
    () => overview.data?.venues.map((entry) => entry.venue).sort() ?? [],
    [overview.data],
  )
  const symbols = useMemo(() => {
    const entry = overview.data?.venues.find((item) => item.venue === venue)
    return (entry?.instruments.map((instrument) => instrument.symbol) ?? []).sort()
  }, [overview.data, venue])

  const submit = useMutation({
    mutationFn: async (input: DemoOrderInput) => {
      const key = input.idempotency_key ?? `demo-browser-${crypto.randomUUID()}`
      if (key === lastSent && attemptKey !== null) {
        // Same attempt retried: reuse the key so the kernel replays it.
        input.idempotency_key = attemptKey
      } else {
        input.idempotency_key = key
        setAttemptKey(key)
      }
      setLastSent(key)
      return api.demoOrder(input)
    },
    onSuccess: (data) => {
      setResult(data)
      setRejection(null)
      void queryClient.invalidateQueries()
    },
    onError: (error: unknown) => {
      setRejection(
        error instanceof ApiError ? error.message : String(error),
      )
    },
  })

  const engaged = killSwitch.data?.kill_switch ?? false

  function resetForm() {
    setResult(null)
    setRejection(null)
    setAttemptKey(null)
    setLastSent(null)
  }

  const venueInvalid = venue !== '' && !venues.includes(venue)
  const symbolInvalid = symbol !== '' && !symbols.includes(symbol)

  return (
    <Page
      title={t('screen.order.title')}
      description={t('screen.order.description')}
    >
      <div className="grid gap-5 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <Send className="size-4" aria-hidden /> {t('screen.order.place')}
            </CardTitle>
            <CardDescription>{t('screen.order.anchor')}</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {engaged && <Notice>{t('screen.order.killEngaged')}</Notice>}

            <div className="grid gap-3 sm:grid-cols-2">
              <div className="space-y-1.5">
                <Label htmlFor="order-venue">{t('table.venue')}</Label>
                <select
                  id="order-venue"
                  className="h-8 w-full rounded-lg border border-input bg-background px-2 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring aria-invalid:border-destructive"
                  value={venue}
                  onChange={(event) => {
                    setVenue(event.target.value)
                    setSymbol('')
                  }}
                  aria-invalid={venueInvalid}
                >
                  <option value="">{t('screen.order.selectVenue')}</option>
                  {venues.map((name) => (
                    <option key={name} value={name}>
                      {venueLabel(name)}
                    </option>
                  ))}
                </select>
                {venueInvalid && <p className="text-xs text-destructive">{t('screen.order.notInUniverse')}</p>}
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="order-symbol">{t('table.symbol')}</Label>
                <select
                  id="order-symbol"
                  className="h-8 w-full rounded-lg border border-input bg-background px-2 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring aria-invalid:border-destructive"
                  value={symbol}
                  onChange={(event) => setSymbol(event.target.value)}
                  disabled={venue === ''}
                  aria-invalid={symbolInvalid}
                >
                  <option value="">{t('screen.order.selectSymbol')}</option>
                  {symbols.map((name) => (
                    <option key={name} value={name}>
                      {name}
                    </option>
                  ))}
                </select>
                {symbolInvalid && <p className="text-xs text-destructive">{t('screen.order.notInUniverse')}</p>}
              </div>
            </div>

            <div className="space-y-1.5">
              <Label>{t('screen.order.side')}</Label>
              <div className="grid grid-cols-2 gap-1 rounded-lg border border-border p-1" role="group" aria-label={t('screen.order.side')}>
                {(['BUY', 'SELL'] as const).map((value) => (
                  <button
                    key={value}
                    type="button"
                    className={cn(
                      'h-7 rounded-md text-sm font-medium outline-none focus-visible:ring-2 focus-visible:ring-ring',
                      side === value
                        ? value === 'BUY'
                          ? 'bg-emerald-500/15 text-emerald-500'
                          : 'bg-destructive/15 text-destructive'
                        : 'text-muted-foreground hover:bg-muted',
                    )}
                    onClick={() => setSide(value)}
                    aria-pressed={side === value}
                  >
                    {value}
                  </button>
                ))}
              </div>
            </div>

            <div className="grid gap-3 sm:grid-cols-2">
              <div className="space-y-1.5">
                <Label htmlFor="order-quantity">{t('screen.order.quantity')}</Label>
                <Input
                  id="order-quantity"
                  type="number"
                  min="0"
                  step="any"
                  value={quantity}
                  onChange={(event) => setQuantity(event.target.value)}
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="order-limit">{t('screen.order.limit')}</Label>
                <Input
                  id="order-limit"
                  type="number"
                  min="0"
                  step="any"
                  placeholder={t('screen.order.marketOrder')}
                  value={limitPrice}
                  onChange={(event) => setLimitPrice(event.target.value)}
                />
              </div>
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="order-key">{t('screen.order.idempotency')}</Label>
              <Input
                id="order-key"
                placeholder={t('screen.order.idemPlaceholder')}
                value={idempotencyKey}
                onChange={(event) => setIdempotencyKey(event.target.value)}
              />
            </div>

            {rejection && (
              <p className="flex items-start gap-2 rounded-lg border border-destructive/40 bg-destructive/10 px-3 py-2 text-xs text-destructive">
                <CircleX className="mt-0.5 size-3.5 shrink-0" aria-hidden />
                <span>
                  {t('screen.order.refused')} <code className="font-mono">{rejection}</code>
                </span>
              </p>
            )}

            <Button
              className="w-full gap-1.5"
              disabled={
                venue === '' ||
                symbol === '' ||
                quantity === '' ||
                Number(quantity) <= 0 ||
                venueInvalid ||
                symbolInvalid ||
                submit.isPending
              }
              onClick={() =>
                void submit.mutate({
                  venue,
                  symbol,
                  side,
                  quantity: Number(quantity),
                  limit_price: limitPrice === '' ? undefined : Number(limitPrice),
                  idempotency_key: idempotencyKey === '' ? undefined : idempotencyKey,
                })
              }
            >
              {submit.isPending ? t('screen.order.submitting') : t('screen.order.submit')}
            </Button>
            <p className="text-[11px] text-muted-foreground">{t('screen.order.gateNote')}</p>
          </CardContent>
        </Card>

        <div className="space-y-5">
          {!result && !rejection && (
            <Card>
              <CardHeader>
                <CardTitle className="text-base">{t('screen.order.path.title')}</CardTitle>
                <CardDescription>{t('screen.order.path.description')}</CardDescription>
              </CardHeader>
              <CardContent className="space-y-1 text-sm text-muted-foreground">
                <p><Link className="text-primary hover:underline" to="/markets">{t('screen.order.path.markets')}</Link> → venue + symbol</p>
                <p><Link className="text-primary hover:underline" to="/research/forecasts">{t('screen.order.path.forecasts')}</Link> → signal context</p>
                <p><b className="text-foreground">{t('screen.order.path.paper')}</b> → kernel risk gate → fill</p>
                <p><Link className="text-primary hover:underline" to="/trading/positions">{t('screen.order.path.positions')}</Link> → the fill lands</p>
                <p><Link className="text-primary hover:underline" to="/ops/audit">{t('screen.order.path.audit')}</Link> → the order is journaled</p>
                <p><Link className="text-primary hover:underline" to="/risk">{t('screen.order.path.risk')}</Link> → limits and alerts read the same state</p>
              </CardContent>
            </Card>
          )}

          {result && (
            <Card className="border-emerald-500/40">
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-base text-emerald-500">
                  <CircleCheck className="size-4" aria-hidden /> {result.order.order_id} ·{' '}
                  {result.order.status}
                </CardTitle>
                <CardDescription>
                  {result.order.instrument.venue}:{result.order.instrument.symbol} {result.order.side}{' '}
                  {formatQuantity(result.order.quantity)} · {t('screen.order.created', { timestamp: result.order.created_at })}
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-3 text-sm">
                <dl className="grid grid-cols-2 gap-x-4 gap-y-2">
                  <dt className="text-muted-foreground">{t('screen.order.result.type')}</dt>
                  <dd className="text-right font-mono">{result.order.order_type}</dd>
                  <dt className="text-muted-foreground">{t('screen.order.result.filled')}</dt>
                  <dd className="text-right font-mono">
                    {formatQuantity(result.order.filled_quantity)} @ {moneyPrecise(result.order.average_fill_price)}
                  </dd>
                  {result.order.limit_price !== null && (
                    <>
                      <dt className="text-muted-foreground">{t('screen.order.result.limit')}</dt>
                      <dd className="text-right font-mono">{moneyPrecise(result.order.limit_price)}</dd>
                    </>
                  )}
                  <dt className="text-muted-foreground">{t('screen.overview.account.cash')}</dt>
                  <dd className="text-right font-mono">{money(result.account.cash)}</dd>
                  <dt className="text-muted-foreground">{t('screen.overview.account.equity')}</dt>
                  <dd className="text-right font-mono">{money(result.account.equity)}</dd>
                </dl>
                <div className="flex flex-wrap gap-2">
                  <Button size="sm" variant="outline" render={<Link to="/trading/positions" />}>
                    {t('screen.positions.title')}
                  </Button>
                  <Button size="sm" variant="outline" render={<Link to="/trading/pnl" />}>
                    {t('screen.pnl.title')}
                  </Button>
                  <Button size="sm" variant="outline" render={<Link to="/ops/audit" />}>
                    {t('screen.order.result.auditTrail')}
                  </Button>
                  <Button size="sm" variant="ghost" onClick={resetForm}>
                    {t('screen.order.result.another')}
                  </Button>
                </div>
              </CardContent>
            </Card>
          )}
        </div>
      </div>
    </Page>
  )
}
