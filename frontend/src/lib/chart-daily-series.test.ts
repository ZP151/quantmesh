import { describe, expect, it } from 'vitest'
import type { HistoricalBar, HistoricalSeries } from './api'
import { buildDailyWeeklySeries, chartLookbackWindow, type ChartCalendar } from './chart-daily-series'

const instrument = { symbol: 'NVDA', venue: 'moomoo', currency: 'USD', instrument_type: 'equity', metadata: {} } as const
function bar(date: string, values: Partial<HistoricalBar> = {}): HistoricalBar {
  return { instrument, interval: '1d', timestamp: `${date}T05:00:00Z`, open: 10, high: 15, low: 8, close: 12, volume: 100, is_live_tail: false, ...values }
}
function history(bars: readonly HistoricalBar[], patch: Partial<HistoricalSeries> = {}): HistoricalSeries {
  return { instrument, bars, interval: '1d', calendar: 'XNYS', as_of: '2026-11-28T12:00:00Z', adjustment: 'unadjusted', range: '1y', source: 'engineering-demo', license: 'internal-only', dataset_id: 'fixture', dataset_revision: 1, generated_at: '2026-11-28T12:00:00Z', coverage_scope: 'historical-only', coverage: { start: bars[0]?.timestamp, end: bars.at(-1)?.timestamp } as HistoricalSeries['coverage'], ...patch }
}
function calendar(dates: string[], early: string[] = []): ChartCalendar {
  return { calendarId: 'XNYS', version: 'test-independent', start: '2026-01-01', end: '2026-12-31', sessions: dates.map((date) => ({ date, open: `${date}T14:30:00Z`, close: `${date}T${early.includes(date) ? '18' : '21'}:00:00Z` })) }
}
const thanksgiving = calendar(['2026-11-23', '2026-11-24', '2026-11-25', '2026-11-27'], ['2026-11-27'])
const days = [bar('2026-11-23'), bar('2026-11-24', { high: 18, close: 17 }), bar('2026-11-25', { low: 7 }), bar('2026-11-27', { close: 14, volume: 250 })]

describe('daily observations to XNYS weekly display', () => {
  it('aggregates a four-session holiday week, retaining exact lineage and input', () => {
    const input = history([days[2], days[0], days[3], days[1]])
    const before = JSON.stringify(input)
    const result = buildDailyWeeklySeries(input, thanksgiving)
    expect(result.weekly).toHaveLength(1)
    expect(result.weekly[0]).toMatchObject({ open: 10, high: 18, low: 7, close: 14, volume: 550, timestamp: days[0].timestamp, weekStart: '2026-11-23', sessionDates: ['2026-11-23', '2026-11-24', '2026-11-25', '2026-11-27'], issues: [] })
    expect(result.missingDates).toEqual([])
    expect(result.daily.map((d) => d.timestamp)).toEqual(days.map((d) => d.timestamp))
    expect(JSON.stringify(input)).toBe(before)
  })
  it('anchors a holiday-Monday week on Tuesday without inventing a Monday bar', () => {
    const dates = ['2026-01-20', '2026-01-21', '2026-01-22', '2026-01-23']
    const result = buildDailyWeeklySeries(history(dates.map((d) => bar(d)), { as_of: '2026-01-24T12:00:00Z' }), calendar(dates))
    expect(result.weekly[0]).toMatchObject({ weekStart: '2026-01-19', timestamp: '2026-01-20T05:00:00Z', issues: [] })
  })
  it('maps New York dates through the spring DST transition', () => {
    const result = buildDailyWeeklySeries(history([bar('2026-03-06'), bar('2026-03-09', { timestamp: '2026-03-09T04:00:00Z' })], { as_of: '2026-03-10T00:00:00Z' }), calendar(['2026-03-06', '2026-03-09']))
    expect(result.weekly.map((w) => w.weekStart)).toEqual(['2026-03-02', '2026-03-09'])
    expect(result.weekly[1].sessionDates).toEqual(['2026-03-09'])
  })
  it('exposes interior missing sessions without interpolating candles', () => {
    const result = buildDailyWeeklySeries(history([days[0], days[2], days[3]]), thanksgiving)
    expect(result.missingDates).toEqual(['2026-11-24'])
    expect(result.weekly[0].issues).toContain('missing-sessions')
    expect(result.daily).toHaveLength(3)
    expect(result.weekly[0].volume).toBe(450)
  })
  it('exposes missing whole weeks without generating OHLCV', () => {
    const dates = ['2026-11-02', '2026-11-09', '2026-11-16']
    const result = buildDailyWeeklySeries(history([bar(dates[0]), bar(dates[2])]), calendar(dates))
    expect(result.missingDates).toContain('2026-11-09')
    expect(result.weekly.map((w) => w.weekStart)).toEqual(['2026-11-02', '2026-11-16'])
  })
  it('marks the first clipped week rather than calling it complete', () => {
    const result = buildDailyWeeklySeries(history(days.slice(1)), thanksgiving)
    expect(result.weekly[0].issues).toContain('coverage-edge')
    expect(result.missingDates).toEqual([])
  })
  it('marks an ongoing week and a live tail as unfinished, with no future missing days', () => {
    const result = buildDailyWeeklySeries(history([days[0], { ...days[1], is_live_tail: true }], { as_of: '2026-11-24T18:00:00Z' }), thanksgiving)
    expect(result.weekly[0].issues).toEqual(expect.arrayContaining(['in-progress', 'unfinalized']))
    expect(result.missingDates).toEqual([])
  })
  it('ends an early-close session at its actual close', () => {
    const result = buildDailyWeeklySeries(history(days, { as_of: '2026-11-27T19:00:00Z' }), thanksgiving)
    expect(result.weekly[0].issues).toEqual([])
  })
  it.each([
    ['series interval', history(days, { interval: '1h' }), 'daily-required'],
    ['bar interval', history([{ ...days[0], interval: '1h' }]), 'daily-required'],
    ['calendar', history(days, { calendar: '24/7' }), 'calendar-unsupported'],
    ['instrument', history([{ ...days[0], instrument: { ...instrument, symbol: 'AAPL' } }]), 'instrument-mismatch'],
    ['naive timestamp', history([{ ...days[0], timestamp: '2026-11-23T00:00:00' }]), 'invalid-time'],
    ['duplicate session', history([days[0], { ...days[0], timestamp: '2026-11-23T21:00:00Z' }]), 'duplicate-session'],
    ['holiday observation', history([bar('2026-11-26')]), 'non-session'],
    ['calendar boundary', history([bar('2027-01-04')], { as_of: '2027-01-05T00:00:00Z' }), 'calendar-outside'],
    ['future session', history([days[3]], { as_of: '2026-11-24T18:00:00Z' }), 'future-session'],
    ['invalid OHLC', history([{ ...days[0], high: 9 }]), 'invalid-ohlcv'],
    ['invalid volume', history([{ ...days[0], volume: Infinity }]), 'invalid-ohlcv'],
    ['negative volume', history([{ ...days[0], volume: -1 }]), 'invalid-ohlcv'],
  ])('refuses %s without guessing a daily candle', (_name, input, code) => {
    expect(() => buildDailyWeeklySeries(input as HistoricalSeries, thanksgiving)).toThrow(code as string)
  })
  it('handles empty observations explicitly', () => {
    expect(buildDailyWeeklySeries(history([]), thanksgiving)).toMatchObject({ daily: [], weekly: [], missingDates: [] })
  })
})

it('keeps lookback independent of bar interval and clamps month-end', () => {
  expect(chartLookbackWindow('2026-03-31T20:00:00Z', 1)).toEqual({ from: Date.parse('2026-02-28T20:00:00Z') / 1000, to: Date.parse('2026-03-31T20:00:00Z') / 1000 })
  expect(chartLookbackWindow('2026-11-28T12:00:00Z', 12).from).toBe(Date.parse('2025-11-28T12:00:00Z') / 1000)
})
