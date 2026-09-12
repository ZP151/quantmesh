import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { DecisionOutcomeReviewState } from '@/lib/api'
import { PreferencesProvider } from '@/lib/preferences'

const chart = vi.hoisted(() => vi.fn())
vi.mock('@/components/charts/InstrumentChart', () => ({
  InstrumentChart: (props: unknown) => { chart(props); return <div>Comparison chart</div> },
}))
import { ForecastOutcomeComparison } from './ForecastOutcomeComparison'

type Comparison = DecisionOutcomeReviewState['forecast_comparison']
const timestamps = [14, 15, 16, 17, 18, 21, 22].map((day) => `2026-09-${day}T04:00:00Z`)
const actualCloses = [99, 98, 100, 102, 103, 106, 97]
const comparison = {
  benchmark_mae: 3, forecast_artifact_id: 'forecast-original', horizon_sessions: 7,
  interval_coverage: 4 / 7, interval_hits: 4, mean_absolute_error: 17 / 7,
  observed_sessions: 7, outcome_id: 'outcome-frozen', policy_version: 'exact-close-v1',
  reason: null, status: 'complete', terminal_error: -3,
  rows: timestamps.map((timestamp, index) => ({
    absolute_error: Math.abs(actualCloses[index] - 100), actual_close: actualCloses[index], p10: 98, p50: 100, p90: 102,
    session: index + 1, timestamp, within_interval: index < 4,
  })),
} as Comparison
const outcome = {
  outcome_id: comparison.outcome_id,
  root_packet: {
    as_of: '2026-09-11T20:00:00Z', selected_range: '6m',
    evidence: { forecast_synthetic: true, forecast_paths: [{ sessions: 7, points: comparison.rows }] },
    instrument: { symbol: 'NVDA', currency: 'USD', venue: 'moomoo' },
  },
  path: { source: 'demo-synthetic', dataset_id: 'outcome-data', dataset_revision: 2, cutoff_at: timestamps[2], path_digest: 'frozen-digest' },
} as unknown as DecisionOutcomeReviewState['outcome']

function show(value = comparison, saved = false) {
  return render(<PreferencesProvider><ForecastOutcomeComparison comparison={value} outcome={outcome} saved={saved} /></PreferencesProvider>)
}

beforeEach(() => { window.localStorage.clear(); vi.clearAllMocks() })

describe('ForecastOutcomeComparison', () => {
  it('shows descriptive complete scores and exact dated evidence', async () => {
    show()
    expect(screen.getByRole('heading', { name: 'Forecast vs actual' })).toBeVisible()
    expect(screen.getByText('7 of 7 sessions observed')).toBeVisible()
    expect(screen.getByText('2.43 USD')).toBeVisible()
    expect(screen.getByText('3.00 USD')).toBeVisible()
    expect(screen.getByText('-3.00 USD')).toBeVisible()
    expect(screen.getByText('4 / 7')).toBeVisible()
    expect(screen.getByText(/correlated path observations/)).toBeVisible()
    expect(screen.getByText('Synthetic data')).toBeVisible()
    await userEvent.click(screen.getByText('Session details and provenance'))
    const table = screen.getByRole('table', { name: 'Forecast and actual daily prices' })
    expect(within(table).getByText('2026-09-14')).toBeVisible()
    expect(within(table).getByText('97.00')).toBeVisible()
    expect(screen.getByText('forecast-original')).toBeVisible()
    expect(screen.getByText('outcome-frozen')).toBeVisible()
  })

  it('preserves missing sessions and splits actual lines rather than bridging a gap', () => {
    show({ ...comparison, status: 'partial', observed_sessions: 6,
      mean_absolute_error: null, benchmark_mae: null, interval_hits: null,
      interval_coverage: null, terminal_error: null,
      rows: comparison.rows.map((row, index) => index === 1 ? { ...row, actual_close: null, absolute_error: null, within_interval: null } : row),
    })
    expect(screen.getByText('Incomplete evidence')).toBeVisible()
    expect(screen.getByText(/Scores require every selected session/)).toBeVisible()
    expect(screen.queryByText('2.00 USD')).not.toBeInTheDocument()
    const props = chart.mock.calls.at(-1)![0]
    expect(props.indicators).toHaveLength(2)
    expect(props.indicators.map((line: { points: unknown[] }) => line.points.length)).toEqual([1, 5])
    expect(props.indicators.every((line: { pointMarkersVisible: boolean }) => line.pointMarkersVisible)).toBe(true)
  })

  it('shows frozen review and no plot for a refused comparison', () => {
    show({ ...comparison, status: 'unavailable', rows: [], observed_sessions: 0,
      mean_absolute_error: null, benchmark_mae: null, interval_hits: null,
      interval_coverage: null, terminal_error: null,
    }, true)
    expect(screen.getByText('Frozen at review save')).toBeVisible()
    expect(screen.getAllByText('Unavailable').length).toBeGreaterThan(0)
    expect(chart).not.toHaveBeenCalled()
  })

  it('localizes score semantics and dates in Chinese', () => {
    window.localStorage.setItem('quantmesh.preferences', JSON.stringify({ locale: 'zh-CN', theme: 'dark' }))
    show()
    expect(screen.getByRole('heading', { name: '预测与实际对照' })).toBeVisible()
    expect(screen.getByText('中位数平均绝对误差')).toBeVisible()
    expect(screen.getByText('已观察 7 / 7 个交易日')).toBeVisible()
    expect(screen.getByText(/不是校准准确率/)).toBeVisible()
  })
})
