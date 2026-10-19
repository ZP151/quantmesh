import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
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

it('keeps verified report A through a new job and downloads the exact A and B comparison artifacts', async () => {
  const user = userEvent.setup()
  const identity = {
    fixture_sha256: 'b'.repeat(64), engine_sha256: 'c'.repeat(64),
    versions: { vnpy: '4.5.0', vnpy_ctastrategy: '1.4.1', vnpy_sqlite: '1.1.3' },
    strategy_sources: { DoubleMaStrategy: 'd'.repeat(64), AtrRsiStrategy: 'e'.repeat(64) },
    adapter_sha256: 'f'.repeat(64), runner_sha256: '1'.repeat(64),
    cost_units: { fee_bps: 'bps of turnover', half_spread_price: 'USD/unit/fill', slippage_price: 'USD/unit/fill' },
    capital_usd: 100000, contract_size: 1, tick: 0.01, annual_days: 252,
    replay_period: ['2013-10-07', '2013-10-11'], exchange_timezone: 'America/New_York', fixture_only: true,
  }
  const requestB = { ...request, costs: { ...request.costs, fee_bps: 10 } }
  const textA = JSON.stringify({ ...report, identity })
  const textB = JSON.stringify({ ...report, identity, request: requestB, request_digest: '2'.repeat(64),
    statistics: { ...report.statistics, end_balance: 100043.91, total_commission: 3.14 } })
  const shaA = createHash('sha256').update(textA).digest('hex')
  const shaB = createHash('sha256').update(textB).digest('hex')
  mocks.submit.mockResolvedValueOnce({ ...job, report_sha256: shaA })
    .mockResolvedValueOnce({ ...job, job_id: 'job2', request: requestB, request_digest: '2'.repeat(64), report_sha256: shaB })
  mocks.report.mockResolvedValueOnce({ schema_version: 1, sha256: shaA, request_digest: digest, text: textA })
    .mockResolvedValueOnce({ schema_version: 1, sha256: shaB, request_digest: '2'.repeat(64), text: textB })
  const { Blob: NodeBlob } = await import('node:buffer')
  const downloaded: globalThis.Blob[] = []
  const filenames: string[] = []
  const originalBlob = globalThis.Blob
  vi.stubGlobal('Blob', NodeBlob)
  const createUrl = vi.fn((blob: globalThis.Blob) => { downloaded.push(blob); return `blob:verified-${downloaded.length}` })
  const revokeUrl = vi.fn()
  vi.stubGlobal('URL', class extends URL {
    static createObjectURL = createUrl
    static revokeObjectURL = revokeUrl
  })
  const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (this: HTMLAnchorElement) {
    filenames.push(this.download)
  })
  try {
    render(<VnpyFixturePanel />)
    await screen.findByRole('option', { name: 'AtrRsiStrategy' })
    await user.click(screen.getByRole('button', { name: 'Run vn.py backtest' }))
    await user.click(await screen.findByRole('button', { name: 'Open verified report' }))
    await user.click(await screen.findByRole('button', { name: 'Keep as comparison reference' }))
    await user.click(screen.getByRole('button', { name: 'New fixture job' }))
    const retained = screen.getByRole('region', { name: 'Native report comparison' })
    expect(within(retained).getByText(shaA, { exact: false })).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('Fee (bps)'), { target: { value: '10' } })
    await user.click(screen.getByRole('button', { name: 'Run vn.py backtest' }))
    await user.click(await screen.findByRole('button', { name: 'Open verified report' }))
    const comparison = await screen.findByRole('region', { name: 'Native report comparison' })
    expect(within(comparison).getByText(shaA, { exact: false })).toBeInTheDocument()
    expect(within(comparison).getByText(shaB, { exact: false })).toBeInTheDocument()
    await user.click(within(comparison).getByRole('button', { name: 'Download reference JSON' }))
    await user.click(within(comparison).getByRole('button', { name: 'Download candidate JSON' }))
    expect(await downloaded[0].text()).toBe(textA)
    expect(await downloaded[1].text()).toBe(textB)
    expect(filenames[0]).toContain(shaA)
    expect(filenames[1]).toContain(shaB)
    await waitFor(() => expect(revokeUrl).toHaveBeenCalledTimes(2), { timeout: 1600 })
    await user.click(within(comparison).getByRole('button', { name: 'Clear comparison reference' }))
    expect(screen.queryByRole('region', { name: 'Native report comparison' })).toBeNull()
  } finally {
    click.mockRestore()
    vi.stubGlobal('Blob', originalBlob)
    vi.unstubAllGlobals()
  }
})
