/** Explicit local synthetic paper authority. No quotes, paths or account state are uploaded. */
export type Venue = 'moomoo' | 'hyperliquid' | 'polymarket' | 'kalshi'
export type PaperReceipt = {
  id: string; action: 'startup' | 'pause' | 'resume'; key: string; reason: string;
  requested_revision: string; confirmation: boolean; target: Venue | null; boot: string;
  configuration: string; account_binding: string; recorded_at: string; outcome: 'completed';
}
export type PaperStatus = {
  synthetic: true; paper: true; paused: boolean; blocked: boolean; pause_reason: string;
  checks: string[]; revision: string; limits: { max_order_quantity: number; max_notional: number; max_position_quantity: number } | null;
  costs: { fee_bps: number; min_fee: number; slippage_bps: number }; venue_stops: Partial<Record<Venue, boolean>>;
  last_receipt: PaperReceipt | null; history: PaperReceipt[];
}
export type Transition = { key: string; reason: string; revision?: string; confirmation?: boolean; target?: Venue | null }
export type PaperTransition = { receipt: PaperReceipt; replay: boolean; status: PaperStatus }
const prefix = '/api/paper-controls'
const venues = ['moomoo', 'hyperliquid', 'polymarket', 'kalshi']
const hash = /^[a-f0-9]{64}$/
const codes = ['unavailable', 'invalid_response', 'integrity', 'request_failed', 'stale_revision', 'key_conflict',
  'confirmation_required', 'paper_control_evidence_blocked', 'publication_failed', 'audit_invalid_or_incomplete'] as const
export type PaperErrorCode = typeof codes[number]
export class PaperControlError extends Error {
  code: PaperErrorCode
  constructor(code: PaperErrorCode) { super(code); this.code = code }
}
function object(v: unknown): v is Record<string, unknown> { return v !== null && typeof v === 'object' && !Array.isArray(v) }
function text(v: unknown, max = 240): v is string { return typeof v === 'string' && v.length <= max }
function finite(v: unknown): v is number { return typeof v === 'number' && Number.isFinite(v) && v >= 0 }
function digest(v: unknown): v is string { return typeof v === 'string' && hash.test(v) }
function receipt(v: unknown): v is PaperReceipt {
  return object(v) && digest(v.id) && ['startup', 'pause', 'resume'].includes(String(v.action))
    && text(v.key, 96) && text(v.reason) && text(v.requested_revision, 64) && typeof v.confirmation === 'boolean'
    && (v.target === null || venues.includes(String(v.target))) && text(v.boot, 96) && digest(v.configuration)
    && digest(v.account_binding) && text(v.recorded_at, 64) && v.outcome === 'completed'
}
function status(v: unknown): PaperStatus {
  if (!object(v) || v.synthetic !== true || v.paper !== true || typeof v.paused !== 'boolean' || typeof v.blocked !== 'boolean'
    || !text(v.pause_reason) || !digest(v.revision) || !Array.isArray(v.checks) || v.checks.length > 12 || !v.checks.every(c => text(c, 96))
    || !(v.limits === null || object(v.limits) && ['max_order_quantity', 'max_notional', 'max_position_quantity']
      .every(k => finite(v.limits && (v.limits as Record<string, unknown>)[k]) && Number((v.limits as Record<string, unknown>)[k]) > 0))
    || !object(v.costs) || !['fee_bps', 'min_fee', 'slippage_bps'].every(k => finite((v.costs as Record<string, unknown>)[k]))
    || !object(v.venue_stops) || !Object.entries(v.venue_stops).every(([k, value]) => venues.includes(k) && typeof value === 'boolean')
    || !(v.last_receipt === null || receipt(v.last_receipt)) || !Array.isArray(v.history) || v.history.length > 20 || !v.history.every(receipt)) {
    throw new PaperControlError('invalid_response')
  }
  return v as unknown as PaperStatus
}
async function bytes(response: Response): Promise<Uint8Array<ArrayBuffer>> {
  if (!response.body) throw new PaperControlError('invalid_response')
  const reader = response.body.getReader(), chunks: Uint8Array[] = []
  let size = 0
  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      size += value.byteLength
      if (size > 2 * 1024 * 1024) { await reader.cancel(); throw new PaperControlError('invalid_response') }
      chunks.push(value)
    }
    const result = new Uint8Array(size); let offset = 0
    for (const chunk of chunks) { result.set(chunk, offset); offset += chunk.byteLength }
    return result
  } finally { reader.releaseLock() }
}
async function request(path: string, payload?: unknown): Promise<Response> {
  try {
    const response = await fetch(prefix + path, {
      method: payload === undefined ? 'GET' : 'POST', credentials: 'same-origin', mode: 'same-origin', redirect: 'error',
      signal: AbortSignal.timeout(15000), ...(payload === undefined ? {} : {
        headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
      }),
    })
    if (!response.ok) {
      let detail: unknown
      try { detail = JSON.parse(new TextDecoder().decode(await bytes(response))).detail } catch { /* fixed safe fallback */ }
      if (response.status === 503 && detail === 'paper_controls_unavailable') throw new PaperControlError('unavailable')
      throw new PaperControlError(detail !== 'unavailable' && codes.includes(detail as PaperErrorCode) ? detail as PaperErrorCode : 'request_failed')
    }
    return response
  } catch (error) {
    if (error instanceof PaperControlError) throw error
    throw new PaperControlError('request_failed')
  }
}
async function json(response: Response): Promise<unknown> {
  try { return JSON.parse(new TextDecoder().decode(await bytes(response))) }
  catch { throw new PaperControlError('invalid_response') }
}
export const paperControlsApi = {
  async status() { return status(await json(await request(''))) },
  async preflight(target: Venue | null) { return status(await json(await request('/preflight', { target }))) },
  async transition(action: 'pause' | 'resume', payload: Transition): Promise<PaperTransition> {
    const value = await json(await request(`/${action}`, payload))
    if (!object(value) || !receipt(value.receipt) || typeof value.replay !== 'boolean') throw new PaperControlError('invalid_response')
    return { receipt: value.receipt, replay: value.replay, status: status(value.status) }
  },
  async download(kind: 'audit' | 'receipt', id?: string): Promise<Blob> {
    if (kind === 'receipt' && (!id || !hash.test(id))) throw new PaperControlError('integrity')
    const response = await request(kind === 'audit' ? '/audit' : `/receipts/${id}`)
    const expected = response.headers.get('X-Content-SHA256')
    if (!expected || !hash.test(expected)) throw new PaperControlError('integrity')
    const value = await bytes(response)
    try {
      const actual = Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', value)), b => b.toString(16).padStart(2, '0')).join('')
      if (actual !== expected) throw new PaperControlError('integrity')
    } catch { throw new PaperControlError('integrity') }
    return new Blob([value], { type: 'application/octet-stream' })
  },
}
