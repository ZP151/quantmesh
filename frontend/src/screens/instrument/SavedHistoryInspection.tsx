import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Button } from '@/components/ui/button'
import { api, type HistoricalVenue } from '@/lib/api'
import { usePreferences } from '@/lib/preferences'
import { MarketCanvas } from './MarketCanvas'

export function SavedHistoryInspection({ venue, symbol, onReturn }: {
  venue: HistoricalVenue; symbol: string; onReturn: () => void
}) {
  const { t } = usePreferences()
  const [draft, setDraft] = useState('')
  const [selected, setSelected] = useState<string | null>(null)
  const [inputError, setInputError] = useState(false)
  const [mode, setMode] = useState<'line' | 'candles'>('line')
  const [volume, setVolume] = useState(false)
  const [sma20, setSma20] = useState(false)
  const [sma50, setSma50] = useState(false)
  const query = useQuery({
    queryKey: ['history-inspection', venue, symbol, selected],
    queryFn: ({ signal }) => api.historyInspection(venue, symbol, selected!, signal),
    enabled: selected !== null,
    retry: false,
    gcTime: 0,
  })
  const value = selected !== null ? query.data : undefined
  function submit(event: React.FormEvent) {
    event.preventDefault()
    const at = draft.trim()
    const valid = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2}(?:\.\d{1,6})?)?(?:Z|[+-]\d{2}:\d{2})$/.test(at)
      && Number.isFinite(Date.parse(at)) && Date.parse(at) <= Date.now()
    setInputError(!valid)
    setSelected(valid ? at : null)
    if (valid && selected === at) void query.refetch()
  }
  return <section className="min-w-0 space-y-5" aria-label={t('inspection.title')}>
    <header className="flex flex-wrap items-start justify-between gap-3 border-b pb-4">
      <div className="space-y-1"><h1 className="text-xl font-semibold">{symbol} · {t('inspection.title')}</h1><p className="max-w-prose text-sm text-muted-foreground">{t('inspection.notice')}</p></div>
      <Button className="min-h-11" variant="outline" onClick={onReturn}>{t('inspection.return')}</Button>
    </header>
    <form className="flex flex-wrap items-end gap-3" onSubmit={submit}>
      <div className="min-w-0 grow space-y-2 sm:max-w-md">
        <label className="block text-sm font-medium" htmlFor="history-window-end">{t('inspection.end')}</label>
        <input id="history-window-end" type="text" autoComplete="off" spellCheck={false} maxLength={64}
          className="min-h-11 w-full min-w-0 rounded-md border bg-background px-3 font-mono text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
          placeholder="2026-10-23T23:44:01Z" aria-describedby="history-window-help" aria-invalid={inputError}
          value={draft} onChange={event => { setDraft(event.target.value); setSelected(null); setInputError(false) }} />
        <p id="history-window-help" className="text-xs text-muted-foreground">{t('inspection.help')}</p>
      </div>
      <Button className="min-h-11" type="submit" disabled={query.isFetching}>{t('inspection.show')}</Button>
    </form>
    {inputError && <p role="alert" className="text-sm text-destructive">{t('inspection.invalid')}</p>}
    {selected !== null && query.isFetching && <p role="status" className="text-sm">{t('inspection.loading')}</p>}
    {selected !== null && query.isError && <p role="alert" className="break-words text-sm text-destructive">{t('inspection.unavailable')} {query.error instanceof Error ? query.error.message : ''}</p>}
    {value !== undefined && !query.isFetching && !query.isError && <>
      <p className="text-sm font-medium" role="status">{t(value.stale ? 'inspection.stale' : 'inspection.recent')}</p>
      <dl className="grid min-w-0 gap-x-6 gap-y-4 text-xs sm:grid-cols-2 lg:grid-cols-3">
        {([
          ['inspection.viewed', value.observed_at], ['inspection.selected', value.window_end],
          ['inspection.sourceTime', value.source_time], ['inspection.receipt', value.source_received_at ?? t('inspection.unknownReceipt')],
          ['inspection.source', value.primary.source], ['inspection.coverage', `${value.primary.coverage.start} → ${value.primary.coverage.end}`],
        ] as const).map(([label, text]) => <div key={label}><dt className="text-muted-foreground">{t(label)}</dt><dd aria-label={t(label)} className="mt-1 break-words font-mono">{text}</dd></div>)}
      </dl>
      <p className="text-xs text-muted-foreground">{value.primary.coverage.rows} {t('inspection.rows')} · {value.primary.interval} · {value.primary.license}</p>
      <MarketCanvas chartFirst showStatistics={false} history={value.primary} comparison={null} forecast={null}
        mode={mode} onModeChange={setMode} range="1d" onRangeChange={() => {}}
        volume={volume} showSma20={sma20} showSma50={sma50}
        onVolumeChange={setVolume} onSma20Change={setSma20} onSma50Change={setSma50} />
      <div className="space-y-2 border-t pt-3 text-xs text-muted-foreground">
        <p>{t('inspection.continuity')}</p>
        {value.primary.limitations.map((text, index) => <p key={index} className="break-words">{text}</p>)}
      </div>
    </>}
  </section>
}
