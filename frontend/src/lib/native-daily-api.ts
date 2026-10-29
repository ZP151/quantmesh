// Candidate-specific, reference-only boundary. Original bytes are verified before
// presentation or download; reading an existing ID never submits a calculation.
export const NATIVE_CANDIDATE = 'doublema_daily_overlay_candidate_v1' as const
export const nativeUuid = (v: unknown): v is string => typeof v === 'string' && /^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/.test(v)
export type NativeRef = { algorithm: 'sha256'; digest: string; byte_length: number; media_type: string }
export type NativeRequest = { candidate: typeof NATIVE_CANDIDATE; package_ref: NativeRef | null; grant_ref: NativeRef | null; approved_scope_ref: NativeRef | null; protocol_ref: NativeRef | null }
export type NativeOptions = { configured: boolean; candidate: typeof NATIVE_CANDIDATE; kernel: 'native-daily-v2'; packages: { label: string; evidence_kind: 'engineering_fixture'; package_ref: NativeRef; approved_scope_ref: NativeRef; protocol_ref: NativeRef }[]; grants: { label: string; package_digest: string; grant_ref: NativeRef }[]; real_input_enabled: false }
export type NativeJob = { job_id: string; request: NativeRequest; request_digest: string; state: 'not_run' | 'running' | 'succeeded' | 'failed' | 'interrupted'; admission_status: 'INSUFFICIENT' | 'REJECT' | 'ACCEPTED_ENGINEERING'; admission_reasons: string[]; admission: NativeRef; report: NativeRef | null; decision: NativeRef | null; trial_consumed: boolean; created_at: string; completed_at: string | null }
export type NativeDecisionRequest = { request_digest: string; admission_digest: string; report_digest: string | null; disposition: 'reject' | 'watch'; reason: string }
export type NativeArtifact = { bytes: Uint8Array<ArrayBuffer>; value: Record<string, unknown>; digest: string }
export const nativeArms = ['T', 'TO', 'B50', 'B100', 'C'] as const
export type NativeArm = typeof nativeArms[number]
export type NativeMetrics = { sessions: number; terminal_equity: number; total_return: number; max_drawdown: number; friction_usd: number; fills: number }
export type NativeReport = { calculation: Record<'base5' | 'stress10', Record<NativeArm, { metrics: NativeMetrics }>> }
const prefix = '/api/research/native-daily'
const MAX_BYTES = 1024 * 1024
const object = (v: unknown): v is Record<string, unknown> => !!v && typeof v === 'object' && !Array.isArray(v)
const hash = (v: unknown): v is string => typeof v === 'string' && /^[a-f0-9]{64}$/.test(v)
const bounded = (v: unknown, max: number): v is string => typeof v === 'string' && v.length > 0 && v.length <= max
const date = (v: unknown): v is string => typeof v === 'string' && Number.isFinite(Date.parse(v))
const safe = (v: Record<string, unknown>) => v.financial_qualification === 'INSUFFICIENT' && v.paper_allowed === false && v.live_allowed === false
export class NativeDailyError extends Error {
  readonly code: string
  constructor(code: string) { super(code); this.code = code }
}
function invalid(): never { throw new NativeDailyError('invalid_response') }
function artifactInvalid(): never { throw new NativeDailyError('artifact_invalid') }
function canonical(v: unknown): string {
  if (Array.isArray(v)) return `[${v.map(canonical).join(',')}]`
  if (object(v)) return `{${Object.keys(v).sort().map(key => `${JSON.stringify(key)}:${canonical(v[key])}`).join(',')}}`
  // Match the server's canonical JSON (ensure_ascii=True); request objects have
  // only fixed keys, strings, integer byte lengths and null references.
  return JSON.stringify(v).replace(/[\u007f-\uffff]/g, char => `\\u${char.charCodeAt(0).toString(16).padStart(4, '0')}`)
}
async function digest(bytes: Uint8Array<ArrayBuffer>) {
  return [...new Uint8Array(await crypto.subtle.digest('SHA-256', bytes))].map(v => v.toString(16).padStart(2, '0')).join('')
}
export function nativeRef(v: unknown): v is NativeRef {
  return object(v) && v.algorithm === 'sha256' && hash(v.digest) && Number.isSafeInteger(v.byte_length) && Number(v.byte_length) > 0 && Number(v.byte_length) <= MAX_BYTES && bounded(v.media_type, 160)
}
export function nativeRequest(v: unknown): v is NativeRequest {
  return object(v) && Object.keys(v).length === 5 && v.candidate === NATIVE_CANDIDATE && ['package_ref', 'grant_ref', 'approved_scope_ref', 'protocol_ref'].every(key => v[key] === null || nativeRef(v[key]))
}
const sameRef = (a: unknown, b: unknown) => a === null || b === null ? a === b : nativeRef(a) && nativeRef(b) && canonical(a) === canonical(b)
function options(v: unknown): NativeOptions {
  if (!object(v) || !safe(v) || typeof v.configured !== 'boolean' || v.candidate !== NATIVE_CANDIDATE || v.kernel !== 'native-daily-v2' || v.real_input_enabled !== false
    || !Array.isArray(v.packages) || v.packages.length > 32 || !Array.isArray(v.grants) || v.grants.length > 32
    || !v.packages.every(p => object(p) && bounded(p.label, 160) && p.evidence_kind === 'engineering_fixture' && nativeRef(p.package_ref) && nativeRef(p.approved_scope_ref) && nativeRef(p.protocol_ref))
    || !v.grants.every(g => object(g) && bounded(g.label, 160) && hash(g.package_digest) && nativeRef(g.grant_ref))) return invalid()
  return v as unknown as NativeOptions
}
async function job(v: unknown, id: string, expected?: NativeRequest): Promise<NativeJob> {
  if (!object(v) || !safe(v) || v.job_id !== id || !nativeUuid(id) || !nativeRequest(v.request) || !hash(v.request_digest)
    || (expected && canonical(v.request) !== canonical(expected)) || await digest(new TextEncoder().encode(canonical(v.request))) !== v.request_digest
    || !['not_run', 'running', 'succeeded', 'failed', 'interrupted'].includes(String(v.state)) || !['INSUFFICIENT', 'REJECT', 'ACCEPTED_ENGINEERING'].includes(String(v.admission_status))
    || !Array.isArray(v.admission_reasons) || !v.admission_reasons.every(r => bounded(r, 160)) || !nativeRef(v.admission) || v.admission.media_type !== 'application/json'
    || !(v.report === null || nativeRef(v.report)) || !(v.decision === null || nativeRef(v.decision)) || typeof v.trial_consumed !== 'boolean'
    || !date(v.created_at) || !(v.completed_at === null || date(v.completed_at))
    || (v.state === 'succeeded') !== (v.report !== null) || (v.state === 'running' && (v.completed_at !== null || v.decision !== null))
    || (v.state === 'not_run' && v.trial_consumed !== false)
    || (v.state !== 'not_run' && (v.admission_status !== 'ACCEPTED_ENGINEERING' || v.trial_consumed !== true))) return invalid()
  return v as unknown as NativeJob
}
const codes = ['not_found', 'invalid_request', 'idempotency_conflict', 'decision_conflict', 'capacity_exceeded', 'artifact_invalid', 'artifact_unavailable', 'service_closed', 'service_unavailable']
async function request(path: string, init?: RequestInit) {
  try {
    const response = await fetch(prefix + path, { ...init, mode: 'same-origin', credentials: 'same-origin', redirect: 'error', signal: AbortSignal.timeout(15000) })
    if (!response.ok) {
      let code = 'request_failed'
      try { const value: unknown = await response.json(); if (object(value) && codes.includes(String(value.detail))) code = String(value.detail) } catch { /* bounded fallback */ }
      throw new NativeDailyError(code)
    }
    return response
  } catch (cause) { if (cause instanceof NativeDailyError) throw cause; throw new NativeDailyError('request_failed') }
}
async function json(response: Response): Promise<unknown> { try { return await response.json() } catch { return invalid() } }
function requireId(id: string) { if (!nativeUuid(id)) throw new NativeDailyError('invalid_request') }
function post(body: unknown, key: string): RequestInit { requireId(key); return { method: 'POST', headers: { 'Content-Type': 'application/json', 'Idempotency-Key': key }, body: JSON.stringify(body) } }
async function verifyReport(v: Record<string, unknown>, saved: NativeJob) {
  if (v.schema_id !== 'qm.native-daily.real-report.v1' || v.evidence_kind !== 'engineering_fixture'
    || !['package_ref', 'grant_ref', 'protocol_ref'].every(key => sameRef(v[key], saved.request[key as keyof NativeRequest]))
    || !object(v.calculation) || Object.keys(v.calculation).length !== 2 || !saved.request.protocol_ref) return artifactInvalid()
  for (const [scenario, bps] of [['base5', 5], ['stress10', 10]] as const) {
    const matrix = v.calculation[scenario]
    if (!object(matrix) || Object.keys(matrix).length !== 5) return artifactInvalid()
    for (const arm of nativeArms) {
      const child = matrix[arm]
      if (!object(child) || !object(child.binding) || child.binding.schema_id !== 'qm.native-daily.candidate.arm.v1'
        || child.binding.request_digest !== saved.request.protocol_ref.digest || child.binding.arm !== arm || child.binding.cost_bps !== bps
        || await digest(new TextEncoder().encode(canonical(child.binding))) !== child.child_id
        || !object(child.metrics) || !['sessions', 'terminal_equity', 'total_return', 'max_drawdown', 'friction_usd', 'fills'].every(key => typeof (child.metrics as Record<string, unknown>)[key] === 'number' && Number.isFinite((child.metrics as Record<string, unknown>)[key]))
        || child.metrics.sessions !== 21 || !Number.isInteger(child.metrics.fills) || Number(child.metrics.fills) < 0
        || !Array.isArray(child.daily) || !Array.isArray(child.trades) || !Array.isArray(child.trace)) return artifactInvalid()
    }
  }
}
async function artifact(saved: NativeJob, kind: 'admission' | 'report' | 'decision'): Promise<NativeArtifact> {
  const reference = saved[kind]
  if (!reference || reference.media_type !== 'application/json') return artifactInvalid()
  const response = await request(`/jobs/${saved.job_id}/artifact?kind=${kind}`)
  const announced = response.headers.get('Content-Length')
  if (announced && Number(announced) > MAX_BYTES) return artifactInvalid()
  // Bound stream collection as well as the final digest, so a bad peer cannot
  // bypass ObjectRef.byte_length by omitting Content-Length.
  const reader = response.body?.getReader()
  if (!reader) return artifactInvalid()
  const chunks: Uint8Array[] = []; let length = 0
  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      length += value.byteLength
      if (length > reference.byte_length || length > MAX_BYTES) { await reader.cancel(); return artifactInvalid() }
      chunks.push(value)
    }
  } finally { reader.releaseLock() }
  const bytes = new Uint8Array(length); let offset = 0
  for (const chunk of chunks) { bytes.set(chunk, offset); offset += chunk.byteLength }
  const actual = await digest(bytes)
  if (length !== reference.byte_length || actual !== reference.digest || response.headers.get('X-Content-SHA256') !== actual) return artifactInvalid()
  let v: unknown
  try { v = JSON.parse(new TextDecoder('utf-8', { fatal: true }).decode(bytes)) } catch { return artifactInvalid() }
  if (!object(v) || !safe(v) || v.job_id !== saved.job_id || v.request_digest !== saved.request_digest) return artifactInvalid()
  if (kind === 'admission' && (v.schema_id !== 'qm.native-daily.admission.v1' || !nativeRequest(v.request) || canonical(v.request) !== canonical(saved.request) || v.status !== saved.admission_status || canonical(v.reasons) !== canonical(saved.admission_reasons))) return artifactInvalid()
  if (kind === 'report') await verifyReport(v, saved)
  if (kind === 'decision' && (v.schema_id !== 'qm.native-daily.research-decision.v1' || !nativeUuid(v.decision_key) || v.admission_digest !== saved.admission.digest || v.report_digest !== (saved.report?.digest ?? null) || !['reject', 'watch'].includes(String(v.disposition)) || !bounded(v.reason, 1000) || !v.reason.trim())) return artifactInvalid()
  return { bytes, value: v, digest: actual }
}
export const nativeDailyApi = {
  options: async () => options(await json(await request('/options'))),
  get: async (id: string, expected?: NativeRequest) => { requireId(id); return job(await json(await request(`/jobs/${id}`)), id, expected) },
  submit: async (body: NativeRequest, key: string) => { if (!nativeRequest(body)) return invalid(); return job(await json(await request('/jobs', post(body, key))), key, body) },
  decide: async (saved: NativeJob, body: NativeDecisionRequest, key: string) => job(await json(await request(`/jobs/${saved.job_id}/decision`, post(body, key))), saved.job_id, saved.request),
  artifact,
}
