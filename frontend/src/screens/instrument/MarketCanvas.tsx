import { useMemo } from 'react'

import { InstrumentChart, type ChartLine } from '@/components/charts/InstrumentChart'
import { Button } from '@/components/ui/button'
import type {
  ComparisonSeries,
  ForecastPath,
  HistoricalSeries,
  HistoryRange,
  DecisionPacket,
} from '@/lib/api'
import { dateTime } from '@/lib/format'
import { usePreferences } from '@/lib/preferences'
import { IndicatorStrip } from './IndicatorStrip'
import { dedupeObservedBars, indicatorSnapshot, movingAverageLine } from './market-analysis'

const RANGES: readonly { label: string; value: HistoryRange }[] = [
  { label: '1D', value: '1d' },
  { label: '5D', value: '5d' },
  { label: '1M', value: '1m' },
  { label: '3M', value: '3m' },
  { label: '6M', value: '6m' },
  { label: '1Y', value: '1y' },
]

export interface MarketCanvasProps {
  archivedPacket?: boolean
  comparison: ComparisonSeries | null
  forecast: ForecastPath | null
  history: HistoricalSeries
  marketState?: DecisionPacket['market_state']
  mode: 'candles' | 'line'
  onModeChange: (mode: 'candles' | 'line') => void
  onRangeChange: (range: HistoryRange) => void
  onSma20Change: (enabled: boolean) => void
  onSma50Change: (enabled: boolean) => void
  onVolumeChange: (enabled: boolean) => void
  range: HistoryRange
  showSma20: boolean
  showSma50: boolean
  volume: boolean
}

export function MarketCanvas(props: MarketCanvasProps) {
  const { locale, resolvedTheme, t } = usePreferences()
  const chartLabels = useMemo(() => ({
    attribution: t('screen.workspace.chartAttribution'),
    caption: t('screen.workspace.chartCaption'),
    chart: t('screen.workspace.chartAria'),
    dataTable: t('screen.workspace.chartData'),
    forecast: t('screen.workspace.forecastMedian'),
    forecastP025: t('screen.workspace.forecastP025'),
    forecastP10: t('screen.workspace.forecastP10'),
    forecastP25: t('screen.workspace.forecastP25'),
    forecastP75: t('screen.workspace.forecastP75'),
    forecastP90: t('screen.workspace.forecastP90'),
    forecastP975: t('screen.workspace.forecastP975'),
    observed: t('screen.workspace.observed'),
    observedClose: t('screen.workspace.observedClose'),
    observedHigh: t('screen.workspace.observedHigh'),
    observedLow: t('screen.workspace.observedLow'),
    observedOpen: t('screen.workspace.observedOpen'),
    observedVolume: t('screen.workspace.observedVolume'),
    series: t('screen.workspace.series'),
    timestamp: t('screen.workspace.timestamp'),
    value: t('screen.workspace.value'),
  }), [t])
  const bars = dedupeObservedBars(props.history.bars)
  const indicators: ChartLine[] = []
  const hasSma20 = bars.length >= 20
  const hasSma50 = bars.length >= 50
  if (props.showSma20 && hasSma20) {
    indicators.push({
      color: '#22d3ee',
      key: 'sma20',
      label: 'SMA 20',
      points: movingAverageLine(bars, 20),
    })
  }
  if (props.showSma50 && hasSma50) {
    indicators.push({
      color: '#fbbf24',
      key: 'sma50',
      label: 'SMA 50',
      points: movingAverageLine(bars, 50),
    })
  }
  const hasVolume = bars.length > 0 && bars.every((bar) => Number.isFinite(bar.volume) && bar.volume >= 0)
  const values = indicatorSnapshot(
    bars,
    props.history.interval,
    props.history.instrument.instrument_type,
    props.history.calendar,
  )

  return (
    <div className="space-y-3">
      {props.archivedPacket && (
        <p className="border-l-2 border-amber-500 bg-amber-500/5 px-3 py-2 text-xs text-muted-foreground" role="note">
          {t('screen.workspace.currentMarketNotArchived')}
        </p>
      )}
      <div className="flex flex-wrap items-center justify-between gap-3 px-1">
        <div className="flex flex-wrap gap-1" aria-label={t('screen.workspace.ranges')}>
          {RANGES.map((item) => (
            <Button
              aria-pressed={props.range === item.value}
              className="h-7 px-2 font-mono text-[10px]"
              key={item.value}
              onClick={() => props.onRangeChange(item.value)}
              type="button"
              variant={props.range === item.value ? 'secondary' : 'ghost'}
            >
              {item.label}
            </Button>
          ))}
        </div>
        <div className="flex flex-wrap gap-1">
          <Button aria-pressed={props.mode === 'candles'} onClick={() => props.onModeChange('candles')} type="button" variant={props.mode === 'candles' ? 'secondary' : 'ghost'}>
            {t('screen.workspace.candles')}
          </Button>
          <Button aria-pressed={props.mode === 'line'} onClick={() => props.onModeChange('line')} type="button" variant={props.mode === 'line' ? 'secondary' : 'ghost'}>
            {t('screen.workspace.line')}
          </Button>
          <Button aria-describedby={!hasVolume ? 'volume-unavailable' : undefined} aria-disabled={!hasVolume} aria-pressed={props.volume && hasVolume} onClick={() => hasVolume && props.onVolumeChange(!props.volume)} type="button" variant={props.volume && hasVolume ? 'secondary' : 'ghost'}>
            {t('screen.workspace.volume')}
          </Button>
          <Button aria-describedby={!hasSma20 ? 'sma20-unavailable' : undefined} aria-disabled={!hasSma20} aria-pressed={props.showSma20 && hasSma20} onClick={() => hasSma20 && props.onSma20Change(!props.showSma20)} type="button" variant={props.showSma20 && hasSma20 ? 'secondary' : 'ghost'}>SMA 20</Button>
          <Button aria-describedby={!hasSma50 ? 'sma50-unavailable' : undefined} aria-disabled={!hasSma50} aria-pressed={props.showSma50 && hasSma50} onClick={() => hasSma50 && props.onSma50Change(!props.showSma50)} type="button" variant={props.showSma50 && hasSma50 ? 'secondary' : 'ghost'}>SMA 50</Button>
        </div>
      </div>
      <div className="space-y-0.5 px-1 text-[10px] text-muted-foreground" role="note">
        {!hasVolume && <p id="volume-unavailable">{t('screen.workspace.volumeUnavailable')}</p>}
        {!hasSma20 && <p id="sma20-unavailable">{t('screen.workspace.smaUnavailable', { count: '20' })}</p>}
        {!hasSma50 && <p id="sma50-unavailable">{t('screen.workspace.smaUnavailable', { count: '50' })}</p>}
      </div>
      <div className="flex items-center justify-between gap-3 px-1 text-[10px] text-muted-foreground">
        <span>{t('screen.workspace.observed')} · {props.history.interval}</span>
        <span>{t('screen.workspace.asOf', { time: dateTime(props.history.as_of, locale) })}</span>
      </div>
      {props.marketState && (
        <section className="border-y border-border px-1 py-3" aria-label={t('screen.workspace.marketStructure')}>
          <div className="mb-2 flex flex-wrap items-baseline justify-between gap-2">
            <h2 className="text-sm font-semibold">
              {t(`screen.workspace.trend.${props.marketState.trend}`)}
            </h2>
            <span className="font-mono text-[10px] text-muted-foreground">
              {t('screen.workspace.serverDerived')}
            </span>
          </div>
          <dl className="grid grid-cols-3 gap-x-4 gap-y-2 text-xs">
            <LevelFact label={t('screen.workspace.support')} value={props.marketState.support} />
            <LevelFact label={t('screen.workspace.resistance')} value={props.marketState.resistance} />
            <LevelFact label={t('screen.workspace.invalidation')} value={props.marketState.invalidation} />
          </dl>
          <div
            className="mt-3 min-w-0 border-t border-border pt-2 text-xs"
            title={props.marketState.key_level_bar_times.join(' · ')}
          >
            <p className="text-[10px] uppercase tracking-wider text-muted-foreground">
              {t('screen.workspace.keyLevelSourceBars')}
            </p>
            <p
              className="mt-1 break-all font-mono text-[10px] [overflow-wrap:anywhere]"
            >
              {props.marketState.key_level_bar_times.map((time) => dateTime(time, locale)).join(' · ')}
            </p>
          </div>
        </section>
      )}
      {props.comparison !== null && props.comparison.points.length > 0 && (
        <p className="px-1 font-mono text-[10px] text-muted-foreground">
          {t('screen.workspace.indexedComparison', {
            time: dateTime(props.comparison.points[0].timestamp, locale),
          })}
        </p>
      )}
      <InstrumentChart
        appearance={resolvedTheme}
        comparisons={props.comparison}
        forecast={props.forecast}
        indicators={indicators}
        labels={chartLabels}
        locale={locale}
        mode={props.mode}
        primary={{ ...props.history, bars }}
        volume={props.volume && hasVolume}
      />
      <IndicatorStrip values={values} />
    </div>
  )
}

function LevelFact({ label, value }: { label: string; value: number }) {
  return (
    <div className="min-w-0">
      <dt className="text-[10px] uppercase tracking-wider text-muted-foreground">{label}</dt>
      <dd className="font-mono tabular-nums">{value}</dd>
    </div>
  )
}
