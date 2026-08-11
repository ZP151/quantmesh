import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { api, type InstrumentWorkspace, type PaperProposal } from '@/lib/api'
import { money, moneyPrecise, quantity } from '@/lib/format'
import { ageText } from '@/lib/live'
import { usePreferences } from '@/lib/preferences'
import { ProposalConfirmation } from './ProposalConfirmation'

function errorText(error: unknown): string {
  return error instanceof Error ? error.message : String(error)
}

export function DecisionRail({ workspace }: { workspace: InstrumentWorkspace }) {
  const { locale, t } = usePreferences()
  const [side, setSide] = useState<'buy' | 'sell'>('buy')
  const [quantityValue, setQuantityValue] = useState('10')
  const [limitPrice, setLimitPrice] = useState('')
  const [createdProposal, setCreatedProposal] = useState<{
    authority: InstrumentWorkspace['proposal']['proposals']
    proposal: PaperProposal
  } | null>(null)
  const resumedProposal = [...workspace.proposal.proposals]
    .reverse()
    .find((candidate) => candidate.status === 'pending') ?? null
  const localProposal = createdProposal?.authority === workspace.proposal.proposals
    ? createdProposal.proposal
    : null
  const proposal = localProposal ?? resumedProposal
  const forecast = workspace.forecast
  const numericQuantity = Number(quantityValue)
  const numericLimit = limitPrice.trim() === '' ? null : Number(limitPrice)
  const validInput = Number.isFinite(numericQuantity)
    && numericQuantity > 0
    && (numericLimit === null || (Number.isFinite(numericLimit) && numericLimit > 0))
  const actionAllowed = workspace.proposal.allowed && forecast?.eligible === true && validInput
  const create = useMutation({
    mutationFn: () => api.createPaperProposal({
      artifact_id: forecast!.artifact_id,
      limit_price: numericLimit,
      quantity: numericQuantity,
      side,
      symbol: workspace.instrument.symbol,
      venue: workspace.instrument.venue,
    }),
    onSuccess: (next) => setCreatedProposal({
      authority: workspace.proposal.proposals,
      proposal: next,
    }),
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
          <Fact label={t('screen.workspace.accountEquity')} value={money(workspace.risk.equity, locale)} />
          <Fact label={t('screen.workspace.position')} value={workspace.position === null ? t('screen.workspace.noPosition') : quantity(workspace.position.quantity, locale)} />
          <Fact label={t('screen.workspace.averageCost')} value={workspace.position === null ? '—' : moneyPrecise(workspace.position.average_cost, locale)} />
          <Fact label={t('screen.workspace.positionMark')} value={workspace.position?.mark === null || workspace.position?.mark === undefined ? t('screen.workspace.valueUnavailable') : moneyPrecise(workspace.position.mark, locale)} />
          <Fact label={t('screen.workspace.unrealizedPnl')} value={workspace.position?.unrealized_pnl === null || workspace.position?.unrealized_pnl === undefined ? t('screen.workspace.valueUnavailable') : money(workspace.position.unrealized_pnl, locale)} />
          <Fact label={t('screen.workspace.realizedPnl')} value={workspace.position === null ? '—' : money(workspace.position.realized_pnl, locale)} />
          <Fact label={t('screen.workspace.maxOrderQuantity')} value={quantity(workspace.risk.max_order_quantity, locale)} />
          <Fact label={t('screen.workspace.maxNotional')} value={money(workspace.risk.max_notional, locale)} />
          <Fact label={t('screen.workspace.maxPositionQuantity')} value={quantity(workspace.risk.max_position_quantity, locale)} />
          <Fact label={t('screen.workspace.globalKillSwitch')} value={t(workspace.risk.global_kill_switch ? 'screen.workspace.switchEngaged' : 'screen.workspace.switchDisarmed')} />
          <Fact label={t('screen.workspace.venueKillSwitch')} value={t(workspace.risk.venue_kill_switch ? 'screen.workspace.switchEngaged' : 'screen.workspace.switchDisarmed')} />
          <Fact label={t('screen.workspace.quoteFreshness')} value={liveLabel(workspace.live.label, t)} />
          <Fact label={t('screen.workspace.quoteAge')} value={workspace.live.age_ms === null || workspace.live.age_ms === undefined ? t('screen.workspace.valueUnavailable') : ageText(workspace.live.age_ms)} />
        </dl>
      </section>

      {workspace.proposal.blockers.length > 0 && (
        <ul className="space-y-1 border-b border-border px-4 pb-3 text-xs text-destructive">
          {workspace.proposal.blockers.map((blocker) => <li key={blocker}>{blocker}</li>)}
        </ul>
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
