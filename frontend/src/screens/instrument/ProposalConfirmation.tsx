import { useEffect, useRef, useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router-dom'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  ProposalRefusalError,
  api,
  type PaperProposal,
  type ProposalConfirmation as ProposalConfirmationResult,
} from '@/lib/api'
import { dateTime, moneyPrecise, quantity } from '@/lib/format'
import { usePreferences } from '@/lib/preferences'
import { evidenceText } from './evidence-copy'

function errorText(error: unknown): string {
  if (error instanceof ProposalRefusalError) return error.result.blocker ?? error.message
  return error instanceof Error ? error.message : String(error)
}

export function ProposalConfirmation({
  contextKey,
  interactionBlocked = false,
  onDismiss,
  packetId,
  proposal,
}: {
  contextKey?: string
  interactionBlocked?: boolean
  onDismiss: () => void
  packetId?: string
  proposal: PaperProposal
}) {
  const { locale, t } = usePreferences()
  const queryClient = useQueryClient()
  const [confirmationToken, setConfirmationToken] = useState('')
  const [result, setResult] = useState<ProposalConfirmationResult | null>(null)
  const confirmationIdentity = {
    contextKey: contextKey ?? `${proposal.instrument.venue}:${proposal.instrument.symbol}`,
    proposalId: proposal.id,
    symbol: proposal.instrument.symbol,
    venue: proposal.instrument.venue,
  }
  const identityRef = useRef(confirmationIdentity)
  const activeRef = useRef(true)
  identityRef.current = confirmationIdentity
  useEffect(() => {
    activeRef.current = true
    return () => {
      activeRef.current = false
    }
  }, [])
  const effectiveProposal = result?.proposal ?? proposal
  const proposalBlocked = effectiveProposal.status !== 'pending' || effectiveProposal.blockers.length > 0
  const confirmation = useMutation({
    mutationFn: async () => {
      const submitted = confirmationIdentity
      try {
        const next = await api.confirmPaperProposal(proposal.id, confirmationToken)
        if (!activeRef.current || !sameConfirmationIdentity(identityRef.current, submitted)) return null
        assertConfirmationResult(next, submitted)
        return next
      } catch (error) {
        if (!(error instanceof ProposalRefusalError)) throw error
        if (!activeRef.current || !sameConfirmationIdentity(identityRef.current, submitted)) return null
        assertConfirmationResult(error.result, submitted)
        return error.result
      }
    },
    onSuccess: (next) => {
      if (next === null) return
      setResult(next)
      void Promise.all(
        ['instrument-workspace', 'orders', 'positions', 'pnl', 'audit', 'packet-outcome-review'].map((key) =>
          queryClient.invalidateQueries({ queryKey: [key] }),
        ),
      )
    },
  })
  const confirmationError = confirmationErrorText(result, confirmation.error)

  if (
    effectiveProposal.status === 'confirmed'
    && effectiveProposal.order_id !== null
    && effectiveProposal.order_id !== undefined
  ) {
    const order = result?.order
    return (
      <section className="space-y-3 border-t border-border px-4 pt-4" aria-live="polite">
        <p className="text-sm font-semibold text-emerald-800 dark:text-emerald-400">
          {t('screen.workspace.orderCreated')}
        </p>
        <dl className="space-y-1 text-xs">
          {packetId && <Fact label={t('screen.workspace.packetId')} value={packetId} />}
          <Fact label={t('screen.workspace.proposalId')} value={effectiveProposal.id} />
          <Fact label={t('screen.workspace.orderId')} value={effectiveProposal.order_id} />
          {order !== null && order !== undefined && (
            <Fact label={t('screen.workspace.orderStatus')} value={orderStatus(order.status, t)} />
          )}
          {order !== null && order !== undefined && (
            <Fact label={t('screen.workspace.filledQuantity')} value={quantity(order.filled_quantity, locale)} />
          )}
          <Fact
            label={t('screen.workspace.quoteProvenance')}
            value={result?.quote_provenance ?? effectiveProposal.quote_provenance ?? '—'}
          />
        </dl>
        <Link
          className="inline-flex text-xs font-medium text-emerald-800 underline-offset-4 hover:underline dark:text-emerald-400"
          to={`/ops/audit?order=${encodeURIComponent(effectiveProposal.order_id)}`}
        >
          {t('screen.workspace.openAuditLineage')}
        </Link>
        <Button className="w-full" onClick={onDismiss} type="button" variant="outline">
          {t('screen.workspace.startAnotherProposal')}
        </Button>
      </section>
    )
  }

  return (
    <section className="space-y-4 border-t border-border px-4 pt-4">
      {effectiveProposal.status === 'rejected' && (
        <p className="text-sm font-semibold text-destructive" role="alert">
          {t('screen.workspace.proposalRejected')}
        </p>
      )}
      <div>
        <h3 className="text-sm font-semibold">{t('screen.workspace.proposalPreview')}</h3>
        <p className="mt-1 text-xs text-muted-foreground">{t('screen.workspace.proposalPreviewNote')}</p>
      </div>
      <dl className="space-y-1 text-xs">
        {packetId && <Fact label={t('screen.workspace.packetId')} value={packetId} />}
        <Fact label={t('screen.workspace.proposalId')} value={effectiveProposal.id} />
        <Fact label={t('screen.workspace.venue')} value={effectiveProposal.instrument.venue} />
        <Fact label={t('screen.workspace.symbol')} value={effectiveProposal.instrument.symbol} />
        <Fact label={t('screen.workspace.instrumentType')} value={effectiveProposal.instrument.instrument_type} />
        <Fact label={t('screen.workspace.currency')} value={effectiveProposal.instrument.currency} />
        <Fact label={t('screen.workspace.instrumentMetadata')} value={metadataText(effectiveProposal.instrument.metadata)} />
        <Fact label={t('screen.workspace.side')} value={t(effectiveProposal.side === 'buy' ? 'screen.workspace.buy' : 'screen.workspace.sell')} />
        <Fact label={t('screen.workspace.quantity')} value={quantity(effectiveProposal.quantity, locale)} />
        <Fact label={t('screen.workspace.orderType')} value={t(effectiveProposal.order_type === 'market' ? 'screen.workspace.marketOrder' : 'screen.workspace.limitOrder')} />
        <Fact label={t('screen.workspace.limitPrice')} value={moneyPrecise(effectiveProposal.limit_price, locale)} />
        <Fact label={t('screen.workspace.artifact')} value={effectiveProposal.artifact_id} />
        <Fact label={t('screen.workspace.datasetRevision')} value={`${effectiveProposal.dataset_id} · ${effectiveProposal.dataset_revision}`} />
        <Fact label={t('screen.workspace.modelVersion')} value={effectiveProposal.model_version} />
        <DigestFact label={t('screen.workspace.configDigest')} value={effectiveProposal.config_digest} />
        <DigestFact label={t('screen.workspace.historyDigest')} value={effectiveProposal.history_digest} />
        <Fact label={t('screen.workspace.forecastVintage')} value={dateTime(effectiveProposal.forecast_generated_at, locale)} />
        <Fact label={t('screen.workspace.quoteProvenance')} value={effectiveProposal.quote_provenance ?? '—'} />
      </dl>
      {effectiveProposal.blockers.length > 0 && (
        <ul className="space-y-1 text-xs text-destructive" role="alert">
          {effectiveProposal.blockers.map((blocker) => (
            <li key={blocker} title={blocker}>{evidenceText(blocker, locale, t)}</li>
          ))}
        </ul>
      )}
      {result?.order && (
        <dl className="space-y-1 border-y border-border py-3 text-xs">
          <Fact label={t('screen.workspace.orderId')} value={result.order.order_id} />
          <Fact label={t('screen.workspace.orderStatus')} value={orderStatus(result.order.status, t)} />
          <Fact label={t('screen.workspace.filledQuantity')} value={quantity(result.order.filled_quantity, locale)} />
        </dl>
      )}
      {effectiveProposal.order_id !== null && effectiveProposal.order_id !== undefined && (
        <Link
          className="inline-flex text-xs font-medium text-foreground underline underline-offset-4"
          to={`/ops/audit?order=${encodeURIComponent(effectiveProposal.order_id)}`}
        >
          {t('screen.workspace.openAuditLineage')}
        </Link>
      )}
      <div className="border-y border-border py-3">
        <p className="text-[10px] uppercase tracking-wider text-muted-foreground">
          {t('screen.workspace.displayedToken')}
        </p>
        <code className="mt-1 block break-all font-mono text-xs [overflow-wrap:anywhere]">{proposal.confirmation_token}</code>
      </div>
      <div className="space-y-2">
        <Label htmlFor="proposal-confirmation-token">{t('screen.workspace.confirmationToken')}</Label>
        <Input
          autoComplete="off"
          disabled={interactionBlocked}
          id="proposal-confirmation-token"
          onChange={(event) => setConfirmationToken(event.target.value)}
          value={confirmationToken}
        />
      </div>
      {confirmation.isError && confirmationError !== null && !effectiveProposal.blockers.includes(confirmationError) && (
        <p className="text-xs text-destructive" role="alert">{confirmationError}</p>
      )}
      <Button
        className="w-full"
        disabled={interactionBlocked || proposalBlocked || confirmation.isPending || confirmationToken !== effectiveProposal.confirmation_token}
        onClick={() => {
          if (!interactionBlocked) confirmation.mutate()
        }}
        type="button"
      >
        {confirmation.isPending
          ? t('screen.workspace.confirmingProposal')
          : t('screen.workspace.confirmProposal')}
      </Button>
      {(effectiveProposal.status === 'blocked'
        || effectiveProposal.status === 'confirmed'
        || effectiveProposal.status === 'rejected') && (
        <Button className="w-full" onClick={onDismiss} type="button" variant="outline">
          {t('screen.workspace.startAnotherProposal')}
        </Button>
      )}
    </section>
  )
}

function confirmationErrorText(
  result: ProposalConfirmationResult | null,
  error: unknown,
): string | null {
  if (result?.blocker) return result.blocker
  if (error === null || error === undefined) return null
  return errorText(error)
}

interface ConfirmationIdentity {
  contextKey: string
  proposalId: string
  symbol: string
  venue: PaperProposal['instrument']['venue']
}

function sameConfirmationIdentity(
  current: ConfirmationIdentity,
  submitted: ConfirmationIdentity,
): boolean {
  return current.contextKey === submitted.contextKey
    && current.proposalId === submitted.proposalId
    && current.symbol === submitted.symbol
    && current.venue === submitted.venue
}

function assertConfirmationResult(
  result: ProposalConfirmationResult,
  submitted: ConfirmationIdentity,
): void {
  if (
    result.proposal.id !== submitted.proposalId
    || result.proposal.instrument.venue !== submitted.venue
    || result.proposal.instrument.symbol !== submitted.symbol
    || (result.order !== null && result.order !== undefined && (
      result.order.instrument.venue !== submitted.venue
      || result.order.instrument.symbol !== submitted.symbol
    ))
  ) {
    throw new Error('Proposal confirmation response does not match the displayed packet context.')
  }
}

function metadataText(metadata: Readonly<Record<string, string>> | undefined): string {
  if (metadata === undefined || Object.keys(metadata).length === 0) return '—'
  return JSON.stringify(Object.fromEntries(Object.entries(metadata).sort(([left], [right]) => left.localeCompare(right))))
}

function DigestFact({ label, value }: { label: string; value: string }) {
  return (
    <div className="space-y-1 py-1">
      <dt className="text-muted-foreground">{label}</dt>
      <dd><code className="block select-all break-all font-mono text-[10px] [overflow-wrap:anywhere]">{value}</code></dd>
    </div>
  )
}

function orderStatus(
  status: NonNullable<ProposalConfirmationResult['order']>['status'],
  t: ReturnType<typeof usePreferences>['t'],
): string {
  if (status === 'pending') return t('screen.workspace.statusPending')
  if (status === 'accepted') return t('screen.workspace.statusAccepted')
  if (status === 'partially_filled') return t('screen.workspace.statusPartiallyFilled')
  if (status === 'filled') return t('screen.workspace.statusFilled')
  if (status === 'canceled') return t('screen.workspace.statusCanceled')
  return t('screen.workspace.statusRejected')
}

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex min-w-0 justify-between gap-3">
      <dt className="shrink-0 text-muted-foreground">{label}</dt>
      <dd className="min-w-0 max-w-44 break-all text-right font-mono tabular-nums [overflow-wrap:anywhere]">{value}</dd>
    </div>
  )
}
