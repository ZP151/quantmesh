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
    timeScale: vi.fn(() => timeScale),
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
  LineSeries: chartHarness.definitions.line,
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
    expect(screen.getByRole('table', { name: 'NVDA chart data' })).toHaveTextContent(
      'Observed close',
    )
    expect(screen.getByRole('table', { name: 'NVDA chart data' })).toHaveTextContent(
      'Forecast median',
    )
    expect(screen.getByRole('link', { name: 'Charts by TradingView' })).toHaveAttribute(
      'href',
      'https://www.tradingview.com/',
    )
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
})
