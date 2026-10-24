import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { localCsvApi } from './local-csv-api'
import { localReport } from '@/test/local-csv-fixture'
const fetchMock = vi.fn()
beforeEach(() => { vi.stubGlobal('fetch', fetchMock); fetchMock.mockReset() })
afterEach(() => vi.unstubAllGlobals())
const json = (value: unknown, status = 200) => new Response(JSON.stringify(value), { status, headers: { 'content-type': 'application/json' } })
it('uses the generated path and same-origin bounded transport for a catalog read', async () => {
  fetchMock.mockResolvedValue(json({ schema_version: 1, snapshots: [localReport] }))
  expect(await localCsvApi.list()).toHaveLength(1)
  expect(fetchMock.mock.calls[0][0].url).toContain('/api/research/data-snapshots/local-csv')
  expect(fetchMock.mock.calls[0][1]).toMatchObject({ credentials: 'same-origin', redirect: 'error', mode: 'same-origin' })
})
it('rejects an unsafe identifier before any network request', async () => {
  await expect(localCsvApi.get('../other')).rejects.toMatchObject({ message: 'invalid_response' })
  expect(fetchMock).not.toHaveBeenCalled()
})
it('rejects a report belonging to another saved import', async () => {
  fetchMock.mockResolvedValue(json(localReport))
  await expect(localCsvApi.get('f'.repeat(64))).rejects.toMatchObject({ message: 'invalid_response' })
})
it.each([
  { ...localReport, coverage: { ...localReport.coverage, missing_sessions: null } },
  { ...localReport, source: { ...localReport.source, provider: {} } },
  { ...localReport, qualification: { ...localReport.qualification, status: 'AVAILABLE' } },
  { ...localReport, next_action: { ...localReport.next_action, submission_allowed: true } },
])('refuses malformed or upgraded report data rather than rendering success', async value => {
  fetchMock.mockResolvedValue(json({ schema_version: 1, snapshots: [value] }))
  await expect(localCsvApi.list()).rejects.toMatchObject({ message: 'invalid_response' })
})
it('preserves a safe HTTP error status without leaking raw response detail', async () => {
  fetchMock.mockResolvedValue(json({ detail: 'private traceback' }, 409))
  await expect(localCsvApi.get(localReport.snapshot_id)).rejects.toMatchObject({ status: 409, message: 'local_csv_request_failed' })
})
it('rejects a planning reference that changes identity or submission authority', async () => {
  fetchMock.mockResolvedValue(json({ schema_version: 1, snapshot_id: 'f'.repeat(64), eligibility: { status: 'BLOCKED', reasons: [] }, intended_use: 'local_protocol_planning_only', runner_status: 'blocked_unqualified_input', dataset_ref: localReport.dataset_ref }))
  await expect(localCsvApi.reference(localReport.snapshot_id)).rejects.toMatchObject({ message: 'invalid_response' })
})
