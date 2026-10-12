import { describe, expect, it } from 'vitest'
import type { SessionFreshness } from '@/lib/api'
import { liveDataPresentation } from './live-data-badge'

const closed: SessionFreshness = {
  market_state: 'closed', data_state: 'latest_session',
  last_source_at: '2026-10-09T20:00:00Z', expected_last_bar_end: '2026-10-09T20:00:00Z',
  next_open_at: '2026-10-12T13:30:00Z', calendar_version: 'XNYS:pinned',
  reason: 'closed_latest_session_covered_without_latency_assumption',
  policy_version: 'quantmesh:session-freshness:1', provider_delay_seconds: null,
  opening_grace_seconds: 120,
}
const sunday = Date.parse('2026-10-11T12:00:00Z')

describe('shared calendar presentation', () => {
  it('shows valid closed coverage neutrally without assuming zero provider latency', () => {
    expect(liveDataPresentation(closed, 'stale', sunday)).toEqual({
      key: 'live.session.closedLatest', tone: 'bg-muted text-muted-foreground',
    })
  })
  it('expires closed coverage at the server-provided next open', () => {
    expect(liveDataPresentation(closed, 'stale', Date.parse(closed.next_open_at!)).key)
      .toBe('live.session.refresh')
  })
  it.each([false, true])('does not certify synthetic or absent real evidence (%s)', (real) => {
    expect(liveDataPresentation(closed, real ? 'synthetic' : 'unavailable', sunday, real).key)
      .toBe(real ? 'live.label.synthetic' : 'live.label.unavailable')
  })
  it('keeps missing and unknown closed coverage distinct from normal closure', () => {
    expect(liveDataPresentation({ ...closed, data_state: 'missing' }, 'stale', sunday).key)
      .toBe('live.session.closedMissing')
    expect(liveDataPresentation({ ...closed, data_state: 'unknown' }, 'stale', sunday).key)
      .toBe('live.session.closedUnknown')
  })
  it('does not keep cached open coverage green after its next due interval', () => {
    const open = { ...closed, market_state: 'open' as const, data_state: 'fresh' as const,
      last_source_at: '2026-10-12T13:37:00Z', expected_last_bar_end: '2026-10-12T13:37:00Z',
      next_open_at: null, provider_delay_seconds: 0, evaluated_at: '2026-10-12T13:37:20Z' }
    expect(liveDataPresentation(open, 'stale', Date.parse('2026-10-12T13:39:00Z')).key)
      .toBe('live.session.refresh')
  })
  it('does not certify undeclared latency during an open session', () => {
    expect(liveDataPresentation({ ...closed, market_state: 'open', data_state: 'fresh' },
      'real', Date.parse('2026-10-12T13:37:00Z')).key).toBe('live.session.unknown')
  })
})
