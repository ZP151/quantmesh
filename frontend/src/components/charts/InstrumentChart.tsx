import { useEffect, useMemo, useRef } from 'react'
import {
  CandlestickSeries,
  ColorType,
  CrosshairMode,
  HistogramSeries,
  LineSeries,
  createChart,
  type IChartApi,
  type ISeriesApi,
  type UTCTimestamp,
} from 'lightweight-charts'

import type { ComparisonSeries, ForecastPath, HistoricalSeries } from '@/lib/api'

export interface InstrumentChartProps {
  comparisons?: ComparisonSeries | null
  forecast?: ForecastPath | null
  mode: 'candles' | 'line'
  primary: HistoricalSeries
  volume?: boolean
}

type LineApi = ISeriesApi<'Line'>

interface ChartRefs {
  candles: ISeriesApi<'Candlestick'>
  chart: IChartApi
  close: LineApi
  forecast: Record<ForecastKey, LineApi>
  volume: ISeriesApi<'Histogram'>
}

const COMPARISON_COLORS = ['#5eead4', '#a78bfa', '#fbbf24'] as const
const FORECAST_KEYS = ['p025', 'p10', 'p25', 'p50', 'p75', 'p90', 'p975'] as const
type ForecastKey = (typeof FORECAST_KEYS)[number]

const FORECAST_STYLE: Record<ForecastKey, { color: string; lineWidth: 1 | 2 }> = {
  p025: { color: 'rgba(16, 185, 129, 0.24)', lineWidth: 1 },
  p10: { color: 'rgba(16, 185, 129, 0.36)', lineWidth: 1 },
  p25: { color: 'rgba(16, 185, 129, 0.52)', lineWidth: 1 },
  p50: { color: '#34d399', lineWidth: 2 },
  p75: { color: 'rgba(16, 185, 129, 0.52)', lineWidth: 1 },
  p90: { color: 'rgba(16, 185, 129, 0.36)', lineWidth: 1 },
  p975: { color: 'rgba(16, 185, 129, 0.24)', lineWidth: 1 },
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

export function InstrumentChart({
  comparisons = null,
  forecast = null,
  mode,
  primary,
  volume = false,
}: InstrumentChartProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const refs = useRef<ChartRefs | null>(null)
  const comparisonRefs = useRef(new Map<string, LineApi>())
  const contextRef = useRef<string | null>(null)

  const priceFormatter = useMemo(() => {
    const locale = typeof navigator === 'undefined' ? 'en-US' : navigator.language
    const formatter = new Intl.NumberFormat(locale, {
      maximumFractionDigits: 4,
      minimumFractionDigits: 2,
    })
    return (price: number) => formatter.format(price)
  }, [])

  useEffect(() => {
    const container = containerRef.current
    if (container === null) return
    const ownedComparisons = comparisonRefs.current

    const reduceMotion = prefersReducedMotion()
    const chart = createChart(container, {
      autoSize: true,
      crosshair: { mode: CrosshairMode.Normal },
      grid: {
        horzLines: { color: 'rgba(148, 163, 184, 0.08)' },
        vertLines: { color: 'rgba(148, 163, 184, 0.08)' },
      },
      kineticScroll: { mouse: !reduceMotion, touch: !reduceMotion },
      layout: {
        attributionLogo: true,
        background: { color: 'transparent', type: ColorType.Solid },
        textColor: '#94a3b8',
      },
      localization: { priceFormatter },
      rightPriceScale: { borderColor: 'rgba(148, 163, 184, 0.18)' },
      timeScale: {
        borderColor: 'rgba(148, 163, 184, 0.18)',
        secondsVisible: false,
        timeVisible: true,
      },
    })
    const candles = chart.addSeries(CandlestickSeries, {
      borderDownColor: '#fb7185',
      borderUpColor: '#34d399',
      downColor: '#fb7185',
      priceLineVisible: false,
      upColor: '#34d399',
      wickDownColor: '#fb7185',
      wickUpColor: '#34d399',
    })
    const close = chart.addSeries(LineSeries, {
      color: '#34d399',
      lineWidth: 2,
      priceLineVisible: false,
      title: 'Observed close',
      visible: false,
    })
    const volumeSeries = chart.addSeries(HistogramSeries, {
      priceFormat: { type: 'volume' },
      priceLineVisible: false,
      priceScaleId: '',
      title: 'Volume',
      visible: false,
    })
    volumeSeries.priceScale().applyOptions({
      scaleMargins: { bottom: 0, top: 0.82 },
    })
    const forecastSeries = Object.fromEntries(
      FORECAST_KEYS.map((key) => [
        key,
        chart.addSeries(LineSeries, {
          ...FORECAST_STYLE[key],
          lastValueVisible: key === 'p50',
          priceLineVisible: false,
          title: key === 'p50' ? 'Forecast median' : `Forecast ${key.slice(1)}`,
          visible: false,
        }),
      ]),
    ) as Record<ForecastKey, LineApi>

    refs.current = { candles, chart, close, forecast: forecastSeries, volume: volumeSeries }
    return () => {
      ownedComparisons.clear()
      contextRef.current = null
      refs.current = null
      chart.remove()
    }
  }, [priceFormatter])

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
        color: bar.close >= bar.open ? 'rgba(52, 211, 153, 0.28)' : 'rgba(251, 113, 133, 0.28)',
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
          color: COMPARISON_COLORS[index % COMPARISON_COLORS.length],
          lineWidth: 1,
          priceLineVisible: false,
          priceScaleId: 'comparison',
          title: key,
        })
        comparisonRefs.current.set(key, series)
      }
      series.setData((comparisons?.points ?? []).flatMap((point) => {
        const time = utcTimestamp(point.timestamp)
        const value = point.values[key]
        return time === null || value === undefined || !finite(value) ? [] : [{ time, value }]
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
  }, [comparisons, forecast, mode, primary, volume])

  const accessibleObserved = primary.bars.slice(-50)
  return (
    <figure className="relative min-h-80 w-full" aria-label={`${primary.instrument.symbol} market chart`}>
      <div
        ref={containerRef}
        className="h-[30rem] w-full"
        role="img"
        aria-label={`${primary.instrument.symbol} ${mode === 'candles' ? 'candlestick' : 'line'} chart`}
      />
      <a
        className="absolute bottom-1 left-2 text-[10px] text-muted-foreground/70 underline-offset-2 hover:underline"
        href="https://www.tradingview.com/"
        rel="noreferrer"
        target="_blank"
      >
        Charts by TradingView
      </a>
      <table className="sr-only" aria-label={`${primary.instrument.symbol} chart data`}>
        <caption>
          Latest observed prices and the selected probabilistic forecast path. Forecast values are not observations.
        </caption>
        <thead>
          <tr><th>Timestamp</th><th>Series</th><th>Value</th></tr>
        </thead>
        <tbody>
          {accessibleObserved.map((bar) => (
            <tr key={`observed-${bar.timestamp}`}>
              <td>{bar.timestamp}</td><td>Observed close</td><td>{bar.close}</td>
            </tr>
          ))}
          {(forecast?.points ?? []).map((point) => (
            <tr key={`forecast-${point.timestamp}`}>
              <td>{point.timestamp}</td><td>Forecast median</td><td>{point.p50}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </figure>
  )
}
