import type { ReactNode } from 'react'
import { Link, Route, Routes } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { Badge } from '@/components/ui/badge'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'

// Phase A spike (iteration 0014): the smallest real slice of the
// QuantMesh surface — read the kernel API through the generated
// contract, render loading/error/empty states, and prove deep links
// work against the production build. Phase C replaces this shell with
// the full app (market -> forecast -> paper order -> position/P&L ->
// risk/audit) and Phase B supplies the deterministic demo runtime.

type Health = {
  status: string
  project: string
  version: string
  paper_mode: boolean
  live_trading: boolean
}

type Account = {
  cash: number
  starting_cash: number
  total_fees: number
  kill_switch: boolean
  order_sequence: number
}

const api = {
  async health(): Promise<Health> {
    const response = await fetch('/api/health')
    if (!response.ok) throw new Error(`health endpoint ${response.status}`)
    return response.json()
  },
  async account(): Promise<Account> {
    const response = await fetch('/api/account')
    if (!response.ok) throw new Error(`account endpoint ${response.status}`)
    return response.json()
  },
}

function money(value: number): string {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
  }).format(value)
}

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-4">
      <span className="text-muted-foreground">{label}</span>
      <span className="tabular-nums">{children}</span>
    </div>
  )
}

function HealthCard() {
  const query = useQuery({ queryKey: ['health'], queryFn: api.health })
  return (
    <Card>
      <CardHeader>
        <CardTitle>Kernel</CardTitle>
        <CardDescription>Read-only observability surface</CardDescription>
      </CardHeader>
      <CardContent className="space-y-2 text-sm">
        {query.isPending && <Skeleton className="h-24 w-full" />}
        {query.isError && (
          <p className="text-destructive">Health unavailable — {String(query.error)}</p>
        )}
        {query.data && (
          <>
            <Row label="Project">{query.data.project}</Row>
            <Row label="Version">{query.data.version}</Row>
            <Row label="Status">
              <Badge variant={query.data.status === 'ok' ? 'default' : 'destructive'}>
                {query.data.status}
              </Badge>
            </Row>
            <Row label="Paper mode">{query.data.paper_mode ? 'on' : 'off'}</Row>
            <Row label="Live trading">{query.data.live_trading ? 'armed' : 'blocked'}</Row>
          </>
        )}
      </CardContent>
    </Card>
  )
}

function AccountCard() {
  const query = useQuery({ queryKey: ['account'], queryFn: api.account })
  return (
    <Card>
      <CardHeader>
        <CardTitle>Account</CardTitle>
        <CardDescription>Paper account bound to this workstation</CardDescription>
      </CardHeader>
      <CardContent className="space-y-2 text-sm">
        {query.isPending && <Skeleton className="h-24 w-full" />}
        {query.isError && (
          <p className="text-destructive">Account unavailable — {String(query.error)}</p>
        )}
        {query.data && (
          <>
            <Row label="Cash">{money(query.data.cash)}</Row>
            <Row label="Starting cash">{money(query.data.starting_cash)}</Row>
            <Row label="Total fees">{money(query.data.total_fees)}</Row>
            <Row label="Kill switch">
              <Badge variant={query.data.kill_switch ? 'destructive' : 'outline'}>
                {query.data.kill_switch ? 'engaged' : 'disarmed'}
              </Badge>
            </Row>
            <Row label="Order sequence">{query.data.order_sequence}</Row>
          </>
        )}
      </CardContent>
    </Card>
  )
}

function Overview() {
  return (
    <div className="space-y-6">
      <div className="space-y-1">
        <h1 className="text-2xl font-semibold tracking-tight">Workstation</h1>
        <p className="text-sm text-muted-foreground">
          QuantMesh v0.1.0-rc2 — the interactive product surface. The deterministic
          demo runtime lands in Phase B; the market → forecast → order → P&L → risk
          loop in Phase C.
        </p>
      </div>
      <div className="grid gap-4 md:grid-cols-2">
        <HealthCard />
        <AccountCard />
      </div>
    </div>
  )
}

function Markets() {
  return (
    <div className="space-y-6">
      <div className="space-y-1">
        <h1 className="text-2xl font-semibold tracking-tight">Markets</h1>
        <p className="text-sm text-muted-foreground">
          Cross-venue instrument overview — the Phase C tracer-bullet starts here.
        </p>
      </div>
      <Card>
        <CardHeader>
          <CardTitle>No markets mounted yet</CardTitle>
          <CardDescription>
            This screen is the deep-link proof for the Phase A spike. The demo
            runtime (Phase B) mounts deterministic cross-market data with
            provenance labels, and this page becomes the live market board.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Link to="/" className="text-sm text-primary hover:underline">
            ← Back to overview
          </Link>
        </CardContent>
      </Card>
    </div>
  )
}

function NotFound() {
  return (
    <Card className="mx-auto max-w-md">
      <CardHeader>
        <CardTitle>No such screen</CardTitle>
        <CardDescription>
          That deep link is not part of the Phase A spike — the full route set
          arrives with the app shell in Phase C.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <Link to="/" className="text-sm text-primary hover:underline">
          ← Back to overview
        </Link>
      </CardContent>
    </Card>
  )
}

export default function App() {
  return (
    <div className="min-h-screen">
      <header className="border-b border-border bg-card">
        <div className="mx-auto flex max-w-5xl items-center justify-between gap-4 px-4 py-3">
          <Link to="/" className="text-sm font-semibold tracking-tight">
            QuantMesh
          </Link>
          <nav className="flex items-center gap-4 text-sm">
            <Link to="/" className="text-muted-foreground hover:text-foreground">
              Overview
            </Link>
            <Link to="/markets" className="text-muted-foreground hover:text-foreground">
              Markets
            </Link>
          </nav>
        </div>
      </header>
      <main className="mx-auto max-w-5xl px-4 py-8">
        <Routes>
          <Route path="/" element={<Overview />} />
          <Route path="/markets" element={<Markets />} />
          <Route path="*" element={<NotFound />} />
        </Routes>
      </main>
    </div>
  )
}
