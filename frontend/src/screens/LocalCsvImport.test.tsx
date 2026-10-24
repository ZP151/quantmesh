import { fireEvent, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, expect, it, vi } from 'vitest'
import { PreferencesProvider } from '@/lib/preferences'
import { LocalCsvImport } from './LocalCsvImport'

const mocks = vi.hoisted(() => ({ list: vi.fn(), import: vi.fn(), get: vi.fn() }))
vi.mock('@/lib/local-csv-api', async original => ({ ...await original<typeof import('@/lib/local-csv-api')>(), localCsvApi: mocks }))
import { localReport } from '@/test/local-csv-fixture'

function mount() { return render(<PreferencesProvider><LocalCsvImport /></PreferencesProvider>) }
async function fill() {
  await userEvent.upload(screen.getByLabelText('Daily OHLCV CSV'), new File(['timestamp_utc,open,high,low,close,volume\n2026-10-19T13:30:00Z,1,2,1,2,100'], 'my-prices.csv', { type: 'text/csv' }))
  fireEvent.change(screen.getByLabelText('Symbol'), { target: { value: 'SPY' } })
  fireEvent.change(screen.getByLabelText('Coverage starts'), { target: { value: '2026-10-19' } })
  fireEvent.change(screen.getByLabelText('Coverage ends'), { target: { value: '2026-10-21' } })
}
beforeEach(() => { vi.clearAllMocks(); localStorage.clear(); mocks.list.mockResolvedValue([]); mocks.import.mockResolvedValue(localReport); mocks.get.mockResolvedValue(localReport) })

it('shows an actionable empty catalog and requires file, symbol and coverage', async () => {
  mount(); await screen.findByText('No CSV imports yet')
  expect(screen.getByRole('button', { name: 'Import and check data' })).toBeDisabled()
  expect(screen.getByText(/timestamp_utc,open,high,low,close,volume/)).toBeInTheDocument()
})
it('imports actual selected bytes with unknown claims and separates structure from qualification', async () => {
  mount(); await screen.findByText('No CSV imports yet'); await fill()
  await userEvent.click(screen.getByRole('button', { name: 'Import and check data' }))
  const result = await screen.findByRole('region', { name: 'Import result' })
  expect(result).toHaveTextContent('Structure passed')
  expect(result).toHaveTextContent('Research qualification insufficient')
  expect(result).toHaveTextContent('Corporate actions are unknown')
  expect(within(result).getByText('Source received at').nextElementSibling).toHaveTextContent('Unknown')
  expect(mocks.import.mock.calls[0][0]).toMatchObject({ symbol: 'SPY', calendar_id: 'XNYS', required_start: '2026-10-19', source: { received_at: null, pit_status: 'unknown' } })
  expect(mocks.import.mock.calls[0][0].csv_text).toContain('2026-10-19T13:30:00Z')
  expect(screen.getByRole('link', { name: 'Plan an experiment with this reference' })).toHaveAttribute('href', `/app/research/jobs?snapshot=${localReport.snapshot_id}`)
  expect(screen.queryByText('Available for research')).not.toBeInTheDocument()
})
it('renders rejected rows and omits the planning action without a usable reference', async () => {
  const rejected = { ...localReport, dataset_ref: null, qualification: { ...localReport.qualification, status: 'REJECT', structural_status: 'REJECT' },
    next_action: { ...localReport.next_action, kind: 'inspect_issues' },
    checks: [{ code: 'bar_values', status: 'REJECT', count: 17, message: 'Low exceeds high', locations_truncated: true,
      locations: [{ row: 4, date: '2026-10-21', field: 'low', expected: 'low <= high', actual: '120 > 100' }] }] }
  mocks.import.mockResolvedValue(rejected)
  mount(); await screen.findByText('No CSV imports yet'); await fill()
  await userEvent.click(screen.getByRole('button', { name: 'Import and check data' }))
  expect(await screen.findByText('Low exceeds high')).toBeInTheDocument()
  expect(screen.getByRole('table', { name: 'Data issues' })).toHaveTextContent('120 > 100')
  expect(screen.getByText(/Showing a limited set of locations/)).toBeInTheDocument()
  expect(screen.queryByRole('link', { name: 'Plan an experiment with this reference' })).not.toBeInTheDocument()
})
it('retains a labeled previous result after failure and allows retry without raw server details', async () => {
  mocks.list.mockResolvedValue([localReport]); mount()
  await userEvent.click(await screen.findByRole('button', { name: /Open My saved prices/ }))
  await fill(); mocks.import.mockRejectedValue(Object.assign(new Error('secret trace'), { status: 422 }))
  await userEvent.click(screen.getByRole('button', { name: 'Import and check data' }))
  const alert = await screen.findByRole('alert')
  expect(alert).toHaveTextContent('Check the CSV header and import details')
  expect(alert).toHaveFocus()
  expect(screen.getByText('Previous saved report')).toBeInTheDocument()
  expect(screen.queryByText('secret trace')).not.toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Import and check data' })).toBeEnabled()
})
it('blocks oversized files locally and never uploads them', async () => {
  mount(); await screen.findByText('No CSV imports yet')
  const file = new File(['x'], 'large.csv'); Object.defineProperty(file, 'size', { value: 2097153 })
  fireEvent.change(screen.getByLabelText('Daily OHLCV CSV'), { target: { files: [file] } })
  expect(await screen.findByRole('alert')).toHaveTextContent('2 MiB')
  expect(mocks.import).not.toHaveBeenCalled()
})
it('shows checking progress and prevents overlapping imports', async () => {
  let finish!: (value: typeof localReport) => void
  mocks.import.mockReturnValue(new Promise(resolve => { finish = resolve }))
  mount(); await screen.findByText('No CSV imports yet'); await fill()
  await userEvent.click(screen.getByRole('button', { name: 'Import and check data' }))
  expect(screen.getByRole('status')).toHaveTextContent('Uploading and checking data')
  expect(screen.getByRole('button', { name: 'Import and check data' })).toBeDisabled()
  finish(localReport); await screen.findByRole('region', { name: 'Import result' })
})
it('makes an unavailable catalog retryable and does not pretend upload succeeded', async () => {
  mocks.list.mockRejectedValue(Object.assign(new Error('private path'), { status: 503 })); mount()
  expect(await screen.findByRole('alert')).toHaveTextContent('Local data storage is unavailable')
  expect(screen.getByRole('button', { name: 'Import and check data' })).toBeDisabled()
  mocks.list.mockResolvedValue([]); await userEvent.click(screen.getByRole('button', { name: 'Refresh CSV imports' }))
  await screen.findByText('No CSV imports yet')
})

it('explains invalid symbols and inverted coverage before allowing import', async () => {
  mount(); await screen.findByText('No CSV imports yet'); await fill()
  fireEvent.change(screen.getByLabelText('Symbol'), { target: { value: '../../SPY' } })
  expect(screen.getByText(/Use letters, numbers/)).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Import and check data' })).toBeDisabled()
  fireEvent.change(screen.getByLabelText('Symbol'), { target: { value: 'SPY' } })
  fireEvent.change(screen.getByLabelText('Coverage ends'), { target: { value: '2026-10-18' } })
  expect(screen.getByText('Coverage end must be on or after its start.')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Import and check data' })).toBeDisabled()
})
it('refuses invalid UTF-8 locally without submitting replaced bytes', async () => {
  mount(); await screen.findByText('No CSV imports yet'); await fill()
  fireEvent.change(screen.getByLabelText('Daily OHLCV CSV'), { target: { files: [new File([new Uint8Array([255])], 'bad.csv')] } })
  await userEvent.click(screen.getByRole('button', { name: 'Import and check data' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('Check the CSV header and import details')
  expect(mocks.import).not.toHaveBeenCalled()
})
it('uses the existing Chinese preference for the ordinary data action', async () => {
  localStorage.setItem('quantmesh.preferences', JSON.stringify({ locale: 'zh-CN', theme: 'dark' }))
  mount(); await screen.findByText('尚未导入 CSV')
  expect(screen.getByLabelText('日线 OHLCV CSV')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: '导入并检查数据' })).toBeDisabled()
})
