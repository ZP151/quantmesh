import { describe, expect, it } from 'vitest'
import { dateTime, money, moneyPrecise, number, pnlClass, quantity, shortHash, venueLabel } from './format'

describe('money', () => {
  it('formats with USD currency and no decimals', () => {
    expect(money(60610.44)).toBe('$60,610.44')
  })

  it('renders a dash for nullish and NaN', () => {
    expect(money(null)).toBe('—')
    expect(money(undefined)).toBe('—')
    expect(money(Number.NaN)).toBe('—')
  })
})

describe('moneyPrecise', () => {
  it('keeps the kernel-level precision', () => {
    expect(moneyPrecise(147.591202)).toBe('$147.591202')
  })
})

describe('quantity', () => {
  it('renders up to six decimals without currency', () => {
    expect(quantity(10)).toBe('10')
    expect(quantity(0.000123)).toBe('0.000123')
  })
})

describe('number', () => {
  it('caps at four decimals', () => {
    expect(number(3.14159265)).toBe('3.1416')
  })
})

describe('pnlClass', () => {
  it('colors gains green, losses destructive, zero neutral', () => {
    expect(pnlClass(5)).toBe('text-emerald-500')
    expect(pnlClass(-2)).toBe('text-destructive')
    expect(pnlClass(0)).toBe('text-muted-foreground')
  })
})

describe('shortHash', () => {
  it('truncates long identifiers and leaves short ones alone', () => {
    expect(shortHash('0123456789abcdef')).toBe('01234567…cdef')
    expect(shortHash('abc')).toBe('abc')
  })
})

describe('venueLabel', () => {
  it('capitalizes the known venues and passes others through', () => {
    expect(venueLabel('hyperliquid')).toBe('Hyperliquid')
    expect(venueLabel('moomoo')).toBe('Moomoo')
    expect(venueLabel('kalshi')).toBe('kalshi')
  })
})

describe('dateTime', () => {
  it('formats ISO instants and passes unparseable values through', () => {
    expect(dateTime('2026-08-08T12:00:00+00:00')).not.toBe('2026-08-08T12:00:00+00:00')
    expect(dateTime('not-a-date')).toBe('not-a-date')
  })
})
