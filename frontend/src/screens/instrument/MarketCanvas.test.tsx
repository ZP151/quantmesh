import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import type { HistoricalSeries } from '@/lib/api'
import { PreferencesProvider } from '@/lib/preferences'

vi.mock('@/components/charts/InstrumentChart', () => ({
  InstrumentChart: ({
    indicators,
    locale,
    mode,
    volume,
  }: {
    indicators: readonly { label: string }[]
    locale: string
    mode: string
    volume: boolean
  }) => (
    <div
      data-testid="instrument-chart"
      data-locale={locale}
      data-mode={mode}
      data-volume={String(volume)}
    >
      {indicators.map((indicator) => indicator.label).join(',')}
    </div>
  ),
}))

import { ComparisonPicker } from './ComparisonPicker'
import {
  MarketCanvas,
} from './MarketCanvas'
import {
  dedupeObservedBars,
  indicatorSnapshot,
  movingAverageLine,
} from './market-analysis'

const history: HistoricalSeries = {
  adjustment: 'unadjusted',
  as_of: '2026-08-08T12:00:00Z',
  bars: Array.from({ length: 60 }, (_, index) => {
    const timestamp = new Date(Date.UTC(2026, 4, 1 + index, 20)).toISOString()
    return {
      adjusted_close: null,
      close: 100 + index,
      high: 101 + index,
      instrument: {
        currency: 'USD',
        instrument_type: 'equity' as const,
        metadata: {},
        symbol: 'NVDA',
        venue: 'moomoo' as const,
      },
      interval: '1d',
      is_live_tail: false,
      live_lineage: null,
      low: 99 + index,
      open: 99.5 + index,
      timestamp,
      volume: 1_000 + index,
    }
  }),
  calendar: 'XNYS',
  coverage: {
    end: '2026-06-29T20:00:00Z',
    interval: '1d',
    rows: 60,
    start: '2026-05-01T20:00:00Z',
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
  limitations: [],
  range: '6m',
  resolution_fallback: null,
  source: 'demo-synthetic',
}

describe('MarketCanvas', () => {
  it('changes range and chart controls with real pressed states', async () => {
    const user = userEvent.setup()
    const onRangeChange = vi.fn()
    const onModeChange = vi.fn()
    const onVolumeChange = vi.fn()
    const onSma20Change = vi.fn()
    render(
      <PreferencesProvider>
        <MarketCanvas
          comparison={null}
          forecast={null}
          history={history}
          mode="candles"
          onModeChange={onModeChange}
          onRangeChange={onRangeChange}
          onSma20Change={onSma20Change}
          onSma50Change={vi.fn()}
          onVolumeChange={onVolumeChange}
          range="6m"
          showSma20={false}
          showSma50={false}
          volume={false}
        />
      </PreferencesProvider>,
    )

    await user.click(screen.getByRole('button', { name: '1M' }))
    await user.click(screen.getByRole('button', { name: 'Line' }))
    await user.click(screen.getByRole('button', { name: 'Volume' }))
    await user.click(screen.getByRole('button', { name: 'SMA 20' }))

    expect(onRangeChange).toHaveBeenCalledWith('1m')
    expect(onModeChange).toHaveBeenCalledWith('line')
    expect(onVolumeChange).toHaveBeenCalledWith(true)
    expect(onSma20Change).toHaveBeenCalledWith(true)
    expect(screen.getByRole('button', { name: '6M' })).toHaveAttribute('aria-pressed', 'true')
  })

  it('renders observed-only indicators and labels forecast separately', () => {
    render(
      <PreferencesProvider>
        <MarketCanvas
          comparison={null}
          forecast={null}
          history={history}
          mode="line"
          onModeChange={vi.fn()}
          onRangeChange={vi.fn()}
          onSma20Change={vi.fn()}
          onSma50Change={vi.fn()}
          onVolumeChange={vi.fn()}
          range="6m"
          showSma20
          showSma50
          volume
        />
      </PreferencesProvider>,
    )

    expect(screen.getByTestId('instrument-chart')).toHaveTextContent('SMA 20,SMA 50')
    expect(screen.getByText('Observed')).toBeInTheDocument()
    expect(screen.getByText('Forecast distribution')).toBeInTheDocument()
    expect(screen.getByText('Realized volatility')).toBeInTheDocument()
    expect(screen.getByText('Drawdown')).toBeInTheDocument()
  })

  it('deduplicates a live tail and derives finite bounded indicators', () => {
    const duplicate = {
      ...history.bars.at(-1)!,
      close: 999,
      is_live_tail: true,
    }
    const bars = dedupeObservedBars([...history.bars, duplicate])

    expect(bars).toHaveLength(history.bars.length)
    expect(bars.at(-1)?.close).toBe(999)
    expect(movingAverageLine(bars, 20)).toHaveLength(41)
    expect(indicatorSnapshot(bars, '1d', 'equity', 'XNYS')).toEqual({
      drawdown: expect.any(Number),
      realizedVolatility: expect.any(Number),
    })
  })

  it('uses the trusted 24/7 calendar when annualizing event-market volatility', () => {
    const hourly = history.bars.slice(0, 31).map((bar, index) => ({
      ...bar,
      close: 100 * 1.001 ** (index + (index % 3 === 0 ? 0.5 : 0)),
      instrument: { ...bar.instrument, instrument_type: 'event_contract' as const, venue: 'polymarket' as const },
      interval: '1h',
    }))
    const continuous = indicatorSnapshot(hourly, '1h', 'event_contract', '24/7')
    const exchangeHours = indicatorSnapshot(hourly, '1h', 'event_contract', 'XNYS')

    expect(continuous.realizedVolatility).not.toBeNull()
    expect(exchangeHours.realizedVolatility).not.toBeNull()
    expect(continuous.realizedVolatility!).toBeGreaterThan(exchangeHours.realizedVolatility! * 2)
  })

  it('treats zero volume as observed and explains unavailable moving averages accessibly', async () => {
    const zeroVolume = {
      ...history,
      bars: history.bars.slice(0, 31).map((bar) => ({ ...bar, volume: 0 })),
    }
    const user = userEvent.setup()
    const onVolumeChange = vi.fn()
    const onSma50Change = vi.fn()
    render(
      <PreferencesProvider>
        <MarketCanvas
          comparison={null}
          forecast={null}
          history={zeroVolume}
          mode="candles"
          onModeChange={vi.fn()}
          onRangeChange={vi.fn()}
          onSma20Change={vi.fn()}
          onSma50Change={onSma50Change}
          onVolumeChange={onVolumeChange}
          range="1m"
          showSma20={false}
          showSma50={false}
          volume={false}
        />
      </PreferencesProvider>,
    )

    await user.click(screen.getByRole('button', { name: 'Volume' }))
    expect(onVolumeChange).toHaveBeenCalledWith(true)
    const sma50 = screen.getByRole('button', { name: 'SMA 50' })
    expect(sma50).toHaveAttribute('aria-disabled', 'true')
    expect(sma50).toHaveAttribute('aria-describedby', 'sma50-unavailable')
    expect(screen.getByText('Requires at least 50 observed bars.')).toBeInTheDocument()
    await user.click(sma50)
    expect(onSma50Change).not.toHaveBeenCalled()
  })

  it('formats market timestamps with the selected Chinese locale', () => {
    window.localStorage.setItem(
      'quantmesh.preferences',
      JSON.stringify({ locale: 'zh-CN', theme: 'dark' }),
    )
    render(
      <PreferencesProvider>
        <MarketCanvas
          comparison={null}
          forecast={null}
          history={history}
          mode="candles"
          onModeChange={vi.fn()}
          onRangeChange={vi.fn()}
          onSma20Change={vi.fn()}
          onSma50Change={vi.fn()}
          onVolumeChange={vi.fn()}
          range="6m"
          showSma20={false}
          showSma50={false}
          volume={false}
        />
      </PreferencesProvider>,
    )

    expect(screen.getByText(/^截至 /)).toHaveTextContent('月')
    expect(screen.getByText(/^截至 /)).not.toHaveTextContent('Aug')
    expect(screen.getByTestId('instrument-chart')).toHaveAttribute('data-locale', 'zh-CN')
    window.localStorage.clear()
  })
})

describe('ComparisonPicker', () => {
  it('accepts at most three venue-aware peers', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    const view = render(
      <PreferencesProvider>
        <ComparisonPicker onChange={onChange} primary="moomoo:NVDA" selected={[]} />
      </PreferencesProvider>,
    )
    const input = screen.getByRole('textbox', { name: 'Comparison instrument' })
    await user.type(input, 'moomoo:AAPL')
    await user.click(screen.getByRole('button', { name: 'Add comparison' }))
    expect(onChange).toHaveBeenLastCalledWith(['moomoo:AAPL'])

    view.rerender(
      <PreferencesProvider>
        <ComparisonPicker
          onChange={onChange}
          primary="moomoo:NVDA"
          selected={['moomoo:AAPL', 'hyperliquid:BTC', 'hyperliquid:ETH']}
        />
      </PreferencesProvider>,
    )
    expect(screen.getByRole('button', { name: 'Add comparison' })).toBeDisabled()
    expect(screen.getByText('3 / 3')).toBeInTheDocument()
  })
})
