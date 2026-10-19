import { fireEvent, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, expect, it, vi } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import { PreferencesProvider } from '@/lib/preferences'
import { FrozenExperimentsScreen } from './FrozenExperiments'

const mocks = vi.hoisted(() => ({ list: vi.fn(), import: vi.fn(), get: vi.fn(), download: vi.fn() }))
vi.mock('@/lib/frozen-experiments-api', async original => ({ ...await original<typeof import('@/lib/frozen-experiments-api')>(), frozenExperimentsApi: mocks }))
const id = 'a'.repeat(64)
const metrics = { total_return: 0.2, net_profit_usd: 20000, cagr: 0.1, max_drawdown: -0.1,
  max_underwater_sessions: 100, historical_es_95: -0.02, friction_usd: 500,
  gross_traded_notional_over_initial_capital: 10, naive_sharpe_rf_zero: null }
const record = {
  schema_version: 1, package_id: id, experiment_id: 'QM-REAL-ETF-001-D-20261018',
  snapshot_id: 'b'.repeat(64), imported_at: '2026-10-19T00:00:00Z',
  verification: { identities: 'VERIFIED', economics: 'IMPORTED_NOT_RECOMPUTED', chronology: 'UNVERIFIED' },
  proxy_verdict: 'REJECT', formal_verdict: { R1: 'INSUFFICIENT', R2: 'INSUFFICIENT', R3: 'NOT_AUTHORIZED' },
  oos: { state: 'CONSUMED', pristine_blind: false }, trials: { current: 1, searched: 0, prior: null, source_exposure: true },
  protocol: { sha256: 'c'.repeat(64), frozen_at_claimed: '2026-10-18T15:07:06Z', created_before_results_claimed: true,
    symbol: 'SPY', lookback: 100, comparison: 'completed close > SMA100', execution: 'next-session DAILY OPEN proxy',
    final_window: ['2025-01-02', '2026-10-16'], capital_usd: 100000,
    costs: { single_side_proxy_bps: 5, stress_bps: 10, gross_diagnostic_bps: 0, extra_delay_stress_sessions: 1,
      fee_spread_slippage_breakdown: 'unknown; combined research proxy only', actual_nbbo_and_costs_verified: false } },
  data: { qualification: 'INSUFFICIENT', evidence_kind: 'real_snapshot', rights: 'UNVERIFIED', pit: 'UNVERIFIED', execution: 'UNVERIFIED',
    dividend_conflict: { date: '2021-12-17', yahoo_usd: 1.633, issuer_usd: 1.636431, resolution: 'unresolved; issuer primary' } },
  missing_evidence: ['PIT availability/revision history', 'trading/product data entitlement'],
  cases: ['final-base5bps', 'final-stress10bps', 'final-delay1session5bps', 'final-gross0bps', 'development2020-base5bps',
    'validation2022-base5bps', 'validation2023-base5bps', 'validation2024-base5bps'].map((case_id, i) => ({ case_id, primary: i === 0,
      strategy: metrics, benchmark: { ...metrics, total_return: 0.3 }, cash_benchmark_total_return: 0,
      net_total_return_difference: -0.1, inference: [] })),
  lineage: [{ path: 'protocol.json', sha256: 'c'.repeat(64), bytes: 123 }],
  downloads: [{ kind: 'archive', sha256: id, bytes: 100 }, { kind: 'protocol', sha256: 'c'.repeat(64), bytes: 123 },
    { kind: 'result', sha256: 'd'.repeat(64), bytes: 200 }, { kind: 'report', sha256: 'e'.repeat(64), bytes: 300 }],
}
function mount() { return render(<MemoryRouter><PreferencesProvider><FrozenExperimentsScreen /></PreferencesProvider></MemoryRouter>) }
beforeEach(() => {
  localStorage.clear(); vi.clearAllMocks()
  mocks.list.mockResolvedValue([]); mocks.get.mockResolvedValue(record); mocks.import.mockResolvedValue(record)
})

it('loads then shows the honest empty import state', async () => {
  let finish!: (value: []) => void
  mocks.list.mockReturnValueOnce(new Promise(resolve => { finish = resolve }))
  mount(); expect(screen.getByRole('status')).toHaveTextContent('Loading frozen experiment history')
  finish([]); await screen.findByText('No frozen experiments imported')
  expect(screen.getByRole('button', { name: 'Import experiment' })).toBeDisabled()
})

it('imports and puts recorded verdict, consumed OOS and provenance ahead of metrics', async () => {
  mount(); await screen.findByText('No frozen experiments imported')
  await userEvent.upload(screen.getByLabelText('Frozen experiment ZIP'), new File(['archive'], 'frozen.zip', { type: 'application/zip' }))
  await userEvent.click(screen.getByRole('button', { name: 'Import experiment' }))
  const verdict = await screen.findByRole('region', { name: 'Recorded case verdict' })
  expect(verdict).toHaveTextContent('REJECT')
  expect(verdict).toHaveTextContent('INSUFFICIENT')
  expect(verdict).toHaveTextContent('NOT_AUTHORIZED')
  expect(verdict).toHaveTextContent('Final OOS consumed')
  expect(screen.getByText('Prior trial history').nextElementSibling).toHaveTextContent('Unknown / unavailable')
  expect(screen.getByText('Chronology').nextElementSibling).toHaveTextContent('Unverified')
  expect(screen.getByRole('table', { name: 'Fixed diagnostic cases' }).querySelectorAll('tbody tr')).toHaveLength(8)
  expect(screen.getByRole('region', { name: 'Imported primary result' })).toHaveTextContent('Unknown / unavailable')
  expect(screen.getByText(/Imported historical metrics; references checked/)).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: /Run|Promote|Order/ })).not.toBeInTheDocument()
})

it('reopens stored evidence through the API', async () => {
  mocks.list.mockResolvedValue([record]); mount()
  await userEvent.click(await screen.findByRole('button', { name: /Reopen QM-REAL/ }))
  expect(await screen.findByRole('region', { name: 'Recorded case verdict' })).toBeInTheDocument()
  expect(mocks.get).toHaveBeenCalledWith(id)
})

it('offers the P1 prerequisite link and retains the report when import fails', async () => {
  mocks.list.mockResolvedValue([record]); mount()
  await userEvent.click(await screen.findByRole('button', { name: /Reopen QM-REAL/ }))
  mocks.import.mockRejectedValue(Object.assign(new Error('private payload'), { code: 'snapshot_required' }))
  await userEvent.upload(screen.getByLabelText('Frozen experiment ZIP'), new File(['bad'], 'bad.zip'))
  await userEvent.click(screen.getByRole('button', { name: 'Import experiment' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('Import the matching data snapshot first')
  expect(screen.getAllByRole('link', { name: 'Open data readiness' })[0]).toHaveAttribute('href', '/research/data-readiness')
  expect(screen.getByRole('region', { name: 'Recorded case verdict' })).toBeInTheDocument()
  expect(screen.queryByText('private payload')).not.toBeInTheDocument()
})

it('disables imports when unavailable and retries history', async () => {
  mocks.list.mockRejectedValueOnce(Object.assign(new Error('private'), { code: 'unavailable' }))
  mount(); expect(await screen.findByRole('alert')).toHaveTextContent('Frozen experiment storage is unavailable')
  expect(screen.getByLabelText('Frozen experiment ZIP')).toBeDisabled()
  await userEvent.click(screen.getByRole('button', { name: 'Refresh history' }))
  await screen.findByText('No frozen experiments imported')
})

it('uses the Chinese preference and blocks oversized selection', async () => {
  localStorage.setItem('quantmesh.preferences', JSON.stringify({ locale: 'zh-CN', theme: 'dark' }))
  mount(); await screen.findByText('尚未导入冻结实验')
  const file = new File(['x'], 'large.zip')
  Object.defineProperty(file, 'size', { value: 8 * 1024 * 1024 + 1 })
  fireEvent.change(screen.getByLabelText('冻结实验 ZIP'), { target: { files: [file] } })
  expect(await screen.findByRole('alert')).toHaveTextContent('ZIP 超过 8 MiB')
  expect(mocks.import).not.toHaveBeenCalled()
})

it('shows integrity errors on downloads without rendering imported content', async () => {
  mocks.list.mockResolvedValue([record]); mocks.download.mockRejectedValue(Object.assign(new Error('private'), { code: 'integrity' }))
  mount(); await userEvent.click(await screen.findByRole('button', { name: /Reopen QM-REAL/ }))
  await userEvent.click(screen.getByRole('button', { name: 'Download original archive' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('Evidence integrity check failed')
  expect(within(screen.getByRole('region', { name: 'Original evidence' })).getByRole('button', { name: 'Download original report' })).toBeEnabled()
  expect(document.querySelector('iframe')).toBeNull()
})

it('downloads selected original artifacts only after transport verification', async () => {
  const saved: string[] = []
  vi.stubGlobal('URL', class extends URL { static createObjectURL = vi.fn(() => 'blob:verified'); static revokeObjectURL = vi.fn() })
  const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (this: HTMLAnchorElement) { saved.push(this.download) })
  mocks.list.mockResolvedValue([record]); mocks.download.mockResolvedValue(new Blob(['verified original bytes']))
  mount(); await userEvent.click(await screen.findByRole('button', { name: /Reopen QM-REAL/ }))
  await userEvent.click(screen.getByRole('button', { name: 'Download original archive' }))
  await userEvent.click(screen.getByRole('button', { name: 'Download original report' }))
  expect(saved).toEqual([`${id}-archive.zip`, `${id}-report.md`])
  expect(mocks.download).toHaveBeenNthCalledWith(1, id, record.downloads[0])
  expect(mocks.download).toHaveBeenNthCalledWith(2, id, record.downloads[3])
  click.mockRestore(); vi.unstubAllGlobals()
})

it('exposes import progress while preventing overlapping actions', async () => {
  let finish!: (value: typeof record) => void
  mocks.import.mockReturnValueOnce(new Promise(resolve => { finish = resolve }))
  mount(); await screen.findByText('No frozen experiments imported')
  await userEvent.upload(screen.getByLabelText('Frozen experiment ZIP'), new File(['archive'], 'frozen.zip'))
  await userEvent.click(screen.getByRole('button', { name: 'Import experiment' }))
  expect(screen.getByRole('status')).toHaveTextContent('Importing and checking references')
  expect(screen.getByRole('button', { name: 'Refresh history' })).toBeDisabled()
  expect(screen.getByRole('button', { name: 'Import experiment' })).toBeDisabled()
  finish(record)
  expect(await screen.findByRole('region', { name: 'Recorded case verdict' })).toBeInTheDocument()
})
