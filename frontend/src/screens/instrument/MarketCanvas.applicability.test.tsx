import { render, screen } from '@testing-library/react'
import { expect, it, vi } from 'vitest'
import { PreferencesProvider } from '@/lib/preferences'
import type { HistoricalSeries } from '@/lib/api'
import { workspace } from './scenario-lab-fixture'
import { MarketCanvas } from './MarketCanvas'

vi.mock('@/components/charts/InstrumentChart', () => ({ InstrumentChart: ({ primary }: { primary: HistoricalSeries }) => <output data-testid="unchanged-observations">{primary.bars.map(bar => `${bar.timestamp}:${bar.close}`).join('|')}</output> }))
const history: HistoricalSeries = { ...workspace.history, bars: [
  { ...workspace.history.bars[0], timestamp: '2026-10-26T07:37:00Z', close: 79966 },
  { ...workspace.history.bars[0], timestamp: '2026-10-26T07:38:00Z', close: 80002 },
] }
function mount(showStatistics?: boolean) {
  return render(<PreferencesProvider><MarketCanvas comparison={null} forecast={null} history={history} mode="line" range="1d" volume={false} showSma20={false} showSma50={false} showStatistics={showStatistics} onModeChange={vi.fn()} onRangeChange={vi.fn()} onVolumeChange={vi.fn()} onSma20Change={vi.fn()} onSma50Change={vi.fn()} /></PreferencesProvider>)
}
it('summary applicability hides the full statistics and generic forecast summary without removing observed bars', () => {
  mount(false)
  expect(screen.queryByText('Realized volatility')).not.toBeInTheDocument()
  expect(screen.queryByText('Drawdown')).not.toBeInTheDocument()
  expect(screen.queryByText('Forecast distribution')).not.toBeInTheDocument()
  expect(screen.getByTestId('unchanged-observations')).toHaveTextContent('2026-10-26T07:37:00Z:79966|2026-10-26T07:38:00Z:80002')
})
it.each([undefined, true])('summary applicability keeps ordinary default/true summary and original values for %s', value => {
  mount(value)
  expect(screen.getByText('Realized volatility').nextElementSibling).toHaveTextContent('0%')
  expect(screen.getByText('Drawdown').nextElementSibling).toHaveTextContent('0%')
  expect(screen.getByText('Forecast distribution')).toBeInTheDocument()
  expect(screen.getByTestId('unchanged-observations')).toHaveTextContent('2026-10-26T07:38:00Z:80002')
})
