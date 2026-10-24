import createClient from 'openapi-fetch'
import type { components, paths } from '@/api/client'

export const MAX_LOCAL_CSV_BYTES = 2 * 1024 * 1024
export type LocalCsvReport = components['schemas']['LocalCsvReport']
export type LocalCsvRequest = components['schemas']['LocalCsvRequest']
export type LocalCsvReference = components['schemas']['LocalCsvReference']
export class LocalCsvError extends Error {
  status: number
  constructor(status: number, message = 'local_csv_request_failed') { super(message); this.status = status }
}
const client = createClient<paths>({ baseUrl: window.location.origin,
  fetch: request => fetch(request, { credentials: 'same-origin', mode: 'same-origin', redirect: 'error', signal: AbortSignal.timeout(15000) }),
})
const digest = (value: unknown): value is string => typeof value === 'string' && /^[a-f0-9]{64}$/.test(value)
function object(value: unknown): value is Record<string, unknown> { return !!value && typeof value === 'object' && !Array.isArray(value) }
const strings = (value: unknown): value is string[] => Array.isArray(value) && value.every(item => typeof item === 'string')
const text = (value: unknown): value is string => typeof value === 'string'
const nullableText = (value: unknown) => value === null || text(value)
const count = (value: unknown) => Number.isSafeInteger(value) && Number(value) >= 0
const nullableCount = (value: unknown) => value === null || count(value)
function source(value: unknown): boolean {
  return object(value) && ['provider', 'license_scope', 'license_evidence', 'pit_status', 'session_semantics'].every(key => text(value[key]))
    && nullableText(value.received_at) && ['raw', 'adjusted', 'unknown'].includes(String(value.adjustment))
    && ['shares', 'base_units', 'contracts', 'unknown'].includes(String(value.volume_unit))
}
function coverage(value: unknown): boolean {
  return object(value) && ['rows', 'valid_rows', 'expected_sessions'].every(key => count(value[key]))
    && nullableText(value.first_date) && nullableText(value.last_date)
    && strings(value.missing_sessions) && strings(value.unexpected_sessions)
}
function freshness(value: unknown): boolean {
  return object(value) && text(value.as_of) && nullableText(value.latest_complete_session) && nullableText(value.last_session)
    && nullableCount(value.age_sessions) && ['CURRENT', 'STALE', 'INSUFFICIENT'].includes(String(value.status))
}
function ref(value: unknown): boolean {
  return object(value) && typeof value.dataset_id === 'string' && value.revision === 1 && digest(value.manifest_digest)
    && digest(value.export_digest) && value.permission_class === 'local_research'
}
function report(value: unknown, expectedId?: string): LocalCsvReport {
  if (!object(value) || value.schema_version !== 1 || !digest(value.snapshot_id) || (expectedId && value.snapshot_id !== expectedId)
    || typeof value.label !== 'string' || typeof value.symbol !== 'string' || typeof value.imported_at !== 'string'
    || !source(value.source) || !coverage(value.coverage) || !freshness(value.freshness) || !object(value.qualification)
    || value.qualification.R1 !== 'INSUFFICIENT' || value.qualification.R2 !== 'INSUFFICIENT' || value.qualification.R3 !== 'NOT_AUTHORIZED'
    || !['PASS', 'REJECT'].includes(String(value.qualification.structural_status))
    || !['REJECT', 'INSUFFICIENT'].includes(String(value.qualification.status))
    || !strings(value.qualification.reasons) || !strings(value.qualification.allowed_use)
    || !Array.isArray(value.checks) || !value.checks.every(check => object(check) && typeof check.message === 'string'
      && typeof check.code === 'string' && ['PASS', 'REJECT', 'INSUFFICIENT'].includes(String(check.status))
      && Number.isSafeInteger(check.count) && Number(check.count) >= 0 && Array.isArray(check.locations)
      && (check.locations_truncated === undefined || typeof check.locations_truncated === 'boolean')
      && check.locations.every(location => object(location) && text(location.field) && nullableCount(location.row)
        && nullableText(location.date) && nullableText(location.expected) && nullableText(location.actual)))
    || (value.dataset_ref !== null && !ref(value.dataset_ref)) || !digest(value.report_digest) || !object(value.lineage)
    || !digest(value.lineage.original_sha256)
    || !object(value.next_action) || !text(value.next_action.reason) || value.next_action.submission_allowed !== false
    || !['inspect_issues', 'plan_experiment'].includes(String(value.next_action.kind))) throw new LocalCsvError(0, 'invalid_response')
  return value as unknown as LocalCsvReport
}
function checkId(id: string) { if (!digest(id)) throw new LocalCsvError(0, 'invalid_response') }
function failure(response: Response): never { throw new LocalCsvError(response.status) }
export const localCsvApi = {
  async list(): Promise<LocalCsvReport[]> {
    const { data, response } = await client.GET('/api/research/data-snapshots/local-csv')
    if (!response.ok) failure(response)
    if (!object(data) || data.schema_version !== 1 || !Array.isArray(data.snapshots)) throw new LocalCsvError(0, 'invalid_response')
    return data.snapshots.map(item => report(item))
  },
  async import(body: LocalCsvRequest): Promise<LocalCsvReport> {
    if (new TextEncoder().encode(body.csv_text).length > MAX_LOCAL_CSV_BYTES) throw new LocalCsvError(413)
    const { data, response } = await client.POST('/api/research/data-snapshots/local-csv', { body })
    if (!response.ok) failure(response)
    return report(data)
  },
  async get(id: string): Promise<LocalCsvReport> {
    checkId(id)
    const { data, response } = await client.GET('/api/research/data-snapshots/local-csv/{snapshot_id}', { params: { path: { snapshot_id: id } } })
    if (!response.ok) failure(response)
    return report(data, id)
  },
  async reference(id: string): Promise<LocalCsvReference> {
    checkId(id)
    const { data, response } = await client.GET('/api/research/data-snapshots/local-csv/{snapshot_id}/reference', { params: { path: { snapshot_id: id } } })
    if (!response.ok) failure(response)
    if (!object(data) || data.schema_version !== 1 || data.snapshot_id !== id || !object(data.eligibility)
      || data.eligibility.status !== 'BLOCKED' || !strings(data.eligibility.reasons)
      || data.intended_use !== 'local_protocol_planning_only' || data.runner_status !== 'blocked_unqualified_input'
      || (data.dataset_ref !== null && !ref(data.dataset_ref))) throw new LocalCsvError(0, 'invalid_response')
    return data as unknown as LocalCsvReference
  },
}
