import { createHash, webcrypto } from 'node:crypto'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'

const preferences = vi.hoisted(() => ({ locale: 'en' }))
vi.mock('@/lib/preferences', () => ({ usePreferences: () => preferences }))
let key = '11111111-1111-4111-8111-111111111111'
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

// Browser-only scripted originals, never actual provider/input authority.
function declaredDev(state: 'succeeded' | 'failed' | 'interrupted' | 'running' = 'failed') {
  vi.mocked(crypto.randomUUID).mockReset().mockReturnValue(decisionKey)
  const reference = objectRef('{}')
  const registered = { candidate: request.candidate, package_ref: reference, grant_ref: reference, approved_scope_ref: reference, protocol_ref: reference }
  const policy = objectRef('scripted-policy'); const authorization = objectRef('scripted-authorization')
  const basis = { scope_id: sha('scripted-ui-scope'), scope_trial_key: sha('scripted-ui-trial'), job_id: key, output_root_digest: sha('scripted-root'),
    proofs: { scope_ref: reference, effect_ref: reference, execution_ref: reference, windows_policy_ref: reference, go_ref: reference, acceptance_ref: reference, expected_go_sha256: reference.digest, expected_acceptance_sha256: reference.digest,
      capture_policy_ref: policy, authorization_ref: authorization, expected_policy_sha256: policy.digest, expected_authorization_sha256: authorization.digest },
    source_facts_ref: reference, capture_ref: reference, parent_close_ref: reference, source_use: 'private_diagnostic_internal_once_external_retention_unknown', provider_permission_verified: false, external_API_retention_applicability: 'UNKNOWN',
    diagnostic_mode: 'DEV_DIAGNOSTIC', policy_sha256: policy.digest, authorization_sha256: authorization.digest, hard_limit_enforced: false, provider_tail_max: 'UNKNOWN' }
  current = { ...makeJob(registered, true), state, completed_at: state === 'running' ? null : '2026-10-30T00:00:00Z', admission_status: 'ACCEPTED_DECLARED_RESEARCH', admission_reasons: [], trial_consumed: true }
  artifacts.admission = JSON.stringify({ ...JSON.parse(artifacts.admission), schema_id: 'qm.native-daily.admission.v2', status: 'ACCEPTED_DECLARED_RESEARCH', reasons: [], use_basis: basis })
  current = { ...current, admission: objectRef(artifacts.admission) }
  if (state === 'succeeded') {
    const scenario = (bps: number) => Object.fromEntries(['T', 'TO', 'B50', 'B100', 'C'].map(arm => {
      const binding = { schema_id: 'qm.native-daily.candidate.arm.v1', request_digest: reference.digest, arm, cost_bps: bps }
      return [arm, { binding, child_id: sha(canonical(binding)), metrics: { sessions: 21, terminal_equity: 100000, total_return: 0, max_drawdown: 0, friction_usd: bps, fills: 0 }, daily: [], trades: [], trace: [] }]
    }))
    artifacts.report = JSON.stringify({ schema_id: 'qm.native-daily.real-report.v2', job_id: key, request_digest: current.request_digest, protocol_ref: reference, package_ref: reference, grant_ref: reference, evidence_kind: 'reviewed_real', use_basis: basis,
      runtime_receipt: { schema_id: 'qm.ivv.numeric-close.v1', job_commit_bytes: 536870912, affinity: 1, process_affinity: 1, kernel_flags: 0x2210, child_membership_verified: true, returncode: 0, active_processes: 0, owned_fds_closed: true, wall_seconds: 0.1, code: { test: reference.digest } }, calculation: { base5: scenario(5), stress10: scenario(10) }, ...safety })
    current = { ...current, report: objectRef(artifacts.report) }
  }
  history.replaceState(null, '', `/app/research/jobs?engine=native-daily-v2&native_job=${key}`)
  return basis
}
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
  key = '11111111-1111-4111-8111-111111111111'
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
  expect(screen.getByText('No report was calculated. No research trial was consumed.')).toBeVisible()
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

it.each([{ forced: false, incompleteFirst: false, refusedFirst: false }, { forced: true, incompleteFirst: false, refusedFirst: false }, { forced: false, incompleteFirst: true, refusedFirst: false }, { forced: false, incompleteFirst: false, refusedFirst: true }])('requires normal closure and keeps designated identity for complete admission (%j)', async ({ forced, incompleteFirst, refusedFirst }) => {
  const reference = objectRef('{}')
  const registered = { candidate: request.candidate, package_ref: reference, grant_ref: reference, approved_scope_ref: reference, protocol_ref: reference }
  const basis = { scope_id: sha('scripted-ui-scope'), scope_trial_key: sha('scripted-ui-trial'), job_id: key, output_root_digest: sha('scripted-root'),
    proofs: { scope_ref: reference, effect_ref: reference, execution_ref: reference, windows_policy_ref: reference, go_ref: reference, acceptance_ref: reference, expected_go_sha256: reference.digest, expected_acceptance_sha256: reference.digest },
    source_facts_ref: reference, capture_ref: reference, parent_close_ref: reference, source_use: 'private_diagnostic_internal_once_external_retention_unknown', provider_permission_verified: false, external_API_retention_applicability: 'UNKNOWN' }
  options = { ...options, real_input_enabled: true,
    packages: [{ label: 'Scripted declared input', evidence_kind: 'reviewed_real', package_ref: reference, approved_scope_ref: reference, protocol_ref: reference, job_id: key }],
    grants: [{ label: 'Internal once only', package_digest: reference.digest, grant_ref: reference }] }
  current = { ...makeJob(registered, true), state: 'succeeded', admission_status: 'ACCEPTED_DECLARED_RESEARCH', trial_consumed: true }
  artifacts.admission = JSON.stringify({ ...JSON.parse(artifacts.admission), schema_id: 'qm.native-daily.admission.v2', status: 'ACCEPTED_DECLARED_RESEARCH', reasons: [], use_basis: basis })
  current = { ...current, admission: objectRef(artifacts.admission), admission_reasons: [] }
  const scenario = (bps: number) => Object.fromEntries(['T', 'TO', 'B50', 'B100', 'C'].map(arm => {
    const binding = { schema_id: 'qm.native-daily.candidate.arm.v1', request_digest: reference.digest, arm, cost_bps: bps }
    return [arm, { binding, child_id: sha(canonical(binding)), metrics: { sessions: 21, terminal_equity: 100000, total_return: 0, max_drawdown: 0, friction_usd: bps, fills: 0 }, daily: [], trades: [], trace: [] }]
  }))
  artifacts.report = JSON.stringify({ schema_id: 'qm.native-daily.real-report.v2', job_id: key, request_digest: current.request_digest, protocol_ref: reference, package_ref: reference, grant_ref: reference,
    evidence_kind: 'reviewed_real', use_basis: basis,
    runtime_receipt: { schema_id: 'qm.ivv.numeric-close.v1', job_commit_bytes: 536870912, affinity: 1, process_affinity: 1, kernel_flags: 0x2210, child_membership_verified: true, returncode: forced ? 1 : 0, active_processes: 0, owned_fds_closed: true, wall_seconds: 0.1, code: { test: reference.digest } },
    calculation: { base5: scenario(5), stress10: scenario(10) }, ...safety })
  current = { ...current, report: objectRef(artifacts.report) }
  if (forced) {
    const api = (await import('@/lib/native-daily-api')).nativeDailyApi
    await expect(api.artifact(await api.get(key), 'report')).rejects.toMatchObject({ code: 'artifact_invalid' })
    return
  }
  const ordinaryId = '33333333-3333-4333-8333-333333333333'
  const completeJob = current; const completeAdmission = artifacts.admission
  if (refusedFirst) {
    const original = fetcher.getMockImplementation()!; let first = true
    fetcher.mockImplementation((url: string, init?: RequestInit) => {
      if (url.endsWith('/jobs') && init?.method === 'POST' && first) {
        first = false; return Promise.resolve(response({ detail: 'study_not_admitted' }, 409))
      }
      return original(url, init)
    })
  }
  if (incompleteFirst) {
    vi.mocked(crypto.randomUUID).mockReset().mockReturnValue(ordinaryId)
    const original = fetcher.getMockImplementation()!
    fetcher.mockImplementation((url: string, init?: RequestInit) => {
      if (url.endsWith('/jobs') && init?.method === 'POST') {
        const body = JSON.parse(String(init.body))
        if (body.grant_ref === null) {
          current = { ...makeJob(body), job_id: ordinaryId }
          artifacts.admission = JSON.stringify({ ...JSON.parse(artifacts.admission), job_id: ordinaryId })
          current = { ...current, admission: objectRef(artifacts.admission) }
        }
      }
      return original(url, init)
    })
  }
  await mount()
  fireEvent.change(await screen.findByLabelText('Registered package'), { target: { value: reference.digest } })
  if (incompleteFirst) {
    fireEvent.click(screen.getByRole('button', { name: 'Save insufficient evidence' }))
    await waitFor(() => expect(posts()).toHaveLength(1))
    expect(posts()[0][1].headers['Idempotency-Key']).toBe(ordinaryId)
    await screen.findByText('Not run · evidence insufficient')
    fireEvent.click(screen.getByRole('button', { name: 'Return to study input' }))
    current = completeJob; artifacts.admission = completeAdmission
    fireEvent.change(await screen.findByLabelText('Registered package'), { target: { value: reference.digest } })
  }
  fireEvent.change(screen.getByLabelText('Candidate grant'), { target: { value: reference.digest } })
  fireEvent.click(screen.getByRole('button', { name: 'Submit fixed study' }))
  if (refusedFirst) {
    expect(await screen.findByRole('alert')).toHaveTextContent('Study was not admitted. No research trial was consumed; resolve admission checks and retry this saved request.')
    fireEvent.click(screen.getByRole('button', { name: 'Retry saved submission' }))
  }
  expect(await screen.findByText('Report ready · retrospective research')).toBeVisible()
  expect(await screen.findByRole('table', { name: 'Same-cost comparison' })).toBeVisible()
  expect(screen.getByText(/Private diagnostic once; external API retention applicability UNKNOWN/)).toBeVisible()
  expect(posts().at(-1)![1].headers['Idempotency-Key']).toBe(key)
  if (refusedFirst) expect(posts().map(([, init]) => init.headers['Idempotency-Key'])).toEqual([key, key])
  expect(crypto.randomUUID).toHaveBeenCalledTimes(incompleteFirst ? 1 : 0)
})

it('rejects real options without the fixed submission identity instead of relaxing input guards', async () => {
  const reference = objectRef('{}')
  options = { ...options, real_input_enabled: true,
    packages: [{ label: 'Bad real option', evidence_kind: 'reviewed_real', package_ref: reference, approved_scope_ref: reference, protocol_ref: reference }] }
  const api = (await import('@/lib/native-daily-api')).nativeDailyApi
  await expect(api.options()).rejects.toMatchObject({ code: 'invalid_response' })
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
  expect(await screen.findByText('未计算报告，未消耗研究计算试验额度。')).toBeVisible()
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
  fireEvent.click(screen.getByRole('button', { name: 'Return to study input' }))
  fireEvent.change(screen.getByLabelText('Saved study ID'), { target: { value: key } })
  try {
    expect(screen.getByRole('button', { name: 'Open study' })).toBeEnabled()
  } finally { release(response(current)) }
})

it.each(['succeeded', 'failed', 'interrupted'] as const)('shows verified DEV provenance for %s; cold reads and decisions retain originals', async state => {
  const basis = declaredDev(state)
  const view = await mount()
  expect(await screen.findByText('DEV_DIAGNOSTIC · capture policy exception')).toBeVisible()
  expect(screen.getByText(/Provider storage hard limit not enforced; provider tail maximum UNKNOWN/)).toBeVisible()
  expect(screen.getByText(/Diagnostic capture alone is unreviewed/)).toBeVisible()
  fireEvent.click(screen.getByText('Capture policy and authorization originals'))
  expect(screen.getByText(basis.policy_sha256)).toBeVisible()
  expect(screen.getByText(basis.authorization_sha256)).toBeVisible()
  expect(screen.queryByRole('button', { name: 'Submit fixed study' })).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Retry saved submission' })).not.toBeInTheDocument()
  if (state !== 'succeeded') {
    expect(screen.getByText(/The reserved research trial remains consumed/)).toBeVisible()
    expect(screen.queryByRole('table')).not.toBeInTheDocument()
  }
  fireEvent.change(screen.getByLabelText('Reason'), { target: { value: 'Await stronger independent evidence.' } })
  fireEvent.click(screen.getByRole('button', { name: 'Save research decision' }))
  expect(await screen.findByText('Watch · Await stronger independent evidence.')).toBeVisible()
  const sent = JSON.parse(String(posts()[0][1].body))
  expect(sent.admission_digest).toBe((current.admission as { digest: string }).digest)
  expect(sent.report_digest).toBe((current.report as { digest: string } | null)?.digest ?? null)
  view.unmount(); await mount()
  expect(await screen.findByText('DEV_DIAGNOSTIC · capture policy exception')).toBeVisible()
  expect(await screen.findByText('Watch · Await stronger independent evidence.')).toBeVisible()
  expect(posts()).toHaveLength(1) // decision only, no submission/recalculation
})

it('explains DEV guarantees in Chinese without authorizing Paper or live', async () => {
  preferences.locale = 'zh-CN'; declaredDev('failed')
  await mount()
  expect(await screen.findByText('DEV_DIAGNOSTIC · 采集政策例外')).toBeVisible()
  expect(screen.getByText(/未强制实施供应商存储硬上限/)).toBeVisible()
  expect(screen.getByText(/诊断采集原件本身仍未审核/)).toBeVisible()
  expect(posts()).toHaveLength(0)
})

it('explains why captured-unreviewed originals do not enable submission or computation', async () => {
  await mount()
  expect(await screen.findByText(/Captured originals remain unreviewed until independent input acceptance/)).toBeVisible()
  expect(screen.queryByRole('button', { name: 'Submit fixed study' })).not.toBeInTheDocument()
  expect(posts()).toHaveLength(0)
})

it('refuses a captured-unreviewed package advertised as selectable without treating its label as authority', async () => {
  const reference = objectRef('{}')
  options.packages = [{ label: 'DEV_DIAGNOSTIC captured originals', evidence_kind: 'CAPTURED_UNREVIEWED', package_ref: reference, approved_scope_ref: reference, protocol_ref: reference }]
  await mount()
  expect(await screen.findByText('The server response did not match the fixed study contract. Reopen the saved ID.')).toBeVisible()
  expect(screen.queryByRole('button', { name: 'Submit fixed study' })).not.toBeInTheDocument()
  expect(posts()).toHaveLength(0)
})

it.each(['policy_digest', 'authorization_ref', 'missing_mode', 'partial_proof', 'hard_limit', 'tail', 'unknown_mode'])('refuses malformed DEV provenance (%s) before exposing originals or decisions', async defect => {
  declaredDev()
  const admission = JSON.parse(artifacts.admission); const b = admission.use_basis
  if (defect === 'policy_digest') b.policy_sha256 = sha('wrong')
  if (defect === 'authorization_ref') b.proofs.authorization_ref = objectRef('wrong')
  if (defect === 'missing_mode') delete b.diagnostic_mode
  if (defect === 'partial_proof') delete b.proofs.expected_policy_sha256
  if (defect === 'hard_limit') b.hard_limit_enforced = true
  if (defect === 'tail') b.provider_tail_max = 33554432
  if (defect === 'unknown_mode') b.diagnostic_mode = 'QUALIFIED'
  artifacts.admission = JSON.stringify(admission); current = { ...current, admission: objectRef(artifacts.admission) }
  await mount()
  expect(await screen.findByText('Original evidence could not be verified. Reopen this ID to try again.')).toBeVisible()
  expect(screen.queryByRole('button', { name: 'Download admission' })).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Save research decision' })).not.toBeInTheDocument()
  expect(posts()).toHaveLength(0)
})

it('refuses individually valid DEV originals with mismatching policies before report/decision display', async () => {
  declaredDev('succeeded')
  const report = JSON.parse(artifacts.report); const other = objectRef('other-scripted-policy')
  report.use_basis.policy_sha256 = other.digest
  report.use_basis.proofs.capture_policy_ref = other
  report.use_basis.proofs.expected_policy_sha256 = other.digest
  artifacts.report = JSON.stringify(report); current = { ...current, report: objectRef(artifacts.report) }
  await mount()
  expect(await screen.findByText('Original evidence could not be verified. Reopen this ID to try again.')).toBeVisible()
  expect(screen.queryByRole('table')).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Save research decision' })).not.toBeInTheDocument()
  expect(posts()).toHaveLength(0)
})


it('keeps verified DEV source visible while running without offering a decision or report', async () => {
  declaredDev('running'); await mount()
  expect(await screen.findByText('DEV_DIAGNOSTIC · capture policy exception')).toBeVisible()
  expect(screen.getByText('Running · retrospective research')).toBeVisible()
  expect(screen.queryByRole('table')).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Save research decision' })).not.toBeInTheDocument()
  expect(posts()).toHaveLength(0)
})

it('does not infer capture-once usage from empty options or restore authority by returning to input', async () => {
  declaredDev('failed'); await mount()
  expect(await screen.findByText(/Capture-once usage: UNKNOWN on this page/)).toBeVisible()
  expect(screen.getByText(/read this ID instead of rerunning it/)).toBeVisible()
  fireEvent.click(screen.getByRole('button', { name: 'Return to study input' }))
  expect(await screen.findByText(/DEV capture and review status: UNKNOWN in this input list/)).toBeVisible()
  expect(screen.queryByRole('button', { name: 'Submit fixed study' })).not.toBeInTheDocument()
  expect(posts()).toHaveLength(0)
})


// Frozen public fragment: only authorization digest is a real schema discriminator.
// Every other reference is fictional UI evidence, not an input/GO/store object.
const trustedFragment = {
  "authorization_sha256": "3fede456cf8fff2e4ee29748fa6037617fe250d382c8b09474e1f6be4fe7e452",
  "channel_assurance": "UNVERIFIED_TRUSTED_EXTERNAL",
  "diagnostic_mode": "DEV_TRUSTED_ENVIRONMENT",
  "hard_limit_enforced": false,
  "policy_sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "proofs": {
    "authorization_ref": {
      "algorithm": "sha256",
      "byte_length": 3022,
      "digest": "3fede456cf8fff2e4ee29748fa6037617fe250d382c8b09474e1f6be4fe7e452",
      "media_type": "application/json"
    },
    "capture_policy_ref": {
      "algorithm": "sha256",
      "byte_length": 2,
      "digest": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
      "media_type": "application/json"
    },
    "expected_authorization_sha256": "3fede456cf8fff2e4ee29748fa6037617fe250d382c8b09474e1f6be4fe7e452",
    "expected_policy_sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
  },
  "provider_tail_max": "UNKNOWN"
} as const

function declaredTrusted(state: Parameters<typeof declaredDev>[0] = 'failed') {
  const original = declaredDev(state)
  const basis = { ...original, ...trustedFragment, proofs: { ...original.proofs, ...trustedFragment.proofs } }
  for (const kind of (state === 'succeeded' ? ['admission', 'report'] : ['admission'])) {
    artifacts[kind] = JSON.stringify({ ...JSON.parse(artifacts[kind]), use_basis: basis })
    current = { ...current, [kind]: objectRef(artifacts[kind]) }
  }
  return basis
}

it.each(['failed', 'interrupted', 'running', 'succeeded'] as const)('displays frozen DEV trusted-environment %s without downcasting; same-ID cold reads add no POST', async state => {
  const basis = declaredTrusted(state); const view = await mount()
  expect(await screen.findByText('DEV_TRUSTED_ENVIRONMENT · unverified external environment')).toBeVisible()
  expect(screen.getByText(/UNVERIFIED_TRUSTED_EXTERNAL/)).toBeVisible()
  expect(screen.getByText(/Provider storage hard limit not enforced; provider tail maximum UNKNOWN/)).toBeVisible()
  expect(screen.queryByText('DEV_DIAGNOSTIC · capture policy exception')).not.toBeInTheDocument()
  fireEvent.click(screen.getByText('Capture policy and authorization originals'))
  expect(screen.getByText(basis.policy_sha256)).toBeVisible()
  expect(screen.getByText(basis.authorization_sha256)).toBeVisible()
  if (state !== 'succeeded') expect(screen.queryByRole('table')).not.toBeInTheDocument()
  if (state === 'running') expect(screen.queryByRole('button', { name: 'Save research decision' })).not.toBeInTheDocument()
  if (state === 'failed' || state === 'interrupted') expect(screen.getByText(/The reserved research trial remains consumed/)).toBeVisible()
  view.unmount(); await mount()
  expect(await screen.findByText('DEV_TRUSTED_ENVIRONMENT · unverified external environment')).toBeVisible()
  expect(posts()).toHaveLength(0)
})

it('keeps trusted-external mode explicit in Chinese and a decision bound to the original admission', async () => {
  preferences.locale = 'zh-CN'; declaredTrusted()
  await mount()
  expect(await screen.findByText('DEV_TRUSTED_ENVIRONMENT · 外部环境未核验')).toBeVisible()
  expect(screen.getByText(/UNVERIFIED_TRUSTED_EXTERNAL/)).toBeVisible()
  expect(screen.getByText(/未强制实施供应商存储硬上限/)).toBeVisible()
  fireEvent.change(screen.getByLabelText('理由'), { target: { value: '离线UI替身；等待真实独立证据。' } })
  fireEvent.click(screen.getByRole('button', { name: '保存研究决定' }))
  expect(await screen.findByText('观察 · 离线UI替身；等待真实独立证据。')).toBeVisible()
  const sent = JSON.parse(String(posts()[0][1].body))
  expect(sent.admission_digest).toBe((current.admission as { digest: string }).digest)
  expect(sent.report_digest).toBeNull()
})

it.each(['missing_channel', 'wrong_channel', 'missing_mode', 'policy_digest', 'policy_pin', 'authorization_ref', 'wrong_authorization', 'hard_limit', 'known_tail', 'downcast_to_A', 'channel_only_strict', 'channel_on_A'])('refuses partial/mismatched/wrong-identity trusted fragment (%s)', async defect => {
  if (defect === 'channel_on_A') declaredDev(); else declaredTrusted()
  const raw = JSON.parse(artifacts.admission); const basis = raw.use_basis
  if (defect === 'missing_channel') delete basis.channel_assurance
  if (defect === 'wrong_channel') basis.channel_assurance = 'VERIFIED'
  if (defect === 'missing_mode') delete basis.diagnostic_mode
  if (defect === 'policy_digest') basis.policy_sha256 = sha('wrong')
  if (defect === 'policy_pin') basis.proofs.expected_policy_sha256 = sha('wrong')
  if (defect === 'authorization_ref') basis.proofs.authorization_ref = objectRef('wrong')
  if (defect === 'wrong_authorization') {
    const wrong = objectRef('A-or-other-authorization')
    basis.authorization_sha256 = wrong.digest; basis.proofs.authorization_ref = wrong; basis.proofs.expected_authorization_sha256 = wrong.digest
  }
  if (defect === 'hard_limit') basis.hard_limit_enforced = true
  if (defect === 'known_tail') basis.provider_tail_max = 0
  if (defect === 'downcast_to_A') { basis.diagnostic_mode = 'DEV_DIAGNOSTIC'; delete basis.channel_assurance }
  if (defect === 'channel_on_A') basis.channel_assurance = 'UNVERIFIED_TRUSTED_EXTERNAL'
  if (defect === 'channel_only_strict') {
    for (const name of ['diagnostic_mode', 'policy_sha256', 'authorization_sha256', 'hard_limit_enforced', 'provider_tail_max']) delete basis[name]
    for (const name of ['capture_policy_ref', 'authorization_ref', 'expected_policy_sha256', 'expected_authorization_sha256']) delete basis.proofs[name]
  }
  artifacts.admission = JSON.stringify(raw); current = { ...current, admission: objectRef(artifacts.admission) }
  const api = (await import('@/lib/native-daily-api')).nativeDailyApi
  await expect(api.artifact(await api.get(key), 'admission')).rejects.toMatchObject({ code: 'artifact_invalid' })
  expect(posts()).toHaveLength(0)
})

const additionalFragment = {
  "additional_task_id": "ivv-additional-20261103-01",
  "authorization_sha256": "595c2987fda4cc0275d785b91137b6e61824800888500e2f7c5a78ea7b5f5832",
  "capture_budget": {
    "business_requests": 7,
    "carrier_submissions": 1,
    "contexts": 1,
    "init_connect": 1,
    "keepalive": 96
  },
  "capture_effect_sha256": "a6681407439408a9d01baecedb3026f16f8e9513d601b2edd56910b0228eee17",
  "capture_once_key": "189ac10caf73ef7fd31fa01fb4691bb4b00f19a371cc7792330df60bc6d7ac2c",
  "capture_scope_id": "53badf05a10d955cc0826dccc592d1807bfbcfec8abcd4f9e3a194857e3d1858",
  "channel_assurance": "UNVERIFIED_TRUSTED_EXTERNAL",
  "descriptor_sha256": "06f192d60c76a95e91f150e4e4b867218f243759996442abeb58290f7faf6a25",
  "diagnostic_mode": "DEV_ADDITIONAL_TRUSTED_ENVIRONMENT",
  "hard_limit_enforced": false,
  "historical_actual_cumulative": "UNKNOWN",
  "legacy_capture_charge": {
    "business_requests": 7,
    "contexts": 1
  },
  "provider_tail_max": "UNKNOWN",
  "research_effect_sha256": "03cade7368127b1ed36425ff9f7334892aba51fbbf516376a65b4da992dabbda",
  "research_scope_id": "75bdbea142ca73c3c7964fd2fbcb7d2ded82aded73788c903a0d57d9528ebd0a"
} as const

function declaredAdditional(state: Parameters<typeof declaredDev>[0] = 'failed') {
  key = '1d05c58d-b536-4b64-b2c3-89e4217cc4ad'
  const original = declaredDev(state)
  const auth = { ...objectRef('{}'), digest: additionalFragment.authorization_sha256, byte_length: 7912 }
  const policy = { ...auth, digest: 'c784651ae76033a3a3695fad97d19d7721d7de5c28dc4a901408f101c6ae1e55', byte_length: 1547 }
  const descriptor = { ...auth, digest: '76944da09e615b0fec9c60a6ed7ea78d7fa364543684b4d4e5832618860dfa12', byte_length: 3300 }
  const windows = { ...auth, digest: '22f6cb798c94c436759f4ff85d16b6101010ae5e550e5e7d4dc155c71ca54179', byte_length: 949 }
  const basis = { ...original, ...additionalFragment, scope_id: additionalFragment.research_scope_id,
    scope_trial_key: sha(canonical({ execution: auth.digest, scope: additionalFragment.research_scope_id, trial: 1 })),
    policy_sha256: policy.digest, capture_usage_ref: original.capture_ref,
    capture_usage: { logical_state: 'SPENT', actual_contexts: 1, actual_business_requests: 7, actual_init_connect: 1, actual_keepalive: 2 },
    proofs: { ...original.proofs, scope_ref: descriptor, effect_ref: auth, execution_ref: auth, authorization_ref: auth, windows_policy_ref: windows,
      capture_policy_ref: policy, expected_policy_sha256: policy.digest, expected_authorization_sha256: auth.digest } }
  for (const kind of (state === 'succeeded' ? ['admission', 'report'] : ['admission'])) {
    artifacts[kind] = JSON.stringify({ ...JSON.parse(artifacts[kind]), use_basis: basis })
    current = { ...current, [kind]: objectRef(artifacts[kind]) }
  }
  return basis
}

it.each(['failed', 'interrupted', 'running', 'succeeded'] as const)('shows separate additional task and observed usage for %s, preserving cold-read no POST', async state => {
  declaredAdditional(state); const view = await mount()
  expect(await screen.findByText('Additional IVV task · unverified external environment')).toBeVisible()
  expect(screen.getByText(/Old task: UNKNOWN_LOCKED; nominal allowance consumed/)).toBeVisible()
  expect(screen.getByText(/Historical actual cumulative usage: UNKNOWN/)).toBeVisible()
  expect(screen.getByText(/This task limits: 1 carrier, 1 context, 7 business requests/)).toBeVisible()
  expect(screen.getByText(/Observed: 1 context, 7 business requests, 1 InitConnect, 2 KeepAlive/)).toBeVisible()
  expect(screen.queryByText(/Capture-once usage: UNKNOWN on this page/)).not.toBeInTheDocument()
  view.unmount(); await mount()
  expect(await screen.findByText('Additional IVV task · unverified external environment')).toBeVisible()
  expect(posts()).toHaveLength(0)
})

it('keeps additional-task limits and consumed state explicit in Chinese', async () => {
  preferences.locale = 'zh-CN'; declaredAdditional()
  await mount()
  expect(await screen.findByText('新增 IVV 任务 · 外部环境未核验')).toBeVisible()
  expect(screen.getByText(/历史实际累计使用量：UNKNOWN/)).toBeVisible()
  expect(screen.getByText(/实际观察：1 个 context、7 次业务请求、1 次 InitConnect、2 次 KeepAlive/)).toBeVisible()
  expect(posts()).toHaveLength(0)
})

it.each(['old_authority', 'old_scope', 'wrong_job', 'effect_is_file_hash', 'missing_key', 'known_history', 'ref_alias', 'missing_counts', 'bool_count', 'excess_rpc', 'excess_keepalive', 'missing_descriptor', 'old_windows', 'downcast_to_A', 'stripped_mode'])('rejects additional-task contract defect (%s)', async defect => {
  declaredAdditional()
  const a = JSON.parse(artifacts.admission); const b = a.use_basis
  if (defect === 'old_authority') { b.authorization_sha256 = trustedFragment.authorization_sha256; b.proofs.authorization_ref.digest = b.authorization_sha256; b.proofs.expected_authorization_sha256 = b.authorization_sha256 }
  if (defect === 'old_scope') b.scope_id = sha('old-scope')
  if (defect === 'wrong_job') b.job_id = decisionKey
  if (defect === 'effect_is_file_hash') b.capture_effect_sha256 = b.authorization_sha256
  if (defect === 'missing_key') delete b.capture_once_key
  if (defect === 'known_history') b.historical_actual_cumulative = 2
  if (defect === 'ref_alias') b.capture_usage_ref = objectRef('different capture')
  if (defect === 'missing_counts') delete b.capture_usage.actual_contexts
  if (defect === 'bool_count') b.capture_usage.actual_contexts = true
  if (defect === 'excess_rpc') b.capture_usage.actual_business_requests = 8
  if (defect === 'excess_keepalive') b.capture_usage.actual_keepalive = 97
  if (defect === 'missing_descriptor') delete b.descriptor_sha256
  if (defect === 'old_windows') b.proofs.windows_policy_ref.digest = sha('old policy')
  if (defect === 'downcast_to_A') { b.diagnostic_mode = 'DEV_DIAGNOSTIC'; delete b.channel_assurance }
  if (defect === 'stripped_mode') delete b.diagnostic_mode
  artifacts.admission = JSON.stringify(a); current = { ...current, admission: objectRef(artifacts.admission) }
  const api = (await import('@/lib/native-daily-api')).nativeDailyApi
  await expect(api.artifact(await api.get(key), 'admission')).rejects.toMatchObject({ code: 'artifact_invalid' })
  expect(posts()).toHaveLength(0)
})
