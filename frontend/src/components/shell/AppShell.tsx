import { useEffect, useState } from 'react'
import { NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AlertTriangle, Menu, Power, RotateCcw, Search, Settings, ShieldCheck, X } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Separator } from '@/components/ui/separator'
import { CommandPalette } from '@/components/shell/CommandPalette'
import { useSurface } from '@/components/state'
import { api } from '@/lib/api'
import { dateTime } from '@/lib/format'
import { NAV_GROUPS, NAV_ITEMS, isNavActive } from '@/lib/nav'
import { usePreferences } from '@/lib/preferences'
import { cn } from '@/lib/utils'

function SidebarContent({
  onNavigate,
  version,
  runtimeMode,
  t,
}: {
  onNavigate?: () => void
  version: string
  runtimeMode: 'demo' | 'live' | 'operator'
  t: ReturnType<typeof usePreferences>['t']
}) {
  const location = useLocation()
  return (
    <div className="flex h-full flex-col">
      <div className="flex h-14 items-center gap-2 px-4">
        <span className="text-base font-semibold tracking-tight">QuantMesh</span>
        <Badge variant="outline" className="font-mono text-[10px]">
          {version}
        </Badge>
      </div>
      <nav className="flex-1 space-y-4 overflow-y-auto px-3 py-2" aria-label={t('shell.nav.screens')}>
        {NAV_GROUPS.map((group) => (
          <div key={group}>
            <p className="px-2 pb-1 text-[10px] font-medium tracking-wider text-muted-foreground uppercase">
              {t(NAV_ITEMS.find((item) => item.group === group)?.groupKey ?? 'group.ops')}
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
                      {t(item.labelKey)}
                    </NavLink>
                  </li>
                )
              })}
            </ul>
          </div>
        ))}
      </nav>
      <p className="border-t border-border px-4 py-3 text-[10px] leading-relaxed text-muted-foreground">
        {t('shell.loopback')}{' '}
        {runtimeMode === 'demo'
          ? t('shell.footerDemo')
          : runtimeMode === 'live'
            ? t('shell.footerLive')
            : t('shell.footerOperator')}
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
  const { t } = usePreferences()

  const health = useSurface(['health'], api.health)
  const runtimeMode = health.data?.runtime_mode ?? 'operator'
  const demoStatus = useQuery({
    queryKey: ['demo-status'],
    queryFn: api.demoStatus,
    enabled: runtimeMode === 'demo',
  })
  const healthVersion = health.data?.version ? `v${health.data.version}` : 'local'
  const demoAttached = runtimeMode === 'demo' && demoStatus.data !== undefined
  const retainedResets = demoStatus.data?.retained_resets ?? []

  const killSwitch = useSurface(['kill-switch'], api.killSwitch)
  const engaged = killSwitch.data?.kill_switch ?? false
  const engagedVenues = Object.entries(killSwitch.data?.kill_switches ?? {})
    .filter(([, value]) => value)
    .map(([name]) => name)
  const killSwitchLabel = engaged
    ? `${t('shell.killSwitchOn')}${engagedVenues.length ? ` · ${engagedVenues.join(', ')}` : ''}`
    : t('shell.killSwitchOff')

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

  const title = t(NAV_ITEMS.find((item) => isNavActive(location.pathname, item))?.labelKey ?? 'shell.workstation')

  return (
    <div className="min-h-screen bg-background">
      {/* Desktop sidebar */}
      <aside className="fixed inset-y-0 left-0 z-30 hidden w-60 border-r border-border bg-sidebar lg:block">
        <SidebarContent version={healthVersion} runtimeMode={runtimeMode} t={t} />
      </aside>

      {/* Mobile drawer */}
      {mobileNav && (
        <div className="fixed inset-0 z-40 lg:hidden" role="dialog" aria-modal="true" aria-label={t('shell.nav.navigation')}>
          <div className="absolute inset-0 bg-black/60" onClick={() => setMobileNav(false)} />
          <div className="absolute inset-y-0 left-0 w-72 border-r border-border bg-sidebar shadow-2xl">
            <button
              type="button"
              className="absolute top-3 right-3 rounded-lg p-2 text-muted-foreground hover:bg-muted"
              onClick={() => setMobileNav(false)}
              aria-label={t('shell.nav.close')}
            >
              <X className="size-4" aria-hidden />
            </button>
            <SidebarContent
              onNavigate={() => setMobileNav(false)}
              version={healthVersion}
              runtimeMode={runtimeMode}
              t={t}
            />
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
            aria-label={t('shell.nav.open')}
          >
            <Menu className="size-4" aria-hidden />
          </Button>
          <h1 className="text-sm font-semibold">{title}</h1>

          <div className="ml-auto flex items-center gap-1.5">
            {demoAttached && demoStatus.data && (
              <Badge
                variant="outline"
                title={t('shell.demoTitle', {
                  root: demoStatus.data.root,
                  anchor: dateTime(demoStatus.data.scenario.anchor),
                })}
                className="hidden font-mono text-[10px] md:inline-flex"
              >
                <span className="mr-1 inline-block size-1.5 rounded-full bg-emerald-500" aria-hidden />
                {t('shell.demoBadge', { seed: String(demoStatus.data.scenario.seed) })}
              </Badge>
            )}

            {retainedResets.length > 0 && demoStatus.data && (
              <Badge
                variant="outline"
                role="status"
                aria-label={t('shell.retainedResetWarning', {
                  count: String(retainedResets.length),
                })}
                title={`${retainedResets.map((item) => item.path).join(' · ')} · ${demoStatus.data.retained_reset_cleanup.instructions}`}
                className="gap-1 border-amber-500/60 bg-amber-500/10 font-mono text-[10px] text-amber-800 dark:text-amber-300"
              >
                <AlertTriangle className="size-3" aria-hidden />
                <span className="sm:hidden" aria-hidden>{retainedResets.length}</span>
                <span className="hidden sm:inline">
                  {t('shell.retainedResetWarning', {
                    count: String(retainedResets.length),
                  })}
                </span>
              </Badge>
            )}

            <Button
              variant={engaged ? 'destructive' : 'outline'}
              size="sm"
              className="gap-1.5 font-mono text-[11px]"
              onClick={() => navigate('/ops/kill-switch')}
              aria-pressed={engaged}
              aria-label={killSwitchLabel}
              title={killSwitchLabel}
            >
              <Power className="size-3.5" aria-hidden />
              <span className="hidden min-[430px]:inline">{killSwitchLabel}</span>
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
                title={t('palette.restoreDemo')}
                aria-label={t('palette.resetDemo')}
              >
                <RotateCcw className="size-3.5" aria-hidden />
                <span className="hidden sm:inline">
                  {resetArmed ? t('shell.confirmReset') : t('shell.demoReset')}
                </span>
              </Button>
            )}

            <Separator orientation="vertical" className="mx-1 h-5" />

            <Button
              variant="outline"
              size="sm"
              className="hidden gap-1.5 text-muted-foreground sm:flex"
              onClick={() => setPaletteOpen(true)}
              aria-label={t('shell.palette.open')}
            >
              <Search className="size-3.5" aria-hidden />
              <span className="text-[11px]">{t('shell.search')}</span>
              <kbd className="rounded border border-border bg-muted px-1 font-sans text-[10px]">⌘K</kbd>
            </Button>
            <Button
              variant="ghost"
              size="icon"
              className="sm:hidden"
              onClick={() => setPaletteOpen(true)}
              aria-label={t('shell.palette.open')}
            >
              <Search className="size-4" aria-hidden />
            </Button>
            <NavLink
              to="/settings"
              className="inline-flex size-8 items-center justify-center rounded-lg text-muted-foreground outline-none transition-colors hover:bg-muted hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring"
              aria-label={t('shell.openSettings')}
              title={t('shell.openSettings')}
            >
              <Settings className="size-4" aria-hidden />
            </NavLink>
          </div>
        </header>

        <main className="mx-auto max-w-6xl px-4 py-6 sm:px-6 lg:px-8">
          <div className="mb-4 flex items-center gap-2 text-[11px] text-muted-foreground">
            <ShieldCheck className="size-3.5" aria-hidden />
            <span>
              {runtimeMode === 'demo'
                ? t('shell.demoSession')
                : runtimeMode === 'live'
                  ? t('shell.liveSession')
                  : t('shell.operatorSession')}
            </span>
          </div>
          <Outlet />
        </main>
      </div>

      <CommandPalette open={paletteOpen} onOpenChange={setPaletteOpen} demoAttached={demoAttached} />
    </div>
  )
}
