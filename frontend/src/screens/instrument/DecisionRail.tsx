import { useEffect, useRef, useState } from 'react'
import { useMutation } from '@tanstack/react-query'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  api,
  type DecisionPacket,
  type DecisionPacketActionResult,
  type InstrumentWorkspace,
} from '@/lib/api'
import { money, moneyPrecise, number, quantity } from '@/lib/format'
import { usePreferences } from '@/lib/preferences'
import { ProposalConfirmation } from './ProposalConfirmation'

function errorText(error: unknown): string {
  return error instanceof Error ? error.message : String(error)
}

interface DecisionRailProps {
  contextKey?: string
  evidenceUpdating?: boolean
  onNewAnalysis?: () => void
  packet?: DecisionPacket
  packetSource?: 'fresh' | 'persisted'
  workspace: InstrumentWorkspace
}

export function DecisionRail(props: DecisionRailProps) {
  const packet = props.packet ?? props.workspace.decision.latest ?? props.workspace.decision.draft
  const contextKey = props.contextKey
    ?? `${packet.instrument.venue}:${packet.instrument.symbol}:${packet.selected_range}`
  const packetSource = props.packetSource
    ?? (props.workspace.decision.latest?.packet_id === packet.packet_id ? 'persisted' : 'fresh')
  return (
    <DecisionRailContext
      {...props}
      contextKey={contextKey}
      key={contextKey}
      packet={packet}
      packetSource={packetSource}
    />
  )
}

function DecisionRailContext({
  contextKey: contextKeyOverride,
  evidenceUpdating = false,
  onNewAnalysis,
  packet: packetOverride,
  packetSource: packetSourceOverride,
  workspace,
}: {
  contextKey: string
  evidenceUpdating?: boolean
  onNewAnalysis?: () => void
  packet: DecisionPacket
  packetSource: 'fresh' | 'persisted'
  workspace: InstrumentWorkspace
}) {
  const { locale, t } = usePreferences()
  const packet = packetOverride
  const contextKey = contextKeyOverride
  const packetSource = packetSourceOverride
  const [actionResult, setActionResult] = useState<DecisionPacketActionResult | null>(null)
  const displayedPacket = actionResult?.packet ?? packet
  const [side, setSide] = useState<'buy' | 'sell'>('buy')
  const [quantityValue, setQuantityValue] = useState(String(packet.risk_plan.suggested_quantity ?? ''))
  const [limitPrice, setLimitPrice] = useState(String(packet.risk_plan.entry_price))
  const [operatorReason, setOperatorReason] = useState('')
  const [dismissedProposalIds, setDismissedProposalIds] = useState<readonly string[]>([])
  const heldPosition = workspace.position !== null && workspace.position !== undefined
    && workspace.position.quantity !== 0
  const positionMarkAvailable = !heldPosition || (
    workspace.position?.mark_status?.status === 'available'
    && typeof workspace.position.mark === 'number'
    && Number.isFinite(workspace.position.mark)
  )
  const valuationComplete = workspace.risk.valuation_complete === false
    ? false
    : workspace.risk.valuation_complete === true
      ? positionMarkAvailable
      : !heldPosition
  const valuationReason = workspace.risk.valuation_reason
    ?? workspace.position?.mark_status?.reason
  const viewIdentity = {
    contextKey,
    packetId: packet.packet_id,
    range: packet.selected_range,
    source: packetSource,
    symbol: packet.instrument.symbol,
    venue: packet.instrument.venue,
  } as const
  const viewIdentityRef = useRef(viewIdentity)
  const activeRef = useRef(true)
  viewIdentityRef.current = viewIdentity
  useEffect(() => {
    activeRef.current = true
    return () => {
      activeRef.current = false
    }
  }, [])

  const numericQuantity = Number(quantityValue)
  const numericLimit = limitPrice.trim() === '' ? null : Number(limitPrice)
  const validPaperInput = Number.isFinite(numericQuantity)
    && numericQuantity > 0
    && (numericLimit === null || (Number.isFinite(numericLimit) && numericLimit > 0))
  const isDraft = displayedPacket.disposition === 'draft'
  const reasonReady = operatorReason.trim().length > 0
  const paperAllowed = isDraft
    && !evidenceUpdating
    && displayedPacket.paper_capability.allowed
    && validPaperInput

  const action = useMutation({
    mutationFn: async (submission: ActionSubmission) => {
      const parent = submission.identity.source === 'persisted'
        ? submission.packet
        : await api.saveDecisionPacket({
            expected_packet_id: submission.packet.packet_id,
            selected_range: submission.identity.range,
            symbol: submission.identity.symbol,
            venue: submission.identity.venue,
          })
      if (!activeRef.current || !sameContext(viewIdentityRef.current, submission.identity)) return null
      assertSavedPacket(parent, submission)
      const result = await api.applyDecisionPacketAction(parent.packet_id, submission.disposition === 'paper_proposal'
        ? {
            disposition: submission.disposition,
            limit_price: submission.limitPrice,
            operator_reason: null,
            quantity: submission.quantity,
            side: submission.side,
          }
        : {
            disposition: submission.disposition,
            limit_price: null,
            operator_reason: submission.operatorReason,
            quantity: null,
            side: null,
          })
      if (!activeRef.current || !sameContext(viewIdentityRef.current, submission.identity)) return null
      assertActionResult(result, parent, submission)
      return result
    },
    onSuccess: (result) => {
      if (result !== null) setActionResult(result)
    },
  })

  const submitAction = (disposition: ActionDisposition) => {
    if (evidenceUpdating) return
    action.mutate({
      disposition,
      identity: viewIdentity,
      limitPrice: numericLimit,
      operatorReason: operatorReason.trim(),
      packet,
      quantity: numericQuantity,
      side,
    })
  }

  const persistedProposals = [...workspace.proposal.proposals]
    .reverse()
    .filter((candidate) => !dismissedProposalIds.includes(candidate.id)
      && candidate.instrument.venue === displayedPacket.instrument.venue
      && candidate.instrument.symbol === displayedPacket.instrument.symbol)
  const proposal = actionResult?.proposal
    ?? persistedProposals.find((candidate) => candidate.id === displayedPacket.proposal_id)
    ?? null

  return (
    <div className="min-w-0 space-y-5">
      <div className="space-y-2 px-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-xs font-semibold uppercase tracking-widest text-muted-foreground">
            {t('screen.workspace.decision')}
          </h2>
          <span className="rounded-lg bg-muted px-2 py-1 text-[10px] font-semibold uppercase tracking-wider" data-testid="decision-phase">
            {phaseText(displayedPacket, t)}
          </span>
        </div>
        <p className="text-xs text-muted-foreground">{t('screen.workspace.paperOnly')}</p>
        {evidenceUpdating && (
          <p className="border-l-2 border-sky-600 bg-sky-500/5 px-2.5 py-2 text-xs text-muted-foreground" role="status">
            {t('screen.workspace.workspaceActionsPaused')}
          </p>
        )}
        <div className="min-w-0 border-y border-border py-2">
          <p className="text-[10px] uppercase tracking-wider text-muted-foreground">{t('screen.workspace.packetId')}</p>
          <code className="block break-all font-mono text-[10px] [overflow-wrap:anywhere]" title={displayedPacket.packet_id}>{displayedPacket.packet_id}</code>
        </div>
        {packetSource === 'persisted' && onNewAnalysis && (
          <Button className="w-full" onClick={onNewAnalysis} type="button" variant="outline">{t('screen.workspace.newAnalysis')}</Button>
        )}
      </div>

      <section className="space-y-3 border-y border-border px-4 py-3" aria-label={t('screen.workspace.riskPlan')}>
        <h3 className="text-xs font-semibold uppercase tracking-widest text-muted-foreground">{t('screen.workspace.riskPlan')}</h3>
        <dl className="space-y-1 text-xs">
          <Fact label={t('screen.workspace.entry')} value={moneyPrecise(displayedPacket.risk_plan.entry_price, locale)} />
          <Fact label={t('screen.workspace.stop')} value={moneyPrecise(displayedPacket.risk_plan.stop_price, locale)} />
          <Fact label={t('screen.workspace.target')} value={moneyPrecise(displayedPacket.risk_plan.target_price, locale)} />
          <Fact label={t('screen.workspace.rMultiple')} value={number(displayedPacket.risk_plan.reward_to_risk, locale)} />
          <Fact label={t('screen.workspace.paperSize')} value={quantity(displayedPacket.risk_plan.suggested_quantity, locale)} />
          <Fact label={t('screen.workspace.paperNotional')} value={money(displayedPacket.risk_plan.suggested_notional, locale)} />
        </dl>
        <dl className="space-y-1 border-t border-border pt-2 text-xs">
          <Fact label={t('screen.workspace.fees')} value={`${number(displayedPacket.evidence.costs.fee_bps, locale)} bps`} />
          <Fact label={t('screen.workspace.slippage')} value={`${number(displayedPacket.evidence.costs.slippage_bps, locale)} bps`} />
        </dl>
        <p className="text-[10px] text-muted-foreground">{t('screen.workspace.spreadAtConfirmation')}</p>
      </section>

      <section className="space-y-2 px-4" aria-label={t('screen.workspace.portfolioRisk')}>
        <h3 className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">{t('screen.workspace.portfolioRisk')}</h3>
        <dl className="space-y-1 text-xs">
          <Fact label={t('screen.workspace.accountEquity')} value={valuationComplete ? money(workspace.risk.equity, locale) : t('screen.workspace.valueUnavailable')} />
          <Fact label={t('screen.workspace.unrealizedPnl')} value={!positionMarkAvailable ? t('screen.workspace.valueUnavailable') : money(workspace.position?.unrealized_pnl, locale)} />
          <Fact label={t('screen.workspace.cash')} value={money(workspace.risk.cash, locale)} />
          <Fact label={t('screen.workspace.globalKillSwitch')} value={t(workspace.risk.global_kill_switch ? 'screen.workspace.switchEngaged' : 'screen.workspace.switchDisarmed')} />
          <Fact label={t('screen.workspace.venueKillSwitch')} value={t(workspace.risk.venue_kill_switch ? 'screen.workspace.switchEngaged' : 'screen.workspace.switchDisarmed')} />
          {heldPosition && <Fact label={t('screen.valuation.markStatus')} value={t(`screen.pnl.marks.status.${workspace.position?.mark_status?.status ?? 'unavailable'}`)} />}
        </dl>
        {!valuationComplete && (
          <div className="rounded-lg bg-amber-500/10 px-2.5 py-2 text-xs" role="status">
            <p className="font-medium text-amber-800 dark:text-amber-300">{t('screen.valuation.incomplete')}</p>
            {valuationReason && <p className="mt-1 text-muted-foreground">{valuationReason}</p>}
            {workspace.position?.mark_status?.reason && workspace.position.mark_status.reason !== valuationReason && (
              <p className="mt-1 text-muted-foreground">{workspace.position.mark_status.reason}</p>
            )}
          </div>
        )}
      </section>

      {displayedPacket.paper_capability.blockers.length > 0 && (
        <section className="space-y-2 px-4" aria-label={t('screen.workspace.paperBlockers')}>
          <h3 className="text-[10px] font-semibold uppercase tracking-wider text-destructive">{t('screen.workspace.paperBlockers')}</h3>
          <ul className="space-y-2 text-xs" role="status">
            {displayedPacket.paper_capability.blockers.map((blocker) => (
              <li className="rounded-lg bg-destructive/10 px-2.5 py-2" key={blocker.code}>
                <span className="font-mono text-[10px] uppercase text-destructive">{blocker.code}</span>
                <p className="mt-1 text-foreground" title={blocker.message}>{blocker.message}</p>
              </li>
            ))}
          </ul>
        </section>
      )}

      {isDraft && proposal === null && (
        <section className="min-w-0 space-y-3 px-4" aria-label={t('screen.workspace.packetActions')}>
          <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">{t('screen.workspace.phase.draft')}</p>
          <div className="space-y-2">
            <Label htmlFor="decision-reason">{t('screen.workspace.decisionReason')}</Label>
            <Input id="decision-reason" onChange={(event) => setOperatorReason(event.target.value)} placeholder={t('screen.workspace.decisionReasonHint')} value={operatorReason} />
          </div>
          <div className="grid grid-cols-2 gap-2">
            <Button disabled={!reasonReady || evidenceUpdating || action.isPending} onClick={() => submitAction('reject')} type="button" variant="outline">{t('screen.workspace.rejectDecision')}</Button>
            <Button disabled={!reasonReady || evidenceUpdating || action.isPending} onClick={() => submitAction('watch')} type="button" variant="outline">{t('screen.workspace.watchDecision')}</Button>
          </div>
          <div className="grid grid-cols-2 gap-3 border-t border-border pt-3">
            <div className="space-y-2">
              <Label htmlFor="proposal-side">{t('screen.workspace.side')}</Label>
              <select className="h-8 w-full min-w-0 rounded-lg border border-input bg-background px-2 text-sm outline-none focus-visible:ring-3 focus-visible:ring-ring/50" id="proposal-side" onChange={(event) => setSide(event.target.value as 'buy' | 'sell')} value={side}>
                <option value="buy">{t('screen.workspace.buy')}</option>
                <option value="sell">{t('screen.workspace.sell')}</option>
              </select>
            </div>
            <div className="space-y-2">
              <Label htmlFor="proposal-quantity">{t('screen.workspace.quantity')}</Label>
              <Input id="proposal-quantity" min="0" onChange={(event) => setQuantityValue(event.target.value)} step="any" type="number" value={quantityValue} />
            </div>
          </div>
          <div className="space-y-2">
            <Label htmlFor="proposal-limit">{t('screen.workspace.optionalLimit')}</Label>
            <Input id="proposal-limit" min="0" onChange={(event) => setLimitPrice(event.target.value)} step="any" type="number" value={limitPrice} />
          </div>
          {evidenceUpdating && <p className="text-xs text-muted-foreground" role="status">{t('screen.workspace.proposalWaitingForEvidence')}</p>}
          {action.isError && <p className="text-xs text-destructive" role="alert">{errorText(action.error)}</p>}
          <Button className="w-full" disabled={!paperAllowed || action.isPending} onClick={() => submitAction('paper_proposal')} type="button">
            {action.isPending ? t('screen.workspace.creatingProposal') : t('screen.workspace.createProposal')}
          </Button>
        </section>
      )}

      {proposal && (
        <ProposalConfirmation
          key={`${proposal.id}:${proposal.status}:${proposal.order_id ?? ''}`}
          contextKey={contextKey}
          interactionBlocked={evidenceUpdating}
          onDismiss={() => {
            setActionResult(null)
            setDismissedProposalIds((current) => [...new Set([...current, proposal.id])])
          }}
          packetId={displayedPacket.packet_id}
          proposal={proposal}
        />
      )}
    </div>
  )
}

type ActionDisposition = 'reject' | 'watch' | 'paper_proposal'

interface ViewIdentity {
  contextKey: string
  packetId: string
  range: DecisionPacket['selected_range']
  source: 'fresh' | 'persisted'
  symbol: string
  venue: DecisionPacket['instrument']['venue']
}

interface ActionSubmission {
  disposition: ActionDisposition
  identity: ViewIdentity
  limitPrice: number | null
  operatorReason: string
  packet: DecisionPacket
  quantity: number
  side: 'buy' | 'sell'
}

function sameContext(current: ViewIdentity, submitted: ViewIdentity): boolean {
  return current.contextKey === submitted.contextKey
    && current.range === submitted.range
    && current.symbol === submitted.symbol
    && current.venue === submitted.venue
}

function assertSavedPacket(saved: DecisionPacket, submission: ActionSubmission): void {
  if (
    saved.packet_id !== submission.identity.packetId
    || saved.instrument.venue !== submission.identity.venue
    || saved.instrument.symbol !== submission.identity.symbol
    || saved.selected_range !== submission.identity.range
  ) {
    throw new Error('Saved DecisionPacket does not match the displayed packet context.')
  }
}

function assertActionResult(
  result: DecisionPacketActionResult,
  parent: DecisionPacket,
  submission: ActionSubmission,
): void {
  const child = result.packet
  const contextMatches = child.parent_packet_id === parent.packet_id
    && child.instrument.venue === submission.identity.venue
    && child.instrument.symbol === submission.identity.symbol
    && child.selected_range === submission.identity.range
    && child.disposition === submission.disposition
  const proposalMatches = submission.disposition !== 'paper_proposal'
    ? result.proposal === null || result.proposal === undefined
    : result.proposal !== null
      && result.proposal !== undefined
      && child.proposal_id === result.proposal.id
      && result.proposal.instrument.venue === submission.identity.venue
      && result.proposal.instrument.symbol === submission.identity.symbol
  if (!contextMatches || !proposalMatches) {
    throw new Error('Decision action response does not match the displayed packet context.')
  }
}

function phaseText(packet: DecisionPacket, t: ReturnType<typeof usePreferences>['t']): string {
  if (packet.disposition === 'watch') return t('screen.workspace.phase.watching')
  if (packet.disposition === 'paper_proposal') return t('screen.workspace.phase.paperProposed')
  if (packet.disposition === 'reject') return t('screen.workspace.phase.rejected')
  return t(packet.paper_capability.allowed ? 'screen.workspace.phase.ready' : 'screen.workspace.phase.blocked')
}

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex min-w-0 justify-between gap-3">
      <dt className="shrink-0 text-muted-foreground">{label}</dt>
      <dd className="min-w-0 break-all text-right font-mono tabular-nums [overflow-wrap:anywhere]">{value}</dd>
    </div>
  )
}
