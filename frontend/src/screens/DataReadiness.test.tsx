import { fireEvent, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, expect, it, vi } from 'vitest'
import { PreferencesProvider } from '@/lib/preferences'
import { DataReadinessScreen } from './DataReadiness'

const mocks = vi.hoisted(() => ({ list: vi.fn(), import: vi.fn(), get: vi.fn(), download: vi.fn() }))
vi.mock('@/lib/realdata-api', async (original) => ({ ...await original<typeof import('@/lib/realdata-api')>(), realdataApi: mocks }))
const id = 'a'.repeat(64)
const historical = {
  schema_version: 1, snapshot_id: id, imported_at: '2026-10-19T00:00:00Z', symbol: 'SPY',
  evidence_kind: 'real_snapshot', report_digest: 'b'.repeat(64),
  source: { provider: 'Yahoo public chart', feed: 'vendor_daily_unverified', url: 'https://example.invalid/source',
    received_at: '2026-10-16T23:00:00Z', license_scope: 'local_research_unverified', license_evidence: null,
    price_unit: 'USD/share', volume_unit: 'shares', session_semantics: 'XNYS regular', pit_status: 'unknown' },
  coverage: { rows: 2965, first_date: '2015-01-02', last_date: '2026-10-16', expected_sessions: 2965,
    missing_sessions: [], unexpected_sessions: [] },
  freshness: { as_of: '2026-10-19T00:00:00Z', latest_complete_session: '2026-10-16', last_session: '2026-10-16',
    age_sessions: 0, status: 'CURRENT' },
  qualification: { status: 'INSUFFICIENT', structural_status: 'PASS', allowed_use: ['local_research_unverified'],
    R1: 'insufficient', R2: 'insufficient', reasons: ['Source rights are unverified', 'Point-in-time evidence is missing'] },
  checks: [{ code: 'distribution-conflict', status: 'INSUFFICIENT', count: 1, message: 'Issuer and Yahoo disagree',
    locations: [{ date: '2021-12-17', row: 42, field: 'dividend', expected: 'issuer value', actual: 'Yahoo value' }] }],
  corporate_actions: { issuer_events: 47, yahoo_events: 47, conflicts: ['2021-12-17: issuer and Yahoo conflict'] },
  lineage: { archive_sha256: id, normalized_sha256: 'c'.repeat(64), calendar_id: 'XNYS', calendar_version: 'pinned-test',
    checker_sha256: 'd'.repeat(64), files: [{ path: 'manifest.json', sha256: 'e'.repeat(64), bytes: 123 }] },
  preview: { head: [], tail: [] },
}
function mount() { return render(<PreferencesProvider><DataReadinessScreen /></PreferencesProvider>) }
beforeEach(() => {
  localStorage.clear(); vi.clearAllMocks(); window.history.replaceState(null, '', '/')
  mocks.list.mockResolvedValue([]); mocks.get.mockResolvedValue(historical); mocks.import.mockResolvedValue(historical)
})

it('shows loading followed by an honest empty local catalog', async () => {
  let finish!: (value: []) => void
  mocks.list.mockReturnValue(new Promise(resolve => { finish = resolve }))
  mount()
  expect(screen.getByRole('status')).toHaveTextContent('Loading snapshot history')
  finish([])
  await screen.findByText('No local snapshots imported')
  expect(screen.getByRole('button', { name: 'Import snapshot' })).toBeDisabled()
  expect(screen.queryByText('Available for research')).not.toBeInTheDocument()
})

it('shows unavailable storage with a retry and no enabled import', async () => {
  mocks.list.mockRejectedValue(Object.assign(new Error('secret traceback'), { status: 503, code: 'unavailable' }))
  mount()
  expect(await screen.findByRole('alert')).toHaveTextContent('Snapshot storage is unavailable')
  expect(screen.queryByText(/secret traceback/)).not.toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Import snapshot' })).toBeDisabled()
  mocks.list.mockResolvedValue([])
  await userEvent.click(screen.getByRole('button', { name: 'Refresh history' }))
  await screen.findByText('No local snapshots imported')
})

it('imports a local ZIP and exposes insufficiencies, locations, conflicts and lineage', async () => {
  const user = userEvent.setup(); mount()
  await screen.findByText('No local snapshots imported')
  const file = new File(['synthetic archive'], 'snapshot.zip', { type: 'application/zip' })
  await user.upload(screen.getByLabelText('Local SPY snapshot ZIP'), file)
  await user.click(screen.getByRole('button', { name: 'Import snapshot' }))
  const qualification = await screen.findByRole('region', { name: 'Qualification and allowed use' })
  expect(qualification).toHaveTextContent('Insufficient evidence')
  expect(qualification).toHaveTextContent('local_research_unverified')
  expect(qualification).toHaveTextContent('Point-in-time evidence is missing')
  expect(qualification).toHaveTextContent('Unknown / unavailable')
  expect(screen.getByText('Rows').nextElementSibling).toHaveTextContent('2,965')
  expect(screen.getByRole('table', { name: 'Located quality checks' })).toHaveTextContent('2021-12-17')
  expect(screen.getByRole('table', { name: 'Located quality checks' })).toHaveTextContent('dividend')
  expect(screen.getByText('2021-12-17: issuer and Yahoo conflict')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Download original ZIP' })).toBeEnabled()
  expect(screen.getByRole('button', { name: 'Download pinned report JSON' })).toBeEnabled()
  await user.click(screen.getByText('Immutable lineage'))
  expect(screen.getByText('manifest.json')).toBeInTheDocument()
})

it('reopens stored history through GET and uses the current recency overlay', async () => {
  mocks.list.mockResolvedValue([historical])
  mocks.get.mockResolvedValue({ ...historical, freshness: { ...historical.freshness, status: 'STALE', age_sessions: 3 } })
  const user = userEvent.setup(); mount()
  await user.click(await screen.findByRole('button', { name: /Reopen SPY/ }))
  expect(await screen.findByText('Stale')).toBeInTheDocument()
  expect(within(screen.getByRole('region', { name: 'Coverage and recency' })).getByText('3')).toBeInTheDocument()
})

it('retains the prior report and shows fixed errors after a failed import', async () => {
  mocks.list.mockResolvedValue([historical])
  const user = userEvent.setup(); mount()
  await user.click(await screen.findByRole('button', { name: /Reopen SPY/ }))
  await screen.findByRole('region', { name: 'Qualification and allowed use' })
  mocks.import.mockRejectedValue(Object.assign(new Error('payload secret'), { status: 422, code: 'invalid_archive' }))
  await user.upload(screen.getByLabelText('Local SPY snapshot ZIP'), new File(['bad'], 'bad.zip'))
  await user.click(screen.getByRole('button', { name: 'Import snapshot' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('Snapshot ZIP is invalid or unsupported')
  expect(screen.getByRole('region', { name: 'Qualification and allowed use' })).toBeInTheDocument()
  expect(screen.queryByText(/payload secret/)).not.toBeInTheDocument()
})

it('leaves unknown coverage values unavailable rather than fabricating zero', async () => {
  const unknown = { ...historical, coverage: { ...historical.coverage, rows: null, expected_sessions: null },
    freshness: { ...historical.freshness, status: 'INSUFFICIENT', age_sessions: null } }
  mocks.list.mockResolvedValue([unknown]); mocks.get.mockResolvedValue(unknown)
  mount(); await userEvent.click(await screen.findByRole('button', { name: /Reopen SPY/ }))
  const coverage = await screen.findByRole('region', { name: 'Coverage and recency' })
  expect(within(coverage).getAllByText('Unknown / unavailable')).toHaveLength(3)
})

it('translates the workflow with the existing Chinese preference', async () => {
  localStorage.setItem('quantmesh.preferences', JSON.stringify({ locale: 'zh-CN', theme: 'dark' }))
  mount()
  await screen.findByText('尚未导入本地快照')
  expect(screen.getByRole('heading', { name: '数据就绪检查' })).toBeInTheDocument()
  expect(screen.getByLabelText('本地 SPY 快照 ZIP')).toBeInTheDocument()
})

it('blocks oversized selection without submitting it', async () => {
  mount(); await screen.findByText('No local snapshots imported')
  const file = new File(['x'], 'too-big.zip')
  Object.defineProperty(file, 'size', { value: 8 * 1024 * 1024 + 1 })
  fireEvent.change(screen.getByLabelText('Local SPY snapshot ZIP'), { target: { files: [file] } })
  expect(await screen.findByRole('alert')).toHaveTextContent('8 MiB')
  expect(mocks.import).not.toHaveBeenCalled()
})

it('downloads original ZIP and pinned report separately and refuses a failed verification', async () => {
  const saved: string[] = []
  const createUrl = vi.fn(() => 'blob:verified')
  vi.stubGlobal('URL', class extends URL { static createObjectURL = createUrl; static revokeObjectURL = vi.fn() })
  const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (this: HTMLAnchorElement) { saved.push(this.download) })
  mocks.download.mockResolvedValue(new Blob(['verified test bytes']))
  mocks.list.mockResolvedValue([historical])
  const user = userEvent.setup(); mount()
  await user.click(await screen.findByRole('button', { name: /Reopen SPY/ }))
  await user.click(await screen.findByRole('button', { name: 'Download original ZIP' }))
  await user.click(screen.getByRole('button', { name: 'Download pinned report JSON' }))
  expect(saved).toEqual([`SPY-${id}.zip`, `SPY-${id}-report.json`])
  mocks.download.mockRejectedValue(Object.assign(new Error('raw secret'), { code: 'integrity' }))
  await user.click(screen.getByRole('button', { name: 'Download original ZIP' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('integrity verification')
  expect(saved).toHaveLength(2)
  click.mockRestore(); vi.unstubAllGlobals()
})

it('exposes import progress and prevents overlapping actions', async () => {
  let finish!: (value: typeof historical) => void
  mocks.import.mockReturnValue(new Promise(resolve => { finish = resolve }))
  const user = userEvent.setup(); mount()
  await screen.findByText('No local snapshots imported')
  await user.upload(screen.getByLabelText('Local SPY snapshot ZIP'), new File(['x'], 'snapshot.zip'))
  await user.click(screen.getByRole('button', { name: 'Import snapshot' }))
  expect(screen.getByRole('status')).toHaveTextContent('Importing and checking snapshot')
  expect(screen.getByRole('button', { name: 'Import snapshot' })).toBeDisabled()
  expect(screen.getByRole('button', { name: 'Refresh history' })).toBeDisabled()
  finish(historical)
  await screen.findByRole('region', { name: 'Qualification and allowed use' })
})

it('puts both original download actions in qualification before technical checks', async () => {
  mocks.list.mockResolvedValue([historical])
  mount(); await userEvent.click(await screen.findByRole('button', { name: /Reopen SPY/ }))
  const qualification = await screen.findByRole('region', { name: 'Qualification and allowed use' })
  const archive = within(qualification).getByRole('button', { name: 'Download original ZIP' })
  const report = within(qualification).getByRole('button', { name: 'Download pinned report JSON' })
  expect(archive).toBeEnabled(); expect(report).toBeEnabled()
  expect(qualification).toHaveTextContent('Downloads preserve original bytes and the initial report')
  const checks = screen.getByRole('heading', { name: 'Located quality checks' })
  expect(archive.compareDocumentPosition(checks) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  expect(report.compareDocumentPosition(checks) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  expect(qualification).toHaveTextContent('Source rights are unverified')
})

it('collapses only exact PASS checks while preserving all non-passing locations and reasons', async () => {
  const mixed = { ...historical, checks: [
    { ...historical.checks[0], code: 'bar_values', status: 'PASS', message: 'Passing value checks retained', count: 0, locations: [] },
    historical.checks[0],
    { ...historical.checks[0], code: 'rejected-check', status: 'REJECT', message: 'Rejected rows remain visible' },
  ] }
  mocks.list.mockResolvedValue([mixed]); mocks.get.mockResolvedValue(mixed)
  const user = userEvent.setup(); mount()
  await user.click(await screen.findByRole('button', { name: /Reopen SPY/ }))
  const summary = await screen.findByText('Passed technical checks (1)')
  const disclosure = summary.closest('details')!
  expect(disclosure).not.toHaveAttribute('open')
  expect(within(disclosure).getByText('Passing value checks retained')).not.toBeVisible()
  const primary = screen.getByRole('table', { name: 'Located quality checks' })
  expect(primary).toHaveTextContent('Issuer and Yahoo disagree')
  expect(primary).toHaveTextContent('Rejected rows remain visible')
  expect(primary).toHaveTextContent('2021-12-17')
  expect(primary).toHaveTextContent('issuer value')
  expect(primary).not.toHaveTextContent('Passing value checks retained')
  expect(screen.getByText('Point-in-time evidence is missing')).toBeVisible()
  await user.click(summary)
  expect(disclosure).toHaveAttribute('open')
  expect(within(disclosure).getByText('Passing value checks retained')).toBeVisible()
})

it('explains known use and PIT codes while preserving original and unknown evidence', async () => {
  const explained = { ...historical,
    qualification: { ...historical.qualification, allowed_use: ['inspect_evidence_only', 'future_scope_unverified'] },
    source: { ...historical.source, pit_status: 'historical_available_at_and_revision_history_unverified' },
  }
  mocks.list.mockResolvedValue([explained]); mocks.get.mockResolvedValue(explained)
  mount(); await userEvent.click(await screen.findByRole('button', { name: /Reopen SPY/ }))
  expect(await screen.findByText('Inspect evidence only')).toBeVisible()
  expect(screen.getByText('inspect_evidence_only')).toBeVisible()
  expect(screen.getByText('future_scope_unverified')).toBeVisible()
  expect(screen.getByText('Historical availability and revisions unverified')).toHaveAttribute('title', explained.source.pit_status)
  expect(screen.getByText('distribution-conflict')).toBeVisible()
  expect(screen.getByText('Issuer and Yahoo disagree')).toHaveAttribute('title', 'Issuer and Yahoo disagree')
})

it('keeps insufficient qualification explicit even when every technical check passes', async () => {
  const passing = { ...historical, checks: [{ ...historical.checks[0], status: 'PASS', code: 'bar_values', locations: [] }] }
  mocks.list.mockResolvedValue([passing]); mocks.get.mockResolvedValue(passing)
  mount(); await userEvent.click(await screen.findByRole('button', { name: /Reopen SPY/ }))
  expect(await screen.findByText('Passed technical checks (1)')).toBeVisible()
  expect(screen.getByText('All reported technical checks passed. Research qualification above still applies.')).toBeVisible()
  expect(screen.getByRole('region', { name: 'Qualification and allowed use' })).toHaveTextContent('Insufficient evidence')
  expect(screen.getByText('Source rights are unverified')).toBeVisible()
})

it('keeps missing technical checks unavailable rather than implying they passed', async () => {
  const missing = { ...historical, checks: [] }
  mocks.list.mockResolvedValue([missing]); mocks.get.mockResolvedValue(missing)
  mount(); await userEvent.click(await screen.findByRole('button', { name: /Reopen SPY/ }))
  await screen.findByRole('region', { name: 'Qualification and allowed use' })
  expect(screen.queryByText(/Passed technical checks/)).not.toBeInTheDocument()
  expect(screen.queryByText(/All reported technical checks passed/)).not.toBeInTheDocument()
  expect(screen.getByText('No checks reported')).toBeVisible()
})

it('localizes new explanations and disclosure without translating original evidence', async () => {
  localStorage.setItem('quantmesh.preferences', JSON.stringify({ locale: 'zh-CN', theme: 'dark' }))
  const localized = { ...historical, qualification: { ...historical.qualification, allowed_use: ['inspect_evidence_only'] },
    checks: [{ ...historical.checks[0], code: 'bar_values', status: 'PASS', message: 'Passing price checks retained', locations: [] }, historical.checks[0]] }
  mocks.list.mockResolvedValue([localized]); mocks.get.mockResolvedValue(localized)
  mount(); await userEvent.click(await screen.findByRole('button', { name: /重新打开 SPY/ }))
  expect(await screen.findByText('仅可检查证据')).toBeVisible()
  expect(screen.getByText('inspect_evidence_only')).toBeVisible()
  expect(screen.getByText('已通过的技术检查（1）')).toBeVisible()
  expect(screen.getByText('Issuer and Yahoo disagree')).toBeVisible()
})


it('offers a separate own-CSV workflow without relabeling the retained SPY archive', async () => {
  mount()
  const ownData = screen.getByRole('button', { name: 'My CSV data' })
  expect(ownData).toHaveAttribute('aria-pressed', 'false')
  await userEvent.click(ownData)
  expect(await screen.findByRole('heading', { name: 'Import your daily data' })).toBeInTheDocument()
  expect(screen.queryByLabelText('Local SPY snapshot ZIP')).not.toBeInTheDocument()
})
