import { render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { ComparisonSeries, HistoricalSeries } from '@/lib/api'

const chartHarness = vi.hoisted(() => {
  const series: Array<{
    applyOptions: ReturnType<typeof vi.fn>
    setData: ReturnType<typeof vi.fn>
  }> = []
  const timeScale = {
    fitContent: vi.fn(),
    getVisibleRange: vi.fn(() => ({ from: 1, to: 2 })),
    setVisibleRange: vi.fn(),
  }
  const chart = {
    addSeries: vi.fn(() => {
      const next = {
        applyOptions: vi.fn(),
        priceScale: vi.fn(() => ({ applyOptions: vi.fn() })),
        setData: vi.fn(),
      }
      series.push(next)
      return next
    }),
    remove: vi.fn(),
    removeSeries: vi.fn(),
    subscribeCrosshairMove: vi.fn(),
    timeScale: vi.fn(() => timeScale),
    unsubscribeCrosshairMove: vi.fn(),
  }
  return {
    chart,
    createChart: vi.fn(() => chart),
    definitions: {
      candlestick: { kind: 'candlestick' },
      histogram: { kind: 'histogram' },
      line: { kind: 'line' },
    },
    series,
    timeScale,
  }
})

vi.mock('lightweight-charts', () => ({
  CandlestickSeries: chartHarness.definitions.candlestick,
  ColorType: { Solid: 'solid' },
  CrosshairMode: { Normal: 0 },
  HistogramSeries: chartHarness.definitions.histogram,
  LineStyle: { Dashed: 2, Dotted: 1, Solid: 0, SparseDotted: 4 },
  LineSeries: chartHarness.definitions.line,
  TickMarkType: { DayOfMonth: 2, Month: 1, Time: 3, TimeWithSeconds: 4, Year: 0 },
  createChart: chartHarness.createChart,
}))

import { InstrumentChart } from './InstrumentChart'

const primary: HistoricalSeries = {
  adjustment: 'unadjusted',
  as_of: '2026-08-08T12:00:00Z',
  bars: [
    {
      adjusted_close: null,
      close: 181,
      high: 183,
      instrument: {
        currency: 'USD',
        instrument_type: 'equity',
        metadata: {},
        symbol: 'NVDA',
        venue: 'moomoo',
      },
      interval: '1d',
      is_live_tail: false,
      live_lineage: null,
      low: 178,
      open: 180,
      timestamp: '2026-08-06T20:00:00Z',
      volume: 1_000_000,
    },
    {
      adjusted_close: null,
      close: 184,
      high: 185,
      instrument: {
        currency: 'USD',
        instrument_type: 'equity',
        metadata: {},
        symbol: 'NVDA',
        venue: 'moomoo',
      },
      interval: '1d',
      is_live_tail: true,
      live_lineage: {
        age_ms: 0,
        continuity_proven: true,
        data_time: '2026-08-07T20:00:00Z',
        freshness_label: 'real',
        instrument: 'NVDA',
        interval: '1d',
        predecessor_data_time: '2026-08-06T20:00:00Z',
        predecessor_sequence: 1,
        provenance: 'real',
        received_at: '2026-08-08T12:00:00Z',
        sequence: 2,
        sequence_gap: false,
        source: 'demo-synthetic',
        venue: 'moomoo',
      },
      low: 180,
      open: 181,
      timestamp: '2026-08-07T20:00:00Z',
      volume: 1_200_000,
    },
  ],
  calendar: 'XNYS',
  coverage: {
    end: '2026-08-07T20:00:00Z',
    interval: '1d',
    rows: 2,
    start: '2026-08-06T20:00:00Z',
    symbol: 'NVDA',
    venue: 'moomoo',
  },
  coverage_scope: 'historical-only',
  dataset_id: 'demo-history',
  dataset_revision: 1,
  duplicates: [],
  gaps: [],
  generated_at: '2026-08-08T12:00:00Z',
  instrument: {
    currency: 'USD',
    instrument_type: 'equity',
    metadata: {},
    symbol: 'NVDA',
    venue: 'moomoo',
  },
  interval: '1d',
  license: 'demo-synthetic',
  limitations: ['Synthetic data'],
  range: '6m',
  resolution_fallback: null,
  source: 'demo-synthetic',
}

const comparisons: ComparisonSeries = {
  as_of: primary.as_of,
  keys: ['moomoo:AAPL'],
  limitations: [],
  points: primary.bars.map((bar, index) => ({
    timestamp: bar.timestamp,
    values: { 'moomoo:AAPL': 100 + index * 2 },
  })),
  range: '6m',
}

const forecast = {
  points: [
    {
      p025: 170,
      p10: 175,
      p25: 180,
      p50: 186,
      p75: 191,
      p90: 196,
      p975: 201,
      session: 1,
      timestamp: '2026-08-10T20:00:00Z',
    },
  ],
  sessions: 7 as const,
}

describe('InstrumentChart', () => {
  beforeEach(() => {
    chartHarness.series.length = 0
    vi.clearAllMocks()
  })

  afterEach(() => vi.unstubAllGlobals())

  it('owns one chart lifecycle and does not duplicate series on rerender', () => {
    const view = render(
      <InstrumentChart
        comparisons={comparisons}
        forecast={forecast}
        mode="candles"
        primary={primary}
        volume
      />,
    )

    expect(chartHarness.createChart).toHaveBeenCalledOnce()
    expect(chartHarness.createChart).toHaveBeenCalledWith(
      expect.any(HTMLElement),
      expect.objectContaining({ autoSize: true, crosshair: { mode: 0 } }),
    )
    const originalSeriesCount = chartHarness.chart.addSeries.mock.calls.length

    view.rerender(
      <InstrumentChart
        comparisons={comparisons}
        forecast={forecast}
        mode="line"
        primary={{ ...primary, bars: [...primary.bars] }}
        volume={false}
      />,
    )

    expect(chartHarness.createChart).toHaveBeenCalledOnce()
    expect(chartHarness.chart.addSeries).toHaveBeenCalledTimes(originalSeriesCount)
    view.unmount()
    expect(chartHarness.chart.remove).toHaveBeenCalledOnce()
  })

  it('renders observed, volume, comparison and forecast data with an accessible fallback', () => {
    render(
      <InstrumentChart
        comparisons={comparisons}
        forecast={forecast}
        mode="candles"
        primary={primary}
        volume
      />,
    )

    expect(chartHarness.chart.addSeries).toHaveBeenCalledWith(
      chartHarness.definitions.candlestick,
      expect.any(Object),
    )
    expect(chartHarness.chart.addSeries).toHaveBeenCalledWith(
      chartHarness.definitions.histogram,
      expect.any(Object),
    )
    expect(chartHarness.chart.addSeries).toHaveBeenCalledWith(
      chartHarness.definitions.line,
      expect.objectContaining({ title: 'moomoo:AAPL' }),
    )
    const table = screen.getByRole('table', { name: 'NVDA chart data' })
    expect(table.parentElement).toHaveClass('sr-only')
    expect(table).not.toHaveClass('sr-only')
    expect(Array.from(table.querySelectorAll('thead th'))).toHaveLength(3)
    for (const header of Array.from(table.querySelectorAll('thead th'))) {
      expect(header).toHaveAttribute('scope', 'col')
    }
    for (const series of [
      'Observed open',
      'Observed high',
      'Observed low',
      'Observed close',
      'Observed volume',
      'moomoo:AAPL',
      'Forecast 2.5%',
      'Forecast 10%',
      'Forecast 25%',
      'Forecast median',
      'Forecast 75%',
      'Forecast 90%',
      'Forecast 97.5%',
    ]) {
      expect(table).toHaveTextContent(series)
    }
    expect(screen.getByRole('link', { name: 'Charts by TradingView' })).toHaveAttribute(
      'href',
      'https://www.tradingview.com/',
    )
  })

  it('uses contrast-safe light colors, shape semantics and distinct forecast line styles', () => {
    render(
      <InstrumentChart
        appearance="light"
        forecast={forecast}
        mode="candles"
        primary={primary}
        volume
      />,
    )

    expect(chartHarness.createChart).toHaveBeenCalledWith(
      expect.any(HTMLElement),
      expect.objectContaining({
        layout: expect.objectContaining({ textColor: '#475569' }),
      }),
    )
    expect(chartHarness.chart.addSeries).toHaveBeenCalledWith(
      chartHarness.definitions.candlestick,
      expect.objectContaining({
        borderDownColor: '#be123c',
        downColor: 'rgba(0, 0, 0, 0)',
        upColor: '#047857',
      }),
    )
    const addSeriesCalls = chartHarness.chart.addSeries.mock.calls as unknown as Array<[
      unknown,
      { lineStyle?: number } | undefined,
    ]>
    const forecastCalls = addSeriesCalls.filter(
      ([definition]) => definition === chartHarness.definitions.line,
    )
    expect(forecastCalls.map(([, options]) => options?.lineStyle)).toEqual(
      expect.arrayContaining([0, 1, 2, 4]),
    )
  })

  it('exposes every observed bar in the accessible chart table', () => {
    const bars = Array.from({ length: 55 }, (_, index) => ({
      ...primary.bars[0],
      timestamp: new Date(Date.UTC(2026, 0, index + 1)).toISOString(),
    }))
    render(<InstrumentChart mode="candles" primary={{ ...primary, bars }} />)

    const rows = screen.getByRole('table', { name: 'NVDA chart data' }).querySelectorAll('tbody tr')
    expect(rows).toHaveLength(55 * 5)
  })

  it('localizes chart, fallback and attribution copy supplied by the workspace', () => {
    render(
      <InstrumentChart
        labels={{
          attribution: '图表技术由 TradingView 提供',
          caption: '观测值与概率预测值分开列示。',
          chart: '市场图表',
          dataTable: '图表数据',
          forecastP025: '预测 2.5%',
          observedOpen: '观测开盘价',
        }}
        mode="candles"
        primary={primary}
      />,
    )

    expect(screen.getByRole('img', { name: 'NVDA 市场图表' })).toBeInTheDocument()
    expect(screen.getByRole('table', { name: 'NVDA 图表数据' })).toHaveTextContent('观测开盘价')
    expect(screen.getByText('观测值与概率预测值分开列示。')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: '图表技术由 TradingView 提供' })).toBeInTheDocument()
  })

  it('formats chart prices with the selected app locale instead of the browser locale', () => {
    vi.stubGlobal('navigator', { language: 'de-DE' })
    render(<InstrumentChart locale="en" mode="candles" primary={primary} />)

    const createCalls = chartHarness.createChart.mock.calls as unknown as Array<[
      HTMLElement,
      { localization: { priceFormatter: (price: number) => string } },
    ]>
    const createOptions = createCalls[0][1]
    expect(createOptions.localization.priceFormatter(1234.5)).toBe('1,234.50')
  })

  it.each([
    {
      crosshair: 'Aug 8, 2026, 12:05 UTC',
      locale: 'en' as const,
      ticks: ['2026', 'Aug', 'Aug 8', '12:05', '12:05:09'],
    },
    {
      crosshair: '2026年8月8日 12:05 UTC',
      locale: 'zh-CN' as const,
      ticks: ['2026', '8月', '8月8日', '12:05', '12:05:09'],
    },
  ])('formats $locale chart time independently of the browser locale', ({ crosshair, locale, ticks }) => {
    vi.stubGlobal('navigator', { language: locale === 'en' ? 'zh-CN' : 'en-US' })
    render(<InstrumentChart locale={locale} mode="candles" primary={primary} />)

    const createCalls = chartHarness.createChart.mock.calls as unknown as Array<[
      HTMLElement,
      {
        localization: { locale: string; timeFormatter: (time: number) => string }
        timeScale: { tickMarkFormatter: (time: number, tickMarkType: number) => string }
      },
    ]>
    const createOptions = createCalls[0][1]
    const timestamp = Date.UTC(2026, 7, 8, 12, 5, 9) / 1_000

    expect(createOptions.localization.locale).toBe(locale === 'en' ? 'en-US' : 'zh-CN')
    expect(createOptions.localization.timeFormatter(timestamp)).toBe(crosshair)
    expect(ticks.map((_, tickMarkType) => (
      createOptions.timeScale.tickMarkFormatter(timestamp, tickMarkType)
    ))).toEqual(ticks)
  })

  it('fits only for instrument or range changes and preserves the visible range for live tails', () => {
    const view = render(
      <InstrumentChart mode="candles" primary={primary} volume={false} />,
    )
    expect(chartHarness.timeScale.fitContent).toHaveBeenCalledOnce()

    view.rerender(
      <InstrumentChart
        mode="candles"
        primary={{
          ...primary,
          bars: [
            ...primary.bars,
            {
              ...primary.bars[1],
              close: 185,
              timestamp: '2026-08-08T12:00:00Z',
            },
          ],
        }}
        volume={false}
      />,
    )

    expect(chartHarness.timeScale.fitContent).toHaveBeenCalledOnce()
    expect(chartHarness.timeScale.setVisibleRange).toHaveBeenCalledWith({ from: 1, to: 2 })
  })

  it('reassigns comparison colors by current order after peers are removed and added', () => {
    const first = {
      ...comparisons,
      keys: ['moomoo:AAPL', 'hyperliquid:BTC'],
      points: comparisons.points.map((point) => ({
        ...point,
        values: { 'moomoo:AAPL': 100, 'hyperliquid:BTC': 101 },
      })),
    }
    const view = render(
      <InstrumentChart comparisons={first} mode="line" primary={primary} volume={false} />,
    )
    const addSeriesCalls = chartHarness.chart.addSeries.mock.calls as unknown as Array<[
      unknown,
      { title?: string } | undefined,
    ]>
    const btcSeriesIndex = addSeriesCalls.findIndex(
      ([definition, options]) => definition === chartHarness.definitions.line && options?.title === 'hyperliquid:BTC',
    )
    const btcSeries = chartHarness.series[btcSeriesIndex]

    view.rerender(
      <InstrumentChart
        comparisons={{
          ...first,
          keys: ['hyperliquid:BTC', 'hyperliquid:ETH'],
          points: first.points.map((point) => ({
            ...point,
            values: { 'hyperliquid:BTC': 101, 'hyperliquid:ETH': 102 },
          })),
        }}
        mode="line"
        primary={primary}
        volume={false}
      />,
    )

    expect(btcSeries?.applyOptions).toHaveBeenLastCalledWith(expect.objectContaining({ color: '#5eead4' }))
  })
})
