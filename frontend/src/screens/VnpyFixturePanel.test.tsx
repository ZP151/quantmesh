import { render, screen, waitFor } from '@testing-library/react'
import { createHash, webcrypto } from 'node:crypto'
import userEvent from '@testing-library/user-event'
import { beforeEach, expect, it, vi } from 'vitest'
import { VnpyFixturePanel } from './VnpyFixturePanel'

const mocks = vi.hoisted(() => ({ options: vi.fn(), submit: vi.fn(), get: vi.fn(), cancel: vi.fn(), report: vi.fn() }))
vi.mock('@/lib/vnpy-fixture-api', () => ({ vnpyFixtureApi: mocks }))
const digest = 'a'.repeat(64)
const request = { schema_version: 1, strategy_id: 'DoubleMaStrategy', parameters: { fast_window: 10, slow_window: 20 },
  costs: { fee_bps: 5, half_spread_price: 0.005, slippage_price: 0.005 } }
const job = { schema_version: 1, job_id: 'job1', request_digest: digest, request,
  state: 'succeeded', stage: 'complete', completed_bars: 1950, total_bars: 1950, error_code: null,
  report_sha256: '' }
const report = { schema_version: 1, request_digest: digest, request,
  statistics: { end_balance: 100045.48, total_commission: 1.57, total_slippage: 0.31, total_trade_count: 31 },
  daily: [{ date: '2013-10-07', balance: 100010, net_pnl: 10 }], trades: [], lifecycle: {}, identity: {}, semantics: 'Synthetic workflow evidence only.' }
const text = JSON.stringify(report)
const sha = createHash('sha256').update(text).digest('hex')

beforeEach(() => {
  vi.stubGlobal('crypto', webcrypto)
  localStorage.clear()
  vi.clearAllMocks()
  mocks.options.mockResolvedValue({ schema_version: 1, fixture_sha256: digest, fixture_label: 'Synthetic SPY · 1950 bars',
    engine_versions: { vnpy: '4.5.0' }, strategies: ['DoubleMaStrategy', 'AtrRsiStrategy'].map(strategy_id => ({
      strategy_id, source_sha256: digest, parameters: [{ name: 'fast_window', default: 10, minimum: 2, maximum: 80, integer: true },
        { name: 'slow_window', default: 20, minimum: 3, maximum: 90, integer: true }] })) })
  mocks.submit.mockImplementation(async (body) => ({ ...job, request: body, state: 'running', stage: 'replaying', completed_bars: 100, report_sha256: null }))
  mocks.get.mockResolvedValue({ ...job, report_sha256: sha })
  mocks.report.mockResolvedValue({ schema_version: 1, sha256: sha, request_digest: digest, text })
  mocks.cancel.mockResolvedValue({ ...job, state: 'cancelled' })
})

it('configures native costs, submits, observes progress and verifies a report', async () => {
  const user = userEvent.setup()
  render(<VnpyFixturePanel />)
  await screen.findByRole('option', { name: 'AtrRsiStrategy' })
  expect(screen.getByLabelText('Half spread (USD/unit/fill)')).toHaveValue(0.005)
  await user.click(screen.getByRole('button', { name: 'Run vn.py backtest' }))
  await screen.findByText('replaying · 100 / 1950 bars')
  expect(mocks.submit.mock.calls[0][0]).toEqual(request)
  await user.click(screen.getByRole('button', { name: 'Refresh status' }))
  await screen.findByText('succeeded')
  await user.click(screen.getByRole('button', { name: 'Open verified report' }))
  await screen.findByText('100,045.48')
  expect(screen.getByText(`SHA256 ${sha}`)).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Download report JSON' })).toBeEnabled()
})

it('refuses corrupt report bytes', async () => {
  const user = userEvent.setup()
  mocks.submit.mockResolvedValue({ ...job, report_sha256: sha })
  mocks.report.mockResolvedValue({ schema_version: 1, sha256: sha, request_digest: digest, text: text + ' ' })
  render(<VnpyFixturePanel />)
  await screen.findByRole('option', { name: 'AtrRsiStrategy' })
  await user.click(screen.getByRole('button', { name: 'Run vn.py backtest' }))
  await user.click(await screen.findByRole('button', { name: 'Open verified report' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('Report verification failed')
  expect(screen.queryByRole('button', { name: 'Download report JSON' })).toBeNull()
})

it('shows unavailable runtime without enabling submission', async () => {
  mocks.options.mockRejectedValue(new Error('503'))
  render(<VnpyFixturePanel />)
  await screen.findByText(/vn.py fixture runtime unavailable/)
  expect(screen.getByRole('button', { name: 'Run vn.py backtest' })).toBeDisabled()
})

it('preserves pending identity on transport failure for explicit retry', async () => {
  const user = userEvent.setup()
  mocks.submit.mockRejectedValueOnce(new Error('offline'))
  render(<VnpyFixturePanel />)
  await screen.findByRole('option', { name: 'AtrRsiStrategy' })
  await user.click(screen.getByRole('button', { name: 'Run vn.py backtest' }))
  await screen.findByRole('alert')
  await user.click(screen.getByRole('button', { name: 'Retry same submission' }))
  await waitFor(() => expect(mocks.submit).toHaveBeenCalledTimes(2))
  expect(mocks.submit.mock.calls[0][1]).toEqual(mocks.submit.mock.calls[1][1])
})

it('restores the exact submitted parameters and costs in disabled fields', async () => {
  localStorage.setItem('quantmesh.vnpy-fixture.v1', JSON.stringify({ key: 'retained',
    request: { ...request, parameters: { fast_window: 8, slow_window: 18 }, costs: { ...request.costs, fee_bps: 6 } } }))
  render(<VnpyFixturePanel />)
  await screen.findByRole('option', { name: 'AtrRsiStrategy' })
  expect(screen.getByLabelText('fast_window')).toHaveValue(8)
  expect(screen.getByLabelText('Fee (bps)')).toHaveValue(6)
  expect(screen.getByLabelText('fast_window')).toBeDisabled()
})

it('refuses running to queued status regression', async () => {
  const user = userEvent.setup()
  mocks.get.mockResolvedValue({ ...job, state: 'queued', stage: 'queued', completed_bars: 100 })
  render(<VnpyFixturePanel />)
  await screen.findByRole('option', { name: 'AtrRsiStrategy' })
  await user.click(screen.getByRole('button', { name: 'Run vn.py backtest' }))
  await screen.findByText('running')
  await user.click(screen.getByRole('button', { name: 'Refresh status' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('mismatch')
  expect(screen.getByText('running')).toBeInTheDocument()
})

it('allows a new fixture after restart makes a retained active job unknown', async () => {
  const user = userEvent.setup()
  const running = { ...job, state: 'running', stage: 'loading_data', completed_bars: 0 }
  localStorage.setItem('quantmesh.vnpy-fixture.v1', JSON.stringify({ key: 'retained', request, job: running }))
  mocks.get.mockRejectedValue(Object.assign(new Error('Request failed (404)'), { status: 404 }))
  render(<VnpyFixturePanel />)
  await user.click(screen.getByRole('button', { name: 'Refresh status' }))
  await screen.findByRole('alert')
  await user.click(screen.getByRole('button', { name: 'New fixture job' }))
  await waitFor(() => expect(screen.getByRole('button', { name: 'Run vn.py backtest' })).toBeEnabled())
})
