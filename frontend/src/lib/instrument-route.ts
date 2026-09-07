import type { HistoryRange } from '@/lib/api'

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
