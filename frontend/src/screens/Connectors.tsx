import { useMemo, useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Plug, RefreshCw } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Page } from '@/components/page'
import { Notice, Surface, useSurface } from '@/components/state'
import { api, ApiError, type ConnectorState, type FetchReport } from '@/lib/api'
import { dateTime, moneyPrecise, quantity, venueLabel } from '@/lib/format'
import type { MessageKey } from '@/lib/messages'
import { usePreferences } from '@/lib/preferences'
import { cn } from '@/lib/utils'

const STATE_VARIANT: Record<ConnectorState['state'], 'default' | 'outline' | 'destructive' | 'secondary'> = {
  ok: 'default',
  degraded: 'destructive',
  unavailable: 'destructive',
  unwired: 'outline',
  unprobed: 'secondary',
}

const KIND_KEY: Record<ConnectorState['kind'], MessageKey> = {
  fixture: 'screen.connectors.kind.fixture',
  'public-data': 'screen.connectors.kind.public',
  'execution-sim': 'screen.connectors.kind.execution',
  unwired: 'screen.connectors.kind.unwired',
}

/** Connectors: explicit diagnostics for every data surface. The panel
 * never guesses — each card shows the venue's own probe verdict, and
 * the Hyperliquid card can run the read-only public fetch (testnet
 * pinned, cached under .datalink, deterministic fallback to the seeded
 * book labeled synthetic). Missing software, credentials or network
 * access are instructive states here, never blank pages. */
export function ConnectorsScreen() {
  const queryClient = useQueryClient()
  const panel = useSurface(['connectors'], api.connectors)
  const overview = useSurface(['overview'], api.overview)

  const { t } = usePreferences()

  const probe = useMutation({
    mutationFn: api.probeConnectors,
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['connectors'] }),
  })

  const hyperliquidSymbols = useMemo(
    () =>
      overview.data?.venues
        .find((entry) => entry.venue === 'hyperliquid')
        ?.instruments.map((instrument) => instrument.symbol)
        .sort() ?? [],
    [overview.data],
  )

  return (
    <Page
      title={t('screen.connectors.title')}
      description={t('screen.connectors.description')}
      actions={
        <Button variant="outline" size="sm" onClick={() => probe.mutate()} disabled={probe.isPending}>
          <RefreshCw className={cn('size-3.5', probe.isPending && 'animate-spin')} aria-hidden />
          {t('screen.connectors.probeAll')}
        </Button>
      }
    >
      <Surface query={panel} title={t('screen.connectors.title')}>
        {(connectors) => (
          <div className="space-y-5">
            {probe.isError && (
              <Notice>
                {t('screen.connectors.probeRefused', {
                  detail: probe.error instanceof ApiError ? probe.error.message : String(probe.error),
                })}
              </Notice>
            )}
            <div className="grid gap-4 md:grid-cols-2">
              {connectors.map((connector) => (
                <ConnectorCard key={connector.venue} connector={connector} />
              ))}
            </div>
            <PublicFetchCard
              symbols={hyperliquidSymbols}
              onFetched={() => void queryClient.invalidateQueries({ queryKey: ['datalink-cache'] })}
            />
          </div>
        )}
      </Surface>
    </Page>
  )
}

function ConnectorCard({ connector }: { connector: ConnectorState }) {
  const { t } = usePreferences()
  const badge = (
    <Badge variant={STATE_VARIANT[connector.state] ?? 'outline'} className="font-mono text-[10px]">
      {connector.state}
    </Badge>
  )
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center gap-2 text-base">
          <Plug className="size-4" aria-hidden />
          {venueLabel(connector.venue)}
          {badge}
        </CardTitle>
        <CardDescription>
          {t(KIND_KEY[connector.kind])} · {connector.mode} ·{' '}
          {connector.read_only ? t('screen.connectors.readOnly') : t('screen.connectors.writable')}
          {connector.credentials_required
            ? ` · ${t('screen.connectors.credentialsRequired')}`
            : ` · ${t('screen.connectors.credentialFree')}`}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-2 text-sm">
        <p className="text-muted-foreground">{connector.detail}</p>
        <dl className="grid grid-cols-2 gap-x-4 gap-y-1 font-mono text-[11px] text-muted-foreground">
          <dt>{t('screen.connectors.dl.wired')}</dt>
          <dd className="text-right">
            {connector.wired ? t('screen.connectors.dl.yes') : t('screen.connectors.dl.no')}
          </dd>
          <dt>{t('screen.connectors.dl.lastProbe')}</dt>
          <dd className="text-right">
            {connector.last_checked_at ? dateTime(connector.last_checked_at) : t('screen.connectors.dl.never')}
          </dd>
          {connector.latency_ms !== null && (
            <>
              <dt>{t('screen.connectors.dl.latency')}</dt>
              <dd className="text-right">{connector.latency_ms.toFixed(0)} ms</dd>
            </>
          )}
        </dl>
      </CardContent>
    </Card>
  )
}

function PublicFetchCard({
  symbols,
  onFetched,
}: {
  symbols: string[]
  onFetched: () => void
}) {
  const { t } = usePreferences()
  const [selection, setSelection] = useState<string[]>([])
  const [report, setReport] = useState<FetchReport | null>(null)
  const [error, setError] = useState<string | null>(null)
  const fetch = useMutation({
    mutationFn: api.datalinkFetch,
    onSuccess: (data) => {
      setReport(data)
      setError(null)
      onFetched()
    },
    onError: (cause: unknown) =>
      setError(cause instanceof ApiError ? cause.message : String(cause)),
  })

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center gap-2 text-base">
          {t('screen.connectors.fetch.title')}
          <Badge variant="outline" className="font-mono text-[10px]">
            {t('screen.connectors.fetch.pinned')}
          </Badge>
        </CardTitle>
        <CardDescription>{t('screen.connectors.fetch.description', { cache: '.datalink' })}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex flex-wrap items-center gap-2">
          {symbols.map((symbol) => {
            const checked = selection.includes(symbol)
            return (
              <button
                key={symbol}
                type="button"
                aria-pressed={checked}
                onClick={() =>
                  setSelection((current) =>
                    checked ? current.filter((item) => item !== symbol) : [...current, symbol],
                  )
                }
                className={cn(
                  'h-7 rounded-lg border px-2.5 font-mono text-xs outline-none focus-visible:ring-2 focus-visible:ring-ring',
                  checked
                    ? 'border-primary bg-primary/10 text-primary'
                    : 'border-border text-muted-foreground hover:bg-muted',
                )}
              >
                {symbol}
              </button>
            )
          })}
          {symbols.length === 0 && (
            <p className="text-xs text-muted-foreground">{t('screen.connectors.fetch.noInstruments')}</p>
          )}
        </div>
        <Button
          size="sm"
          disabled={selection.length === 0 || fetch.isPending}
          onClick={() =>
            fetch.mutate(selection, {
              onSuccess: () => setSelection([]),
            })
          }
        >
          <RefreshCw className={cn('size-3.5', fetch.isPending && 'animate-spin')} aria-hidden />
          {fetch.isPending
            ? t('screen.connectors.fetch.fetching')
            : selection.length === 1
              ? t('screen.connectors.fetch.fetchOne')
              : t('screen.connectors.fetch.fetchMany', { count: String(selection.length) })}
        </Button>
        {error && (
          <p className="rounded-lg border border-destructive/40 bg-destructive/10 px-3 py-2 text-xs text-destructive">
            {error}
          </p>
        )}
        {report && (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[560px] text-sm">
              <thead>
                <tr className="border-b border-border text-left text-xs text-muted-foreground">
                  <th className="py-1.5 pr-3 font-medium">{t('table.symbol')}</th>
                  <th className="py-1.5 pr-3 font-medium">{t('screen.connectors.col.bestBid')}</th>
                  <th className="py-1.5 pr-3 font-medium">{t('screen.connectors.col.bestAsk')}</th>
                  <th className="py-1.5 pr-3 font-medium">{t('screen.connectors.col.levels')}</th>
                  <th className="py-1.5 pr-3 font-medium">{t('screen.connectors.col.source')}</th>
                  <th className="py-1.5 font-medium">{t('screen.connectors.col.provenance')}</th>
                </tr>
              </thead>
              <tbody>
                {report.rows.map((row) => (
                  <tr key={row.symbol} className="border-b border-border/60">
                    <td className="py-2 pr-3 font-mono">{row.symbol}</td>
                    <td className="py-2 pr-3 font-mono tabular-nums">{moneyPrecise(row.best_bid)}</td>
                    <td className="py-2 pr-3 font-mono tabular-nums">{moneyPrecise(row.best_ask)}</td>
                    <td className="py-2 pr-3 font-mono tabular-nums">{row.levels}</td>
                    <td className="py-2 pr-3">
                      <Badge
                        variant={row.synthetic ? 'outline' : 'default'}
                        className="font-mono text-[10px]"
                      >
                        {row.source}
                      </Badge>
                    </td>
                    <td className="py-2 font-mono text-[11px] text-muted-foreground">
                      {row.synthetic ? (
                        <span className="text-amber-500">
                          {row.degraded} — {row.reason}
                        </span>
                      ) : (
                        <>
                          {dateTime(row.fetched_at)} ·{' '}
                          {t('screen.connectors.levelsCount', { count: quantity(row.levels) })}
                          {row.cache && <> · <code>{row.cache}</code></>}
                        </>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </CardContent>
    </Card>
  )
}
