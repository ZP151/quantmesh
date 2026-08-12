export function instrumentPath(venue: string, symbol: string): string {
  return `/instruments/${encodeURIComponent(venue)}/${encodeURIComponent(symbol)}`
}
