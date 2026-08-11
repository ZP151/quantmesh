import { useState } from 'react'
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
import { dateTime, moneyPrecise, quantity, shortHash } from '@/lib/format'
import { usePreferences } from '@/lib/preferences'

function errorText(error: unknown): string {
  if (error instanceof ProposalRefusalError) return error.result.blocker ?? error.message
  return error instanceof Error ? error.message : String(error)
}

export function ProposalConfirmation({ proposal }: { proposal: PaperProposal }) {
  const { t } = usePreferences()
  const queryClient = useQueryClient()
  const [confirmationToken, setConfirmationToken] = useState('')
  const [result, setResult] = useState<ProposalConfirmationResult | null>(null)
  const proposalBlocked = proposal.status !== 'pending' || proposal.blockers.length > 0
  const confirmation = useMutation({
    mutationFn: () => api.confirmPaperProposal(proposal.id, confirmationToken),
    onSuccess: (next) => {
      setResult(next)
      void Promise.all(
        ['instrument-workspace', 'orders', 'positions', 'pnl', 'audit'].map((key) =>
          queryClient.invalidateQueries({ queryKey: [key] }),
        ),
      )
    },
  })

  if (result?.order) {
    return (
      <section className="space-y-3 border-t border-border px-4 pt-4" aria-live="polite">
        <p className="text-sm font-semibold text-emerald-600 dark:text-emerald-400">
          {t('screen.workspace.orderCreated')}
        </p>
        <dl className="space-y-1 text-xs">
          <Fact label={t('screen.workspace.orderId')} value={result.order.order_id} />
          <Fact label={t('screen.workspace.orderStatus')} value={orderStatus(result.order.status, t)} />
          <Fact label={t('screen.workspace.filledQuantity')} value={quantity(result.order.filled_quantity)} />
          <Fact label={t('screen.workspace.quoteProvenance')} value={result.quote_provenance ?? '—'} />
        </dl>
        <Link
          className="inline-flex text-xs font-medium text-emerald-600 underline-offset-4 hover:underline dark:text-emerald-400"
          to={`/ops/audit?order=${encodeURIComponent(result.order.order_id)}`}
        >
          {t('screen.workspace.openAuditLineage')}
        </Link>
      </section>
    )
  }

  return (
    <section className="space-y-4 border-t border-border px-4 pt-4">
      <div>
        <h3 className="text-sm font-semibold">{t('screen.workspace.proposalPreview')}</h3>
        <p className="mt-1 text-xs text-muted-foreground">{t('screen.workspace.proposalPreviewNote')}</p>
      </div>
      <dl className="space-y-1 text-xs">
        <Fact label={t('screen.workspace.proposalId')} value={proposal.id} />
        <Fact label={t('screen.workspace.side')} value={t(proposal.side === 'buy' ? 'screen.workspace.buy' : 'screen.workspace.sell')} />
        <Fact label={t('screen.workspace.quantity')} value={quantity(proposal.quantity)} />
        <Fact label={t('screen.workspace.orderType')} value={t(proposal.order_type === 'market' ? 'screen.workspace.marketOrder' : 'screen.workspace.limitOrder')} />
        <Fact label={t('screen.workspace.limitPrice')} value={moneyPrecise(proposal.limit_price)} />
        <Fact label={t('screen.workspace.artifact')} value={proposal.artifact_id} />
        <Fact label={t('screen.workspace.datasetRevision')} value={`${proposal.dataset_id} · ${proposal.dataset_revision}`} />
        <Fact label={t('screen.workspace.modelVersion')} value={proposal.model_version} />
        <Fact label={t('screen.workspace.configDigest')} value={shortHash(proposal.config_digest)} />
        <Fact label={t('screen.workspace.historyDigest')} value={shortHash(proposal.history_digest)} />
        <Fact label={t('screen.workspace.forecastVintage')} value={dateTime(proposal.forecast_generated_at)} />
        <Fact label={t('screen.workspace.quoteProvenance')} value={proposal.quote_provenance ?? '—'} />
      </dl>
      {proposal.blockers.length > 0 && (
        <ul className="space-y-1 text-xs text-destructive" role="alert">
          {proposal.blockers.map((blocker) => <li key={blocker}>{blocker}</li>)}
        </ul>
      )}
      <div className="border-y border-border py-3">
        <p className="text-[10px] uppercase tracking-wider text-muted-foreground">
          {t('screen.workspace.displayedToken')}
        </p>
        <code className="mt-1 block break-all font-mono text-xs">{proposal.confirmation_token}</code>
      </div>
      <div className="space-y-2">
        <Label htmlFor="proposal-confirmation-token">{t('screen.workspace.confirmationToken')}</Label>
        <Input
          autoComplete="off"
          id="proposal-confirmation-token"
          onChange={(event) => setConfirmationToken(event.target.value)}
          value={confirmationToken}
        />
      </div>
      {confirmation.isError && (
        <p className="text-xs text-destructive" role="alert">{errorText(confirmation.error)}</p>
      )}
      <Button
        className="w-full"
        disabled={proposalBlocked || confirmation.isPending || confirmationToken !== proposal.confirmation_token}
        onClick={() => confirmation.mutate()}
        type="button"
      >
        {confirmation.isPending
          ? t('screen.workspace.confirmingProposal')
          : t('screen.workspace.confirmProposal')}
      </Button>
    </section>
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
    <div className="flex justify-between gap-3">
      <dt className="text-muted-foreground">{label}</dt>
      <dd className="max-w-44 break-all text-right font-mono tabular-nums">{value}</dd>
    </div>
  )
}
