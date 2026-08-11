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
    limitations: ['Deterministic synthetic demo artifact'],
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
    expect(screen.getByText('Benchmark MAE').closest('div')).toHaveTextContent('127')
    expect(screen.getByText('Residual samples').closest('div')).toHaveTextContent('20')
    expect(screen.getByText('Dataset revision').closest('div')).toHaveTextContent('demo-history · 1')
    expect(screen.getByText('Model version').closest('div')).toHaveTextContent('1.0.0')
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
})

describe('DecisionRail', () => {
  it('shows portfolio/risk truth and creates a preview without placing an order', async () => {
    const user = userEvent.setup()
    render(<DecisionRail workspace={workspace} />, { wrapper: Providers })

    expect(screen.getByText('Average cost').closest('div')).toHaveTextContent('180')
    expect(screen.getByText('Unrealized P&L').closest('div')).toHaveTextContent('20')
    expect(screen.getByText('Account equity').closest('div')).toHaveTextContent('100,020')
    expect(screen.getByText('Quote age').closest('div')).toHaveTextContent('500 ms')
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
  })

  it('requires the displayed token, confirms once, and links the resulting audit lineage', async () => {
    const user = userEvent.setup()
    render(<DecisionRail workspace={workspace} />, { wrapper: Providers })
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
      order: null,
      proposal: { ...proposal, blockers: ['Quote crossed the freshness fence.'], status: 'blocked' },
      quote_provenance: null,
    }
    mocked.confirmPaperProposal.mockRejectedValue(new ProposalRefusalError(refused))
    render(<DecisionRail workspace={workspace} />, { wrapper: Providers })
    await user.click(screen.getByRole('button', { name: 'Create paper proposal' }))
    await user.type(await screen.findByLabelText('Confirmation token'), proposal.confirmation_token)
    await user.click(screen.getByRole('button', { name: 'Confirm paper proposal' }))

    expect(await screen.findByText('Quote crossed the freshness fence.')).toBeInTheDocument()
    expect(mocked.confirmPaperProposal).toHaveBeenCalledTimes(1)
  })
})
