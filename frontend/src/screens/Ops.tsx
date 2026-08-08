import { KeyRound, Power } from 'lucide-react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Page } from '@/components/page'
import { Notice, Surface, useSurface } from '@/components/state'
import { api, ApiError } from '@/lib/api'
import { venueLabel } from '@/lib/format'

// --- Kill switch ----------------------------------------------------------

/**
 * The kill-switch control: the global bit plus every venue the
 * workstation knows. The flip POSTs to the same account object the
 * kernel gate reads — this UI is only its mirror, the refusal is
 * real. Disarm is always possible.
 */
export function KillSwitchScreen() {
  const query = useSurface(['kill-switch'], api.killSwitch)
  const queryClient = useQueryClient()
  const flip = useMutation({
    mutationFn: ({ engage, venue }: { engage: boolean; venue?: string }) =>
      engage ? api.engageKillSwitch(venue) : api.disarmKillSwitch(venue),
    onSuccess: () => void queryClient.invalidateQueries(),
    onError: (error: unknown) => {
      // The flip failed — surface the kernel's verdict verbatim.
      window.alert(error instanceof ApiError ? error.message : String(error))
    },
  })

  return (
    <Page
      title="Kill switch"
      description="The global gate and the per-venue gates. Engaging refuses every paper and live submission through the accounting risk gate — no model surface is involved, and disarm always works."
    >
      <Surface query={query} title="Kill switch">
        {(state) => (
          <div className="space-y-5">
            <Card className={state.kill_switch ? 'border-destructive/50' : ''}>
              <CardHeader className="pb-2">
                <CardTitle className="flex items-center gap-2 text-base">
                  <Power className="size-4" aria-hidden /> Global
                  <Badge variant={state.kill_switch ? 'destructive' : 'outline'} className="font-mono text-[10px]">
                    {state.kill_switch ? 'engaged' : 'disarmed'}
                  </Badge>
                </CardTitle>
                <CardDescription>
                  Refuses every order — paper and live — at the accounting gate. The order form on
                  the Paper order screen shows the same bit.
                </CardDescription>
              </CardHeader>
              <CardContent>
                <Button
                  variant={state.kill_switch ? 'outline' : 'destructive'}
                  size="sm"
                  disabled={flip.isPending}
                  onClick={() => void flip.mutate({ engage: !state.kill_switch })}
                >
                  {state.kill_switch ? 'Disarm global kill switch' : 'Engage global kill switch'}
                </Button>
              </CardContent>
            </Card>

            {Object.keys(state.kill_switches).length > 0 && (
              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-base">Per venue</CardTitle>
                  <CardDescription>
                    A venue switch blocks only its venue; the global bit overrides everything.
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-3">
                  {Object.entries(state.kill_switches).map(([name, engaged]) => (
                    <div key={name} className="flex items-center justify-between gap-3">
                      <span className="text-sm">{venueLabel(name)}</span>
                      <Button
                        variant={engaged ? 'outline' : 'destructive'}
                        size="sm"
                        disabled={flip.isPending}
                        onClick={() => void flip.mutate({ engage: !engaged, venue: name })}
                      >
                        {engaged ? `Disarm ${name}` : `Engage ${name}`}
                      </Button>
                    </div>
                  ))}
                </CardContent>
              </Card>
            )}
          </div>
        )}
      </Surface>
    </Page>
  )
}

// --- Enablement -----------------------------------------------------------

/** Enablement: read-only per-venue state from the approval ledger,
 * plus the recorded gate text. There is deliberately no form — live
 * enablement transitions are CLI/operator-owned and never permitted
 * from the UI (ADR-0011 decision 6). */
export function EnablementScreen() {
  const query = useSurface(['enablement'], api.enablement)

  return (
    <Page
      title="Enablement"
      description="Per-venue live-trading state from the approval ledger. Read-only: enablement transitions are operator-owned and never permitted from the UI."
    >
      <Surface query={query} title="Enablement">
        {(enablement) => (
          <div className="space-y-5">
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="flex items-center gap-2 text-base">
                  <KeyRound className="size-4" aria-hidden /> Venues
                  {!enablement.bound && (
                    <Badge variant="outline" className="text-[10px]">
                      ledger not bound
                    </Badge>
                  )}
                </CardTitle>
                <CardDescription>The approval ledger's current states.</CardDescription>
              </CardHeader>
              <CardContent className="space-y-2">
                {enablement.states.map(({ venue, state }) => (
                  <div key={venue} className="flex items-center justify-between gap-3">
                    <span className="text-sm">{venueLabel(venue)}</span>
                    <Badge
                      variant={state === 'enabled' ? 'default' : state === 'pending' ? 'secondary' : 'outline'}
                      className="font-mono text-[10px]"
                    >
                      {state}
                    </Badge>
                  </div>
                ))}
              </CardContent>
            </Card>
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-base">The recorded gate</CardTitle>
                <CardDescription>The exact text recorded at enablement time (ADR-0011 decision 6).</CardDescription>
              </CardHeader>
              <CardContent>
                <Notice>{enablement.gate_text}</Notice>
              </CardContent>
            </Card>
          </div>
        )}
      </Surface>
    </Page>
  )
}
