import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, expect, it, vi } from 'vitest'
import { PreferencesProvider } from '@/lib/preferences'
import { LocalCsvPlanning } from './LocalCsvPlanning'
const reference = vi.hoisted(() => vi.fn())
vi.mock('@/lib/local-csv-api', async original => ({ ...await original<typeof import('@/lib/local-csv-api')>(), localCsvApi: { reference } }))
const id = 'a'.repeat(64)
const data = { schema_version: 1, snapshot_id: id, dataset_ref: { dataset_id: 'local-data', revision: 1,
  manifest_digest: 'b'.repeat(64), export_digest: 'c'.repeat(64), permission_class: 'local_research' }, manifest: null, normalized_csv: null,
  eligibility: { status: 'BLOCKED', reasons: ['Historical availability remains unknown'] }, evidence: {},
  intended_use: 'local_protocol_planning_only', runner_status: 'blocked_unqualified_input' }
beforeEach(() => { localStorage.clear(); vi.clearAllMocks(); reference.mockResolvedValue(data) })
it('revalidates the chosen reference and keeps it out of fixture submission', async () => {
  render(<PreferencesProvider><LocalCsvPlanning snapshotId={id} /></PreferencesProvider>)
  expect(await screen.findByText('local-data')).toBeInTheDocument()
  expect(reference).toHaveBeenCalledWith(id)
  expect(screen.getByText('Historical availability remains unknown')).toBeInTheDocument()
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
