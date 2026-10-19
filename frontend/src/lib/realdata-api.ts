export const MAX_SNAPSHOT_BYTES = 8 * 1024 * 1024
const prefix = '/api/research/data-snapshots'
const hash = /^[a-f0-9]{64}$/
export type SnapshotErrorCode = 'unavailable' | 'too_large' | 'invalid_archive' | 'not_found' | 'request_failed' | 'invalid_response' | 'integrity'
export class SnapshotError extends Error {
  code: SnapshotErrorCode
  status?: number
  constructor(code: SnapshotErrorCode, status?: number) { super(code); this.code = code; this.status = status }
}
export type SnapshotCheck = {
  code: string; status: 'PASS' | 'REJECT' | 'INSUFFICIENT'; count: number; message: string;
  locations: { date: string | null; row: number | null; field: string; expected: string | null; actual: string | null }[];
}
export type SnapshotReport = {
  schema_version: 1; snapshot_id: string; imported_at: string; symbol: 'SPY';
  evidence_kind: 'real_snapshot' | 'fixture'; report_digest: string;
  source: { provider: string | null; feed: string | null; url: string | null; received_at: string | null;
    license_scope: string | null; license_evidence: string | null; price_unit: string | null;
    volume_unit: string | null; session_semantics: string | null; pit_status: string | null };
  coverage: { rows: number | null; first_date: string | null; last_date: string | null;
    expected_sessions: number | null; missing_sessions: string[] | null; unexpected_sessions: string[] | null };
  freshness: { as_of: string; latest_complete_session: string | null; last_session: string | null;
    age_sessions: number | null; status: 'CURRENT' | 'STALE' | 'INSUFFICIENT' };
  qualification: { status: 'AVAILABLE' | 'REJECT' | 'INSUFFICIENT'; structural_status: 'PASS' | 'REJECT';
    allowed_use: string[]; R1: string; R2: string; reasons: string[] };
  checks: SnapshotCheck[];
  corporate_actions: { issuer_events: number | null; yahoo_events: number | null; conflicts: string[] };
  lineage: { archive_sha256: string; files: { path: string; sha256: string; bytes: number }[];
    normalized_sha256: string; calendar_id: string; calendar_version: string; checker_sha256: string };
  preview: { head: Record<string, unknown>[]; tail: Record<string, unknown>[] };
}
function object(v: unknown): v is Record<string, unknown> { return v !== null && typeof v === 'object' && !Array.isArray(v) }
function text(v: unknown): v is string { return typeof v === 'string' }
function nullableText(v: unknown) { return v === null || text(v) }
function count(v: unknown) { return Number.isSafeInteger(v) && Number(v) >= 0 }
function nullableCount(v: unknown) { return v === null || count(v) }
function strings(v: unknown): v is string[] { return Array.isArray(v) && v.every(text) }
function nullableStrings(v: unknown) { return v === null || strings(v) }
function digest(v: unknown) { return text(v) && hash.test(v) }
function identifier(id: string) { if (!hash.test(id)) throw new SnapshotError('invalid_response') }
function report(v: unknown): SnapshotReport {
  if (!object(v) || v.schema_version !== 1 || !digest(v.snapshot_id) || !digest(v.report_digest)
    || !text(v.imported_at) || v.symbol !== 'SPY' || !['real_snapshot', 'fixture'].includes(String(v.evidence_kind))
    || !object(v.source) || !['provider', 'feed', 'url', 'received_at', 'license_scope', 'license_evidence',
      'price_unit', 'volume_unit', 'session_semantics', 'pit_status'].every(k => nullableText(v.source[k]))
    || !object(v.coverage) || !nullableCount(v.coverage.rows) || !nullableCount(v.coverage.expected_sessions)
    || !nullableText(v.coverage.first_date) || !nullableText(v.coverage.last_date)
    || !nullableStrings(v.coverage.missing_sessions) || !nullableStrings(v.coverage.unexpected_sessions)
    || !object(v.freshness) || !text(v.freshness.as_of) || !nullableText(v.freshness.latest_complete_session)
    || !nullableText(v.freshness.last_session) || !nullableCount(v.freshness.age_sessions)
    || !['CURRENT', 'STALE', 'INSUFFICIENT'].includes(String(v.freshness.status))
    || !object(v.qualification) || !['AVAILABLE', 'REJECT', 'INSUFFICIENT'].includes(String(v.qualification.status))
    || !['PASS', 'REJECT'].includes(String(v.qualification.structural_status))
    || !strings(v.qualification.allowed_use) || !strings(v.qualification.reasons)
    || !text(v.qualification.R1) || !text(v.qualification.R2)
    || !Array.isArray(v.checks) || !v.checks.every(c => object(c) && text(c.code) && text(c.message)
      && ['PASS', 'REJECT', 'INSUFFICIENT'].includes(String(c.status)) && count(c.count)
      && Array.isArray(c.locations) && c.locations.every(l => object(l) && nullableText(l.date)
        && nullableCount(l.row) && text(l.field) && nullableText(l.expected) && nullableText(l.actual)))
    || !object(v.corporate_actions) || !nullableCount(v.corporate_actions.issuer_events)
    || !nullableCount(v.corporate_actions.yahoo_events) || !strings(v.corporate_actions.conflicts)
    || !object(v.lineage) || !digest(v.lineage.archive_sha256) || v.lineage.archive_sha256 !== v.snapshot_id
    || !digest(v.lineage.normalized_sha256) || !digest(v.lineage.checker_sha256)
    || !text(v.lineage.calendar_id) || !text(v.lineage.calendar_version)
    || !Array.isArray(v.lineage.files) || !v.lineage.files.every(f => object(f) && text(f.path) && digest(f.sha256) && count(f.bytes))
    || !object(v.preview) || !Array.isArray(v.preview.head) || !v.preview.head.every(object)
    || !Array.isArray(v.preview.tail) || !v.preview.tail.every(object)) throw new SnapshotError('invalid_response')
  return v as unknown as SnapshotReport
}
async function request(path: string, init?: RequestInit): Promise<Response> {
  try {
    const response = await fetch(prefix + path, { ...init, credentials: 'same-origin', mode: 'same-origin',
      redirect: 'error', signal: AbortSignal.timeout(12000) })
    if (!response.ok) {
      const codes: Record<number, SnapshotErrorCode> = { 503: 'unavailable', 413: 'too_large', 422: 'invalid_archive', 404: 'not_found' }
      throw new SnapshotError(codes[response.status] ?? 'request_failed', response.status)
    }
    return response
  } catch (error) {
    if (error instanceof SnapshotError) throw error
    throw new SnapshotError('request_failed')
  }
}
async function json(response: Response): Promise<unknown> {
  try { return await response.json() } catch { throw new SnapshotError('invalid_response') }
}
export const realdataApi = {
  async list(): Promise<SnapshotReport[]> {
    const value = await json(await request(''))
    if (!object(value) || value.schema_version !== 1 || !Array.isArray(value.snapshots)) throw new SnapshotError('invalid_response')
    return value.snapshots.map(report)
  },
  async import(archive: Blob): Promise<SnapshotReport> {
    if (archive.size > MAX_SNAPSHOT_BYTES) throw new SnapshotError('too_large')
    if (!archive.size) throw new SnapshotError('invalid_archive')
    return report(await json(await request('', { method: 'POST', body: archive, headers: { 'Content-Type': 'application/zip' } })))
  },
  async get(id: string): Promise<SnapshotReport> {
    identifier(id)
    const value = report(await json(await request(`/${id}`)))
    if (value.snapshot_id !== id) throw new SnapshotError('invalid_response')
    return value
  },
  async download(id: string, kind: 'archive' | 'report', expectedDigest: string): Promise<Blob> {
    identifier(id); identifier(expectedDigest)
    const response = await request(`/${id}/${kind}`)
    const declared = response.headers.get('X-Content-SHA256')
    if (declared !== null && declared !== expectedDigest) throw new SnapshotError('integrity')
    const limit = kind === 'archive' ? MAX_SNAPSHOT_BYTES : 16 * 1024 * 1024
    const reader = response.body?.getReader()
    if (!reader) throw new SnapshotError('integrity')
    const chunks: Uint8Array<ArrayBuffer>[] = []
    let size = 0
    try {
      for (;;) {
        const { done, value } = await reader.read()
        if (done) break
        size += value.byteLength
        if (size > limit) { await reader.cancel(); throw new SnapshotError('integrity') }
        chunks.push(new Uint8Array(value))
      }
      const bytes = new Uint8Array(size)
      let offset = 0
      for (const chunk of chunks) { bytes.set(chunk, offset); offset += chunk.byteLength }
      const result = await crypto.subtle.digest('SHA-256', bytes)
      const actual = Array.from(new Uint8Array(result), byte => byte.toString(16).padStart(2, '0')).join('')
      if (!size || actual !== expectedDigest) throw new SnapshotError('integrity')
      return new Blob([bytes], { type: kind === 'archive' ? 'application/zip' : 'application/json' })
    } catch (error) {
      if (error instanceof SnapshotError) throw error
      throw new SnapshotError('integrity')
    } finally { reader.releaseLock() }
  },
}
