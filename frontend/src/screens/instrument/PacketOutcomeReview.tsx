import { useEffect, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { Button } from '@/components/ui/button'
import {
  api,
  type DecisionOutcomeReviewInput,
  type DecisionOutcomeReviewState,
} from '@/lib/api'
import { usePreferences } from '@/lib/preferences'

interface PacketOutcomeReviewProps {
  contextKey: string
  packetId: string | null
}

type Classification = DecisionOutcomeReviewInput['classification']
type Outcome = DecisionOutcomeReviewState['outcome']

const CLASSIFICATIONS: readonly Classification[] = [
  'supported',
  'challenged',
  'mixed',
  'inconclusive',
]

const classificationKeys = {
  challenged: 'screen.workspace.reviewChallenged',
  inconclusive: 'screen.workspace.reviewInconclusive',
  mixed: 'screen.workspace.reviewMixed',
  supported: 'screen.workspace.reviewSupported',
} as const

const statusKeys = {
  complete: 'screen.workspace.reviewStatus.complete',
  partial: 'screen.workspace.reviewStatus.partial',
  pending: 'screen.workspace.reviewStatus.pending',
  unavailable: 'screen.workspace.reviewStatus.unavailable',
} as const

const scenarioKeys = {
  base: 'screen.workspace.reviewScenario.base',
  bear: 'screen.workspace.reviewScenario.bear',
  bull: 'screen.workspace.reviewScenario.bull',
} as const

const paperKeys = {
  accepted_unfilled: 'screen.workspace.reviewPaper.accepted_unfilled',
  blocked: 'screen.workspace.reviewPaper.blocked',
  filled_open: 'screen.workspace.reviewPaper.filled_open',
  not_applicable: 'screen.workspace.reviewPaper.not_applicable',
  pending_no_order: 'screen.workspace.reviewPaper.pending_no_order',
  risk_rejected: 'screen.workspace.reviewPaper.risk_rejected',
  unavailable: 'screen.workspace.reviewPaper.unavailable',
  watch_only: 'screen.workspace.reviewPaper.watch_only',
} as const

const monitoringKeys = {
  coverage_incomplete: 'screen.workspace.reviewMonitoring.coverage_incomplete',
  no_trigger_recorded: 'screen.workspace.reviewMonitoring.no_trigger_recorded',
  not_applicable: 'screen.workspace.reviewMonitoring.not_applicable',
  not_monitored: 'screen.workspace.reviewMonitoring.not_monitored',
  triggered: 'screen.workspace.reviewMonitoring.triggered',
} as const

const orderingKeys = {
  ambiguous_same_bar: 'screen.workspace.reviewOrdering.ambiguous_same_bar',
  neither: 'screen.workspace.reviewOrdering.neither',
  stop_first: 'screen.workspace.reviewOrdering.stop_first',
  target_first: 'screen.workspace.reviewOrdering.target_first',
  unavailable: 'screen.workspace.reviewOrdering.unavailable',
} as const

export function PacketOutcomeReview({ contextKey, packetId }: PacketOutcomeReviewProps) {
  const { locale, t } = usePreferences()
  const queryClient = useQueryClient()
  const currentContext = useRef({ contextKey, packetId })
  const [classification, setClassification] = useState<Classification>('inconclusive')
  const [note, setNote] = useState('')
  const [failedContext, setFailedContext] = useState<string | null>(null)
  currentContext.current = { contextKey, packetId }

  useEffect(() => {
    setClassification('inconclusive')
    setNote('')
    setFailedContext(null)
  }, [contextKey, packetId])

  const queryKey = ['packet-outcome-review', contextKey, packetId] as const
  const query = useQuery({
    enabled: packetId !== null,
    queryFn: () => api.packetOutcomeReview(packetId!),
    queryKey,
    retry: false,
  })
  const save = useMutation({
    mutationFn: (requested: {
      contextKey: string
      input: DecisionOutcomeReviewInput
      packetId: string
    }) => api.savePacketOutcomeReview(requested.packetId, requested.input),
    mutationKey: ['save-packet-outcome-review', contextKey, packetId],
    onError: (_error, requested) => {
      if (
        currentContext.current.contextKey === requested.contextKey
        && currentContext.current.packetId === requested.packetId
      ) setFailedContext(`${requested.contextKey}:${requested.packetId}`)
    },
    onSuccess: (state, requested) => {
      if (
        currentContext.current.contextKey !== requested.contextKey
        || currentContext.current.packetId !== requested.packetId
        || state.packet_id !== requested.packetId
      ) return
      queryClient.setQueryData(
        ['packet-outcome-review', requested.contextKey, requested.packetId],
        state,
      )
      setFailedContext(null)
    },
  })

  const state = query.data?.packet_id === packetId ? query.data : null
  const outcome = state?.outcome ?? null
  const saved = state?.review ?? null
  const ownContext = packetId === null ? null : `${contextKey}:${packetId}`
  const unavailable = query.isError || failedContext === ownContext
  const loading = packetId !== null && (query.isPending || (
    save.isPending
    && save.variables.contextKey === contextKey
    && save.variables.packetId === packetId
  ))
  const complete = outcome?.evidence_status === 'complete'

  const submit = () => {
    if (packetId === null || outcome === null || saved !== null) return
    save.mutate({
      contextKey,
      input: {
        classification,
        expected_outcome_id: outcome.outcome_id,
        note: note.trim() || null,
      },
      packetId,
    })
  }

  return (
    <details
      className="min-w-0 border-y border-border py-3"
      data-testid="packet-outcome-review"
      open
    >
      <summary className="mx-3 cursor-pointer text-sm font-semibold focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
        {t('screen.workspace.review')}
      </summary>
      <div className="min-w-0 space-y-3 px-3 pt-3">
        <p className="text-xs leading-relaxed text-muted-foreground">
          {t('screen.workspace.reviewAdvisory')}
        </p>
        {packetId === null ? (
          <p className="text-xs text-muted-foreground">{t('screen.workspace.reviewSaveFirst')}</p>
        ) : unavailable ? (
          <p className="text-xs text-destructive" role="alert">
            {t('screen.workspace.reviewUnavailable')}
          </p>
        ) : loading && outcome === null ? (
          <p className="text-xs text-muted-foreground" role="status">
            {t('screen.workspace.reviewLoading')}
          </p>
        ) : outcome !== null ? (
          <>
            <OutcomeEvidence locale={locale} outcome={outcome} />
            {saved === null ? (
              <form className="min-w-0 space-y-3" onSubmit={(event) => {
                event.preventDefault()
                submit()
              }}>
                <label className="block min-w-0 space-y-1 text-xs">
                  <span className="font-medium">{t('screen.workspace.reviewClassification')}</span>
                  <select
                    className="h-9 w-full rounded-md border border-input bg-background px-3 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                    disabled={loading}
                    onChange={(event) => setClassification(event.target.value as Classification)}
                    value={classification}
                  >
                    {CLASSIFICATIONS.map((value) => (
                      <option disabled={!complete && value !== 'inconclusive'} key={value} value={value}>
                        {t(classificationKeys[value])}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="block min-w-0 space-y-1 text-xs">
                  <span className="font-medium">{t('screen.workspace.reviewNote')}</span>
                  <textarea
                    className="min-h-20 w-full resize-y rounded-md border border-input bg-background px-3 py-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                    disabled={loading}
                    maxLength={2000}
                    onChange={(event) => setNote(event.target.value)}
                    value={note}
                  />
                </label>
                <Button disabled={loading} size="sm" type="submit">
                  {t('screen.workspace.reviewSave')}
                </Button>
              </form>
            ) : (
              <section className="min-w-0 space-y-2 border-t border-border pt-3" aria-label={t('screen.workspace.reviewSaved')}>
                <p className="text-sm font-semibold">{t('screen.workspace.reviewSaved')}</p>
                <dl className="min-w-0 space-y-2 text-xs">
                  <Fact label={t('screen.workspace.reviewId')} value={saved.review_id} mono />
                  <Fact
                    label={t('screen.workspace.reviewClassification')}
                    value={t(classificationKeys[saved.classification])}
                  />
                  {saved.note !== null && <Fact label={t('screen.workspace.reviewNote')} value={saved.note} />}
                </dl>
              </section>
            )}
          </>
        ) : null}
      </div>
    </details>
  )
}

function OutcomeEvidence({ locale, outcome }: { locale: string, outcome: Outcome }) {
  const { t } = usePreferences()
  const formatTime = (value: string | null | undefined) => value
    ? new Intl.DateTimeFormat(locale, { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value))
    : t('screen.workspace.reviewUnavailableValue')
  const observation = (state: 'observed' | 'not_observed' | 'unavailable') => ({
    not_observed: t('screen.workspace.reviewNotObserved'),
    observed: t('screen.workspace.reviewObserved'),
    unavailable: t('screen.workspace.reviewUnavailableValue'),
  })[state]
  return (
    <div className="min-w-0 space-y-3">
      <p className="text-xs font-medium">{t(statusKeys[outcome.evidence_status])}</p>
      <dl className="min-w-0 divide-y divide-border border-y border-border text-xs">
        <Fact label={t('screen.workspace.reviewOutcomeId')} value={outcome.outcome_id} mono />
        <Fact label={t('screen.workspace.reviewHorizon')} value={formatTime(outcome.horizon_target_at)} />
        <Fact label={t('screen.workspace.reviewEvaluated')} value={formatTime(outcome.evaluated_at)} />
      </dl>
      <ul className="min-w-0 divide-y divide-border border-y border-border text-xs">
        {outcome.scenarios.map((scenario) => (
          <li className="min-w-0 space-y-1 py-2" key={scenario.kind}>
            <span className="font-medium">
              {t('screen.workspace.reviewScenario', {
                kind: t(scenarioKeys[scenario.kind]),
                threshold: String(scenario.threshold),
              })}
            </span>
            <span className="block text-muted-foreground">
              {observation(scenario.threshold_state)}
              {scenario.threshold_at === null ? '' : ` · ${formatTime(scenario.threshold_at)}`}
            </span>
          </li>
        ))}
      </ul>
      <dl className="min-w-0 divide-y divide-border border-y border-border text-xs">
        <Fact label={t('screen.workspace.reviewPaper')} value={t(paperKeys[outcome.paper.state])} />
        {outcome.paper.reason !== null && <Fact label={t('screen.workspace.reviewUnavailableValue')} value={outcome.paper.reason} />}
        <Fact label={t('screen.workspace.reviewMonitoring')} value={t(monitoringKeys[outcome.monitoring.status])} />
        <Fact label={t('screen.workspace.reviewOrdering')} value={t(orderingKeys[outcome.target_stop_ordering])} />
      </dl>
      <dl className="min-w-0 divide-y divide-border border-y border-border text-xs">
        <Metric label={t('screen.workspace.reviewPlannedR')} value={outcome.planned_reward_to_risk} />
        <Metric label={t('screen.workspace.reviewGrossR')} metric={outcome.gross_path_r} />
        <Metric label={t('screen.workspace.reviewEntryR')} metric={outcome.entry_fill_deviation_r} />
        <Metric label={t('screen.workspace.reviewMarkR')} metric={outcome.mark_to_market_paper_r} />
        <Metric label={t('screen.workspace.reviewRealizedR')} metric={outcome.realized_paper_r} />
      </dl>
    </div>
  )
}

function Fact({ label, mono = false, value }: { label: string, mono?: boolean, value: string }) {
  return (
    <div className="flex min-w-0 flex-wrap justify-between gap-x-3 gap-y-1 py-2">
      <dt className="text-muted-foreground">{label}</dt>
      <dd className={`min-w-0 max-w-full text-right [overflow-wrap:anywhere] ${mono ? 'font-mono' : ''}`}>
        {value}
      </dd>
    </div>
  )
}

function Metric({
  label,
  metric,
  value,
}: {
  label: string
  metric?: Outcome['gross_path_r']
  value?: number
}) {
  const { t } = usePreferences()
  const available = value ?? (metric?.status === 'available' ? metric.value : null)
  return (
    <div className="flex min-w-0 flex-wrap justify-between gap-x-3 gap-y-1 py-2">
      <dt className="text-muted-foreground">{label}</dt>
      <dd
        className="min-w-0 max-w-full text-right font-mono tabular-nums [overflow-wrap:anywhere]"
        title={metric?.reason ?? undefined}
      >
        {available === null || available === undefined
          ? t('screen.workspace.reviewUnavailableValue')
          : `${available.toFixed(2)} R`}
      </dd>
    </div>
  )
}

export default PacketOutcomeReview
