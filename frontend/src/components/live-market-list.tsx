import { useCallback, useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { api, type LiveInstrumentState, type MarketUpdate } from '@/lib/api'
import { ageText, instrumentLabel, LABEL_TEXT, labelTone, liveInstrumentKey, mergeUpdate, midOf, normalizeLiveInstruments, quoteNumbers, reconcileInstrumentState, useAgedInstruments, useLiveConnection } from '@/lib/live'
import { dateTime, money, timeOfDay } from '@/lib/format'
import { instrumentPath } from '@/lib/instrument-route'
import { usePreferences } from '@/lib/preferences'
import { Badge } from '@/components/ui/badge'
import { ErrorState, LoadingState } from '@/components/state'

/** Configured live feeds are separate from registered decision watches. */
export function LiveMarketList() {
  const { locale, t } = usePreferences()
  const snapshot = useQuery({ queryKey: ['live', 'state'], queryFn: api.liveState, refetchInterval: 10_000, retry: false })
  const directory = useQuery({ queryKey: ['markets'], queryFn: api.markets, refetchInterval: 10_000, retry: false })
  const [instruments, setInstruments] = useState<Record<string, LiveInstrumentState>>({})
  useEffect(() => {
    if (!snapshot.data) return
    const incoming = normalizeLiveInstruments(snapshot.data.instruments)
    setInstruments(previous => Object.fromEntries(Object.entries(incoming).map(([key, row]) => [key, reconcileInstrumentState(previous[key], row)])))
  }, [snapshot.data])
  const onUpdate = useCallback((update: MarketUpdate) => setInstruments(previous => mergeUpdate(previous, update)), [])
  const connection = useLiveConnection(onUpdate)
  const aged = useAgedInstruments(instruments)
  const configured: Record<string, LiveInstrumentState> = Object.fromEntries(
    (directory.data?.instruments ?? []).map(row => {
      const key = liveInstrumentKey(row.venue, row.symbol)
      return [key, aged[key] ?? { venue: row.venue, instrument: row.symbol, label: 'unavailable', kinds: {} }]
    }),
  )
  const rows = Object.entries(directory.data ? configured : aged).sort(([a], [b]) => a.localeCompare(b))
  if ((snapshot.isPending || directory.isPending) && rows.length === 0) return <LoadingState rows={3} />
  const error = snapshot.error ?? directory.error
  if (error && rows.length === 0) return <ErrorState title={t('liveMarkets.unavailable')} detail={error.message} />
  return <section className="min-w-0 space-y-3" aria-label={t('liveMarkets.title')}>
    <div className="flex flex-wrap items-baseline justify-between gap-2">
      <h2 className="text-base font-semibold">{t('liveMarkets.title')}</h2>
      <p className="text-xs text-muted-foreground">{t(`screen.cockpit.banner.${connection}`)}</p>
    </div>
    <p className="text-sm text-muted-foreground">{t('liveMarkets.description')}</p>
    {error && <p role="status" className="text-sm text-destructive">{t('liveMarkets.refreshError')}</p>}
    {rows.length === 0 ? <p className="py-6 text-sm text-muted-foreground">{t('liveMarkets.empty')}</p> : <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead><tr className="border-b border-border text-left text-xs text-muted-foreground">
          {(['table.symbol', 'table.venue', 'liveMarkets.mid', 'liveMarkets.state', 'liveMarkets.event', 'liveMarkets.age'] as const).map(key => <th key={key} className="px-3 py-2 font-medium first:pl-0">{t(key)}</th>)}
        </tr></thead>
        <tbody>{rows.map(([key, row]) => {
          const quote = row.kinds.quote
          const label = instrumentLabel(row)
          return <tr key={key} className="border-b border-border/60">
            <td className="py-3 pr-3 font-mono font-medium"><Link className="underline-offset-4 hover:text-primary hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring" to={`${instrumentPath(row.venue, row.instrument)}?range=1d&mode=line`}>{row.instrument}</Link></td>
            <td className="px-3 py-3 text-xs">{row.venue}</td>
            <td className="px-3 py-3 font-mono tabular-nums">{money(midOf(quoteNumbers(quote)), locale)}</td>
            <td className="px-3 py-3"><Badge className={labelTone(label)}>{t(LABEL_TEXT[label])}</Badge></td>
            <td className="whitespace-nowrap px-3 py-3 font-mono text-xs">{quote ? <time dateTime={quote.data_time} title={dateTime(quote.data_time, locale)}>{timeOfDay(quote.data_time)}</time> : '—'}</td>
            <td className="whitespace-nowrap px-3 py-3 font-mono text-xs">{quote ? ageText(quote.age_ms, locale) : '—'}</td>
          </tr>
        })}</tbody>
      </table>
    </div>}
  </section>
}
