import { lazy, Suspense } from 'react'
import { Route, Routes } from 'react-router-dom'
import { AppShell } from '@/components/shell/AppShell'
import { LoadingState } from '@/components/state'
import { Card, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { AuditScreen } from '@/screens/Audit'
import { CockpitDetailScreen } from '@/screens/CockpitDetail'
import { CockpitScreen } from '@/screens/Cockpit'
import { ConnectorsScreen } from '@/screens/Connectors'
import { ImportsScreen } from '@/screens/Imports'
import { MarketsScreen } from '@/screens/Markets'
import { OrderScreen } from '@/screens/Order'
import { EnablementScreen, KillSwitchScreen } from '@/screens/Ops'
import { PredictionScreen } from '@/screens/Prediction'
import { OverviewScreen } from '@/screens/Overview'
import { ExperimentsScreen, ForecastsScreen, PromotionsScreen } from '@/screens/Research'
import { RiskScreen } from '@/screens/Risk'
import { SettingsScreen } from '@/screens/Settings'
import { OrdersScreen, PnLScreen, PositionsScreen } from '@/screens/Trading'
import { WatchlistScreen } from '@/screens/Watchlist'
import { usePreferences } from '@/lib/preferences'

const InstrumentWorkspaceScreen = lazy(() => import('@/screens/InstrumentWorkspace'))

// The target IA (iteration 0014 Phase C): the 13 legacy screens
// consolidated under the /app router base, per LEGACY_TO_SPA. The
// tracer-bullet loop — market evidence → strategy/prediction → paper
// order → fill → positions/P&L → risk/audit — is the first complete
// path; every other screen renders the same providers.

function NotFound() {
  const { t } = usePreferences()
  return (
    <Card className="mx-auto max-w-md">
      <CardHeader>
        <CardTitle>{t('shell.notFound.title')}</CardTitle>
        <CardDescription>{t('shell.notFound.description')}</CardDescription>
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
        <Route path="cockpit" element={<CockpitScreen />} />
        <Route path="cockpit/:symbol" element={<CockpitDetailScreen />} />
        <Route
          path="instruments/:venue/:symbol"
          element={
            <Suspense fallback={<LoadingState rows={3} />}>
              <InstrumentWorkspaceScreen />
            </Suspense>
          }
        />
        <Route path="prediction" element={<PredictionScreen />} />
        <Route path="research/experiments" element={<ExperimentsScreen />} />
        <Route path="research/promotions" element={<PromotionsScreen />} />
        <Route path="research/forecasts" element={<ForecastsScreen />} />
        <Route path="trading/order" element={<OrderScreen />} />
        <Route path="trading/positions" element={<PositionsScreen />} />
        <Route path="trading/orders" element={<OrdersScreen />} />
        <Route path="trading/pnl" element={<PnLScreen />} />
        <Route path="risk" element={<RiskScreen />} />
        <Route path="ops/connectors" element={<ConnectorsScreen />} />
        <Route path="ops/imports" element={<ImportsScreen />} />
        <Route path="ops/audit" element={<AuditScreen />} />
        <Route path="ops/kill-switch" element={<KillSwitchScreen />} />
        <Route path="ops/enablement" element={<EnablementScreen />} />
        <Route path="settings" element={<SettingsScreen />} />
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  )
}
