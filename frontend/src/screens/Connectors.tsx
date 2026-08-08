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
import { cn } from '@/lib/utils'

const STATE_VARIANT: Record<ConnectorState['state'], 'default' | 'outline' | 'destructive' | 'secondary'> = {
  ok: 'default',
  degraded: 'destructive',
  unavailable: 'destructive',
  unwired: 'outline',
  unprobed: 'secondary',
}

const KIND_LABEL: Record<ConnectorState['kind'], string> = {
  fixture: 'Deterministic demo fixture',
  'public-data': 'Credential-free public data',
  'execution-sim': 'Execution simulator',
  unwired: 'Fixture-only in this release',
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
      title="Connectors"
      description="Read-only diagnostics for every data surface. Only the demo fixture and the credential-free Hyperliquid testnet path are wired in this release; everything else is an explicit unwired or degraded state."
      actions={
        <Button variant="outline" size="sm" onClick={() => probe.mutate()} disabled={probe.isPending}>
          <RefreshCw className={cn('size-3.5', probe.isPending && 'animate-spin')} aria-hidden />
          Probe all
        </Button>
      }
    >
      <Surface query={panel} title="Connectors">
        {(connectors) => (
          <div className="space-y-5">
            {probe.isError && (
              <Notice>
                Probe refused: {probe.error instanceof ApiError ? probe.error.message : String(probe.error)}
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
          {KIND_LABEL[connector.kind]} · {connector.mode} · {connector.read_only ? 'read-only' : 'writable'}
          {connector.credentials_required ? ' · credentials required' : ' · credential-free'}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-2 text-sm">
        <p className="text-muted-foreground">{connector.detail}</p>
        <dl className="grid grid-cols-2 gap-x-4 gap-y-1 font-mono text-[11px] text-muted-foreground">
          <dt>wired</dt>
          <dd className="text-right">{connector.wired ? 'yes' : 'no'}</dd>
          <dt>last probe</dt>
          <dd className="text-right">
            {connector.last_checked_at ? dateTime(connector.last_checked_at) : 'never'}
          </dd>
          {connector.latency_ms !== null && (
            <>
              <dt>latency</dt>
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
          Hyperliquid public fetch
          <Badge variant="outline" className="font-mono text-[10px]">
            read-only · testnet pinned
          </Badge>
        </CardTitle>
        <CardDescription>
          One credential-free l2Book snapshot per symbol, cached under <code className="font-mono">.datalink</code>.
          A missing SDK, unreachable venue or rate-limit answer falls back to the seeded demo book — labeled
          synthetic, never a blank row.
        </CardDescription>
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
            <p className="text-xs text-muted-foreground">No Hyperliquid instruments in the demo universe.</p>
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
          {fetch.isPending ? 'Fetching…' : `Fetch ${selection.length} snapshot${selection.length === 1 ? '' : 's'}`}
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
                  <th className="py-1.5 pr-3 font-medium">Symbol</th>
                  <th className="py-1.5 pr-3 font-medium">Best bid</th>
                  <th className="py-1.5 pr-3 font-medium">Best ask</th>
                  <th className="py-1.5 pr-3 font-medium">Levels</th>
                  <th className="py-1.5 pr-3 font-medium">Source</th>
                  <th className="py-1.5 font-medium">Provenance</th>
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
                          {dateTime(row.fetched_at)} · {quantity(row.levels)} levels
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
