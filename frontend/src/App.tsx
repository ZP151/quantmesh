import { Route, Routes } from 'react-router-dom'
import { AppShell } from '@/components/shell/AppShell'
import { Card, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { AuditScreen } from '@/screens/Audit'
import { MarketsScreen } from '@/screens/Markets'
import { OrderScreen } from '@/screens/Order'
import { EnablementScreen, KillSwitchScreen } from '@/screens/Ops'
import { OverviewScreen } from '@/screens/Overview'
import { ExperimentsScreen, ForecastsScreen, PromotionsScreen } from '@/screens/Research'
import { RiskScreen } from '@/screens/Risk'
import { OrdersScreen, PnLScreen, PositionsScreen } from '@/screens/Trading'
import { WatchlistScreen } from '@/screens/Watchlist'

// The target IA (iteration 0014 Phase C): the 13 legacy screens
// consolidated under the /app router base, per LEGACY_TO_SPA. The
// tracer-bullet loop — market evidence → strategy/prediction → paper
// order → fill → positions/P&L → risk/audit — is the first complete
// path; every other screen renders the same providers.

function NotFound() {
  return (
    <Card className="mx-auto max-w-md">
      <CardHeader>
        <CardTitle>No such screen</CardTitle>
        <CardDescription>
          That deep link is not part of the workstation. Use the command palette (⌘K) to jump to a
          screen.
        </CardDescription>
      </CardHeader>
    </Card>
  )
}

export default function App() {
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route index element={<OverviewScreen />} />
        <Route path="markets" element={<MarketsScreen />} />
        <Route path="markets/watchlist" element={<WatchlistScreen />} />
        <Route path="research/experiments" element={<ExperimentsScreen />} />
        <Route path="research/promotions" element={<PromotionsScreen />} />
        <Route path="research/forecasts" element={<ForecastsScreen />} />
        <Route path="trading/order" element={<OrderScreen />} />
        <Route path="trading/positions" element={<PositionsScreen />} />
        <Route path="trading/orders" element={<OrdersScreen />} />
        <Route path="trading/pnl" element={<PnLScreen />} />
        <Route path="risk" element={<RiskScreen />} />
        <Route path="ops/audit" element={<AuditScreen />} />
        <Route path="ops/kill-switch" element={<KillSwitchScreen />} />
        <Route path="ops/enablement" element={<EnablementScreen />} />
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  )
}
