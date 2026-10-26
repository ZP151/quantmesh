// Dedicated five-operation contract frozen by the backend owner. No uploaded
// paths, user code, arbitrary parameters or fixture-authority flags are sent.
export type ReplayRequest = { snapshot_digest: string; protocol_digest: string }
export type ReplayPolicyException = {
  schema_version: 3; policy_status: 'POLICY_EXCEPTION_ONCE'; internal_once_exception: 'HUMAN_APPROVED'; provider_permission_verified: false;
  internal_decision: 'APPROVE_ONCE_PRIVATE_DIAGNOSTIC_EXCEPTION'; external_api_storage_applicability: 'UNKNOWN'; diagnostic_status: 'diagnostic_only_under_policy_exception';
  scope: 'US.SPY/1d/private_research'; once_scope_id: string; proposal_sha256: string; capture_intent_id: string; job_idempotency_key: string;
  window_sha256: string; output_root_sha256: string; authority_root_sha256: string; human_approval_ref: ReplaySampleRef; policy_document_ref: ReplaySampleRef;
}
export type ReplayObject = { algorithm: 'sha256'; digest: string; media_type: 'application/json'; byte_length: number }
export type ReplayInput = ReplayRequest & { symbol: 'SPY'; interval: '1d'; as_of_utc: string; frozen_at_utc: string;
  warmup_start: string; observation_start: string; observation_end: string;
  evidence_kind: 'reviewed_opend_freeze_v2' | 'engineering_fixture' | 'reviewed_opend_policy_exception_once_v3'; limitations: string[]; policy_exception?: ReplayPolicyException }
export type ReplayOptions = { schema_version: 1; configured: boolean; unavailable_reason: string | null; input: ReplayInput | null;
  fixed: { strategy_id: 'SMA100-long-cash'; warmup_sessions: 100; observation_sessions: 21; capital_usd: 100000;
    base_one_way_bps: 5; stress_one_way_bps: 10; cash_interest: 0; fee_spread_slippage_components: null };
  limits: { max_jobs: 32; max_inflight: 1 }; financial_qualification: 'INSUFFICIENT'; paper_allowed: false }
export type ReplayDecision = { schema_version: 1; decision_key: string; job_id: string; request_digest: string;
  snapshot_digest: string; protocol_digest: string; report_digest: string; disposition: 'reject' | 'watch'; reason: string; created_at: string }
export type ReplayJob = { schema_version: 1; job_id: string; request_digest: string; request: ReplayRequest;
  state: 'running' | 'succeeded' | 'failed' | 'interrupted'; created_at: string; updated_at: string; completed_at: string | null;
  report: ReplayObject | null; decision: ReplayDecision | null; decision_ref: ReplayObject | null;
  error_code: string | null; financial_qualification: 'INSUFFICIENT'; paper_allowed: false; sample_freshness_view?: ReplaySampleFreshness }
export type ReplaySampleFact = { value: string | null; status: 'recorded' | 'synthetic' | 'unknown' | 'not_applicable'; reason: string | null }
export type ReplaySampleRef = { algorithm: 'sha256'; digest: string; media_type: string; byte_length: number }
export type ReplaySampleEvidence = {
  schema_version: 1 | 2; snapshot_digest: string; protocol_digest: string; evidence_kind: ReplayInput['evidence_kind'];
  policy_exception?: ReplayPolicyException; capture_intent_ref?: ReplaySampleRef; proof_refs?: Record<string, ReplaySampleRef>;
  sample_id: string; sample_version: string; parent_version: string | null;
  purpose: 'fixed_engineering_regression' | 'historical_development_diagnostic'; sample_role: 'fixed_golden' | 'historical_diagnostic' | 'rolling_diagnostic';
  as_of_utc: string; frozen_at_utc: string; timestamp_basis: 'synthetic_declared' | 'source_receipts'; provider: 'synthetic' | 'opend';
  times: Record<'requested_at_utc' | 'received_at_utc' | 'post_reviewed_at_utc' | 'acceptance_reviewed_at_utc' | 'available_at_utc', ReplaySampleFact>;
  refs: Record<'freeze' | 'raw_capture' | 'authorization' | 'post_review' | 'acceptance' | 'normalized_bars' | 'distributions', ReplaySampleRef | null>;
  source_facts: Record<'source_use' | 'allowed_use' | 'pit' | 'revision_status' | 'price_adjustment' | 'currency' | 'volume_unit' | 'dividend_unit' | 'action_coverage', ReplaySampleFact>;
  review_hashes: Record<'action_coverage_sha256' | 'field_semantics_sha256' | 'independent_input_review_sha256', string | null>;
  quality: { rows: 121; warmup_sessions: 100; observation_sessions: 21; missing_sessions: 0; duplicate_sessions: 0; ordered_sessions_match: true; ohlcv_checked: true; structural_status: 'PASS' };
  calendar: { calendar_id: 'XNYS'; calendar_version: string; source_grace_minutes: 30; last_session: string };
  exposure_status: 'synthetic_not_oos' | 'historical_exposed_not_independent_oos'; first_viewed_at_utc: ReplaySampleFact; trial_count: null; trial_count_reason: 'trial_history_unavailable';
  last_checked_at_utc: string; check_scope: 'structural_bytes_only' | 'structural_bytes_and_receipt_bindings'; next_trigger: 'code_protocol_or_boundary_change' | 'new_qualified_frozen_version';
}
export type ReplaySampleFreshness = { read_at_utc: string; evaluated_snapshot_digest: string; calendar_version: string | null; source_grace_minutes: 30 | null; latest_complete_session: string | null; lag_complete_sessions: number | null;
  applicability: 'fixed_regression_not_required' | 'historical_diagnostic' | 'recent_diagnostic' | 'unknown';
  reason: 'fixed_sample_no_daily_refresh' | 'historical_window_not_recency_target' | 'current' | 'lags_latest_complete_session' | 'legacy_sample_role_unknown' | 'calendar_unavailable' | 'report_unavailable' | 'input_identity_mismatch' | 'sample_end_after_latest_complete' }
export type ReplayJobRead = ReplayJob & { sample_freshness_view: ReplaySampleFreshness }
export type ReplayDecisionRequest = Pick<ReplayDecision, 'request_digest' | 'report_digest' | 'disposition' | 'reason'>
export type ReplayArtifact = { bytes: Uint8Array<ArrayBuffer>; value: Record<string, unknown>; digest: string }
export type ReplayMetrics = { sessions: 21; terminal_equity: number; total_return: number; max_drawdown: number; friction_usd: number; fills: number; long_entries?: number; gross_traded_notional_over_initial_capital?: number; cagr: number | null; annualized_volatility: number | null; naive_sharpe_rf_zero: number | null; sortino_target_zero: number | null; calmar: number | null }
export type ReplayScenario = { one_way_bps: 5 | 10; strategy: { metrics: ReplayMetrics; daily: Record<string, unknown>[]; trades: Record<string, unknown>[] }; buyhold: { metrics: ReplayMetrics; daily: Record<string, unknown>[]; trades: Record<string, unknown>[] }; comparison: { terminal_equity_difference_usd: number; total_return_difference: number } }
export type ReplayReport = { schema_version: 1 | 2 | 3; sample_evidence?: ReplaySampleEvidence; job_id: string; request_digest: string; snapshot_digest: string; protocol_digest: string; evidence_kind: ReplayInput['evidence_kind']; window: { warmup_start: string; score_start: string; score_end: string; as_of_utc?: string; calendar_version?: string; source_grace_minutes?: number }; costs: { base_one_way_bps: 5; stress_one_way_bps: 10; fee_spread_slippage_components: null; reason: 'not_calibrated' }; calculation: { scenarios: { base5: ReplayScenario; stress10: ReplayScenario }; cash_benchmark: { capital_usd: 100000; terminal_equity: 100000; total_return: 0; max_drawdown: 0; interest_rate_assumed: 0; sessions: 21 } }; limitations: string[]; financial_qualification: 'INSUFFICIENT'; paper_allowed: false }
const prefix = '/api/research/spy-replay'
const hash = (v: unknown): v is string => typeof v === 'string' && /^[a-f0-9]{64}$/.test(v)
export const replayUuid = (v: unknown): v is string => typeof v === 'string' && /^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/.test(v)
const object = (v: unknown): v is Record<string, unknown> => !!v && typeof v === 'object' && !Array.isArray(v)
const text = (v: unknown): v is string => typeof v === 'string'
const strings = (v: unknown): v is string[] => Array.isArray(v) && v.every(text)
const date = (v: unknown): v is string => text(v) && Number.isFinite(Date.parse(v))
const same = (a: ReplayRequest, b: ReplayRequest) => a.snapshot_digest === b.snapshot_digest && a.protocol_digest === b.protocol_digest
export class SpyReplayError extends Error { status: number; code: string; constructor(code: string, status = 0) { super(code); this.status = status; this.code = code } }
function invalid(): never { throw new SpyReplayError('invalid_response') }
function pin(v: unknown): v is ReplayRequest { return object(v) && hash(v.snapshot_digest) && hash(v.protocol_digest) }
function ref(v: unknown): v is ReplayObject { return object(v) && v.algorithm === 'sha256' && hash(v.digest) && v.media_type === 'application/json' && Number.isSafeInteger(v.byte_length) && Number(v.byte_length) > 0 && Number(v.byte_length) <= 16 * 1024 * 1024 }
function decision(v: unknown, job: ReplayJob): v is ReplayDecision {
  return object(v) && v.schema_version === 1 && replayUuid(v.decision_key) && v.job_id === job.job_id && v.request_digest === job.request_digest
    && v.snapshot_digest === job.request.snapshot_digest && v.protocol_digest === job.request.protocol_digest && v.report_digest === job.report?.digest
    && ['reject', 'watch'].includes(String(v.disposition)) && text(v.reason) && v.reason.trim().length > 0 && v.reason.length <= 1000 && date(v.created_at)
}
function job(value: unknown, id: string, expected?: ReplayRequest): ReplayJob {
  if (!object(value) || value.schema_version !== 1 || value.job_id !== id || !hash(value.request_digest) || !pin(value.request)
    || (expected && !same(value.request, expected)) || !['running', 'succeeded', 'failed', 'interrupted'].includes(String(value.state))
    || !date(value.created_at) || !date(value.updated_at) || !(value.completed_at === null || date(value.completed_at))
    || !(value.report === null || ref(value.report)) || !(value.decision_ref === null || ref(value.decision_ref))
    || !(value.error_code === null || text(value.error_code)) || value.financial_qualification !== 'INSUFFICIENT' || value.paper_allowed !== false
    || (value.state === 'succeeded' && !ref(value.report)) || (!!value.decision_ref !== !!value.decision)) return invalid()
  const parsed = value as unknown as ReplayJob
  if (parsed.decision && !decision(parsed.decision, parsed)) return invalid()
  // Only GET may attach a separately validated read-time view. POST keeps the
  // original job contract and cannot supply freshness for the saved artifact.
  const { sample_freshness_view: _ignored, ...original } = parsed
  return original
}
function options(v: unknown): ReplayOptions {
  if (!object(v) || v.schema_version !== 1 || typeof v.configured !== 'boolean' || !(v.unavailable_reason === null || text(v.unavailable_reason))
    || !object(v.fixed) || v.fixed.strategy_id !== 'SMA100-long-cash' || v.fixed.warmup_sessions !== 100 || v.fixed.observation_sessions !== 21
    || v.fixed.capital_usd !== 100000 || v.fixed.base_one_way_bps !== 5 || v.fixed.stress_one_way_bps !== 10 || v.fixed.cash_interest !== 0
    || v.fixed.fee_spread_slippage_components !== null || !object(v.limits) || v.limits.max_jobs !== 32 || v.limits.max_inflight !== 1
    || v.financial_qualification !== 'INSUFFICIENT' || v.paper_allowed !== false) return invalid()
  const input = v.input
  if (input !== null && (!object(input) || input.symbol !== 'SPY' || input.interval !== '1d'
    || !date(input.as_of_utc) || !date(input.frozen_at_utc) || !date(input.warmup_start) || !date(input.observation_start) || !date(input.observation_end)
    || !['reviewed_opend_freeze_v2', 'engineering_fixture', 'reviewed_opend_policy_exception_once_v3'].includes(String(input.evidence_kind)) || !strings(input.limitations) || !pin(input))) return invalid()
  if (object(input) && (input.evidence_kind === exceptionKind ? !policyBinding(input.policy_exception) : input.policy_exception !== undefined)) return invalid()
  if (v.configured && input === null) return invalid()
  return v as unknown as ReplayOptions
}
const errors = ['not_found','idempotency_conflict','decision_conflict','capacity_exceeded','job_not_succeeded','artifact_invalid','service_closed','invalid_request','input_not_qualified','input_pin_mismatch','paper_not_authorized','service_unavailable']
async function request(path: string, init?: RequestInit) {
  try {
    const response = await fetch(prefix + path, { ...init, mode: 'same-origin', credentials: 'same-origin', redirect: 'error', signal: AbortSignal.timeout(15000) })
    if (!response.ok) {
      let code = 'request_failed'
      try { const value: unknown = await response.json(); if (object(value) && errors.includes(String(value.detail))) code = String(value.detail) } catch { /* fixed fallback */ }
      throw new SpyReplayError(code, response.status)
    }
    return response
  } catch (cause) { if (cause instanceof SpyReplayError) throw cause; throw new SpyReplayError('request_failed') }
}
async function json(response: Response): Promise<unknown> { try { return await response.json() } catch { return invalid() } }
function requireId(id: string) { if (!replayUuid(id)) throw new SpyReplayError('invalid_request') }
const bounded = (v: unknown, limit: number): v is string => text(v) && v.length > 0 && v.length <= limit
const utc = (v: unknown): v is string => date(v) && /(?:Z|\+00:00)$/.test(v)
const session = (v: unknown): v is string => text(v) && /^\d{4}-\d{2}-\d{2}$/.test(v) && date(v) && new Date(v).toISOString().slice(0, 10) === v
function sampleFact(v: unknown, time = false): boolean {
  return object(v) && (v.value === null || bounded(v.value, 160)) && ['recorded','synthetic','unknown','not_applicable'].includes(String(v.status))
    && (v.reason === null || bounded(v.reason, 160)) && (v.value !== null || bounded(v.reason, 160)) && (!time || v.value === null || utc(v.value))
}
const exceptionKind = 'reviewed_opend_policy_exception_once_v3'
const approvedScope = 'ff2d3886c07504854a6ece89f4029177d51182eb7f99b33354b6268610b9b2c9'
const approvedPolicy = '91cf0c560cadab5f80a3421604fa90b0ad5e7dc6b7ae5492058cb4013f2ccd36'
const approvedProposal = 'aafd036f8e5402a14cb0c2a85421a27ab98cc69180e693c6ab8d4f8bbd7ead13'
const onceJobKey = '890ab692-fbfc-5547-963a-9d53babce592'
const sameRef = (a: unknown, b: unknown) => object(a) && object(b) && ['algorithm','digest','media_type','byte_length'].every(key => a[key] === b[key])
function policyBinding(v: unknown): v is ReplayPolicyException {
  const proof = (x: unknown, digest: string, media: string) => object(x) && x.algorithm === 'sha256' && x.digest === digest && x.media_type === media && Number.isSafeInteger(x.byte_length) && Number(x.byte_length) > 0 && Number(x.byte_length) <= 16384
  return object(v) && Object.keys(v).length === 17 && v.schema_version === 3 && v.policy_status === 'POLICY_EXCEPTION_ONCE'
    && v.internal_once_exception === 'HUMAN_APPROVED' && v.provider_permission_verified === false
    && v.internal_decision === 'APPROVE_ONCE_PRIVATE_DIAGNOSTIC_EXCEPTION' && v.external_api_storage_applicability === 'UNKNOWN'
    && v.diagnostic_status === 'diagnostic_only_under_policy_exception' && v.scope === 'US.SPY/1d/private_research'
    && v.once_scope_id === approvedScope && v.proposal_sha256 === approvedProposal && v.job_idempotency_key === onceJobKey
    && replayUuid(v.capture_intent_id) && [v.window_sha256,v.output_root_sha256,v.authority_root_sha256].every(x => hash(x) && x !== '0'.repeat(64))
    && proof(v.human_approval_ref, approvedScope, 'application/json') && proof(v.policy_document_ref, approvedPolicy, 'text/markdown')
}
function exceptionEvidence(v: Record<string, unknown>, report: ReplayReport): boolean {
  if (!policyBinding(v.policy_exception) || report.job_id !== v.policy_exception.job_idempotency_key || !object(v.proof_refs) || !object(v.refs)) return false
  const names = ['human-approval.json','source-use-policy.md','capture-intent.json','capture-authorization.json','post-review.json','acceptance.json','freeze.json','protocol.json']
  const p = v.proof_refs
  if (Object.keys(p).length !== names.length || !names.every(name => {
    const x = p[name]; return object(x) && x.algorithm === 'sha256' && hash(x.digest) && bounded(x.media_type, 160) && Number.isSafeInteger(x.byte_length) && Number(x.byte_length) > 0 && Number(x.byte_length) <= (['freeze.json','protocol.json'].includes(name) ? 1048576 : 16384)
  })) return false
  return sameRef(p['human-approval.json'], v.policy_exception.human_approval_ref) && sameRef(p['source-use-policy.md'], v.policy_exception.policy_document_ref)
    && sameRef(p['capture-intent.json'], v.capture_intent_ref) && sameRef(p['freeze.json'], v.refs.freeze)
    && sameRef(p['acceptance.json'], v.refs.acceptance) && sameRef(p['capture-authorization.json'], v.refs.authorization) && sameRef(p['post-review.json'], v.refs.post_review)
    && (p['protocol.json'] as ReplaySampleRef).digest === report.protocol_digest
    && object(v.source_facts) && object(v.source_facts.source_use) && v.source_facts.source_use.value === 'POLICY_EXCEPTION_ONCE'
    && object(v.source_facts.pit) && v.source_facts.pit.status === 'unknown' && object(v.source_facts.revision_status) && v.source_facts.revision_status.status === 'unknown'
}
function sampleEvidence(v: unknown, report: ReplayReport): v is ReplaySampleEvidence {
  const safeRef = (value: unknown) => value === null || (object(value) && value.algorithm === 'sha256' && hash(value.digest) && bounded(value.media_type, 160) && Number.isSafeInteger(value.byte_length) && Number(value.byte_length) >= 0 && Number(value.byte_length) <= 8388608)
  if (!object(v) || new TextEncoder().encode(JSON.stringify(v)).byteLength > 32768 || v.schema_version !== (report.schema_version === 3 ? 2 : 1) || v.snapshot_digest !== report.snapshot_digest || v.protocol_digest !== report.protocol_digest || v.evidence_kind !== report.evidence_kind
    || !bounded(v.sample_id, 80) || !bounded(v.sample_version, 80) || !(v.parent_version === null || bounded(v.parent_version, 80))
    || !['fixed_engineering_regression','historical_development_diagnostic'].includes(String(v.purpose)) || !['fixed_golden','historical_diagnostic','rolling_diagnostic'].includes(String(v.sample_role))
    || !utc(v.as_of_utc) || v.as_of_utc !== report.window.as_of_utc || !utc(v.frozen_at_utc) || !utc(v.last_checked_at_utc)
    || !['synthetic_declared','source_receipts'].includes(String(v.timestamp_basis)) || !['synthetic','opend'].includes(String(v.provider))
    || !object(v.times) || !['requested_at_utc','received_at_utc','post_reviewed_at_utc','acceptance_reviewed_at_utc','available_at_utc'].every(k => sampleFact((v.times as Record<string, unknown>)[k], true))
    || !object(v.refs) || !['freeze','raw_capture','authorization','post_review','acceptance','normalized_bars','distributions'].every(k => safeRef((v.refs as Record<string, unknown>)[k]))
    || (v.refs.freeze !== null && (v.refs.freeze as ReplaySampleRef).digest !== report.snapshot_digest)
    || !object(v.source_facts) || !['source_use','allowed_use','pit','revision_status','price_adjustment','currency','volume_unit','dividend_unit','action_coverage'].every(k => sampleFact((v.source_facts as Record<string, unknown>)[k]))
    || !object(v.review_hashes) || !['action_coverage_sha256','field_semantics_sha256','independent_input_review_sha256'].every(k => { const x = (v.review_hashes as Record<string, unknown>)[k]; return x === null || hash(x) })
    || !object(v.quality) || v.quality.rows !== 121 || v.quality.warmup_sessions !== 100 || v.quality.observation_sessions !== 21 || v.quality.missing_sessions !== 0 || v.quality.duplicate_sessions !== 0 || v.quality.ordered_sessions_match !== true || v.quality.ohlcv_checked !== true || v.quality.structural_status !== 'PASS'
    || !object(v.calendar) || v.calendar.calendar_id !== 'XNYS' || !bounded(v.calendar.calendar_version, 160) || v.calendar.calendar_version !== report.window.calendar_version || v.calendar.source_grace_minutes !== 30 || report.window.source_grace_minutes !== 30 || v.calendar.last_session !== report.window.score_end
    || !['synthetic_not_oos','historical_exposed_not_independent_oos'].includes(String(v.exposure_status)) || !sampleFact(v.first_viewed_at_utc, true) || v.trial_count !== null || v.trial_count_reason !== 'trial_history_unavailable'
    || !['structural_bytes_only','structural_bytes_and_receipt_bindings'].includes(String(v.check_scope)) || !['code_protocol_or_boundary_change','new_qualified_frozen_version'].includes(String(v.next_trigger))) return false
  if (report.schema_version === 3 ? !exceptionEvidence(v, report) : v.policy_exception !== undefined || v.capture_intent_ref !== undefined || v.proof_refs !== undefined) return false
  return report.evidence_kind === 'engineering_fixture'
    ? v.provider === 'synthetic' && v.timestamp_basis === 'synthetic_declared' && v.purpose === 'fixed_engineering_regression' && v.sample_role === 'fixed_golden' && v.exposure_status === 'synthetic_not_oos'
    : v.provider === 'opend' && v.timestamp_basis === 'source_receipts' && v.purpose === 'historical_development_diagnostic' && v.exposure_status === 'historical_exposed_not_independent_oos'
}
function sampleFreshness(v: unknown, current: ReplayJob): ReplaySampleFreshness {
  const reasons = ['fixed_sample_no_daily_refresh','historical_window_not_recency_target','current','lags_latest_complete_session','legacy_sample_role_unknown','calendar_unavailable','report_unavailable','input_identity_mismatch','sample_end_after_latest_complete']
  if (!object(v) || !utc(v.read_at_utc) || v.evaluated_snapshot_digest !== current.request.snapshot_digest || !(v.calendar_version === null || bounded(v.calendar_version, 160))
    || !(v.source_grace_minutes === null || v.source_grace_minutes === 30) || !(v.latest_complete_session === null || session(v.latest_complete_session)) || !(v.lag_complete_sessions === null || (Number.isSafeInteger(v.lag_complete_sessions) && Number(v.lag_complete_sessions) >= 0))
    || !['fixed_regression_not_required','historical_diagnostic','recent_diagnostic','unknown'].includes(String(v.applicability)) || !reasons.includes(String(v.reason))) return invalid()
  const expectedApplicability = v.reason === 'fixed_sample_no_daily_refresh' ? 'fixed_regression_not_required' : v.reason === 'historical_window_not_recency_target' ? 'historical_diagnostic' : ['current','lags_latest_complete_session'].includes(String(v.reason)) ? 'recent_diagnostic' : 'unknown'
  if (v.applicability !== expectedApplicability
    || (v.reason === 'fixed_sample_no_daily_refresh' && v.applicability !== 'fixed_regression_not_required')
    || (v.reason === 'historical_window_not_recency_target' && v.applicability !== 'historical_diagnostic')
    || (v.reason === 'current' && (v.applicability !== 'recent_diagnostic' || v.lag_complete_sessions !== 0 || v.latest_complete_session === null))
    || (v.reason === 'lags_latest_complete_session' && (v.applicability !== 'recent_diagnostic' || !(Number(v.lag_complete_sessions) > 0) || v.latest_complete_session === null))) return invalid()
  return v as unknown as ReplaySampleFreshness
}
export function replayReport(value: unknown, current: ReplayJob): ReplayReport {
  const finite = (v: unknown) => typeof v === 'number' && Number.isFinite(v)
  const metrics = (v: unknown) => object(v) && v.sessions === 21 && ['terminal_equity','total_return','max_drawdown','friction_usd','fills'].every(k => finite(v[k])) && Number(v.max_drawdown) <= 0
    && (v.long_entries === undefined || (Number.isSafeInteger(v.long_entries) && Number(v.long_entries) >= 0))
    && (v.gross_traded_notional_over_initial_capital === undefined || (finite(v.gross_traded_notional_over_initial_capital) && Number(v.gross_traded_notional_over_initial_capital) >= 0))
    && ['cagr','annualized_volatility','naive_sharpe_rf_zero','sortino_target_zero','calmar'].every(k => v[k] === null || finite(v[k]))
  const track = (v: unknown) => object(v) && metrics(v.metrics) && Array.isArray(v.daily) && v.daily.every(object) && Array.isArray(v.trades) && v.trades.every(object)
  const scenario = (v: unknown, bps: number) => object(v) && v.one_way_bps === bps && track(v.strategy) && track(v.buyhold) && object(v.comparison) && finite(v.comparison.terminal_equity_difference_usd) && finite(v.comparison.total_return_difference)
  if (!object(value) || ![1,2,3].includes(Number(value.schema_version)) || typeof value.schema_version !== 'number' || value.job_id !== current.job_id || value.request_digest !== current.request_digest || value.snapshot_digest !== current.request.snapshot_digest || value.protocol_digest !== current.request.protocol_digest
    || !['engineering_fixture','reviewed_opend_freeze_v2','reviewed_opend_policy_exception_once_v3'].includes(String(value.evidence_kind)) || value.financial_qualification !== 'INSUFFICIENT' || value.paper_allowed !== false || !strings(value.limitations)
    || !object(value.window) || !['warmup_start','score_start','score_end'].every(k => date((value.window as Record<string, unknown>)[k])) || !object(value.costs) || value.costs.base_one_way_bps !== 5 || value.costs.stress_one_way_bps !== 10 || value.costs.fee_spread_slippage_components !== null || value.costs.reason !== 'not_calibrated'
    || !(value.window.as_of_utc === undefined || (value.schema_version === 1 ? date(value.window.as_of_utc) : utc(value.window.as_of_utc))) || !(value.window.calendar_version === undefined || bounded(value.window.calendar_version, 160)) || !(value.window.source_grace_minutes === undefined || value.window.source_grace_minutes === 30)
    || !object(value.calculation) || !object(value.calculation.scenarios) || !scenario(value.calculation.scenarios.base5, 5) || !scenario(value.calculation.scenarios.stress10, 10)
    || !object(value.calculation.cash_benchmark) || value.calculation.cash_benchmark.capital_usd !== 100000 || value.calculation.cash_benchmark.terminal_equity !== 100000 || value.calculation.cash_benchmark.total_return !== 0 || value.calculation.cash_benchmark.max_drawdown !== 0 || value.calculation.cash_benchmark.interest_rate_assumed !== 0 || value.calculation.cash_benchmark.sessions !== 21) return invalid()
  const parsed = value as unknown as ReplayReport
  if (parsed.schema_version >= 2 && !sampleEvidence(value.sample_evidence, parsed)) return invalid()
  if ((parsed.schema_version === 3) !== (parsed.evidence_kind === exceptionKind)) return invalid()
  return parsed
}
export const spyReplayApi = {
  async options(): Promise<ReplayOptions> { return options(await json(await request(''))) },
  async submit(id: string, body: ReplayRequest): Promise<ReplayJob> {
    requireId(id); if (!pin(body)) throw new SpyReplayError('invalid_request')
    return job(await json(await request('/jobs', { method: 'POST', headers: { 'Content-Type': 'application/json', 'Idempotency-Key': id }, body: JSON.stringify({ snapshot_digest: body.snapshot_digest, protocol_digest: body.protocol_digest }) })), id, body)
  },
  async get(id: string, expected?: ReplayRequest): Promise<ReplayJob> {
    requireId(id); const value = await json(await request(`/jobs/${id}`)); const parsed = job(value, id, expected)
    return { ...parsed, sample_freshness_view: sampleFreshness(object(value) ? value.sample_freshness_view : undefined, parsed) }
  },
  async decide(current: ReplayJob, key: string, body: ReplayDecisionRequest): Promise<ReplayJob> {
    requireId(current.job_id); requireId(key)
    if (current.state !== 'succeeded' || !current.report || body.request_digest !== current.request_digest || body.report_digest !== current.report.digest
      || !['reject','watch'].includes(body.disposition) || !body.reason.trim() || body.reason.length > 1000) throw new SpyReplayError('invalid_request')
    const result = job(await json(await request(`/jobs/${current.job_id}/decision`, { method: 'POST', headers: { 'Content-Type': 'application/json', 'Idempotency-Key': key }, body: JSON.stringify({ request_digest: body.request_digest, report_digest: body.report_digest, disposition: body.disposition, reason: body.reason }) })), current.job_id, current.request)
    if (!result.decision || result.decision.decision_key !== key || result.decision.disposition !== body.disposition || result.decision.reason !== body.reason || result.decision.report_digest !== body.report_digest || result.request_digest !== body.request_digest) return invalid()
    return result
  },
  async artifact(current: ReplayJob, kind: 'report' | 'decision'): Promise<ReplayArtifact> {
    requireId(current.job_id); const expected = kind === 'report' ? current.report : current.decision_ref
    if (!expected) throw new SpyReplayError('artifact_invalid')
    const response = await request(`/jobs/${current.job_id}/artifact?kind=${kind}`)
    if (response.headers.get('X-Content-SHA256') !== expected.digest) throw new SpyReplayError('artifact_invalid')
    const reader = response.body?.getReader(); if (!reader) throw new SpyReplayError('artifact_invalid')
    const chunks: Uint8Array<ArrayBuffer>[] = []; let length = 0
    try {
      for (;;) { const { done, value } = await reader.read(); if (done) break; length += value.byteLength
        if (length > expected.byte_length) { await reader.cancel(); throw new SpyReplayError('artifact_invalid') }
        chunks.push(new Uint8Array(value)) }
      if (length !== expected.byte_length) throw new SpyReplayError('artifact_invalid')
      const bytes = new Uint8Array(length); let offset = 0; for (const chunk of chunks) { bytes.set(chunk, offset); offset += chunk.byteLength }
      const digest = Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', bytes)), byte => byte.toString(16).padStart(2,'0')).join('')
      if (digest !== expected.digest) throw new SpyReplayError('artifact_invalid')
      const value: unknown = JSON.parse(new TextDecoder('utf-8', { fatal: true }).decode(bytes)); if (!object(value)) throw new SpyReplayError('artifact_invalid')
      if (kind === 'report') replayReport(value, current)
      if (kind === 'decision' && (!decision(value, current) || !current.decision || Object.keys(current.decision).some(key => value[key] !== current.decision?.[key as keyof ReplayDecision]))) throw new SpyReplayError('artifact_invalid')
      return { bytes, value, digest }
    } catch (cause) { if (cause instanceof SpyReplayError) throw cause; throw new SpyReplayError('artifact_invalid') }
    finally { reader.releaseLock() }
  },
}
