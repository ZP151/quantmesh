import { createHash, webcrypto } from 'node:crypto'
import { fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import recoveryOriginal from './fixtures/native-daily-recovery-decision-v1.json'
import { NativeDailyPanel } from './NativeDailyPanel'
import { nativeDailyApi } from '@/lib/native-daily-api'

const preferences = vi.hoisted(() => ({ locale: 'en' }))
vi.mock('@/lib/preferences', () => ({ usePreferences: () => preferences }))
const prefix = '/api/research/native-daily'
const safety = { financial_qualification: 'INSUFFICIENT', paper_allowed: false, live_allowed: false }
const request = { candidate: 'doublema_daily_overlay_candidate_v1', package_ref: null, grant_ref: null, approved_scope_ref: null, protocol_ref: null }
const canonical = (v: unknown): string => v && typeof v === 'object' ? Array.isArray(v) ? `[${v.map(canonical).join(',')}]` : `{${Object.entries(v).sort(([a], [b]) => a.localeCompare(b)).map(([k, x]) => `${JSON.stringify(k)}:${canonical(x)}`).join(',')}}` : JSON.stringify(v)
const sha = (raw: string) => createHash('sha256').update(raw).digest('hex')
const ref = (raw: string) => ({ algorithm: 'sha256', digest: sha(raw), byte_length: Buffer.byteLength(raw), media_type: 'application/json' })
const uuid = (n: number) => `${n.toString(16).padStart(8, '0')}-0000-4000-8000-000000000000`
let originals: Record<string, Record<string, string>>
function insufficient(id: string, decided = false) {
  const admission = JSON.stringify({ schema_id: 'qm.native-daily.admission.v1', job_id: id, request, request_digest: sha(canonical(request)), status: 'INSUFFICIENT', reasons: ['package_missing'], ...safety })
  const decision = JSON.stringify({ schema_id: 'qm.native-daily.research-decision.v1', job_id: id, request_digest: sha(canonical(request)), decision_key: uuid(99), admission_digest: sha(admission), report_digest: null, disposition: 'watch', reason: 'Await original input.', ...safety })
  originals[id] = { admission, ...(decided ? { decision } : {}) }
  return { job_id: id, request, request_digest: sha(canonical(request)), state: 'not_run', admission_status: 'INSUFFICIENT', admission_reasons: ['package_missing'], admission: ref(admission), report: null, decision: decided ? ref(decision) : null, trial_consumed: false, created_at: '2026-11-11T00:00:00Z', completed_at: '2026-11-11T00:00:00Z', ...safety }
}
const options = { configured: true, candidate: request.candidate, kernel: 'native-daily-v2', packages: [], grants: [], real_input_enabled: false, ...safety }
const fetcher = vi.fn()
let collection: unknown, listStatus: number
let records: Record<string, unknown>
function json(value: unknown, status = 200) { return new Response(JSON.stringify(value), { status }) }
function posts() { return fetcher.mock.calls.filter(([, init]) => init?.method && init.method !== 'GET') }
function region() { return screen.getByRole('region', { name: 'Saved studies' }) }
function openRow(id: string) { return within(region()).getByRole('button', { name: `Open saved study ${id}` }) }
beforeEach(() => {
  preferences.locale = 'en'; localStorage.clear()
  history.replaceState(null, '', '/app/research/jobs?engine=native-daily-v2')
  vi.stubGlobal('crypto', { subtle: webcrypto.subtle, randomUUID: vi.fn(() => { throw new Error('No new study permitted') }) })
  originals = { [recoveryOriginal.job.job_id]: recoveryOriginal.artifacts }
  const first = insufficient(uuid(3)), second = insufficient(uuid(4), true)
  records = { [first.job_id]: first, [second.job_id]: second, [recoveryOriginal.job.job_id]: recoveryOriginal.job }
  collection = { jobs: [first, second, recoveryOriginal.job] }; listStatus = 200
  fetcher.mockReset().mockImplementation(async (url: string) => {
    if (url === `${prefix}/options`) return json(options)
    if (url === `${prefix}/jobs`) return json(collection, listStatus)
    const match = url.match(/jobs\/([^/?]+)(?:\/artifact\?kind=(admission|report|decision))?$/)
    if (!match) throw new Error(`Unexpected request ${url}`)
    if (match[2]) {
      const raw = originals[match[1]][match[2]]
      return new Response(raw, { headers: { 'X-Content-SHA256': sha(raw), 'Content-Length': String(Buffer.byteLength(raw)) } })
    }
    return json(records[match[1]])
  })
  vi.stubGlobal('fetch', fetcher)
})
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); vi.useRealTimers() })

it('lists three archived originals without browser retention and opens each exact ID without submitting', async () => {
  render(<NativeDailyPanel />)
  await screen.findByRole('button', { name: `Open saved study ${uuid(3)}` })
  expect(within(region()).getAllByRole('button', { name: /Open saved study/ })).toHaveLength(3)
  expect(within(region()).getByText('Report ready · Retrospective research admitted, financial evidence still insufficient')).toBeVisible()
  expect(location.search).not.toContain('native_job=')
  expect(localStorage.getItem('quantmesh.native-daily.v1')).toBeNull()
  fireEvent.click(openRow(uuid(3)))
  await screen.findByRole('button', { name: 'Download admission' })
  expect(screen.getByLabelText('Saved study ID')).toHaveValue(uuid(3))
  fireEvent.click(openRow(uuid(4)))
  await screen.findByText('Watch · Original reason: Await original input.')
  expect(screen.getByLabelText('Saved study ID')).toHaveValue(uuid(4))
  fireEvent.click(openRow(recoveryOriginal.job.job_id))
  await screen.findByRole('button', { name: 'Download report' })
  await screen.findByRole('button', { name: 'Download decision' })
  expect(screen.getByLabelText('Saved study ID')).toHaveValue(recoveryOriginal.job.job_id)
  expect(location.search).toContain(`native_job=${recoveryOriginal.job.job_id}`)
  const saved = await nativeDailyApi.get(recoveryOriginal.job.job_id)
  for (const kind of ['admission', 'report', 'decision'] as const) {
    const artifact = await nativeDailyApi.artifact(saved, kind)
    expect(new TextDecoder().decode(artifact.bytes)).toBe(recoveryOriginal.artifacts[kind])
    expect(artifact.digest).toBe(saved[kind]?.digest)
  }
  expect(posts()).toHaveLength(0)
  expect(crypto.randomUUID).not.toHaveBeenCalled()
})

it('shows configured empty separately from unavailable and never describes unused authority', async () => {
  collection = { jobs: [] }
  render(<NativeDailyPanel />)
  expect(await screen.findByText('No saved studies in this configured store.')).toBeVisible()
  expect(within(region()).getByText(/does not describe capture or research-trial usage/)).toBeVisible()
  expect(within(region()).queryByRole('button', { name: /Open saved study/ })).not.toBeInTheDocument()
  expect(posts()).toHaveLength(0)
})

it.each([[503, 'service_unavailable', 'Saved studies are unavailable.'], [409, 'artifact_invalid', 'Saved study originals could not be verified.']])('keeps HTTP %s visible as a list failure rather than empty success', async (status, detail, label) => {
  collection = { detail }; listStatus = Number(status)
  render(<NativeDailyPanel />)
  expect(await screen.findByText(label)).toBeVisible()
  expect(screen.queryByText('No saved studies in this configured store.')).not.toBeInTheDocument()
  expect(within(region()).getByRole('button', { name: 'Refresh saved studies' })).toBeEnabled()
  expect(posts()).toHaveLength(0)
})

it.each(['shape', 'extra', 'duplicate', 'oversize', 'job_digest'])('rejects %s collection atomically through the existing strict job boundary', async defect => {
  const valid = (collection as { jobs: unknown[] }).jobs
  if (defect === 'shape') collection = { jobs: null }
  if (defect === 'extra') collection = { jobs: valid, authority: true }
  if (defect === 'duplicate') collection = { jobs: [valid[0], valid[0]] }
  if (defect === 'oversize') collection = { jobs: Array.from({ length: 33 }, (_, i) => insufficient(uuid(i + 100))) }
  if (defect === 'job_digest') collection = { jobs: [valid[0], { ...(valid[1] as object), request_digest: 'f'.repeat(64) }] }
  await expect(nativeDailyApi.savedStudies()).rejects.toMatchObject({ code: 'invalid_response' })
  expect(posts()).toHaveLength(0)
})

it('accepts all 32 verified records and preserves the frozen server order', async () => {
  const jobs = Array.from({ length: 32 }, (_, i) => insufficient(uuid(i + 100)))
  collection = { jobs }
  const saved = await nativeDailyApi.savedStudies()
  expect(saved.map(row => row.job_id)).toEqual(jobs.map(row => row.job_id))
  expect(posts()).toHaveLength(0)
})

it('does not automatically replace a deep-linked study when the archive refreshes or fails', async () => {
  history.replaceState(null, '', `/app/research/jobs?engine=native-daily-v2&native_job=${uuid(3)}`)
  render(<NativeDailyPanel />)
  await screen.findByRole('button', { name: 'Download admission' })
  await screen.findByRole('button', { name: `Open saved study ${uuid(4)}` })
  collection = { detail: 'artifact_invalid' }; listStatus = 409
  fireEvent.click(within(region()).getByRole('button', { name: 'Refresh saved studies' }))
  await screen.findByText('Saved study originals could not be verified.')
  expect(screen.getByLabelText('Saved study ID')).toHaveValue(uuid(3))
  expect(screen.getByRole('button', { name: 'Download admission' })).toBeEnabled()
  expect(location.search).toContain(uuid(3))
  expect(posts()).toHaveLength(0)
})

it('renders Chinese list controls with original full IDs and qualification labels', async () => {
  preferences.locale = 'zh-CN'
  render(<NativeDailyPanel />)
  const archive = await screen.findByRole('region', { name: '已保存研究' })
  expect(await within(archive).findByRole('button', { name: `打开已保存研究 ${uuid(3)}` })).toBeEnabled()
  expect(within(archive).getByRole('button', { name: '刷新研究档案' })).toBeEnabled()
  expect(within(archive).getByText(recoveryOriginal.job.job_id)).toBeVisible()
  expect(within(archive).getByText('报告已就绪 · 回溯研究已准入，金融证据仍不足')).toBeVisible()
  const row = within(archive).getByText(recoveryOriginal.job.job_id).closest('li')!
  const raw = within(row).getByText('succeeded · ACCEPTED_DECLARED_RESEARCH')
  expect(raw).not.toBeVisible()
  fireEvent.click(within(row).getByText('原始证据'))
  expect(raw).toBeVisible()
  expect(within(row).getByText(/2026.*UTC/)).toBeVisible()
  expect(posts()).toHaveLength(0)
})


it('reveals the existing evidence section after an explicit archive selection', async () => {
  render(<NativeDailyPanel />)
  await screen.findByRole('button', { name: `Open saved study ${uuid(3)}` })
  fireEvent.click(openRow(uuid(3)))
  await screen.findByRole('button', { name: 'Download admission' })
  expect(screen.getByRole('region', { name: 'Study evidence' })).toHaveFocus()
  expect(posts()).toHaveLength(0)
})
