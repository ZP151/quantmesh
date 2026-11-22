import { useEffect } from 'react'
import { render, screen } from '@testing-library/react'
import { expect, it, vi } from 'vitest'
import type { HistoricalSeries } from '@/lib/api'
import type { ChartInteraction } from '@/lib/chart-time-link'
import { PreferencesProvider } from '@/lib/preferences'
import { LinkedMarketCharts } from './LinkedMarketCharts'

const harness = vi.hoisted(() => ({ calls: [] as { bars: readonly { timestamp: string }[]; interaction: ChartInteraction; setRange: ReturnType<typeof vi.fn> }[] }))
vi.mock('./InstrumentChart', () => ({ InstrumentChart: function MockChart({ primary, interaction, labels }: { primary: { bars: readonly { timestamp: string }[] }; interaction: ChartInteraction; labels: { chart: string } }) {
  useEffect(() => {
    const setRange = vi.fn()
    harness.calls.push({ bars: primary.bars, interaction, setRange })
    return interaction.mount({ setRange, setCrosshair: vi.fn() })
  }, [interaction, primary.bars])
  return <div role="img" aria-label={labels.chart} />
} }))
const daily = [{ timestamp: '2026-11-23T05:00:00Z', open: 10, high: 15, low: 8, close: 12, volume: 100, is_live_tail: false }]
const weekly = [{ ...daily[0], weekStart: '2026-11-23', sourceTimestamps: [daily[0].timestamp], sessionDates: ['2026-11-23'], issues: [] }]
const history = { instrument: { symbol: 'NVDA', venue: 'moomoo', currency: 'USD' }, as_of: '2026-11-28T12:00:00Z', range: '1y' } as HistoricalSeries

it('shows separate daily/weekly charts with the same absolute lookback and updates without rebuilding the link', () => {
  harness.calls.length = 0
  const series = { daily: daily as HistoricalSeries['bars'], weekly, missingDates: [] }
  const view = render(<PreferencesProvider><LinkedMarketCharts history={history} series={series} months={3} view="both" /></PreferencesProvider>)
  expect(screen.getByRole('heading', { name: 'Daily candles' })).toBeInTheDocument()
  expect(screen.getByRole('heading', { name: 'Weekly candles' })).toBeInTheDocument()
  expect(harness.calls).toHaveLength(2)
  expect(harness.calls[0].bars).toBe(daily)
  expect(harness.calls[1].bars).toBe(weekly)
  expect(harness.calls[0].setRange).toHaveBeenLastCalledWith({ from: Date.parse('2026-08-28T12:00:00Z') / 1000, to: Date.parse(history.as_of) / 1000 })
  view.rerender(<PreferencesProvider><LinkedMarketCharts history={history} series={series} months={1} view="daily" /></PreferencesProvider>)
  expect(screen.queryByRole('heading', { name: 'Weekly candles' })).not.toBeInTheDocument()
  expect(harness.calls).toHaveLength(2)
  expect(harness.calls[0].setRange).toHaveBeenLastCalledWith({ from: Date.parse('2026-10-28T12:00:00Z') / 1000, to: Date.parse(history.as_of) / 1000 })
})
