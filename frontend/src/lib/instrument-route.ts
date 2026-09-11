import type { HistoryRange } from '@/lib/api'

export function supportedLabTicker(value: string): 'AAPL' | 'NVDA' | null {
  const ticker = value.trim().toUpperCase()
  return ticker === 'AAPL' || ticker === 'NVDA' ? ticker : null
}

export function scenarioLabPath(symbol: 'AAPL' | 'NVDA', horizon: 7 | 30 = 30): string {
  return `${instrumentPath('moomoo', symbol)}?horizon=${horizon}&analysis=fresh`
}

export function chartEntryPath(venue: string, symbol: string): string {
  const ticker = supportedLabTicker(symbol)
  return venue === 'moomoo' && ticker !== null
    ? scenarioLabPath(ticker)
    : instrumentPath(venue, symbol)
}

export function instrumentPath(venue: string, symbol: string): string {
  return `/instruments/${encodeURIComponent(venue)}/${encodeURIComponent(symbol)}`
}

export function decisionPacketPath(
  venue: string,
  symbol: string,
  range: HistoryRange,
  packetId: string,
): string {
  const query = new URLSearchParams({ range, packet: packetId })
  return `${instrumentPath(venue, symbol)}?${query.toString()}`
}
