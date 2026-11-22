import type { HistoricalSeries } from './api'

export interface ChartSession { date: string; open: string; close: string }
export interface ChartCalendar {
  calendarId: string
  version: string
  start: string
  end: string
  sessions: readonly ChartSession[]
}

export type ChartCandle = Pick<HistoricalSeries['bars'][number], 'timestamp' | 'open' | 'high' | 'low' | 'close' | 'volume' | 'is_live_tail'>
export type WeeklyIssue = 'coverage-edge' | 'calendar-edge' | 'missing-sessions' | 'in-progress' | 'unfinalized'
export interface WeeklyCandle extends ChartCandle {
  weekStart: string
  sessionDates: readonly string[]
  sourceTimestamps: readonly string[]
  issues: readonly WeeklyIssue[]
}
export interface DailyWeeklySeries {
  daily: readonly HistoricalSeries['bars'][number][]
  weekly: readonly WeeklyCandle[]
  missingDates: readonly string[]
}

const dayFormatter = new Intl.DateTimeFormat('en-CA', { timeZone: 'America/New_York', year: 'numeric', month: '2-digit', day: '2-digit' })
function instant(value: string): number {
  if (!/(Z|[+-]\d{2}:\d{2})$/i.test(value) || !Number.isFinite(Date.parse(value))) throw new Error('invalid-time')
  return Date.parse(value)
}
export function newYorkSessionDate(timestamp: string): string {
  const parts = dayFormatter.formatToParts(new Date(instant(timestamp)))
  const part = (name: Intl.DateTimeFormatPartTypes) => parts.find((p) => p.type === name)!.value
  return `${part('year')}-${part('month')}-${part('day')}`
}
export function sessionWeekStart(date: string): string {
  const value = new Date(`${date}T00:00:00Z`)
  value.setUTCDate(value.getUTCDate() - ((value.getUTCDay() + 6) % 7))
  return value.toISOString().slice(0, 10)
}

/** Display aggregation only. It grants no data, forecast, research or trading qualification. */
export function buildDailyWeeklySeries(history: HistoricalSeries, calendar: ChartCalendar): DailyWeeklySeries {
  if (history.interval !== '1d' || history.bars.some((bar) => bar.interval !== '1d')) throw new Error('daily-required')
  if (history.calendar !== 'XNYS' || calendar.calendarId !== history.calendar) throw new Error('calendar-unsupported')
  const asOf = instant(history.as_of)
  const asOfDate = newYorkSessionDate(history.as_of)
  if (asOfDate < calendar.start || asOfDate > calendar.end) throw new Error('calendar-outside')
  const sessions = new Map(calendar.sessions.map((session) => [session.date, session]))
  const observed = new Map<string, HistoricalSeries['bars'][number]>()
  const daily = [...history.bars].sort((a, b) => instant(a.timestamp) - instant(b.timestamp))
  for (const bar of daily) {
    if (bar.instrument.symbol !== history.instrument.symbol || bar.instrument.venue !== history.instrument.venue || bar.instrument.currency !== history.instrument.currency || bar.instrument.instrument_type !== history.instrument.instrument_type) throw new Error('instrument-mismatch')
    const date = newYorkSessionDate(bar.timestamp)
    if (date < calendar.start || date > calendar.end) throw new Error('calendar-outside')
    if (date > asOfDate || instant(bar.timestamp) > asOf) throw new Error('future-session')
    if (!sessions.has(date)) throw new Error('non-session')
    if (observed.has(date)) throw new Error('duplicate-session')
    if (![bar.open, bar.high, bar.low, bar.close, bar.volume].every(Number.isFinite)
      || bar.volume < 0 || bar.low > Math.min(bar.open, bar.close)
      || bar.high < Math.max(bar.open, bar.close) || bar.low > bar.high) throw new Error('invalid-ohlcv')
    observed.set(date, bar)
  }
  if (daily.length === 0) return { daily, weekly: [], missingDates: [] }
  const firstDate = newYorkSessionDate(daily[0].timestamp)
  const missingDates = calendar.sessions.filter((session) => session.date >= firstDate && instant(session.close) <= asOf && !observed.has(session.date)).map((session) => session.date)
  const groups = new Map<string, Array<{ date: string; bar: HistoricalSeries['bars'][number] }>>()
  for (const [date, bar] of observed) {
    const start = sessionWeekStart(date)
    const group = groups.get(start) ?? []
    group.push({ date, bar })
    groups.set(start, group)
  }
  const weekly: WeeklyCandle[] = []
  for (const [weekStart, group] of groups) {
    const expected = calendar.sessions.filter((s) => sessionWeekStart(s.date) === weekStart)
    const issues: WeeklyIssue[] = []
    if (expected.some((s) => s.date < firstDate)) issues.push('coverage-edge')
    const weekEnd = new Date(`${weekStart}T00:00:00Z`)
    weekEnd.setUTCDate(weekEnd.getUTCDate() + 6)
    if (weekStart < calendar.start || weekEnd.toISOString().slice(0, 10) > calendar.end) issues.push('calendar-edge')
    if (expected.some((s) => s.date >= firstDate && instant(s.close) <= asOf && !observed.has(s.date))) issues.push('missing-sessions')
    if (expected.some((s) => instant(s.close) > asOf)) issues.push('in-progress')
    const unfinalized = group.some(({ date, bar }) => bar.is_live_tail || instant(sessions.get(date)!.close) > asOf)
    if (unfinalized) issues.push('unfinalized')
    const volume = group.reduce((sum, { bar }) => sum + bar.volume, 0)
    if (!Number.isFinite(volume)) throw new Error('invalid-ohlcv')
    weekly.push({
      timestamp: group[0].bar.timestamp, weekStart,
      open: group[0].bar.open, high: Math.max(...group.map(({ bar }) => bar.high)),
      low: Math.min(...group.map(({ bar }) => bar.low)), close: group.at(-1)!.bar.close,
      volume, is_live_tail: unfinalized, sessionDates: group.map(({ date }) => date),
      sourceTimestamps: group.map(({ bar }) => bar.timestamp), issues,
    })
  }
  return { daily, weekly, missingDates }
}

export function chartLookbackWindow(asOf: string, months: 1 | 3 | 6 | 12): { from: number; to: number } {
  const to = instant(asOf)
  const date = new Date(to)
  const day = date.getUTCDate()
  date.setUTCDate(1)
  date.setUTCMonth(date.getUTCMonth() - months)
  const lastDay = new Date(Date.UTC(date.getUTCFullYear(), date.getUTCMonth() + 1, 0)).getUTCDate()
  date.setUTCDate(Math.min(day, lastDay))
  return { from: date.getTime() / 1000, to: to / 1000 }
}
