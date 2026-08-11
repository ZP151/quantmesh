import { useMemo } from 'react'

import { InstrumentChart, type ChartLine } from '@/components/charts/InstrumentChart'
import { Button } from '@/components/ui/button'
import type {
  ComparisonSeries,
  ForecastPath,
  HistoricalSeries,
  HistoryRange,
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
  comparison: ComparisonSeries | null
  forecast: ForecastPath | null
  history: HistoricalSeries
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
  const { t } = usePreferences()
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
  if (props.showSma20) {
    indicators.push({
      color: '#22d3ee',
      key: 'sma20',
      label: 'SMA 20',
      points: movingAverageLine(bars, 20),
    })
  }
  if (props.showSma50) {
    indicators.push({
      color: '#fbbf24',
      key: 'sma50',
      label: 'SMA 50',
      points: movingAverageLine(bars, 50),
    })
  }
  const hasVolume = bars.some((bar) => bar.volume > 0)
  const values = indicatorSnapshot(
    bars,
    props.history.interval,
    props.history.instrument.instrument_type,
  )

  return (
    <div className="space-y-3">
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
          <Button aria-pressed={props.volume} disabled={!hasVolume} onClick={() => props.onVolumeChange(!props.volume)} title={!hasVolume ? t('screen.workspace.volumeUnavailable') : undefined} type="button" variant={props.volume ? 'secondary' : 'ghost'}>
            {t('screen.workspace.volume')}
          </Button>
          <Button aria-pressed={props.showSma20} onClick={() => props.onSma20Change(!props.showSma20)} type="button" variant={props.showSma20 ? 'secondary' : 'ghost'}>SMA 20</Button>
          <Button aria-pressed={props.showSma50} onClick={() => props.onSma50Change(!props.showSma50)} type="button" variant={props.showSma50 ? 'secondary' : 'ghost'}>SMA 50</Button>
        </div>
      </div>
      <div className="flex items-center justify-between gap-3 px-1 text-[10px] text-muted-foreground">
        <span>{t('screen.workspace.observed')} · {props.history.interval}</span>
        <span>{t('screen.workspace.asOf', { time: dateTime(props.history.as_of) })}</span>
      </div>
      {props.comparison !== null && props.comparison.points.length > 0 && (
        <p className="px-1 font-mono text-[10px] text-muted-foreground">
          {t('screen.workspace.indexedComparison', {
            time: dateTime(props.comparison.points[0].timestamp),
          })}
        </p>
      )}
      <InstrumentChart
        comparisons={props.comparison}
        forecast={props.forecast}
        indicators={indicators}
        labels={chartLabels}
        mode={props.mode}
        primary={{ ...props.history, bars }}
        volume={props.volume && hasVolume}
      />
      <IndicatorStrip values={values} />
    </div>
  )
}
