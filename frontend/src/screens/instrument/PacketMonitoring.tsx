import { useEffect, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { Button } from '@/components/ui/button'
import {
  api,
  type WatchConditionKind,
} from '@/lib/api'
import { usePreferences } from '@/lib/preferences'

interface PacketMonitoringProps {
  contextKey: string
  packetId: string | null
}

const FIXED_CONDITIONS: readonly WatchConditionKind[] = [
  'entry_zone',
  'invalidation',
  'data_stale',
  'forecast_drift',
]

type MonitoringState = Awaited<ReturnType<typeof api.packetMonitoring>>

const labelKey: Record<WatchConditionKind, 'screen.workspace.monitoringEntry' | 'screen.workspace.monitoringInvalidation' | 'screen.workspace.monitoringStale' | 'screen.workspace.monitoringDrift'> = {
  data_stale: 'screen.workspace.monitoringStale',
  entry_zone: 'screen.workspace.monitoringEntry',
  forecast_drift: 'screen.workspace.monitoringDrift',
  invalidation: 'screen.workspace.monitoringInvalidation',
}

export function PacketMonitoring({ contextKey, packetId }: PacketMonitoringProps) {
  const { t } = usePreferences()
  const queryClient = useQueryClient()
  const currentRequestContext = useRef({ contextKey, packetId })
  const [selectedKinds, setSelectedKinds] = useState<readonly WatchConditionKind[]>(FIXED_CONDITIONS)
  const [failedRequest, setFailedRequest] = useState<{ contextKey: string; packetId: string } | null>(null)
  currentRequestContext.current = { contextKey, packetId }
  useEffect(() => {
    setSelectedKinds(FIXED_CONDITIONS)
    setFailedRequest(null)
  }, [contextKey, packetId])

  const queryKey = ['packet-monitoring', contextKey, packetId] as const
  const query = useQuery({
    enabled: packetId !== null,
    queryFn: () => api.packetMonitoring(packetId!),
    queryKey,
    retry: false,
  })
  const check = useMutation({
    mutationFn: (requested: {
      contextKey: string
      kinds: readonly WatchConditionKind[]
      packetId: string
    }) => api.checkPacketMonitoring(requested.packetId, requested.kinds),
    mutationKey: ['check-packet-monitoring', contextKey, packetId],
    onSuccess: (state, requested) => {
      const current = currentRequestContext.current
      if (current.contextKey !== requested.contextKey || current.packetId !== requested.packetId) return
      queryClient.setQueryData(['packet-monitoring', requested.contextKey, requested.packetId], state)
      void queryClient.invalidateQueries({
        exact: true,
        queryKey: ['packet-outcome-review', requested.contextKey, requested.packetId],
      })
    },
    onError: (_error, requested) => setFailedRequest({
      contextKey: requested.contextKey,
      packetId: requested.packetId,
    }),
  })

  const state = query.data
  const registered = state?.registration ?? null
  const evaluation = state?.evaluation ?? null
  const loading = packetId !== null && (query.isPending || (
    check.isPending
    && check.variables.contextKey === contextKey
    && check.variables.packetId === packetId
  ))
  const unavailable = query.isError || (
    failedRequest?.contextKey === contextKey && failedRequest.packetId === packetId
  )
  const submit = () => {
    if (packetId === null) return
    check.mutate({ contextKey, kinds: registered ? registered.conditions.map((condition) => condition.kind) : selectedKinds, packetId })
  }

  return (
    <details className="min-w-0 border-y border-border py-3" data-testid="packet-monitoring" open>
      <summary className="mx-3 cursor-pointer text-sm font-semibold focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
        {t('screen.workspace.monitoring')}
      </summary>
      <div className="min-w-0 space-y-3 px-3 pt-3">
        <p className="text-xs leading-relaxed text-muted-foreground">
          {t('screen.workspace.monitoringAdvisory')}
        </p>
        {packetId === null ? (
          <>
            <p className="text-xs text-muted-foreground">{t('screen.workspace.monitoringSaveFirst')}</p>
            <Button disabled size="sm" type="button" variant="outline">
              {t('screen.workspace.monitoringSaveCheck')}
            </Button>
          </>
        ) : loading ? (
          <div className="space-y-2" role="status">
            <p className="text-xs text-muted-foreground">{t('screen.workspace.monitoringLoading')}</p>
            <div className="h-2 w-full animate-pulse bg-muted motion-reduce:animate-none" />
            <Button disabled size="sm" type="button" variant="outline">
              {registered ? t('screen.workspace.monitoringCheckNow') : t('screen.workspace.monitoringSaveCheck')}
            </Button>
          </div>
        ) : unavailable ? (
          <div className="space-y-2" role="status">
            <p className="text-xs leading-relaxed text-amber-800 dark:text-amber-300">
              {t('screen.workspace.monitoringUnavailable')}
            </p>
            <Button onClick={submit} size="sm" type="button" variant="outline">
              {registered ? t('screen.workspace.monitoringCheckNow') : t('screen.workspace.monitoringSaveCheck')}
            </Button>
          </div>
        ) : registered ? (
          <RegisteredMonitoring evaluation={evaluation} state={state} onCheck={submit} />
        ) : (
          <fieldset className="min-w-0 space-y-2">
            <legend className="sr-only">{t('screen.workspace.monitoring')}</legend>
            {FIXED_CONDITIONS.map((kind) => (
              <label className="flex min-w-0 items-start gap-2 text-xs" key={kind}>
                <input
                  checked={selectedKinds.includes(kind)}
                  className="mt-0.5 shrink-0 accent-sky-600"
                  onChange={() => setSelectedKinds((current) => (
                    current.includes(kind) ? current.filter((item) => item !== kind) : [...current, kind]
                  ))}
                  type="checkbox"
                />
                <span className="min-w-0 [overflow-wrap:anywhere]">{t(labelKey[kind])}</span>
              </label>
            ))}
            <Button disabled={selectedKinds.length === 0} onClick={submit} size="sm" type="button" variant="outline">
              {t('screen.workspace.monitoringSaveCheck')}
            </Button>
          </fieldset>
        )}
      </div>
    </details>
  )
}

function RegisteredMonitoring({
  evaluation,
  onCheck,
  state,
}: {
  evaluation: MonitoringState['evaluation']
  onCheck: () => void
  state: MonitoringState
}) {
  const { t } = usePreferences()
  const conditions = state.registration?.conditions ?? []
  const results = new Map((evaluation?.results ?? []).map((result) => [result.condition_id, result]))
  return (
    <div className="min-w-0 space-y-3">
      <dl className="min-w-0 divide-y divide-border border-y border-border text-xs">
        {conditions.map((condition) => {
          const result = results.get(condition.condition_id)
          return (
            <div className="min-w-0 space-y-1 py-2" key={condition.condition_id}>
              <dt className="font-medium">{t(labelKey[condition.kind])}</dt>
              <dd className="min-w-0 text-muted-foreground [overflow-wrap:anywhere]">
                {definitionText(condition.kind, condition.definition, t)}
              </dd>
              {result && (
                <dd className="min-w-0 flex flex-wrap items-baseline gap-x-2 gap-y-1">
                  <span className="font-medium">{stateText(result.state, t)}</span>
                  <span className="text-muted-foreground [overflow-wrap:anywhere]">{factsText(result.facts, t)}</span>
                </dd>
              )}
            </div>
          )
        })}
      </dl>
      <Button onClick={onCheck} size="sm" type="button" variant="outline">
        {t('screen.workspace.monitoringCheckNow')}
      </Button>
    </div>
  )
}

function definitionText(
  kind: WatchConditionKind,
  definition: NonNullable<MonitoringState['registration']>['conditions'][number]['definition'],
  t: ReturnType<typeof usePreferences>['t'],
) {
  if (kind === 'entry_zone') {
    if ('lower' in definition && 'upper' in definition) {
      return t('screen.workspace.monitoringDefinitionEntry', { lower: String(definition.lower), upper: String(definition.upper) })
    }
    return t('screen.workspace.monitoringUnavailable')
  }
  if (kind === 'invalidation') {
    if ('level' in definition) {
      return t('screen.workspace.monitoringDefinitionInvalidation', { level: String(definition.level) })
    }
    return t('screen.workspace.monitoringUnavailable')
  }
  if (kind === 'data_stale') {
    if ('calendar_id' in definition && 'maximum_completed_sessions' in definition) {
      return t('screen.workspace.monitoringDefinitionStale', {
        calendar: definition.calendar_id,
        sessions: String(definition.maximum_completed_sessions),
      })
    }
    return t('screen.workspace.monitoringUnavailable')
  }
  if ('risk_per_unit' in definition) {
    return t('screen.workspace.monitoringDefinitionDrift', { threshold: String(definition.risk_per_unit) })
  }
  return t('screen.workspace.monitoringUnavailable')
}

function factsText(
  facts: NonNullable<MonitoringState['evaluation']>['results'][number]['facts'],
  t: ReturnType<typeof usePreferences>['t'],
) {
  if ('current_price' in facts) return t('screen.workspace.monitoringFactPrice', { price: String(facts.current_price) })
  if ('completed_sessions' in facts) return t('screen.workspace.monitoringFactStale', { sessions: String(facts.completed_sessions) })
  if ('distance' in facts) {
    return t('screen.workspace.monitoringFactDrift', {
      distance: String(facts.distance),
      threshold: String(facts.threshold),
    })
  }
  return t('screen.workspace.monitoringFactUnavailable', { code: facts.code })
}

function stateText(
  state: 'armed' | 'not_triggered' | 'triggered' | 'not_comparable',
  t: ReturnType<typeof usePreferences>['t'],
) {
  const keys = {
    armed: 'screen.workspace.monitoringArmed',
    not_comparable: 'screen.workspace.monitoringNotComparable',
    not_triggered: 'screen.workspace.monitoringNotTriggered',
    triggered: 'screen.workspace.monitoringTriggered',
  } as const
  return t(keys[state])
}

export default PacketMonitoring
