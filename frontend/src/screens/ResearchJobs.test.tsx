import { act, render, screen, waitFor } from '@testing-library/react'
import { createHash, webcrypto } from 'node:crypto'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ResearchJobsScreen } from './ResearchJobs'

const mocks = vi.hoisted(() => ({
  options: vi.fn(), submit: vi.fn(), get: vi.fn(), cancel: vi.fn(), artifact: vi.fn(),
}))
vi.mock('@/lib/api', () => ({ api: {
  researchJobOptions: mocks.options, submitResearchJob: mocks.submit,
  researchJob: mocks.get, cancelResearchJob: mocks.cancel, researchJobArtifact: mocks.artifact,
} }))

const pin = { dataset_id: 'equities', revision: 1, manifest_digest: 'a'.repeat(64),
  export_digest: 'b'.repeat(64), permission_class: 'fixture' }
const options = { schema_version: 1, status: 'configured', reason: null,
  strategies: ['momentum', 'mean_reversion', 'risk_parity'].map(strategy_id => ({
    strategy_id, version: '1', implementation_digest: 'c'.repeat(64),
  })), datasets: [{ dataset: pin, interval: '1h', minimum_available_bars: 60,
    universe: [{ venue: 'moomoo', symbol: 'AAA' }] }] }
const request = { schema_version: 1, strategy_id: 'momentum', strategy_version: '1', dataset: pin,
  interval: '1h', universe: [{ venue: 'moomoo', symbol: 'AAA' }], parameters: {},
  costs: { fee_bps: 1, half_spread_bps: 2, slippage_bps: 3 },
  window_spec: { train_bars: 10, test_bars: 5, step_bars: 5 }, analysis_requested: true,
  budget: { timeout_seconds: 900, memory_mib: 2048, cpu_limit: 1,
    max_model_calls: 12, max_estimated_model_usd: 1 } }
const reportText = JSON.stringify({ schema_version: 1, result: { metrics: {
  total_return: 0.01, total_cost: 0.003 }, evidence: { build_digest: 'f'.repeat(64) } } })
const reportDigest = createHash('sha256').update(reportText).digest('hex')
function job(state = 'queued') {
  return { job_id: 'fixture-job', operator_id: 'local', idempotency_key: 'saved-key', request,
    request_digest: 'd'.repeat(64), implementation_digest: 'c'.repeat(64), state, attempt: 0,
    cancel_requested: false, created_at: '2026-01-01T00:00:00Z', updated_at: '2026-01-01T00:00:00Z',
    artifacts: state === 'succeeded' ? [{ kind: 'report', artifact_id: reportDigest,
      sha256: reportDigest, byte_size: Buffer.byteLength(reportText), schema_version: 1,
      object_key: `fixture-job/${reportDigest}.json` }] : [],
    usage: {}, analysis_state: state === 'succeeded' ? 'unavailable' : 'pending', analysis: null }
}

beforeEach(() => {
  vi.stubGlobal('crypto', webcrypto)
  localStorage.clear()
  vi.clearAllMocks()
  mocks.options.mockResolvedValue(options)
  mocks.submit.mockImplementation(async (_request, key) => ({ ...job(), idempotency_key: key }))
  mocks.get.mockResolvedValue(job('succeeded'))
  mocks.cancel.mockResolvedValue(job('cancelled'))
  mocks.artifact.mockResolvedValue(reportText)
})
afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals() })

describe('fixture research loop', () => {
  it('submits pinned setup, reaches report, reloads and keeps Agent unavailable independent', async () => {
    const user = userEvent.setup()
    const first = render(<ResearchJobsScreen />)
    await user.click(await screen.findByRole('button', { name: 'Submit fixture job' }))
    await screen.findByText('queued')
    await user.click(screen.getByRole('button', { name: 'Refresh status' }))
    await screen.findByText('succeeded')
    await screen.findByText(/Agent unavailable/)
    await user.click(screen.getByRole('button', { name: 'Open immutable report' }))
    await screen.findByText('Canonical report')
    expect(screen.getAllByText(/unavailable/i).length).toBeGreaterThan(0)
    expect(mocks.submit.mock.calls[0][0]).toMatchObject({ dataset: pin,
      costs: { fee_bps: 1, half_spread_bps: 2, slippage_bps: 3 } })
    first.unmount()
    mocks.options.mockRejectedValue(new Error('service_unavailable'))
    mocks.get.mockRejectedValue(new Error('service_unavailable'))
    render(<ResearchJobsScreen />)
    await screen.findByText('Canonical report')
    expect(mocks.submit).toHaveBeenCalledTimes(1)
    expect(screen.queryByRole('button', { name: /order|paper proposal/i })).not.toBeInTheDocument()
  })

  it('preserves ambiguous key and payload across reload and explicitly retries same request', async () => {
    const user = userEvent.setup()
    mocks.submit.mockRejectedValueOnce(new Error('response lost'))
    const first = render(<ResearchJobsScreen />)
    await user.click(await screen.findByRole('button', { name: 'Submit fixture job' }))
    await screen.findByRole('button', { name: 'Retry saved submission' })
    const original = mocks.submit.mock.calls[0]
    first.unmount()
    render(<ResearchJobsScreen />)
    await user.click(await screen.findByRole('button', { name: 'Retry saved submission' }))
    await waitFor(() => expect(mocks.submit).toHaveBeenCalledTimes(2))
    expect(mocks.submit.mock.calls[1]).toEqual(original)
  })

  it('cancels active jobs and does not poll terminal states', async () => {
    const user = userEvent.setup()
    render(<ResearchJobsScreen />)
    await user.click(await screen.findByRole('button', { name: 'Submit fixture job' }))
    await user.click(await screen.findByRole('button', { name: 'Cancel job' }))
    await screen.findByText('cancelled')
    expect(screen.queryByRole('button', { name: 'Cancel job' })).not.toBeInTheDocument()
  })

  it('empty or unavailable options disable submission and failures remain explicit', async () => {
    mocks.options.mockResolvedValue({ ...options, status: 'unavailable', datasets: [],
      reason: 'no_qualified_inputs' })
    render(<ResearchJobsScreen />)
    await screen.findByText(/No qualified fixture inputs/)
    expect(screen.getByRole('button', { name: 'Submit fixture job' })).toBeDisabled()
  })

  it('restores failed job without resubmitting', async () => {
    localStorage.setItem('quantmesh.research-job.v1', JSON.stringify({
      submission: { key: 'saved-key', request }, job: job('failed'),
    }))
    render(<ResearchJobsScreen />)
    await screen.findByText('failed')
    expect(mocks.submit).not.toHaveBeenCalled()
    expect(mocks.get).not.toHaveBeenCalled()
  })

  it('stops automatic status checks at the bound and never polls a terminal job', async () => {
    mocks.get.mockImplementation(async () => job())
    localStorage.setItem('quantmesh.research-job.v1', JSON.stringify({
      submission: { key: 'saved-key', request }, job: job(),
    }))
    render(<ResearchJobsScreen />)
    await screen.findByText('queued')
    vi.useFakeTimers()
    // The first timer was registered before fake timers; force one state refresh.
    await act(async () => {
      screen.getByRole('button', { name: 'Refresh status' }).click()
      await Promise.resolve()
    })
    mocks.get.mockClear()
    for (let index = 0; index < 62; index += 1) {
      await act(async () => { await vi.advanceTimersByTimeAsync(3000) })
    }
    expect(mocks.get).toHaveBeenCalledTimes(60)
    expect(screen.getByText(/Automatic checks paused/)).toBeInTheDocument()
    mocks.get.mockResolvedValue(job('failed'))
    await act(async () => { screen.getByRole('button', { name: 'Refresh status' }).click() })
    mocks.get.mockClear()
    await act(async () => { await vi.advanceTimersByTimeAsync(30000) })
    expect(mocks.get).not.toHaveBeenCalled()
  })

  it('cannot send when the idempotency payload cannot be retained', async () => {
    const user = userEvent.setup()
    const save = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('quota') })
    render(<ResearchJobsScreen />)
    await user.click(await screen.findByRole('button', { name: 'Submit fixture job' }))
    await screen.findByText(/Submission was not sent/)
    expect(mocks.submit).not.toHaveBeenCalled()
    save.mockRestore()
  })

  it('restores the saved costs and selected baseline in disabled configuration controls', async () => {
    const retained = { ...request, strategy_id: 'risk_parity', costs: {
      fee_bps: 7, half_spread_bps: 8, slippage_bps: 9 }, window_spec: {
      train_bars: 20, test_bars: 4, step_bars: 4 } }
    localStorage.setItem('quantmesh.research-job.v1', JSON.stringify({
      submission: { key: 'saved-key', request: retained }, job: { ...job('failed'), request: retained },
    }))
    render(<ResearchJobsScreen />)
    await screen.findByText('failed')
    expect(screen.getByLabelText('Registered baseline')).toHaveValue('risk_parity')
    expect(screen.getByLabelText('Fee (bps)')).toHaveValue(7)
    expect(screen.getByLabelText('Train bars')).toHaveValue(20)
  })

  it('rejects tampered retained report bytes after reload', async () => {
    localStorage.setItem('quantmesh.research-job.v1', JSON.stringify({
      submission: { key: 'saved-key', request }, job: job('succeeded'),
    }))
    localStorage.setItem('quantmesh.research-job.v1.report.fixture-job', JSON.stringify({
      jobId: 'fixture-job', artifactId: reportDigest, text: reportText.replace('0.01', '9.99'),
    }))
    render(<ResearchJobsScreen />)
    await screen.findByText(/Retained report integrity verification failed/)
    expect(screen.queryByText('Canonical report')).not.toBeInTheDocument()
  })
})
