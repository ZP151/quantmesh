import {
  Activity,
  ClipboardList,
  FlaskConical,
  Gauge,
  KeyRound,
  LayoutGrid,
  Power,
  Rocket,
  ScrollText,
  Send,
  ShieldAlert,
  Star,
  TrendingUp,
  Wallet,
  type LucideIcon,
} from 'lucide-react'

// The target IA (iteration 0014 Phase C): the 13 legacy screens
// consolidated into the app shell, one entry per LEGACY_TO_SPA route.
// Paths live under the /app router base (ADR-0013 decision 2).

export interface NavItem {
  label: string
  path: string
  icon: LucideIcon
  group: string
}

export const NAV_ITEMS: NavItem[] = [
  { label: 'Overview', path: '/', icon: LayoutGrid, group: 'Overview' },
  { label: 'Markets', path: '/markets', icon: Activity, group: 'Markets' },
  { label: 'Watchlist', path: '/markets/watchlist', icon: Star, group: 'Markets' },
  { label: 'Experiments', path: '/research/experiments', icon: FlaskConical, group: 'Research' },
  { label: 'Promotions', path: '/research/promotions', icon: Rocket, group: 'Research' },
  { label: 'Forecasts', path: '/research/forecasts', icon: Gauge, group: 'Research' },
  { label: 'Paper order', path: '/trading/order', icon: Send, group: 'Trading' },
  { label: 'Positions', path: '/trading/positions', icon: Wallet, group: 'Trading' },
  { label: 'Orders', path: '/trading/orders', icon: ClipboardList, group: 'Trading' },
  { label: 'P&L', path: '/trading/pnl', icon: TrendingUp, group: 'Trading' },
  { label: 'Risk', path: '/risk', icon: ShieldAlert, group: 'Risk & ops' },
  { label: 'Audit', path: '/ops/audit', icon: ScrollText, group: 'Risk & ops' },
  { label: 'Kill switch', path: '/ops/kill-switch', icon: Power, group: 'Risk & ops' },
  { label: 'Enablement', path: '/ops/enablement', icon: KeyRound, group: 'Risk & ops' },
]

export const NAV_GROUPS = ['Overview', 'Markets', 'Research', 'Trading', 'Risk & ops']

/** Longest-prefix match: /markets stops highlighting when the user is
 * on /markets/watchlist, and the home item never matches anything else. */
export function isNavActive(pathname: string, item: NavItem): boolean {
  if (item.path === '/') return pathname === '/'
  if (pathname === item.path) return true
  if (!pathname.startsWith(`${item.path}/`)) return false
  return !NAV_ITEMS.some(
    (other) =>
      other.path !== item.path &&
      other.path.length > item.path.length &&
      pathname.startsWith(`${other.path}/`),
  )
}

export function navLabel(pathname: string): string {
  for (const item of NAV_ITEMS) {
    if (isNavActive(pathname, item)) return item.label
  }
  return 'Workstation'
}
