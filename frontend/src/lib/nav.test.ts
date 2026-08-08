import { describe, expect, it } from 'vitest'
import { NAV_ITEMS, isNavActive, navLabel } from './nav'

describe('isNavActive', () => {
  it('highlights the home item only on the exact root', () => {
    const home = NAV_ITEMS.find((item) => item.path === '/')!
    expect(isNavActive('/', home)).toBe(true)
    expect(isNavActive('/markets', home)).toBe(false)
  })

  it('uses longest-prefix matching so parents stop highlighting', () => {
    const markets = NAV_ITEMS.find((item) => item.path === '/markets')!
    expect(isNavActive('/markets', markets)).toBe(true)
    expect(isNavActive('/markets/watchlist', markets)).toBe(false)
  })

  it('matches a deeper path against its own item', () => {
    const watchlist = NAV_ITEMS.find((item) => item.path === '/markets/watchlist')!
    expect(isNavActive('/markets/watchlist', watchlist)).toBe(true)
  })

  it('does not match a partial segment', () => {
    const risk = NAV_ITEMS.find((item) => item.path === '/risk')!
    expect(isNavActive('/riskless', risk)).toBe(false)
  })
})

describe('navLabel', () => {
  it('resolves the current screen label from the pathname', () => {
    expect(navLabel('/ops/connectors')).toBe('Connectors')
    expect(navLabel('/ops/imports')).toBe('Data imports')
    expect(navLabel('/unknown-route')).toBe('Workstation')
  })
})
