import { useEffect, useState } from 'react'
import { NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Menu, Power, RotateCcw, Search, ShieldCheck, X } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Separator } from '@/components/ui/separator'
import { CommandPalette } from '@/components/shell/CommandPalette'
import { useSurface } from '@/components/state'
import { api, ApiError } from '@/lib/api'
import { dateTime } from '@/lib/format'
import { NAV_GROUPS, NAV_ITEMS, isNavActive, navLabel } from '@/lib/nav'
import { cn } from '@/lib/utils'

function SidebarContent({ onNavigate }: { onNavigate?: () => void }) {
  const location = useLocation()
  return (
    <div className="flex h-full flex-col">
      <div className="flex h-14 items-center gap-2 px-4">
        <span className="text-base font-semibold tracking-tight">QuantMesh</span>
        <Badge variant="outline" className="font-mono text-[10px]">
          rc2
        </Badge>
      </div>
      <nav className="flex-1 space-y-4 overflow-y-auto px-3 py-2" aria-label="Screens">
        {NAV_GROUPS.map((group) => (
          <div key={group}>
            <p className="px-2 pb-1 text-[10px] font-medium tracking-wider text-muted-foreground uppercase">
              {group}
            </p>
            <ul className="space-y-0.5">
              {NAV_ITEMS.filter((item) => item.group === group).map((item) => {
                const Icon = item.icon
                const active = isNavActive(location.pathname, item)
                return (
                  <li key={item.path}>
                    <NavLink
                      to={item.path}
                      onClick={onNavigate}
                      className={cn(
                        'flex items-center gap-2.5 rounded-lg px-2 py-1.5 text-sm outline-none transition-colors',
                        'focus-visible:ring-2 focus-visible:ring-ring',
                        active
                          ? 'bg-accent font-medium text-accent-foreground'
                          : 'text-muted-foreground hover:bg-muted hover:text-foreground',
                      )}
                      aria-current={active ? 'page' : undefined}
                    >
                      <Icon className="size-4 shrink-0" aria-hidden />
                      {item.label}
                    </NavLink>
                  </li>
                )
              })}
            </ul>
          </div>
        ))}
      </nav>
      <p className="border-t border-border px-4 py-3 text-[10px] leading-relaxed text-muted-foreground">
        Loopback workstation · the kernel gates every write. Demo surfaces are synthetic and
        labeled.
      </p>
    </div>
  )
}

/**
 * The app shell (iteration 0014 Phase C): responsive sidebar, the
 * persistent paper/kill-switch status in the header, one-click demo
 * reset, and the ⌘K command palette. The kill switch state stays
 * visible on every screen because the shell itself reads it — the gate
 * lives in the kernel, this is only its mirror.
 */
export function AppShell() {
  const [paletteOpen, setPaletteOpen] = useState(false)
  const [mobileNav, setMobileNav] = useState(false)
  const [resetArmed, setResetArmed] = useState(false)
  const location = useLocation()
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  const demoStatus = useSurface(['demo-status'], api.demoStatus)
  const demoAttached =
    demoStatus.data !== undefined ||
    (demoStatus.isError && !(demoStatus.error instanceof ApiError && demoStatus.error.status === 404))

  const killSwitch = useSurface(['kill-switch'], api.killSwitch)
  const engaged = killSwitch.data?.kill_switch ?? false
  const engagedVenues = Object.entries(killSwitch.data?.kill_switches ?? {})
    .filter(([, value]) => value)
    .map(([name]) => name)

  const resetDemo = useMutation({
    mutationFn: api.demoReset,
    onSuccess: () => {
      setResetArmed(false)
      void queryClient.invalidateQueries()
    },
  })

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault()
        setPaletteOpen((value) => !value)
      }
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [])

  const title = navLabel(location.pathname)

  return (
    <div className="min-h-screen bg-background">
      {/* Desktop sidebar */}
      <aside className="fixed inset-y-0 left-0 z-30 hidden w-60 border-r border-border bg-sidebar lg:block">
        <SidebarContent />
      </aside>

      {/* Mobile drawer */}
      {mobileNav && (
        <div className="fixed inset-0 z-40 lg:hidden" role="dialog" aria-modal="true" aria-label="Navigation">
          <div className="absolute inset-0 bg-black/60" onClick={() => setMobileNav(false)} />
          <div className="absolute inset-y-0 left-0 w-72 border-r border-border bg-sidebar shadow-2xl">
            <button
              type="button"
              className="absolute top-3 right-3 rounded-lg p-2 text-muted-foreground hover:bg-muted"
              onClick={() => setMobileNav(false)}
              aria-label="Close navigation"
            >
              <X className="size-4" aria-hidden />
            </button>
            <SidebarContent onNavigate={() => setMobileNav(false)} />
          </div>
        </div>
      )}

      <div className="lg:pl-60">
        <header className="sticky top-0 z-20 flex h-14 items-center gap-2 border-b border-border bg-background/95 px-3 backdrop-blur sm:px-4">
          <Button
            variant="ghost"
            size="icon"
            className="lg:hidden"
            onClick={() => setMobileNav(true)}
            aria-label="Open navigation"
          >
            <Menu className="size-4" aria-hidden />
          </Button>
          <h1 className="text-sm font-semibold">{title}</h1>

          <div className="ml-auto flex items-center gap-1.5">
            {demoAttached && demoStatus.data && (
              <Badge
                variant="outline"
                title={`Demo root ${demoStatus.data.root} · anchored ${dateTime(demoStatus.data.scenario.anchor)} · all surfaces synthetic`}
                className="font-mono text-[10px]"
              >
                <span className="mr-1 inline-block size-1.5 rounded-full bg-emerald-500" aria-hidden />
                Paper demo · seed {demoStatus.data.scenario.seed}
              </Badge>
            )}

            <Button
              variant={engaged ? 'destructive' : 'outline'}
              size="sm"
              className="gap-1.5 font-mono text-[11px]"
              onClick={() => navigate('/ops/kill-switch')}
              aria-pressed={engaged}
            >
              <Power className="size-3.5" aria-hidden />
              {engaged ? `Kill switch on${engagedVenues.length ? ` · ${engagedVenues.join(', ')}` : ''}` : 'Kill switch off'}
            </Button>

            {demoAttached && (
              <Button
                variant="ghost"
                size="sm"
                className="gap-1.5 text-[11px]"
                onClick={() => {
                  if (resetArmed) {
                    setResetArmed(false)
                    resetDemo.mutate()
                  } else {
                    setResetArmed(true)
                    window.setTimeout(() => setResetArmed(false), 3000)
                  }
                }}
                title="Restore the pristine seeded demo root (click twice)"
                aria-label="Reset demo session"
              >
                <RotateCcw className="size-3.5" aria-hidden />
                {resetArmed ? 'Confirm reset' : 'Reset demo'}
              </Button>
            )}

            <Separator orientation="vertical" className="mx-1 h-5" />

            <Button
              variant="outline"
              size="sm"
              className="hidden gap-1.5 text-muted-foreground sm:flex"
              onClick={() => setPaletteOpen(true)}
              aria-label="Open command palette"
            >
              <Search className="size-3.5" aria-hidden />
              <span className="text-[11px]">Search…</span>
              <kbd className="rounded border border-border bg-muted px-1 font-sans text-[10px]">⌘K</kbd>
            </Button>
            <Button
              variant="ghost"
              size="icon"
              className="sm:hidden"
              onClick={() => setPaletteOpen(true)}
              aria-label="Open command palette"
            >
              <Search className="size-4" aria-hidden />
            </Button>
          </div>
        </header>

        <main className="mx-auto max-w-6xl px-4 py-6 sm:px-6 lg:px-8">
          <div className="mb-4 flex items-center gap-2 text-[11px] text-muted-foreground">
            <ShieldCheck className="size-3.5" aria-hidden />
            <span>
              {demoAttached
                ? 'Deterministic paper session — every surface is synthetic and labeled, every order gated by the kernel.'
                : 'Operator mode — no demo session attached.'}
            </span>
          </div>
          <Outlet />
        </main>
      </div>

      <CommandPalette open={paletteOpen} onOpenChange={setPaletteOpen} demoAttached={demoAttached} />
    </div>
  )
}
