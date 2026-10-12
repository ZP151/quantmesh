import { describe, expect, it } from 'vitest'
import type { MarketUpdate } from './api'
import { ageInstruments, instrumentLabel, mergeUpdate, reconcileInstrumentState } from './live'
import { liveDataPresentation } from '@/components/live-data-badge'

const weekend = Date.parse('2026-10-11T12:00:00Z')
const session = {
  market_state: 'closed' as const, data_state: 'latest_session' as const,
  last_source_at: '2026-10-09T20:00:00Z', expected_last_bar_end: '2026-10-09T20:00:00Z',
  next_open_at: '2026-10-12T13:30:00Z', calendar_version: 'exchange-calendars:4.13.2:XNYS',
  reason: 'closed_latest_session_covered_without_latency_assumption',
  policy_version: 'quantmesh:session-freshness:1', provider_delay_seconds: null,
  opening_grace_seconds: 120,
}

function row() {
  return {
    venue: 'moomoo', instrument: 'AAPL', label: 'stale' as const, session_freshness: session,
    kinds: { metrics: { kind: 'metrics' as const, provenance: 'real',
      data_time: '2026-10-09T20:00:00Z', received_at: '2026-10-09T20:00:01Z',
      age_ms: 100_000, sequence: null, sequence_gap: false, label: 'stale' as const,
      payload: { last: 300 }, session_freshness: session } },
  }
}

describe('server session coverage survives client state handling', () => {
  it('preserves server session coverage through snapshot reconciliation and ageing', () => {
    const incoming = row()
    const reconciled = reconcileInstrumentState(incoming, incoming)
    expect(reconciled).toHaveProperty('session_freshness', session)
    const aged = ageInstruments({ 'moomoo:AAPL': reconciled }, weekend)
    expect(aged['moomoo:AAPL']).toHaveProperty('session_freshness', session)
    expect(instrumentLabel(aged['moomoo:AAPL'])).toBe('stale')
    expect(aged['moomoo:AAPL'].kinds.metrics.age_ms).toBeGreaterThan(100_000)
  })

  it('keeps closed coverage for same-session events but drops it for a new trading session', () => {
    const previous = row()
    const update: MarketUpdate = {
      venue: 'moomoo', instrument: 'AAPL', kind: 'metrics', provenance: 'real',
      data_time: '2026-10-09T20:00:00Z', received_at: '2026-10-11T12:00:00Z',
      sequence: null, sequence_gap: false, payload: { last: 300 }, state: null, state_note: null,
    }
    const same = mergeUpdate({ 'moomoo:AAPL': previous }, update)
    expect(same['moomoo:AAPL']).toHaveProperty('session_freshness', session)
    const next = mergeUpdate(same, { ...update, data_time: '2026-10-12T13:31:00Z',
      received_at: '2026-10-12T13:31:01Z' })
    expect(next['moomoo:AAPL'].session_freshness?.data_state).toBe('unknown')
    expect(liveDataPresentation(next['moomoo:AAPL'].session_freshness, 'real',
      Date.parse('2026-10-12T13:31:01Z')).key).toBe('live.session.unknown')
  })

  it.each(['metrics', 'status'] as const)('preserves unknown open policy through %s stream updates', (kind) => {
    const previous = { ...row(), session_freshness: { ...session, market_state: 'open' as const,
      data_state: 'unknown' as const, next_open_at: null } }
    const update: MarketUpdate = { venue: 'moomoo', instrument: 'AAPL', kind, provenance: 'real',
      data_time: '2026-10-12T13:37:21Z', received_at: '2026-10-12T13:37:21Z',
      sequence: null, sequence_gap: false, payload: kind === 'metrics' ? { last: 301 } : {},
      state: kind === 'status' ? 'connected' : null, state_note: null }
    const merged = mergeUpdate({ 'moomoo:AAPL': previous }, update)['moomoo:AAPL']
    expect(liveDataPresentation(merged.session_freshness, instrumentLabel(merged),
      Date.parse(update.received_at)).key).toBe('live.session.unknown')
  })

  it('retains source-backed delayed coverage without reclassifying raw provenance', () => {
    const previous = row()
    const same = reconcileInstrumentState(previous, { ...previous, session_freshness: undefined,
      kinds: { metrics: { ...previous.kinds.metrics, provenance: 'delayed', label: 'delayed' } } })
    expect(same.session_freshness?.data_state).toBe('latest_session')
    expect(same.kinds.metrics.provenance).toBe('delayed')
  })
})
