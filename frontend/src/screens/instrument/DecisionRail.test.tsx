import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useState } from 'react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import {
  ProposalRefusalError,
  api,
  type InstrumentWorkspace,
  type PaperProposal,
  type ProposalConfirmation,
} from '@/lib/api'
import { PreferencesProvider } from '@/lib/preferences'
import { DecisionRail } from './DecisionRail'
import { ForecastEvidence } from './ForecastEvidence'

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>()
  return {
    ...actual,
    api: {
      ...actual.api,
      confirmPaperProposal: vi.fn(),
      createPaperProposal: vi.fn(),
    },
  }
})

const proposal: PaperProposal = {
  artifact_id: 'forecast-nvda-20260808',
  blockers: [],
  config_digest: 'config-1234567890',
  confirmation_token: 'CONFIRM-NVDA-10',
  created_at: '2026-08-08T12:01:00Z',
  dataset_id: 'demo-history',
  dataset_revision: 1,
  forecast_generated_at: '2026-08-08T12:00:00Z',
  history_digest: 'history-1234567890',
  id: 'proposal-1',
  instrument: {
    currency: 'USD',
    instrument_type: 'equity',
    metadata: {},
    symbol: 'NVDA',
    venue: 'moomoo',
  },
  limit_price: null,
  model_version: '1.0.0',
  order_id: null,
  order_type: 'market',
  quantity: 10,
  quote_provenance: 'demo-synthetic',
  side: 'buy',
  status: 'pending',
}

const confirmation: ProposalConfirmation = {
  blocker: null,
  order: {
    broker_order_id: null,
    client_order_id: null,
    created_at: '2026-08-08T12:02:00Z',
    events: [],
    filled_quantity: 10,
    idempotency_key: 'proposal:proposal-1',
    instrument: proposal.instrument,
    limit_price: null,
    order_id: 'paper-order-1',
    order_type: 'market',
    quantity: 10,
    side: 'buy',
    status: 'filled',
  },
  proposal: { ...proposal, order_id: 'paper-order-1', status: 'confirmed' },
  quote_provenance: 'demo-synthetic',
}

const workspace: InstrumentWorkspace = {
  comparison: null,
  forecast: {
    artifact_id: proposal.artifact_id,
    benchmark_name: 'last-close',
    blockers: [],
    config_digest: proposal.config_digest,
    dataset_id: 'demo-history',
    dataset_revision: 1,
    eligible: true,
    generated_at: '2026-08-08T12:00:00Z',
    history_digest: proposal.history_digest,
    synthetic: true,
    limitations: [
      'Intervals are empirical and do not imply a probability of profit or execution outcome.',
      'The artifact is research evidence; the paper kernel remains the only order authority.',
    ],
    metrics: [7, 30, 126].map((sessions) => ({
      benchmark_mae: sessions + 1,
      coverage_50: 0.5,
      coverage_80: 0.8,
      coverage_95: 0.95,
      interval_test_count: 20,
      mae: sessions,
      residual_count: 20,
      rmse: sessions + 0.5,
      sessions: sessions as 7 | 30 | 126,
      test_end: '2026-08-07T20:00:00Z',
      test_start: '2026-07-01T20:00:00Z',
      validation_end: '2026-06-30T20:00:00Z',
      validation_start: '2026-06-01T20:00:00Z',
    })),
    model_name: 'quantile-residual-baseline',
    model_version: '1.0.0',
    paths: [7, 30, 126].map((sessions) => ({
      points: [{
        p025: 170,
        p10: 175,
        p25: 180,
        p50: 190 + sessions,
        p75: 200,
        p90: 205,
        p975: 210,
        session: sessions,
        timestamp: '2026-09-01T20:00:00Z',
      }],
      sessions: sessions as 7 | 30 | 126,
    })),
    target: 'close',
    test_end: '2026-08-07T20:00:00Z',
    test_start: '2026-07-01T20:00:00Z',
    train_end: '2026-05-31T20:00:00Z',
    train_start: '2024-01-01T20:00:00Z',
    validation_end: '2026-06-30T20:00:00Z',
    validation_start: '2026-06-01T20:00:00Z',
  },
  forecast_unavailable_reason: null,
  generated_at: '2026-08-08T12:00:00Z',
  history: {
    adjustment: 'unadjusted',
    as_of: '2026-08-08T12:00:00Z',
    bars: [],
    calendar: 'XNYS',
    coverage: {
      end: '2026-08-07T20:00:00Z',
      interval: '1d',
      rows: 650,
      start: '2024-01-01T20:00:00Z',
      symbol: 'NVDA',
      venue: 'moomoo',
    },
    coverage_scope: 'historical-only',
    dataset_id: 'demo-history',
    dataset_revision: 1,
    duplicates: [],
    gaps: [],
    generated_at: '2026-08-08T12:00:00Z',
    instrument: proposal.instrument,
    interval: '1d',
    license: 'demo-synthetic',
    limitations: ['Synthetic data'],
    range: '6m',
    resolution_fallback: null,
    source: 'demo-synthetic',
  },
  instrument: proposal.instrument,
  live: {
    age_ms: 500,
    ask: 184.2,
    bid: 183.8,
    data_time: '2026-08-08T11:59:59Z',
    label: 'synthetic',
    last: 184,
    provenance: 'demo-synthetic',
    reason: null,
    received_at: '2026-08-08T12:00:00Z',
    sequence: 12,
    sequence_gap: false,
    source: 'demo-synthetic',
    status: 'available',
  },
  position: {
    average_cost: 180,
    mark: 184,
    mark_status: {
      provenance: 'demo-synthetic',
      reason: null,
      received_at: '2026-08-08T12:00:00Z',
      status: 'available',
    },
    quantity: 5,
    realized_pnl: 12,
    unrealized_pnl: 20,
  },
  proposal: { allowed: true, blockers: [], proposals: [] },
  risk: {
    cash: 99_100,
    equity: 100_020,
    global_kill_switch: false,
    mark_available: true,
    valuation_complete: true,
    valuation_reason: null,
    max_notional: 50_000,
    max_order_quantity: 100,
    max_position_quantity: 1_000,
    starting_cash: 100_000,
    venue_kill_switch: false,
  },
}

const mocked = vi.mocked(api)

function Providers({ children }: { children: React.ReactNode }) {
  return (
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <PreferencesProvider>
        <MemoryRouter>{children}</MemoryRouter>
      </PreferencesProvider>
    </QueryClientProvider>
  )
}

function ForecastHarness({ value = workspace }: { value?: InstrumentWorkspace }) {
  const [horizon, setHorizon] = useState<7 | 30 | 126>(30)
  return (
    <ForecastEvidence
      forecast={value.forecast}
      horizon={horizon}
      onHorizonChange={setHorizon}
      synthetic
      unavailableReason={value.forecast_unavailable_reason}
    />
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  window.localStorage.clear()
  mocked.createPaperProposal.mockResolvedValue(proposal)
  mocked.confirmPaperProposal.mockResolvedValue(confirmation)
})

describe('ForecastEvidence', () => {
  it('switches 7/30/126-session paths and exposes intervals, vintage and quality lineage', async () => {
    const user = userEvent.setup()
    render(<ForecastHarness />, { wrapper: Providers })

    expect(screen.getByText('Synthetic demo forecast')).toBeInTheDocument()
    expect(screen.getByText(/Median.*220/)).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: '126 sessions' }))
    expect(screen.getByText(/Median.*316/)).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: '95% interval' }))
    expect(screen.getByText(/170.*210/)).toBeInTheDocument()
    expect(screen.getByText('OOS MAE').closest('div')).toHaveTextContent('126')
    expect(screen.getByText('Benchmark MAE').closest('div')).toHaveTextContent('last-close · 127')
    expect(screen.getByText('Residual samples').closest('div')).toHaveTextContent('20')
    expect(screen.getByText('Dataset revision').closest('div')).toHaveTextContent('demo-history · 1')
    expect(screen.getByText('Model version').closest('div')).toHaveTextContent('1.0.0')
    expect(screen.getByText('Evaluation method').closest('div')).toHaveTextContent(
      'Prequential / rolling out-of-sample',
    )
    const validationWindow = screen.getByText('Rolling validation window').closest('div')
    expect(validationWindow).toHaveTextContent('→')
    expect(validationWindow).toHaveAttribute(
      'title',
      '2026-06-01T20:00:00Z → 2026-06-30T20:00:00Z',
    )
    const testWindow = screen.getByText('Rolling test window').closest('div')
    expect(testWindow).toHaveTextContent('→')
    expect(testWindow).toHaveAttribute(
      'title',
      '2026-07-01T20:00:00Z → 2026-08-07T20:00:00Z',
    )
    expect(screen.getByText(/Train cutoff/)).toBeInTheDocument()
    expect(screen.getByText(/Generated/)).toBeInTheDocument()
  })

  it('shows promotion blockers when the artifact is ineligible', () => {
    const blocked = {
      ...workspace,
      forecast: { ...workspace.forecast!, eligible: false, blockers: ['Coverage gate failed.'] },
    }
    render(<ForecastHarness value={blocked} />, { wrapper: Providers })

    expect(screen.getByText('Forecast not promoted')).toBeInTheDocument()
    expect(screen.getByText('Coverage gate failed.')).toBeInTheDocument()
  })

  it('formats forecast dates with the selected Chinese locale', () => {
    window.localStorage.setItem('quantmesh.preferences', JSON.stringify({ locale: 'zh-CN', theme: 'dark' }))
    render(<ForecastHarness />, { wrapper: Providers })

    const trainCutoff = screen.getByText('训练截止').closest('div')
    expect(trainCutoff).toHaveTextContent('月')
    expect(trainCutoff).not.toHaveTextContent('May')
    expect(screen.getByText('区间来自经验分布，不代表盈利概率或成交结果。')).toHaveAttribute(
      'title',
      'Intervals are empirical and do not imply a probability of profit or execution outcome.',
    )
    expect(screen.getByText('该产物仅是研究证据；模拟交易内核仍是唯一订单权威。')).toBeInTheDocument()
  })
})

describe('DecisionRail', () => {
  it('does not present incomplete account equity as exact and explains the missing mark', () => {
    const incomplete = {
      ...workspace,
      position: {
        ...workspace.position!,
        mark: null,
        mark_status: {
          provenance: 'real',
          reason: 'Quote is older than the valuation fence.',
          received_at: '2026-08-08T11:50:00Z',
          status: 'stale',
        },
        unrealized_pnl: null,
      },
      risk: {
        ...workspace.risk,
        mark_available: false,
        valuation_complete: false,
        valuation_reason: 'One held position has no current mark.',
      },
    } as InstrumentWorkspace

    render(<DecisionRail workspace={incomplete} />, { wrapper: Providers })

    expect(screen.getByText('Account equity').closest('div')).toHaveTextContent('Unavailable')
    expect(screen.getByText('Incomplete valuation')).toBeInTheDocument()
    expect(screen.getByText('One held position has no current mark.')).toBeInTheDocument()
    expect(screen.getByText('Stale')).toBeInTheDocument()
    expect(screen.getByText('Quote is older than the valuation fence.')).toBeInTheDocument()
  })

  it('fails closed when completeness is asserted but the held mark is absent', () => {
    const contradictory = {
      ...workspace,
      position: {
        ...workspace.position!,
        mark: null,
      },
      risk: {
        ...workspace.risk,
        valuation_complete: true,
      },
    } as InstrumentWorkspace

    render(<DecisionRail workspace={contradictory} />, { wrapper: Providers })

    expect(screen.getByText('Account equity').closest('div')).toHaveTextContent('Unavailable')
    expect(screen.getByText('Incomplete valuation')).toBeInTheDocument()
  })

  it('shows portfolio/risk truth and creates a preview without placing an order', async () => {
    const user = userEvent.setup()
    render(<DecisionRail workspace={workspace} />, { wrapper: Providers })

    expect(screen.getByText('Average cost').closest('div')).toHaveTextContent('180')
    expect(screen.getByText('Unrealized P&L').closest('div')).toHaveTextContent('20')
    expect(screen.getByText('Account equity').closest('div')).toHaveTextContent('100,020')
    expect(screen.getByText('Quote age').closest('div')).toHaveTextContent('500 ms')
    expect(screen.getByText('Snapshot as of').closest('div')).toHaveTextContent('Aug 8')
    expect(screen.getByText('Authority').closest('div')).toHaveTextContent('Local paper kernel')
    await user.click(screen.getByRole('button', { name: 'Create paper proposal' }))

    await waitFor(() => expect(mocked.createPaperProposal).toHaveBeenCalledWith({
      artifact_id: proposal.artifact_id,
      limit_price: null,
      quantity: 10,
      side: 'buy',
      symbol: 'NVDA',
      venue: 'moomoo',
    }))
    expect(mocked.confirmPaperProposal).not.toHaveBeenCalled()
    expect(screen.getByText('Immutable proposal preview')).toBeInTheDocument()
    expect(screen.getByText(proposal.confirmation_token)).toBeInTheDocument()
    expect(screen.getByText('Venue').closest('div')).toHaveTextContent('moomoo')
    expect(screen.getByText('Symbol').closest('div')).toHaveTextContent('NVDA')
    expect(screen.getByText('Instrument type').closest('div')).toHaveTextContent('equity')
    expect(screen.getByText('Currency').closest('div')).toHaveTextContent('USD')
    expect(screen.getByText(proposal.config_digest)).toBeInTheDocument()
    expect(screen.getByText(proposal.history_digest)).toBeInTheDocument()
  })

  it('requires the displayed token, confirms once, and links the resulting audit lineage', async () => {
    const user = userEvent.setup()
    const view = render(<DecisionRail workspace={workspace} />, { wrapper: Providers })
    await user.click(screen.getByRole('button', { name: 'Create paper proposal' }))
    const confirm = await screen.findByRole('button', { name: 'Confirm paper proposal' })
    expect(confirm).toBeDisabled()
    await user.type(screen.getByLabelText('Confirmation token'), proposal.confirmation_token)
    expect(confirm).toBeEnabled()
    await user.click(confirm)

    await waitFor(() => expect(mocked.confirmPaperProposal).toHaveBeenCalledTimes(1))
    expect(screen.getByText(/paper-order-1/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Open audit lineage' })).toHaveAttribute(
      'href',
      '/ops/audit?order=paper-order-1',
    )
    expect(screen.queryByRole('button', { name: 'Confirm paper proposal' })).not.toBeInTheDocument()

    view.rerender(
      <DecisionRail
        workspace={{
          ...workspace,
          proposal: { ...workspace.proposal, proposals: [confirmation.proposal] },
        }}
      />,
    )
    expect(screen.getByText(/paper-order-1/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Open audit lineage' })).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Start another paper proposal' }))
    expect(screen.getByRole('button', { name: 'Create paper proposal' })).toBeInTheDocument()
  })

  it('resumes an existing pending proposal after a workspace refresh', () => {
    render(
      <DecisionRail
        workspace={{
          ...workspace,
          proposal: { ...workspace.proposal, proposals: [proposal] },
        }}
      />,
      { wrapper: Providers },
    )

    expect(screen.getByText('Immutable proposal preview')).toBeInTheDocument()
    expect(screen.getByText(proposal.confirmation_token)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Create paper proposal' })).not.toBeInTheDocument()
    expect(mocked.createPaperProposal).not.toHaveBeenCalled()
  })

  it('prioritizes a pending persisted proposal over a terminal proposal', () => {
    render(
      <DecisionRail
        workspace={{
          ...workspace,
          proposal: {
            ...workspace.proposal,
            proposals: [proposal, confirmation.proposal],
          },
        }}
      />,
      { wrapper: Providers },
    )

    expect(screen.getByText('Immutable proposal preview')).toBeInTheDocument()
    expect(screen.getByText(proposal.confirmation_token)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Confirm paper proposal' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Start another paper proposal' })).not.toBeInTheDocument()
  })

  it('keeps a newly persisted pending proposal visible after terminal history is dismissed', async () => {
    const user = userEvent.setup()
    const nextPending = {
      ...proposal,
      confirmation_token: 'CONFIRM-NVDA-20',
      id: 'proposal-2',
    }
    const view = render(
      <DecisionRail
        workspace={{
          ...workspace,
          proposal: { ...workspace.proposal, proposals: [confirmation.proposal] },
        }}
      />,
      { wrapper: Providers },
    )

    await user.click(screen.getByRole('button', { name: 'Start another paper proposal' }))
    view.rerender(
      <DecisionRail
        workspace={{
          ...workspace,
          proposal: {
            ...workspace.proposal,
            proposals: [confirmation.proposal, nextPending],
          },
        }}
      />,
    )

    expect(screen.getByText('Immutable proposal preview')).toBeInTheDocument()
    expect(screen.getByText(nextPending.confirmation_token)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Confirm paper proposal' })).toBeInTheDocument()
  })

  it('restores confirmed order lineage after a full workspace remount', async () => {
    const user = userEvent.setup()
    render(
      <DecisionRail
        workspace={{
          ...workspace,
          proposal: { ...workspace.proposal, proposals: [confirmation.proposal] },
        }}
      />,
      { wrapper: Providers },
    )

    expect(screen.getByText('Paper order created')).toBeInTheDocument()
    expect(screen.getByText('Order ID').closest('div')).toHaveTextContent('paper-order-1')
    expect(screen.getByRole('link', { name: 'Open audit lineage' })).toHaveAttribute(
      'href',
      '/ops/audit?order=paper-order-1',
    )
    await user.click(screen.getByRole('button', { name: 'Start another paper proposal' }))
    expect(screen.getByRole('button', { name: 'Create paper proposal' })).toBeInTheDocument()
  })

  it('dismisses the existing terminal ledger in one start-another action', async () => {
    const user = userEvent.setup()
    const olderRejected: PaperProposal = {
      ...proposal,
      blockers: ['Earlier proposal was rejected.'],
      id: 'proposal-older',
      order_id: 'paper-order-older',
      status: 'rejected',
    }
    render(
      <DecisionRail
        workspace={{
          ...workspace,
          proposal: {
            ...workspace.proposal,
            proposals: [olderRejected, confirmation.proposal],
          },
        }}
      />,
      { wrapper: Providers },
    )

    expect(screen.getByText('Paper order created')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Start another paper proposal' }))
    expect(screen.getByRole('button', { name: 'Create paper proposal' })).toBeInTheDocument()
    expect(screen.queryByText('Earlier proposal was rejected.')).not.toBeInTheDocument()
  })

  it('blocks proposal creation while retained evidence is updating', () => {
    render(<DecisionRail evidenceUpdating workspace={workspace} />, { wrapper: Providers })

    expect(screen.getByText('Paper action waits for the selected evidence to finish loading.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Create paper proposal' })).toBeDisabled()
  })

  it('drops local proposal and result state when refreshed authority removes it', async () => {
    const user = userEvent.setup()
    const view = render(<DecisionRail workspace={workspace} />, { wrapper: Providers })
    await user.click(screen.getByRole('button', { name: 'Create paper proposal' }))
    expect(await screen.findByText('Immutable proposal preview')).toBeInTheDocument()

    view.rerender(
      <DecisionRail
        workspace={{
          ...workspace,
          generated_at: '2026-08-08T12:03:00Z',
          proposal: { ...workspace.proposal, proposals: [] },
        }}
      />,
    )

    expect(await screen.findByRole('button', { name: 'Create paper proposal' })).toBeInTheDocument()
    expect(screen.queryByText('Immutable proposal preview')).not.toBeInTheDocument()
  })

  it('keeps a race-blocked proposal visible and cannot confirm it', async () => {
    const user = userEvent.setup()
    mocked.createPaperProposal.mockResolvedValue({
      ...proposal,
      blockers: ['Risk changed before proposal creation.'],
      status: 'blocked',
    })
    render(<DecisionRail workspace={workspace} />, { wrapper: Providers })
    await user.click(screen.getByRole('button', { name: 'Create paper proposal' }))

    expect(await screen.findByText('Risk changed before proposal creation.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Confirm paper proposal' })).toBeDisabled()
  })

  it('preserves stale/kill-switch blockers and backend confirmation refusals', async () => {
    const user = userEvent.setup()
    const blocked = {
      ...workspace,
      proposal: {
        allowed: false,
        blockers: ['Quote is stale.', 'Global kill switch is engaged.'],
        proposals: [],
      },
      risk: { ...workspace.risk, global_kill_switch: true },
    }
    const first = render(<DecisionRail workspace={blocked} />, { wrapper: Providers })
    expect(screen.getByText('Quote is stale.')).toBeInTheDocument()
    expect(screen.getByText('Global kill switch is engaged.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Create paper proposal' })).toBeDisabled()
    first.unmount()

    const refused: ProposalConfirmation = {
      blocker: 'Quote crossed the freshness fence.',
      order: { ...confirmation.order!, filled_quantity: 0, status: 'rejected' },
      proposal: {
        ...proposal,
        blockers: ['Quote crossed the freshness fence.'],
        order_id: 'paper-order-1',
        status: 'rejected',
      },
      quote_provenance: null,
    }
    mocked.confirmPaperProposal.mockRejectedValue(new ProposalRefusalError(refused))
    const view = render(<DecisionRail workspace={workspace} />, { wrapper: Providers })
    await user.click(screen.getByRole('button', { name: 'Create paper proposal' }))
    await user.type(await screen.findByLabelText('Confirmation token'), proposal.confirmation_token)
    await user.click(screen.getByRole('button', { name: 'Confirm paper proposal' }))

    expect(await screen.findByText('Quote crossed the freshness fence.')).toBeInTheDocument()
    expect(mocked.confirmPaperProposal).toHaveBeenCalledTimes(1)
    expect(screen.getByRole('button', { name: 'Confirm paper proposal' })).toBeDisabled()
    expect(screen.getByText('Proposal rejected')).toBeInTheDocument()
    expect(screen.queryByText('Paper order created')).not.toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Open audit lineage' })).toBeInTheDocument()

    view.rerender(
      <DecisionRail
        workspace={{
          ...workspace,
          proposal: { ...workspace.proposal, proposals: [refused.proposal] },
        }}
      />,
    )
    expect(screen.getByText('Quote crossed the freshness fence.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Confirm paper proposal' })).toBeDisabled()
    await user.click(screen.getByRole('button', { name: 'Start another paper proposal' }))
    expect(screen.getByRole('button', { name: 'Create paper proposal' })).toBeInTheDocument()
  })
})
