import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { api, type InstrumentWorkspace, type PaperProposal } from '@/lib/api'
import { dateTime, money, moneyPrecise, quantity } from '@/lib/format'
import { ageText } from '@/lib/live'
import { usePreferences } from '@/lib/preferences'
import { evidenceText } from './evidence-copy'
import { ProposalConfirmation } from './ProposalConfirmation'

function errorText(error: unknown): string {
  return error instanceof Error ? error.message : String(error)
}

export function DecisionRail({
  evidenceUpdating = false,
  workspace,
}: {
  evidenceUpdating?: boolean
  workspace: InstrumentWorkspace
}) {
  const { locale, t } = usePreferences()
  const heldPosition = workspace.position !== null && workspace.position !== undefined
    && workspace.position.quantity !== 0
  const positionMarkStatus = workspace.position?.mark_status
  const finitePositionMark = typeof workspace.position?.mark === 'number'
    && Number.isFinite(workspace.position.mark)
  const positionMarkAvailable = !heldPosition || (
    positionMarkStatus?.status === 'available' && finitePositionMark
  )
  const valuationComplete = workspace.risk.valuation_complete === false
    ? false
    : workspace.risk.valuation_complete === true
      ? positionMarkAvailable
      : !heldPosition
  const valuationReason = workspace.risk.valuation_reason
    ?? (heldPosition
      ? positionMarkStatus === undefined
        ? t('screen.valuation.legacyReason')
        : positionMarkAvailable ? null : t('screen.valuation.invalidMark')
      : null)
  const [side, setSide] = useState<'buy' | 'sell'>('buy')
  const [quantityValue, setQuantityValue] = useState('10')
  const [limitPrice, setLimitPrice] = useState('')
  const [createdProposal, setCreatedProposal] = useState<{
    authority: InstrumentWorkspace['proposal']['proposals']
    proposal: PaperProposal
  } | null>(null)
  const [dismissedProposalIds, setDismissedProposalIds] = useState<readonly string[]>([])
  const visiblePersistedProposals = [...workspace.proposal.proposals]
    .reverse()
    .filter((candidate) => (
      !dismissedProposalIds.includes(candidate.id)
      && ['pending', 'blocked', 'confirmed', 'rejected'].includes(candidate.status)
    ))
  const resumedPendingProposal = visiblePersistedProposals.find(
    (candidate) => candidate.status === 'pending',
  ) ?? null
  const resumedProposal = resumedPendingProposal ?? visiblePersistedProposals[0] ?? null
  const localProposalStillExists = createdProposal !== null && workspace.proposal.proposals.some(
    (candidate) => candidate.id === createdProposal.proposal.id,
  )
  const localProposal = createdProposal !== null && (
    createdProposal.authority === workspace.proposal.proposals || localProposalStillExists
  ) ? createdProposal.proposal : null
  const proposal = localProposal?.status === 'pending'
    ? localProposal
    : resumedPendingProposal ?? localProposal ?? resumedProposal
  const forecast = workspace.forecast
  const numericQuantity = Number(quantityValue)
  const numericLimit = limitPrice.trim() === '' ? null : Number(limitPrice)
  const validInput = Number.isFinite(numericQuantity)
    && numericQuantity > 0
    && (numericLimit === null || (Number.isFinite(numericLimit) && numericLimit > 0))
  const actionAllowed = !evidenceUpdating
    && workspace.proposal.allowed
    && forecast?.eligible === true
    && validInput
  const create = useMutation({
    mutationFn: () => api.createPaperProposal({
      artifact_id: forecast!.artifact_id,
      limit_price: numericLimit,
      quantity: numericQuantity,
      side,
      symbol: workspace.instrument.symbol,
      venue: workspace.instrument.venue,
    }),
    onSuccess: (next) => {
      setDismissedProposalIds((current) => current.filter((id) => id !== next.id))
      setCreatedProposal({
        authority: workspace.proposal.proposals,
        proposal: next,
      })
    },
  })

  return (
    <div className="space-y-5">
      <div className="space-y-1 px-4">
        <h2 className="text-xs font-semibold uppercase tracking-widest text-muted-foreground">
          {t('screen.workspace.decision')}
        </h2>
        <p className="text-sm font-medium">{t('screen.workspace.paperOnly')}</p>
      </div>

      <section className="space-y-2 border-y border-border px-4 py-3" aria-label={t('screen.workspace.portfolioRisk')}>
        <h3 className="text-[10px] font-semibold uppercase tracking-widest text-muted-foreground">
          {t('screen.workspace.portfolioRisk')}
        </h3>
        <dl className="space-y-1 text-xs">
          <Fact label={t('screen.workspace.cash')} value={money(workspace.risk.cash, locale)} />
          <Fact label={t('screen.workspace.accountEquity')} value={valuationComplete ? money(workspace.risk.equity, locale) : t('screen.workspace.valueUnavailable')} />
          <Fact label={t('screen.workspace.position')} value={workspace.position === null ? t('screen.workspace.noPosition') : quantity(workspace.position.quantity, locale)} />
          <Fact label={t('screen.workspace.averageCost')} value={workspace.position === null ? '—' : moneyPrecise(workspace.position.average_cost, locale)} />
          <Fact label={t('screen.workspace.positionMark')} value={!positionMarkAvailable || workspace.position?.mark === null || workspace.position?.mark === undefined ? t('screen.workspace.valueUnavailable') : moneyPrecise(workspace.position.mark, locale)} />
          <Fact label={t('screen.workspace.unrealizedPnl')} value={!positionMarkAvailable || workspace.position?.unrealized_pnl === null || workspace.position?.unrealized_pnl === undefined ? t('screen.workspace.valueUnavailable') : money(workspace.position.unrealized_pnl, locale)} />
          <Fact label={t('screen.workspace.realizedPnl')} value={workspace.position === null ? '—' : money(workspace.position.realized_pnl, locale)} />
          {heldPosition && (
            <Fact
              label={t('screen.valuation.markStatus')}
              value={t(`screen.pnl.marks.status.${positionMarkStatus?.status ?? 'unavailable'}`)}
            />
          )}
          <Fact label={t('screen.workspace.maxOrderQuantity')} value={quantity(workspace.risk.max_order_quantity, locale)} />
          <Fact label={t('screen.workspace.maxNotional')} value={money(workspace.risk.max_notional, locale)} />
          <Fact label={t('screen.workspace.maxPositionQuantity')} value={quantity(workspace.risk.max_position_quantity, locale)} />
          <Fact label={t('screen.workspace.globalKillSwitch')} value={t(workspace.risk.global_kill_switch ? 'screen.workspace.switchEngaged' : 'screen.workspace.switchDisarmed')} />
          <Fact label={t('screen.workspace.venueKillSwitch')} value={t(workspace.risk.venue_kill_switch ? 'screen.workspace.switchEngaged' : 'screen.workspace.switchDisarmed')} />
          <Fact label={t('screen.workspace.quoteFreshness')} value={liveLabel(workspace.live.label, t)} />
          <Fact label={t('screen.workspace.quoteAge')} value={workspace.live.age_ms === null || workspace.live.age_ms === undefined ? t('screen.workspace.valueUnavailable') : ageText(workspace.live.age_ms, locale)} />
          <Fact label={t('screen.workspace.snapshotAsOf')} value={dateTime(workspace.generated_at, locale)} />
          <Fact label={t('screen.workspace.accountAuthority')} value={t('screen.workspace.localPaperKernel')} />
        </dl>
        {!valuationComplete && (
          <div className="rounded-lg border border-amber-500/40 bg-amber-500/5 px-2.5 py-2 text-xs" role="status">
            <p className="font-medium text-amber-700 dark:text-amber-300">
              {t('screen.valuation.incomplete')}
            </p>
            {valuationReason && <p className="mt-1 text-muted-foreground">{valuationReason}</p>}
            {positionMarkStatus?.reason && (
              <p className="mt-1 text-muted-foreground">{positionMarkStatus.reason}</p>
            )}
          </div>
        )}
      </section>

      {workspace.proposal.blockers.length > 0 && (
        <ul className="space-y-1 border-b border-border px-4 pb-3 text-xs text-destructive">
          {workspace.proposal.blockers.map((blocker) => (
            <li key={blocker} title={blocker}>{evidenceText(blocker, locale, t)}</li>
          ))}
        </ul>
      )}
      {evidenceUpdating && (
        <p className="px-4 text-xs text-sky-700 dark:text-sky-300" role="status">
          {t('screen.workspace.proposalWaitingForEvidence')}
        </p>
      )}

      {proposal === null ? (
        <section className="space-y-3 px-4" aria-label={t('screen.workspace.proposalForm')}>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-2">
              <Label htmlFor="proposal-side">{t('screen.workspace.side')}</Label>
              <select
                className="h-8 w-full rounded-lg border border-input bg-background px-2 text-sm"
                id="proposal-side"
                onChange={(event) => setSide(event.target.value as 'buy' | 'sell')}
                value={side}
              >
                <option value="buy">{t('screen.workspace.buy')}</option>
                <option value="sell">{t('screen.workspace.sell')}</option>
              </select>
            </div>
            <div className="space-y-2">
              <Label htmlFor="proposal-quantity">{t('screen.workspace.quantity')}</Label>
              <Input
                id="proposal-quantity"
                min="0"
                onChange={(event) => setQuantityValue(event.target.value)}
                step="any"
                type="number"
                value={quantityValue}
              />
            </div>
          </div>
          <div className="space-y-2">
            <Label htmlFor="proposal-limit">{t('screen.workspace.optionalLimit')}</Label>
            <Input
              id="proposal-limit"
              min="0"
              onChange={(event) => setLimitPrice(event.target.value)}
              placeholder={t('screen.workspace.marketOrderHint')}
              step="any"
              type="number"
              value={limitPrice}
            />
          </div>
          {create.isError && <p className="text-xs text-destructive" role="alert">{errorText(create.error)}</p>}
          <Button
            className="w-full"
            disabled={!actionAllowed || create.isPending}
            onClick={() => create.mutate()}
            type="button"
          >
            {create.isPending ? t('screen.workspace.creatingProposal') : t('screen.workspace.createProposal')}
          </Button>
        </section>
      ) : (
        <ProposalConfirmation
          key={`${proposal.id}:${proposal.status}:${proposal.order_id ?? ''}`}
          onDismiss={() => {
            setCreatedProposal(null)
            setDismissedProposalIds((current) => [...new Set([
              ...current,
              ...workspace.proposal.proposals
                .filter((candidate) => candidate.status !== 'pending')
                .map((candidate) => candidate.id),
              ...(proposal.status === 'pending' ? [] : [proposal.id]),
            ])])
          }}
          proposal={proposal}
        />
      )}
    </div>
  )
}

function liveLabel(
  label: string | null | undefined,
  t: ReturnType<typeof usePreferences>['t'],
): string {
  if (label === 'real') return t('live.label.real')
  if (label === 'delayed') return t('live.label.delayed')
  if (label === 'stale') return t('live.label.stale')
  if (label === 'synthetic') return t('live.label.synthetic')
  if (label === 'unavailable') return t('live.label.unavailable')
  return label ?? t('screen.workspace.valueUnavailable')
}

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between gap-3">
      <dt className="text-muted-foreground">{label}</dt>
      <dd className="max-w-44 text-right font-mono tabular-nums">{value}</dd>
    </div>
  )
}
