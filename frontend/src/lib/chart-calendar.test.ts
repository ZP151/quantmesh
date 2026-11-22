import { expect, it } from 'vitest'
import { xnysChartCalendar } from './calendars/xnys-sessions'

it('retains pinned XNYS holidays, early closes and DST instants in the generated calendar', () => {
  const sessions = new Map(xnysChartCalendar.sessions.map((s) => [s.date, s]))
  expect(xnysChartCalendar.version).toBe('exchange-calendars:4.13.2:XNYS')
  expect(sessions.has('2026-11-26')).toBe(false)
  expect(sessions.has('2026-01-19')).toBe(false)
  expect(sessions.get('2026-11-27')?.close).toBe('2026-11-27T18:00:00Z')
  expect(sessions.get('2026-03-06')?.open).toBe('2026-03-06T14:30:00Z')
  expect(sessions.get('2026-03-09')?.open).toBe('2026-03-09T13:30:00Z')
  expect(sessions.has('2025-01-09')).toBe(false)
})
