import { createHash, webcrypto } from 'node:crypto'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'

const preferences = vi.hoisted(() => ({ locale: 'en' }))
vi.mock('@/lib/preferences', () => ({ usePreferences: () => preferences }))
const key = '11111111-1111-4111-8111-111111111111'
const decisionKey = '22222222-2222-4222-8222-222222222222'
const storage = 'quantmesh.native-daily.v1'
const request = { candidate: 'doublema_daily_overlay_candidate_v1', package_ref: null, grant_ref: null, approved_scope_ref: null, protocol_ref: null }
const canonical = (v: unknown): string => v && typeof v === 'object' ? Array.isArray(v) ? `[${v.map(canonical).join(',')}]` : `{${Object.entries(v).sort(([a], [b]) => a.localeCompare(b)).map(([k, x]) => `${JSON.stringify(k)}:${canonical(x)}`).join(',')}}` : JSON.stringify(v)
const sha = (v: string) => createHash('sha256').update(v).digest('hex')
const objectRef = (raw: string) => ({ algorithm: 'sha256', digest: sha(raw), byte_length: Buffer.byteLength(raw), media_type: 'application/json' })
const safety = { financial_qualification: 'INSUFFICIENT', paper_allowed: false, live_allowed: false }
const artifacts: Record<string, string> = {}
let options: Record<string, unknown>
let current: Record<string, unknown>
const fetcher = vi.fn()
function makeJob(body: unknown = request, engineering = false) {
  const request_digest = sha(canonical(body))
  const admission = { schema_id: 'qm.native-daily.admission.v1', job_id: key, request: body, request_digest, status: engineering ? 'ACCEPTED_ENGINEERING' : 'INSUFFICIENT', reasons: engineering ? ['engineering_fixture_only'] : ['package_missing', 'candidate_grant_missing'], ...safety }
  artifacts.admission = JSON.stringify(admission)
  return { job_id: key, request: body, request_digest, state: 'not_run', admission_status: admission.status, admission: objectRef(artifacts.admission), report: null, decision: null, trial_consumed: false, created_at: '2026-10-30T00:00:00Z', completed_at: '2026-10-30T00:00:00Z', admission_reasons: admission.reasons, ...safety }
}
function response(value: unknown, status = 200) { return new Response(JSON.stringify(value), { status }) }
async function mount() { const Panel = (await import('./NativeDailyPanel')).NativeDailyPanel; return render(<Panel />) }
function posts() { return fetcher.mock.calls.filter(([, init]) => init?.method === 'POST') }
async function submit() { fireEvent.click(await screen.findByRole('button', { name: 'Save insufficient evidence' })); await screen.findByRole('button', { name: 'Download admission' }) }
beforeEach(() => {
  preferences.locale = 'en'
  localStorage.clear()
  history.replaceState(null, '', '/app/research/jobs?engine=native-daily-v2')
  vi.stubGlobal('crypto', { subtle: webcrypto.subtle, randomUUID: vi.fn().mockReturnValueOnce(key).mockReturnValue(decisionKey) })
  options = { configured: true, candidate: request.candidate, kernel: 'native-daily-v2', packages: [], grants: [], real_input_enabled: false, ...safety }
  current = makeJob()
  fetcher.mockReset().mockImplementation(async (url: string, init?: RequestInit) => {
    if (url.endsWith('/options')) return response(options)
    if (url.includes('/artifact?kind=')) { const kind = url.split('kind=')[1]; return new Response(artifacts[kind], { headers: { 'X-Content-SHA256': sha(artifacts[kind]) } }) }
    if (url.endsWith('/decision') && init?.method === 'POST') {
      const body = JSON.parse(String(init.body))
      artifacts.decision = JSON.stringify({ schema_id: 'qm.native-daily.research-decision.v1', job_id: key, decision_key: decisionKey, ...body, ...safety })
      current = { ...current, decision: objectRef(artifacts.decision) }
    }
    return response(current)
  })
  vi.stubGlobal('fetch', fetcher)
})
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals() })

it('saves visible insufficient evidence and cold reopens the same ID without a POST', async () => {
  const view = await mount()
  await submit()
  expect(screen.getByText('No report was calculated. No trial was consumed.')).toBeVisible()
  expect(screen.getByText('Package missing')).toBeVisible()
  expect(screen.getByRole('button', { name: 'Download admission' })).toBeVisible()
  expect(posts()).toHaveLength(1)
  view.unmount()
  options = { ...options, packages: [], grants: [] }
  await mount()
  await screen.findByText('Not run · evidence insufficient')
  expect(screen.getByLabelText('Saved study ID')).toHaveValue(key)
  expect(posts()).toHaveLength(1)
  expect(location.search).toContain(`native_job=${key}`)
})

it('requires configured durable storage and does not send an ephemeral submission', async () => {
  options.configured = false
  await mount()
  expect(await screen.findByText('Durable research storage is unavailable. Existing IDs can still be reopened.')).toBeVisible()
  expect(screen.queryByRole('button', { name: 'Save insufficient evidence' })).not.toBeInTheDocument()
  expect(posts()).toHaveLength(0)
})

it('persists the UUID and exact request before sending and retries an uncertain POST with the same key', async () => {
  const original = fetcher.getMockImplementation()!
  let first = true
  fetcher.mockImplementation(async (url: string, init?: RequestInit) => {
    if (url.endsWith('/jobs') && init?.method === 'POST') {
      const saved = JSON.parse(localStorage.getItem(`${storage}.${key}`) ?? 'null')
      expect(saved.key).toBe(key)
      expect(saved.request).toEqual(JSON.parse(String(init.body)))
      if (first) { first = false; throw new Error('lost acknowledgement') }
    }
    return original(url, init)
  })
  await mount()
  fireEvent.click(await screen.findByRole('button', { name: 'Save insufficient evidence' }))
  fireEvent.click(await screen.findByRole('button', { name: 'Retry saved submission' }))
  await screen.findByText('Not run · evidence insufficient')
  expect(posts()).toHaveLength(2)
  expect(posts().map(([, init]) => (init.headers as Record<string, string>)['Idempotency-Key'])).toEqual([key, key])
})

it('refuses to submit when the browser cannot retain its intent', async () => {
  vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('full') })
  await mount()
  fireEvent.click(await screen.findByRole('button', { name: 'Save insufficient evidence' }))
  expect(await screen.findByText('The browser could not retain this request. No submission was sent.')).toBeVisible()
  expect(posts()).toHaveLength(0)
})

it('records Watch against original admission with a null report and reopens the immutable decision', async () => {
  const view = await mount()
  await submit()
  fireEvent.change(screen.getByLabelText('Reason'), { target: { value: 'Await a separately approved package.' } })
  fireEvent.click(screen.getByRole('button', { name: 'Watch' }))
  fireEvent.click(screen.getByRole('button', { name: 'Save research decision' }))
  expect(await screen.findByText('Watch · Await a separately approved package.')).toBeVisible()
  const [, init] = posts()[1]
  expect(JSON.parse(String(init.body))).toEqual({ request_digest: current.request_digest, admission_digest: objectRef(artifacts.admission).digest, report_digest: null, disposition: 'watch', reason: 'Await a separately approved package.' })
  view.unmount()
  await mount()
  expect(await screen.findByText('Watch · Await a separately approved package.')).toBeVisible()
  expect(screen.getByRole('button', { name: 'Download decision' })).toBeVisible()
  expect(posts()).toHaveLength(2)
})

it('fails closed on tampered admission bytes and does not offer decisions or downloads', async () => {
  current = { ...current, admission: { ...objectRef(artifacts.admission), digest: 'f'.repeat(64) } }
  await mount()
  fireEvent.click(await screen.findByRole('button', { name: 'Save insufficient evidence' }))
  expect(await screen.findByText('Original evidence could not be verified. Reopen this ID to try again.')).toBeVisible()
  expect(screen.queryByRole('button', { name: 'Download admission' })).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Save research decision' })).not.toBeInTheDocument()
})

it('rejects a correctly hashed artifact bound to a different job', async () => {
  artifacts.admission = JSON.stringify({ ...JSON.parse(artifacts.admission), job_id: decisionKey })
  current = { ...current, admission: objectRef(artifacts.admission) }
  await mount()
  fireEvent.click(await screen.findByRole('button', { name: 'Save insufficient evidence' }))
  expect(await screen.findByText('Original evidence could not be verified. Reopen this ID to try again.')).toBeVisible()
  expect(screen.queryByRole('button', { name: 'Download admission' })).not.toBeInTheDocument()
})

it('shows all five same-cost arms at both costs for a registered engineering substitute', async () => {
  const reference = objectRef('{}')
  const registered = { candidate: request.candidate, package_ref: reference, grant_ref: reference, approved_scope_ref: reference, protocol_ref: reference }
  options.packages = [{ label: 'Frozen engineering package', evidence_kind: 'engineering_fixture', package_ref: reference, approved_scope_ref: reference, protocol_ref: reference }]
  options.grants = [{ label: 'One engineering trial', package_digest: reference.digest, grant_ref: reference }]
  current = { ...makeJob(registered, true), state: 'succeeded', trial_consumed: true }
  const scenario = (bps: number) => Object.fromEntries(['T', 'TO', 'B50', 'B100', 'C'].map((arm, index) => {
    const binding = { schema_id: 'qm.native-daily.candidate.arm.v1', request_digest: reference.digest, arm, cost_bps: bps }
    return [arm, { binding, child_id: sha(canonical(binding)), metrics: { sessions: 21, terminal_equity: 100000 + index - bps, total_return: 0.01, max_drawdown: 0.02, friction_usd: bps, fills: 2 }, daily: [], trades: [], trace: [] }]
  }))
  artifacts.report = JSON.stringify({ schema_id: 'qm.native-daily.real-report.v1', job_id: key, request_digest: current.request_digest, protocol_ref: reference, package_ref: reference, grant_ref: reference, evidence_kind: 'engineering_fixture', calculation: { base5: scenario(5), stress10: scenario(10) }, ...safety })
  current = { ...current, report: objectRef(artifacts.report) }
  await mount()
  fireEvent.change(await screen.findByLabelText('Registered package'), { target: { value: reference.digest } })
  fireEvent.change(screen.getByLabelText('Candidate grant'), { target: { value: reference.digest } })
  fireEvent.click(screen.getByRole('button', { name: 'Submit fixed study' }))
  const table = await screen.findByRole('table', { name: 'Same-cost comparison' })
  for (const arm of ['T', 'TO', 'B50', 'B100', 'C']) expect(within(table).getByRole('rowheader', { name: arm })).toBeVisible()
  expect(within(table).getAllByText('$5.00')).toHaveLength(5)
  fireEvent.click(screen.getByRole('button', { name: '10 bps · stress' }))
  expect(within(table).getAllByText('$10.00')).toHaveLength(5)
  expect(screen.getByText('Engineering fixture only. Financial evidence remains INSUFFICIENT; Paper and live trading are unavailable.')).toBeVisible()
  expect(JSON.parse(String(posts()[0][1].body))).toEqual(registered)
})

it('reads the known ID while submission acknowledgement is unresolved', async () => {
  const original = fetcher.getMockImplementation()!
  fetcher.mockImplementation((url: string, init?: RequestInit) => url.endsWith('/jobs') && init?.method === 'POST' ? new Promise(() => {}) : original(url, init))
  await mount()
  fireEvent.click(await screen.findByRole('button', { name: 'Save insufficient evidence' }))
  fireEvent.click(await screen.findByRole('button', { name: 'Read saved study' }))
  await screen.findByText('Not run · evidence insufficient')
  await waitFor(() => expect(fetcher.mock.calls.some(([url, init]) => url.endsWith(`/jobs/${key}`) && !init?.method)).toBe(true))
  expect(posts()).toHaveLength(1)
})

it('uses the operator locale for input, safety and missing-evidence controls', async () => {
  preferences.locale = 'zh-CN'
  await mount()
  fireEvent.click(await screen.findByRole('button', { name: '保存证据不足记录' }))
  expect(await screen.findByText('未运行 · 证据不足')).toBeVisible()
  expect(await screen.findByText('未计算报告，未消耗试验额度。')).toBeVisible()
  expect(screen.getByRole('button', { name: '下载准入原件' })).toBeVisible()
})

it('can reopen after abandoning a terminal study with a pending read', async () => {
  await mount()
  await submit()
  let release: (value: Response) => void = () => {}
  const original = fetcher.getMockImplementation()!
  fetcher.mockImplementation((url: string, init?: RequestInit) => url.endsWith(`/jobs/${key}`) && !init?.method
    ? new Promise<Response>(resolve => { release = resolve }) : original(url, init))
  fireEvent.click(screen.getByRole('button', { name: 'Read saved study' }))
  await waitFor(() => expect(screen.getByRole('button', { name: 'Read saved study' })).toBeDisabled())
  fireEvent.click(screen.getByRole('button', { name: 'Start another study' }))
  fireEvent.change(screen.getByLabelText('Saved study ID'), { target: { value: key } })
  try {
    expect(screen.getByRole('button', { name: 'Open study' })).toBeEnabled()
  } finally { release(response(current)) }
})
