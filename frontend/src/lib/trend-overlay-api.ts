import createClient from 'openapi-fetch'
import type { components, paths } from '@/api/client'

export type TrendTrace = components['schemas']['TrendOverlayTrace']
export type TrendRow = components['schemas']['TraceRow']
export type TrendCase = TrendTrace['case']
export const trendCases: TrendCase[] = ['campaign', 'exit-cap', 'cash-cap']
const client = createClient<paths>()

export const trendOverlayApi = {
  async get(caseId: TrendCase, signal?: AbortSignal): Promise<TrendTrace> {
    const { data, response } = await client.GET('/api/research/trend-overlay/{case_id}', {
      params: { path: { case_id: caseId } }, signal,
    })
    if (!response.ok || !data || data.case !== caseId
      || data.evidence_kind !== 'synthetic_policy_trace'
      || data.account_and_fill_inputs !== 'explicitly_supplied_fixture'
      || !data.arms.overlay_on.length
      || data.arms.overlay_on.length !== data.arms.overlay_off.length) {
      throw new Error('fixed_trace_unavailable')
    }
    return data
  },
}
