import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, expect, it, vi } from 'vitest'
import { PreferencesProvider } from '@/lib/preferences'
import { LocalCsvPlanning } from './LocalCsvPlanning'
import { actualReferenceEligibility, localReport } from '@/test/local-csv-fixture'
const mocks = vi.hoisted(() => ({ reference: vi.fn(), get: vi.fn() }))
const { reference } = mocks
vi.mock('@/lib/local-csv-api', async original => ({ ...await original<typeof import('@/lib/local-csv-api')>(), localCsvApi: mocks }))
const id = localReport.snapshot_id
const data = { schema_version: 1, snapshot_id: id, dataset_ref: localReport.dataset_ref, manifest: null, normalized_csv: null,
  eligibility: { status: 'BLOCKED', reasons: ['Historical availability remains unknown'] }, evidence: {},
  intended_use: 'local_protocol_planning_only', runner_status: 'blocked_unqualified_input' }
beforeEach(() => { localStorage.clear(); vi.clearAllMocks(); reference.mockResolvedValue(data); mocks.get.mockResolvedValue(localReport) })
it('revalidates the chosen reference and keeps it out of fixture submission', async () => {
  render(<PreferencesProvider><LocalCsvPlanning snapshotId={id} /></PreferencesProvider>)
  expect(await screen.findByRole('heading', { name: localReport.label })).toBeInTheDocument()
  expect(reference).toHaveBeenCalledWith(id)
  expect(within(screen.getByRole('region', { name: 'Selected data and qualification' })).getByText('Historical availability remains unknown')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Download protocol draft' })).toBeDisabled()
  await userEvent.type(screen.getByLabelText('Research question'), 'Does this hypothesis survive realistic costs?')
  expect(screen.getByRole('button', { name: 'Download protocol draft' })).toBeEnabled()
  expect(screen.queryByRole('button', { name: 'Submit fixture job' })).not.toBeInTheDocument()
})
it('shows an unavailable reference with an import recovery link', async () => {
  reference.mockRejectedValue(new Error('private path'))
  render(<PreferencesProvider><LocalCsvPlanning snapshotId={id} /></PreferencesProvider>)
  expect(await screen.findByRole('alert')).toHaveTextContent('The data reference could not be verified')
  expect(screen.getByRole('link', { name: 'Return to my CSV data' })).toHaveAttribute('href', '/app/research/data-readiness?format=csv')
  expect(screen.queryByRole('button', { name: 'Download protocol draft' })).not.toBeInTheDocument()
  expect(screen.queryByText('private path')).not.toBeInTheDocument()
})

it('keeps internal evidence wording and digest identity outside the primary planning flow', async () => {
  const raw = 'Optional Phase1 preauthorization/post-review/source-evidence digests are retained claims, not independently verified receipts.'
  reference.mockResolvedValue({ ...data, eligibility: { status: 'BLOCKED', reasons: [raw] } })
  render(<PreferencesProvider><LocalCsvPlanning snapshotId={id} /></PreferencesProvider>)
  expect(await screen.findByRole('heading', { name: localReport.label })).toBeInTheDocument()
  expect(screen.getByText('Supplied evidence references have not been independently verified.')).toBeVisible()
  expect(screen.getByText(raw)).not.toBeVisible()
})
it('refuses to plan when the report and reference disagree on the chosen data', async () => {
  reference.mockResolvedValue({ ...data, dataset_ref: { ...data.dataset_ref, export_digest: 'f'.repeat(64) } })
  render(<PreferencesProvider><LocalCsvPlanning snapshotId={id} /></PreferencesProvider>)
  expect(await screen.findByRole('alert')).toHaveTextContent('The data reference could not be verified')
  expect(screen.queryByRole('button', { name: 'Download protocol draft' })).not.toBeInTheDocument()
})

it('explains the actual reference vocabulary without putting internal preauthorization text in the primary flow', async () => {
  reference.mockResolvedValue({ ...data, eligibility: actualReferenceEligibility })
  render(<PreferencesProvider><LocalCsvPlanning snapshotId={id} /></PreferencesProvider>)
  await screen.findByRole('heading', { name: localReport.label })
  const primary = screen.getByRole('region', { name: 'Selected data and qualification' })
  expect(within(primary).queryByText(/Phase1 preauthorization/)).not.toBeInTheDocument()
  expect(within(primary).getByText('Supplied evidence references have not been independently verified.')).toBeVisible()
})
