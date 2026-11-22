import { useEffect, useMemo } from 'react'
import type { HistoricalSeries } from '@/lib/api'
import type { DailyWeeklySeries } from '@/lib/chart-daily-series'
import { chartLookbackWindow } from '@/lib/chart-daily-series'
import { createChartTimeLink } from '@/lib/chart-time-link'
import { usePreferences } from '@/lib/preferences'
import { InstrumentChart } from './InstrumentChart'

export interface LinkedMarketChartsProps {
  history: HistoricalSeries
  series: DailyWeeklySeries
  months: 1 | 3 | 6 | 12
  view: 'daily' | 'weekly' | 'both'
}

export function LinkedMarketCharts({ history, series, months, view }: LinkedMarketChartsProps) {
  const { t, locale, resolvedTheme } = usePreferences()
  const link = useMemo(() => createChartTimeLink(series.weekly), [series.weekly])
  const dailyBinding = useMemo(() => link.binding('daily'), [link])
  const weeklyBinding = useMemo(() => link.binding('weekly'), [link])
  useEffect(() => link.setRange(chartLookbackWindow(history.as_of, months)), [history.as_of, link, months])
  const labels = useMemo(() => ({
    attribution: t('screen.workspace.chartAttribution'), caption: t('charts.caption'),
    dataTable: t('screen.workspace.chartData'), observed: t('screen.workspace.observed'),
    observedClose: t('screen.workspace.observedClose'), observedHigh: t('screen.workspace.observedHigh'),
    observedLow: t('screen.workspace.observedLow'), observedOpen: t('screen.workspace.observedOpen'),
    observedVolume: t('screen.workspace.observedVolume'), series: t('screen.workspace.series'),
    timestamp: t('screen.workspace.timestamp'), value: t('screen.workspace.value'),
  }), [t])
  return <div className={`grid min-w-0 gap-6 ${view === 'both' ? 'xl:grid-cols-2' : ''}`}>
    {(['daily', 'weekly'] as const).filter((period) => view === 'both' || view === period).map((period) => {
      const bars = period === 'daily' ? series.daily : series.weekly
      const title = t(period === 'daily' ? 'charts.daily' : 'charts.weekly')
      return <section className="min-w-0" aria-label={title} key={period}>
        <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
          <h3 className="text-base font-semibold">{title}</h3>
          <span className="text-xs text-muted-foreground">{t('charts.observations', { count: String(bars.length), currency: history.instrument.currency })}</span>
        </div>
        <InstrumentChart appearance={resolvedTheme} locale={locale} labels={{ ...labels, chart: title }} height={360}
          interaction={period === 'daily' ? dailyBinding : weeklyBinding} sessionTimeZone="America/New_York"
          primary={{ instrument: history.instrument, range: history.range, bars }} mode="candles" volume />
      </section>
    })}
  </div>
}
