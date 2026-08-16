import {
  Activity,
  ClipboardList,
  FlaskConical,
  Gauge,
  Database,
  KeyRound,
  LayoutGrid,
  Plug,
  Power,
  Radio,
  Rocket,
  Scale,
  ScrollText,
  Send,
  ShieldAlert,
  Star,
  TrendingUp,
  Wallet,
  type LucideIcon,
} from 'lucide-react'
import { Settings } from 'lucide-react'
import type { MessageKey } from '@/lib/messages'

// The target IA (iteration 0014 Phase C): the 13 legacy screens
// consolidated into the app shell, one entry per LEGACY_TO_SPA route.
// Paths live under the /app router base (ADR-0013 decision 2).

export interface NavItem {
  label: string
  path: string
  icon: LucideIcon
  group: string
  labelKey: MessageKey
  groupKey: MessageKey
}

export const NAV_ITEMS: NavItem[] = [
  { label: 'Overview', labelKey: 'nav.overview', path: '/', icon: LayoutGrid, group: 'Overview', groupKey: 'group.overview' },
  { label: 'Markets', labelKey: 'nav.markets', path: '/markets', icon: Activity, group: 'Markets', groupKey: 'group.markets' },
  { label: 'Watchlist', labelKey: 'nav.watchlist', path: '/markets/watchlist', icon: Star, group: 'Markets', groupKey: 'group.markets' },
  { label: 'Live cockpit', labelKey: 'nav.cockpit', path: '/cockpit', icon: Radio, group: 'Markets', groupKey: 'group.markets' },
  { label: 'Prediction markets', labelKey: 'nav.prediction', path: '/prediction', icon: Scale, group: 'Markets', groupKey: 'group.markets' },
  { label: 'Experiments', labelKey: 'nav.experiments', path: '/research/experiments', icon: FlaskConical, group: 'Research', groupKey: 'group.research' },
  { label: 'Promotions', labelKey: 'nav.promotions', path: '/research/promotions', icon: Rocket, group: 'Research', groupKey: 'group.research' },
  { label: 'Forecasts', labelKey: 'nav.forecasts', path: '/research/forecasts', icon: Gauge, group: 'Research', groupKey: 'group.research' },
  { label: 'Paper order', labelKey: 'nav.paperOrder', path: '/trading/order', icon: Send, group: 'Trading', groupKey: 'group.trading' },
  { label: 'Positions', labelKey: 'nav.positions', path: '/trading/positions', icon: Wallet, group: 'Trading', groupKey: 'group.trading' },
  { label: 'Orders', labelKey: 'nav.orders', path: '/trading/orders', icon: ClipboardList, group: 'Trading', groupKey: 'group.trading' },
  { label: 'P&L', labelKey: 'nav.pnl', path: '/trading/pnl', icon: TrendingUp, group: 'Trading', groupKey: 'group.trading' },
  { label: 'Risk', labelKey: 'nav.risk', path: '/risk', icon: ShieldAlert, group: 'Risk & ops', groupKey: 'group.ops' },
  { label: 'Data catalog', labelKey: 'nav.dataCatalog', path: '/ops/data', icon: Database, group: 'Risk & ops', groupKey: 'group.ops' },
  { label: 'Connectors', labelKey: 'nav.connectors', path: '/ops/connectors', icon: Plug, group: 'Risk & ops', groupKey: 'group.ops' },
  { label: 'Data imports', labelKey: 'nav.imports', path: '/ops/imports', icon: Database, group: 'Risk & ops', groupKey: 'group.ops' },
  { label: 'Audit', labelKey: 'nav.audit', path: '/ops/audit', icon: ScrollText, group: 'Risk & ops', groupKey: 'group.ops' },
  { label: 'Kill switch', labelKey: 'nav.killSwitch', path: '/ops/kill-switch', icon: Power, group: 'Risk & ops', groupKey: 'group.ops' },
  { label: 'Enablement', labelKey: 'nav.enablement', path: '/ops/enablement', icon: KeyRound, group: 'Risk & ops', groupKey: 'group.ops' },
  { label: 'Settings', labelKey: 'nav.settings', path: '/settings', icon: Settings, group: 'Risk & ops', groupKey: 'group.ops' },
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
      (pathname === other.path || pathname.startsWith(`${other.path}/`)),
  )
}

export function navLabel(pathname: string): string {
  for (const item of NAV_ITEMS) {
    if (isNavActive(pathname, item)) return item.label
  }
  return 'Workstation'
}
