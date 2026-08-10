// Formatting helpers shared by every screen. Everything is a
// deterministic render of kernel numbers — no wall-clock state.

const moneyFormat = new Intl.NumberFormat('en-US', {
  style: 'currency',
  currency: 'USD',
})

const moneyPrecisionFormat = new Intl.NumberFormat('en-US', {
  style: 'currency',
  currency: 'USD',
  minimumFractionDigits: 4,
  maximumFractionDigits: 6,
})

const numberFormat = new Intl.NumberFormat('en-US', {
  maximumFractionDigits: 4,
})

const percentFormat = new Intl.NumberFormat('en-US', {
  style: 'percent',
  maximumFractionDigits: 2,
})

export function money(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—'
  return moneyFormat.format(value)
}

/** Money at the precision the kernel produces (avg fill prices, marks). */
export function moneyPrecise(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—'
  return moneyPrecisionFormat.format(value)
}

export function number(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—'
  return numberFormat.format(value)
}

export function quantity(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—'
  return new Intl.NumberFormat('en-US', { maximumFractionDigits: 6 }).format(value)
}

export function percent(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—'
  return percentFormat.format(value)
}

export function pnlClass(value: number | null | undefined): string {
  if (value === null || value === undefined || value === 0) return 'text-muted-foreground'
  return value > 0 ? 'text-emerald-500' : 'text-destructive'
}

export function shortHash(value: string): string {
  return value.length > 12 ? `${value.slice(0, 8)}…${value.slice(-4)}` : value
}

const dateTimeFormat = new Intl.DateTimeFormat('en-US', {
  month: 'short',
  day: 'numeric',
  hour: '2-digit',
  minute: '2-digit',
})

export function dateTime(value: string): string {
  const parsed = new Date(value)
  return Number.isNaN(parsed.getTime()) ? value : dateTimeFormat.format(parsed)
}

const timeOfDayFormat = new Intl.DateTimeFormat('en-US', {
  hour: '2-digit',
  minute: '2-digit',
  second: '2-digit',
  hour12: false,
})

/** Compact HH:MM:SS for dense live tables; the raw string survives a
 * parse failure (a non-ISO value is displayed, never silently dropped). */
export function timeOfDay(value: string | null | undefined): string {
  if (value === null || value === undefined) return '—'
  const parsed = new Date(value)
  return Number.isNaN(parsed.getTime()) ? value : timeOfDayFormat.format(parsed)
}

/** Stable title for a venue name shown on screens. */
export function venueLabel(venue: string): string {
  return venue === 'hyperliquid' ? 'Hyperliquid' : venue === 'moomoo' ? 'Moomoo' : venue
}
