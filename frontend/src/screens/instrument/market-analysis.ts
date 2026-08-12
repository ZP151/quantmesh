import type { ChartLine } from '@/components/charts/InstrumentChart'
import type { HistoricalBar } from '@/lib/api'
import type { IndicatorValues } from './IndicatorStrip'

export function dedupeObservedBars(bars: readonly HistoricalBar[]): HistoricalBar[] {
  const byTimestamp = new Map<string, HistoricalBar>()
  for (const bar of bars) {
    const existing = byTimestamp.get(bar.timestamp)
    if (existing === undefined || bar.is_live_tail || !existing.is_live_tail) {
      byTimestamp.set(bar.timestamp, bar)
    }
  }
  return [...byTimestamp.values()].sort((left, right) => left.timestamp.localeCompare(right.timestamp))
}

export function movingAverageLine(
  bars: readonly HistoricalBar[],
  window: number,
): ChartLine['points'] {
  if (!Number.isInteger(window) || window < 2) return []
  const points: Array<{ timestamp: string; value: number }> = []
  let sum = 0
  for (let index = 0; index < bars.length; index += 1) {
    const close = bars[index].close
    if (!Number.isFinite(close)) return []
    sum += close
    if (index >= window) sum -= bars[index - window].close
    if (index >= window - 1) points.push({ timestamp: bars[index].timestamp, value: sum / window })
  }
  return points
}

function periodsPerYear(interval: string, instrumentType: string, calendar: string): number {
  const continuous = calendar.trim().toLowerCase() === '24/7'
    || instrumentType === 'spot'
    || instrumentType === 'perpetual'
  const days = continuous ? 365 : 252
  if (interval === '5m') return days * (continuous ? 288 : 78)
  if (interval === '30m') return days * (continuous ? 48 : 13)
  if (interval === '1h') return days * (continuous ? 24 : 6.5)
  return days
}

export function indicatorSnapshot(
  bars: readonly HistoricalBar[],
  interval: string,
  instrumentType: string,
  calendar: string,
): IndicatorValues {
  const closes = bars.map((bar) => bar.close).filter((value) => Number.isFinite(value) && value > 0)
  if (closes.length < 2) return { drawdown: null, realizedVolatility: null }
  const returns = closes.slice(-31).flatMap((close, index, recent) => {
    if (index === 0) return []
    return [Math.log(close / recent[index - 1])]
  })
  const mean = returns.reduce((total, value) => total + value, 0) / returns.length
  const variance = returns.length > 1
    ? returns.reduce((total, value) => total + (value - mean) ** 2, 0) / (returns.length - 1)
    : 0
  const peak = Math.max(...closes)
  return {
    drawdown: closes.at(-1)! / peak - 1,
    realizedVolatility: Math.sqrt(variance * periodsPerYear(interval, instrumentType, calendar)),
  }
}
