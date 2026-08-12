import { useEffect, useMemo, useRef } from 'react'
import {
  CandlestickSeries,
  ColorType,
  CrosshairMode,
  HistogramSeries,
  LineStyle,
  LineSeries,
  TickMarkType,
  createChart,
  type IChartApi,
  type ISeriesApi,
  type MouseEventParams,
  type Time,
  type UTCTimestamp,
} from 'lightweight-charts'

import type { ComparisonSeries, ForecastPath, HistoricalSeries } from '@/lib/api'
import type { Locale } from '@/lib/preferences'

export interface InstrumentChartProps {
  appearance?: 'dark' | 'light'
  comparisons?: ComparisonSeries | null
  forecast?: ForecastPath | null
  indicators?: readonly ChartLine[]
  labels?: Partial<InstrumentChartLabels>
  locale?: Locale
  mode: 'candles' | 'line'
  primary: HistoricalSeries
  volume?: boolean
}

export interface ChartLine {
  color: string
  key: string
  label: string
  points: readonly { timestamp: string; value: number }[]
}

type LineApi = ISeriesApi<'Line'>

interface ChartRefs {
  candles: ISeriesApi<'Candlestick'>
  chart: IChartApi
  close: LineApi
  forecast: Record<ForecastKey, LineApi>
  volume: ISeriesApi<'Histogram'>
}

const FORECAST_KEYS = ['p025', 'p10', 'p25', 'p50', 'p75', 'p90', 'p975'] as const
type ForecastKey = (typeof FORECAST_KEYS)[number]

const PALETTES = {
  dark: {
    axis: '#cbd5e1',
    border: 'rgba(203, 213, 225, 0.28)',
    comparison: ['#5eead4', '#c4b5fd', '#fcd34d'],
    down: '#fb7185',
    grid: 'rgba(203, 213, 225, 0.12)',
    up: '#34d399',
    volume: '#94a3b8',
  },
  light: {
    axis: '#475569',
    border: 'rgba(71, 85, 105, 0.38)',
    comparison: ['#0f766e', '#6d28d9', '#92400e'],
    down: '#be123c',
    grid: 'rgba(71, 85, 105, 0.16)',
    up: '#047857',
    volume: '#475569',
  },
} as const

export interface InstrumentChartLabels {
  attribution: string
  caption: string
  chart: string
  dataTable: string
  forecast: string
  forecastP025: string
  forecastP10: string
  forecastP25: string
  forecastP75: string
  forecastP90: string
  forecastP975: string
  observed: string
  observedClose: string
  observedHigh: string
  observedLow: string
  observedOpen: string
  observedVolume: string
  series: string
  timestamp: string
  value: string
}

const DEFAULT_LABELS: InstrumentChartLabels = {
  attribution: 'Charts by TradingView',
  caption: 'Latest observed OHLCV, comparisons, indicators, and the selected probabilistic forecast path. Forecast values are not observations.',
  chart: 'market chart',
  dataTable: 'chart data',
  forecast: 'Forecast median',
  forecastP025: 'Forecast 2.5%',
  forecastP10: 'Forecast 10%',
  forecastP25: 'Forecast 25%',
  forecastP75: 'Forecast 75%',
  forecastP90: 'Forecast 90%',
  forecastP975: 'Forecast 97.5%',
  observed: 'Observed',
  observedClose: 'Observed close',
  observedHigh: 'Observed high',
  observedLow: 'Observed low',
  observedOpen: 'Observed open',
  observedVolume: 'Observed volume',
  series: 'Series',
  timestamp: 'Timestamp',
  value: 'Value',
}

function forecastLabel(labels: InstrumentChartLabels, key: ForecastKey): string {
  if (key === 'p025') return labels.forecastP025
  if (key === 'p10') return labels.forecastP10
  if (key === 'p25') return labels.forecastP25
  if (key === 'p50') return labels.forecast
  if (key === 'p75') return labels.forecastP75
  if (key === 'p90') return labels.forecastP90
  return labels.forecastP975
}

function forecastStyle(
  appearance: 'dark' | 'light',
  key: ForecastKey,
): { color: string; lineStyle: LineStyle; lineWidth: 1 | 2 } {
  const color = appearance === 'light' ? '#0f766e' : '#5eead4'
  if (key === 'p50') return { color: appearance === 'light' ? '#065f46' : '#34d399', lineStyle: LineStyle.Solid, lineWidth: 2 }
  if (key === 'p25' || key === 'p75') return { color, lineStyle: LineStyle.Dotted, lineWidth: 1 }
  if (key === 'p10' || key === 'p90') return { color, lineStyle: LineStyle.Dashed, lineWidth: 1 }
  return { color, lineStyle: LineStyle.SparseDotted, lineWidth: 1 }
}

function utcTimestamp(value: string): UTCTimestamp | null {
  const milliseconds = Date.parse(value)
  if (!Number.isFinite(milliseconds)) return null
  return Math.floor(milliseconds / 1_000) as UTCTimestamp
}

function finite(value: number): value is number {
  return Number.isFinite(value)
}

function prefersReducedMotion(): boolean {
  return typeof window.matchMedia === 'function'
    && window.matchMedia('(prefers-reduced-motion: reduce)').matches
}

function chartContext(primary: HistoricalSeries): string {
  return `${primary.instrument.venue}:${primary.instrument.symbol}:${primary.range}`
}

function utcDate(time: Time): Date | null {
  let milliseconds: number
  if (typeof time === 'number') {
    milliseconds = time * 1_000
  } else if (typeof time === 'string') {
    milliseconds = Date.parse(time.length === 10 ? `${time}T00:00:00Z` : time)
  } else {
    milliseconds = Date.UTC(time.year, time.month - 1, time.day)
  }
  return Number.isFinite(milliseconds) ? new Date(milliseconds) : null
}

function datePart(
  formatter: Intl.DateTimeFormat,
  date: Date,
  type: Intl.DateTimeFormatPartTypes,
): string {
  return formatter.formatToParts(date).find((part) => part.type === type)?.value ?? ''
}

function chartTimeFormatters(locale: Locale) {
  const appLocale = locale === 'zh-CN' ? 'zh-CN' : 'en-US'
  const dateFormatter = new Intl.DateTimeFormat(appLocale, {
    day: 'numeric',
    month: 'short',
    timeZone: 'UTC',
    year: 'numeric',
  })
  const timeFormatter = new Intl.DateTimeFormat(appLocale, {
    hour: '2-digit',
    hourCycle: 'h23',
    minute: '2-digit',
    second: '2-digit',
    timeZone: 'UTC',
  })

  const parts = (date: Date) => ({
    day: datePart(dateFormatter, date, 'day'),
    hour: datePart(timeFormatter, date, 'hour'),
    minute: datePart(timeFormatter, date, 'minute'),
    month: locale === 'zh-CN'
      ? `${datePart(dateFormatter, date, 'month')}月`
      : datePart(dateFormatter, date, 'month'),
    second: datePart(timeFormatter, date, 'second'),
    year: datePart(dateFormatter, date, 'year'),
  })

  return {
    locale: appLocale,
    tickMarkFormatter(time: Time, tickMarkType: TickMarkType): string {
      const date = utcDate(time)
      if (date === null) return '—'
      const value = parts(date)
      if (tickMarkType === TickMarkType.Year) return value.year
      if (tickMarkType === TickMarkType.Month) return value.month
      if (tickMarkType === TickMarkType.DayOfMonth) {
        return locale === 'zh-CN' ? `${value.month}${value.day}日` : `${value.month} ${value.day}`
      }
      if (tickMarkType === TickMarkType.TimeWithSeconds) {
        return `${value.hour}:${value.minute}:${value.second}`
      }
      return `${value.hour}:${value.minute}`
    },
    timeFormatter(time: Time): string {
      const date = utcDate(time)
      if (date === null) return '—'
      const value = parts(date)
      return locale === 'zh-CN'
        ? `${value.year}年${value.month}${value.day}日 ${value.hour}:${value.minute} UTC`
        : `${value.month} ${value.day}, ${value.year}, ${value.hour}:${value.minute} UTC`
    },
  }
}

export function InstrumentChart({
  appearance = 'dark',
  comparisons = null,
  forecast = null,
  indicators = [],
  labels,
  locale = 'en',
  mode,
  primary,
  volume = false,
}: InstrumentChartProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const tooltipRef = useRef<HTMLDivElement>(null)
  const refs = useRef<ChartRefs | null>(null)
  const comparisonRefs = useRef(new Map<string, LineApi>())
  const indicatorRefs = useRef(new Map<string, LineApi>())
  const contextRef = useRef<string | null>(null)
  const chartLabels = useMemo(() => ({ ...DEFAULT_LABELS, ...labels }), [labels])
  const palette = PALETTES[appearance]
  const timeFormatters = useMemo(() => chartTimeFormatters(locale), [locale])

  const priceFormatter = useMemo(() => {
    const formatter = new Intl.NumberFormat(locale === 'zh-CN' ? 'zh-CN' : 'en-US', {
      maximumFractionDigits: 4,
      minimumFractionDigits: 2,
    })
    return (price: number) => formatter.format(price)
  }, [locale])

  useEffect(() => {
    const container = containerRef.current
    if (container === null) return
    const ownedComparisons = comparisonRefs.current
    const ownedIndicators = indicatorRefs.current

    const reduceMotion = prefersReducedMotion()
    const chart = createChart(container, {
      autoSize: true,
      crosshair: { mode: CrosshairMode.Normal },
      grid: {
        horzLines: { color: palette.grid },
        vertLines: { color: palette.grid },
      },
      kineticScroll: { mouse: !reduceMotion, touch: !reduceMotion },
      layout: {
        attributionLogo: true,
        background: { color: 'transparent', type: ColorType.Solid },
        textColor: palette.axis,
      },
      localization: {
        locale: timeFormatters.locale,
        priceFormatter,
        timeFormatter: timeFormatters.timeFormatter,
      },
      rightPriceScale: { borderColor: palette.border },
      timeScale: {
        borderColor: palette.border,
        secondsVisible: false,
        tickMarkFormatter: timeFormatters.tickMarkFormatter,
        timeVisible: true,
      },
    })
    const candles = chart.addSeries(CandlestickSeries, {
      borderDownColor: palette.down,
      borderUpColor: palette.up,
      downColor: 'rgba(0, 0, 0, 0)',
      priceLineVisible: false,
      title: chartLabels.observed,
      upColor: palette.up,
      wickDownColor: palette.down,
      wickUpColor: palette.up,
    })
    const close = chart.addSeries(LineSeries, {
      color: palette.up,
      lineWidth: 2,
      priceLineVisible: false,
      title: chartLabels.observedClose,
      visible: false,
    })
    const volumeSeries = chart.addSeries(HistogramSeries, {
      priceFormat: { type: 'volume' },
      priceLineVisible: false,
      priceScaleId: '',
      title: chartLabels.observedVolume,
      visible: false,
    })
    volumeSeries.priceScale().applyOptions({
      scaleMargins: { bottom: 0, top: 0.82 },
    })
    const forecastSeries = Object.fromEntries(
      FORECAST_KEYS.map((key) => [
        key,
        chart.addSeries(LineSeries, {
          ...forecastStyle(appearance, key),
          lastValueVisible: key === 'p50',
          priceLineVisible: false,
          title: forecastLabel(chartLabels, key),
          visible: false,
        }),
      ]),
    ) as Record<ForecastKey, LineApi>

    const onCrosshairMove = (event: MouseEventParams<Time>) => {
      const tooltip = tooltipRef.current
      if (tooltip === null) return
      const observed = event.seriesData.get(candles) ?? event.seriesData.get(close)
      const projected = event.seriesData.get(forecastSeries.p50)
      const observedValue = observed !== undefined && 'close' in observed
        ? observed.close
        : observed !== undefined && 'value' in observed
          ? observed.value
          : null
      const forecastValue = projected !== undefined && 'value' in projected ? projected.value : null
      const parts = []
      if (typeof observedValue === 'number' && finite(observedValue)) {
        parts.push(`${chartLabels.observed} ${priceFormatter(observedValue)}`)
      }
      if (typeof forecastValue === 'number' && finite(forecastValue)) {
        parts.push(`${chartLabels.forecast} ${priceFormatter(forecastValue)}`)
      }
      tooltip.textContent = parts.join(' · ')
      tooltip.hidden = parts.length === 0
    }
    chart.subscribeCrosshairMove(onCrosshairMove)

    refs.current = { candles, chart, close, forecast: forecastSeries, volume: volumeSeries }
    return () => {
      ownedComparisons.clear()
      ownedIndicators.clear()
      contextRef.current = null
      refs.current = null
      chart.unsubscribeCrosshairMove(onCrosshairMove)
      chart.remove()
    }
  }, [appearance, chartLabels, palette, priceFormatter, timeFormatters])

  useEffect(() => {
    const current = refs.current
    if (current === null) return
    const { candles, chart, close, forecast: forecastSeries, volume: volumeSeries } = current
    const nextContext = chartContext(primary)
    const sameContext = contextRef.current === nextContext
    const visibleRange = sameContext ? chart.timeScale().getVisibleRange() : null

    const candleData = primary.bars.flatMap((bar) => {
      const time = utcTimestamp(bar.timestamp)
      if (
        time === null
        || !finite(bar.open)
        || !finite(bar.high)
        || !finite(bar.low)
        || !finite(bar.close)
      ) return []
      return [{ time, open: bar.open, high: bar.high, low: bar.low, close: bar.close }]
    })
    const closeData = primary.bars.flatMap((bar) => {
      const time = utcTimestamp(bar.timestamp)
      return time === null || !finite(bar.close) ? [] : [{ time, value: bar.close }]
    })
    const volumeData = primary.bars.flatMap((bar) => {
      const time = utcTimestamp(bar.timestamp)
      if (time === null || !finite(bar.volume)) return []
      return [{
        color: palette.volume,
        time,
        value: bar.volume,
      }]
    })
    candles.setData(candleData)
    close.setData(closeData)
    volumeSeries.setData(volumeData)
    candles.applyOptions({ visible: mode === 'candles' })
    close.applyOptions({ visible: mode === 'line' })
    volumeSeries.applyOptions({ visible: volume })

    const comparisonKeys = new Set(comparisons?.keys ?? [])
    for (const [key, series] of comparisonRefs.current) {
      if (comparisonKeys.has(key)) continue
      chart.removeSeries(series)
      comparisonRefs.current.delete(key)
    }
    for (const [index, key] of (comparisons?.keys ?? []).entries()) {
      let series = comparisonRefs.current.get(key)
      if (series === undefined) {
        series = chart.addSeries(LineSeries, {
          color: palette.comparison[index % palette.comparison.length],
          lineWidth: 1,
          priceLineVisible: false,
          priceScaleId: 'comparison',
          title: key,
        })
        comparisonRefs.current.set(key, series)
      }
      series.applyOptions({ color: palette.comparison[index % palette.comparison.length] })
      series.setData((comparisons?.points ?? []).flatMap((point) => {
        const time = utcTimestamp(point.timestamp)
        const value = point.values[key]
        return time === null || value === undefined || !finite(value) ? [] : [{ time, value }]
      }))
    }

    const indicatorKeys = new Set(indicators.map((indicator) => indicator.key))
    for (const [key, series] of indicatorRefs.current) {
      if (indicatorKeys.has(key)) continue
      chart.removeSeries(series)
      indicatorRefs.current.delete(key)
    }
    for (const indicator of indicators) {
      let series = indicatorRefs.current.get(indicator.key)
      if (series === undefined) {
        series = chart.addSeries(LineSeries, {
          color: indicator.color,
          lineWidth: 1,
          priceLineVisible: false,
          title: indicator.label,
        })
        indicatorRefs.current.set(indicator.key, series)
      }
      series.setData(indicator.points.flatMap((point) => {
        const time = utcTimestamp(point.timestamp)
        return time === null || !finite(point.value) ? [] : [{ time, value: point.value }]
      }))
    }

    for (const key of FORECAST_KEYS) {
      const data = (forecast?.points ?? []).flatMap((point) => {
        const time = utcTimestamp(point.timestamp)
        const value = point[key]
        return time === null || !finite(value) ? [] : [{ time, value }]
      })
      forecastSeries[key].setData(data)
      forecastSeries[key].applyOptions({ visible: data.length > 0 })
    }

    if (!sameContext) {
      contextRef.current = nextContext
      chart.timeScale().fitContent()
    } else if (visibleRange !== null && primary.bars.some((bar) => bar.is_live_tail)) {
      chart.timeScale().setVisibleRange(visibleRange)
    }
  }, [comparisons, forecast, indicators, mode, palette, primary, volume])

  const accessibleObserved = primary.bars
  return (
    <figure className="relative min-h-80 w-full" aria-label={`${primary.instrument.symbol} ${chartLabels.chart}`}>
      <div
        ref={containerRef}
        className="h-[30rem] w-full"
        role="img"
        aria-label={`${primary.instrument.symbol} ${chartLabels.chart}`}
      />
      <a
        className="absolute bottom-1 left-2 text-[10px] text-muted-foreground/70 underline-offset-2 hover:underline"
        href="https://www.tradingview.com/"
        rel="noreferrer"
        target="_blank"
      >
        {chartLabels.attribution}
      </a>
      <div
        ref={tooltipRef}
        className="pointer-events-none absolute left-3 top-3 border border-border bg-background/95 px-2 py-1 font-mono text-[10px] shadow-sm"
        hidden
        role="tooltip"
      />
      <div className="sr-only">
        <table
          aria-label={`${primary.instrument.symbol} ${chartLabels.dataTable}`}
          className="w-px max-w-px table-fixed whitespace-normal [&_*]:break-all"
        >
          <caption>{chartLabels.caption}</caption>
          <thead>
            <tr><th scope="col">{chartLabels.timestamp}</th><th scope="col">{chartLabels.series}</th><th scope="col">{chartLabels.value}</th></tr>
          </thead>
          <tbody>
          {accessibleObserved.flatMap((bar) => ([
            [chartLabels.observedOpen, bar.open],
            [chartLabels.observedHigh, bar.high],
            [chartLabels.observedLow, bar.low],
            [chartLabels.observedClose, bar.close],
            [chartLabels.observedVolume, bar.volume],
          ] as const).map(([series, value]) => (
            <tr key={`${series}-${bar.timestamp}`}>
              <td>{bar.timestamp}</td><td>{series}</td><td>{value}</td>
            </tr>
          )))}
          {(comparisons?.points ?? []).flatMap((point) => (comparisons?.keys ?? []).flatMap((key) => {
            const value = point.values[key]
            return value === undefined ? [] : [(
              <tr key={`comparison-${key}-${point.timestamp}`}>
                <td>{point.timestamp}</td><td>{key}</td><td>{value}</td>
              </tr>
            )]
          }))}
          {(forecast?.points ?? []).flatMap((point) => FORECAST_KEYS.map((key) => (
            <tr key={`forecast-${key}-${point.timestamp}`}>
              <td>{point.timestamp}</td><td>{forecastLabel(chartLabels, key)}</td><td>{point[key]}</td>
            </tr>
          )))}
          {indicators.flatMap((indicator) => indicator.points.map((point) => (
            <tr key={`${indicator.key}-${point.timestamp}`}>
              <td>{point.timestamp}</td><td>{indicator.label}</td><td>{point.value}</td>
            </tr>
          )))}
          </tbody>
        </table>
      </div>
    </figure>
  )
}
