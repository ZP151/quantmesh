// Formatting helpers shared by every screen. Everything is a
// deterministic render of kernel numbers — no wall-clock state.

type DisplayLocale = 'en' | 'zh-CN'

function intlLocale(locale: DisplayLocale = 'en'): string {
  return locale === 'zh-CN' ? 'zh-CN' : 'en-US'
}

export function money(value: number | null | undefined, locale: DisplayLocale = 'en'): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—'
  return new Intl.NumberFormat(intlLocale(locale), {
    currency: 'USD',
    style: 'currency',
  }).format(value)
}

/** Money at the precision the kernel produces (avg fill prices, marks). */
export function moneyPrecise(value: number | null | undefined, locale: DisplayLocale = 'en'): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—'
  return new Intl.NumberFormat(intlLocale(locale), {
    currency: 'USD',
    maximumFractionDigits: 6,
    minimumFractionDigits: 4,
    style: 'currency',
  }).format(value)
}

export function number(value: number | null | undefined, locale: DisplayLocale = 'en'): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—'
  return new Intl.NumberFormat(intlLocale(locale), { maximumFractionDigits: 4 }).format(value)
}

export function quantity(value: number | null | undefined, locale: DisplayLocale = 'en'): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—'
  return new Intl.NumberFormat(intlLocale(locale), { maximumFractionDigits: 6 }).format(value)
}

export function percent(value: number | null | undefined, locale: DisplayLocale = 'en'): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—'
  return new Intl.NumberFormat(intlLocale(locale), {
    maximumFractionDigits: 2,
    style: 'percent',
  }).format(value)
}

export function pnlClass(value: number | null | undefined): string {
  if (value === null || value === undefined || value === 0) return 'text-muted-foreground'
  return value > 0 ? 'text-emerald-500' : 'text-destructive'
}

export function shortHash(value: string): string {
  return value.length > 12 ? `${value.slice(0, 8)}…${value.slice(-4)}` : value
}

export function dateTime(value: string, locale: DisplayLocale = 'en'): string {
  const parsed = new Date(value)
  return Number.isNaN(parsed.getTime()) ? value : new Intl.DateTimeFormat(intlLocale(locale), {
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    month: 'short',
  }).format(parsed)
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
