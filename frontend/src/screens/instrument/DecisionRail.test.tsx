import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import {
  ProposalRefusalError,
  api,
  type DecisionPacket,
  type InstrumentWorkspace,
  type PaperProposal,
  type ProposalConfirmation,
} from '@/lib/api'
import { PreferencesProvider } from '@/lib/preferences'
import { DecisionRail } from './DecisionRail'

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>()
  return {
    ...actual,
    api: {
      ...actual.api,
      applyDecisionPacketAction: vi.fn(),
      confirmPaperProposal: vi.fn(),
      saveDecisionPacket: vi.fn(),
    },
  }
})

const instrument = {
  currency: 'USD',
  instrument_type: 'equity' as const,
  metadata: {},
  symbol: 'NVDA',
  venue: 'moomoo' as const,
}

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
  instrument,
  limit_price: 182,
  model_version: '1.0.0',
  order_id: null,
  order_type: 'limit',
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
    instrument,
    limit_price: 182,
    order_id: 'paper-order-1',
    order_type: 'limit',
    quantity: 10,
    side: 'buy',
    status: 'filled',
  },
  proposal: { ...proposal, order_id: 'paper-order-1', status: 'confirmed' },
  quote_provenance: 'demo-synthetic',
}

const packet = {
  as_of: '2026-08-08T12:00:00Z',
  created_at: '2026-08-08T12:00:00Z',
  disposition: 'draft',
  evidence: {
    costs: { fee_bps: 1.5, half_spread_bps: null, slippage_bps: 2.5, spread_status: 'confirmation-quote-required' },
    forecast_artifact_id: proposal.artifact_id,
    forecast_benchmark_name: 'last-close',
    forecast_blockers: [],
    forecast_eligible: true,
    forecast_generated_at: '2026-08-08T12:00:00Z',
    forecast_limitations: [],
    forecast_metrics: [],
    forecast_paths: [],
    forecast_synthetic: true,
    history_dataset_id: 'demo-history',
    history_dataset_revision: 1,
    history_duplicates: [],
    history_gaps: [],
    history_generated_at: '2026-08-08T12:00:00Z',
    history_limitations: ['Synthetic data'],
    history_source: 'demo-synthetic',
  },
  instrument,
  market_state: {
    invalidation: 176,
    key_level_bar_times: ['2026-08-07T20:00:00Z'],
    latest_close: 184,
    observed_drawdown: -0.08,
    observed_volatility: 0.24,
    resistance: 195,
    sma20: 185,
    sma50: 180,
    support: 180,
    trend: 'bullish',
  },
  operator_reason: null,
  packet_id: 'packet-draft-000000000001',
  paper_capability: { allowed: true, blockers: [] },
  parent_packet_id: null,
  proposal_id: null,
  risk_plan: {
    entry_price: 182,
    proposal_input_only: true,
    reward_per_unit: 18,
    reward_to_risk: 3,
    risk_per_unit: 6,
    stop_price: 176,
    suggested_notional: 1820,
    suggested_quantity: 10,
    target_price: 200,
  },
  scenarios: [
    { confidence: 'qualitative', confidence_reason: 'Not calibrated.', invalidation: 180, kind: 'bull', probability: null, target: 210, thesis: 'Bull thesis', trigger: 'Bull trigger' },
    { confidence: 'qualitative', confidence_reason: 'Not calibrated.', invalidation: 178, kind: 'base', probability: null, target: 200, thesis: 'Base thesis', trigger: 'Base trigger' },
    { confidence: 'qualitative', confidence_reason: 'Not calibrated.', invalidation: 176, kind: 'bear', probability: null, target: 165, thesis: 'Bear thesis', trigger: 'Bear trigger' },
  ],
  selected_range: '6m',
  version: 1,
} as DecisionPacket

const workspace = {
  comparison: null,
  decision: { draft: packet, latest: null },
  forecast: null,
  forecast_unavailable_reason: null,
  generated_at: '2026-08-08T12:00:00Z',
  history: {
    adjustment: 'unadjusted', as_of: '2026-08-08T12:00:00Z', bars: [], calendar: 'XNYS',
    coverage: { end: '2026-08-07T20:00:00Z', interval: '1d', rows: 650, start: '2024-01-01T20:00:00Z', symbol: 'NVDA', venue: 'moomoo' },
    coverage_scope: 'historical-only', dataset_id: 'demo-history', dataset_revision: 1,
    duplicates: [], gaps: [], generated_at: '2026-08-08T12:00:00Z', instrument, interval: '1d',
    license: 'demo-synthetic', limitations: [], range: '6m', resolution_fallback: null, source: 'demo-synthetic',
  },
  instrument,
  live: {
    age_ms: 500, ask: 184.2, bid: 183.8, data_time: '2026-08-08T11:59:59Z', label: 'synthetic',
    last: 184, provenance: 'demo-synthetic', reason: null, received_at: '2026-08-08T12:00:00Z',
    sequence: 12, sequence_gap: false, source: 'demo-synthetic', status: 'available',
  },
  position: { average_cost: 180, mark: 184, mark_status: { provenance: 'demo-synthetic', reason: null, received_at: '2026-08-08T12:00:00Z', status: 'available' }, quantity: 5, realized_pnl: 12, unrealized_pnl: 20 },
  proposal: { allowed: true, blockers: [], proposals: [] },
  risk: { cash: 99_100, equity: 100_020, global_kill_switch: false, mark_available: true, valuation_complete: true, valuation_reason: null, max_notional: 50_000, max_order_quantity: 100, max_position_quantity: 1_000, starting_cash: 100_000, venue_kill_switch: false },
} as InstrumentWorkspace

const mocked = vi.mocked(api)

function Providers({ children }: { children: React.ReactNode }) {
  return (
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <PreferencesProvider><MemoryRouter>{children}</MemoryRouter></PreferencesProvider>
    </QueryClientProvider>
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  mocked.saveDecisionPacket.mockResolvedValue(packet)
  mocked.applyDecisionPacketAction.mockResolvedValue({
    packet: { ...packet, disposition: 'paper_proposal', packet_id: 'packet-paper-000000000001', parent_packet_id: packet.packet_id, proposal_id: proposal.id, version: 2 },
    proposal,
  })
  mocked.confirmPaperProposal.mockResolvedValue(confirmation)
})

describe('DecisionRail', () => {
  it('shows risk, explicit costs, and accessible server-owned paper inputs', () => {
    render(<DecisionRail workspace={workspace} />, { wrapper: Providers })

    expect(screen.getByText('Draft analysis')).toBeInTheDocument()
    expect(screen.getByText('Ready to decide')).toBeInTheDocument()
    expect(screen.getByText('Entry').closest('div')).toHaveTextContent('182')
    expect(screen.getByText('Stop').closest('div')).toHaveTextContent('176')
    expect(screen.getByText('Target').closest('div')).toHaveTextContent('200')
    expect(screen.getByText('R multiple').closest('div')).toHaveTextContent('3')
    expect(screen.getByText('Paper size').closest('div')).toHaveTextContent('10')
    expect(screen.getByText('Fees').closest('div')).toHaveTextContent('1.5 bps')
    expect(screen.getByText('Slippage').closest('div')).toHaveTextContent('2.5 bps')
    expect(screen.getByText('Spread captured at confirmation')).toBeInTheDocument()
    expect(screen.getByLabelText('Decision reason')).toBeInTheDocument()
    expect(screen.getByLabelText('Quantity')).toHaveValue(10)
    expect(screen.getByLabelText('Optional limit price')).toHaveValue(182)
  })

  it('keeps Reject and Watch usable while evidence blocks Paper, then displays the saved packet ID', async () => {
    const user = userEvent.setup()
    const blocked = {
      ...packet,
      paper_capability: { allowed: false, blockers: [{ code: 'forecast-freshness', evidence_ref: 'forecast-1', message: 'Forecast is stale.' }] },
    } as DecisionPacket
    const value = { ...workspace, decision: { draft: blocked, latest: null } } as InstrumentWorkspace
    const watch = { ...blocked, disposition: 'watch' as const, operator_reason: 'Wait for fresh evidence', packet_id: 'packet-watch-000000000001', parent_packet_id: blocked.packet_id, version: 2 }
    mocked.saveDecisionPacket.mockResolvedValue(blocked)
    mocked.applyDecisionPacketAction.mockResolvedValue({ packet: watch, proposal: null })
    render(<DecisionRail workspace={value} />, { wrapper: Providers })

    expect(screen.getByText('Evidence blocked')).toBeInTheDocument()
    expect(screen.getByText('Forecast is stale.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Create paper proposal' })).toBeDisabled()
    await user.type(screen.getByLabelText('Decision reason'), 'Wait for fresh evidence')
    expect(screen.getByRole('button', { name: 'Reject decision' })).toBeEnabled()
    expect(screen.getByRole('button', { name: 'Watch decision' })).toBeEnabled()
    await user.click(screen.getByRole('button', { name: 'Watch decision' }))

    await waitFor(() => expect(mocked.saveDecisionPacket).toHaveBeenCalledWith({
      expected_packet_id: blocked.packet_id, selected_range: '6m', symbol: 'NVDA', venue: 'moomoo',
    }))
    expect(mocked.applyDecisionPacketAction).toHaveBeenCalledWith(blocked.packet_id, {
      disposition: 'watch', limit_price: null, operator_reason: 'Wait for fresh evidence', quantity: null, side: null,
    })
    expect(await screen.findByText('packet-watch-000000000001')).toBeInTheDocument()
    expect(screen.getByText('Watching')).toBeInTheDocument()
  })

  it('saves the exact draft before creating a packet-bound proposal and leaves confirmation explicit', async () => {
    const user = userEvent.setup()
    render(<DecisionRail workspace={workspace} />, { wrapper: Providers })
    await user.click(screen.getByRole('button', { name: 'Create paper proposal' }))

    await waitFor(() => expect(mocked.saveDecisionPacket).toHaveBeenCalledTimes(1))
    expect(mocked.applyDecisionPacketAction).toHaveBeenCalledWith(packet.packet_id, {
      disposition: 'paper_proposal', limit_price: 182, operator_reason: null, quantity: 10, side: 'buy',
    })
    expect(screen.getByText('Paper proposed')).toBeInTheDocument()
    expect(screen.getAllByText('packet-paper-000000000001').length).toBeGreaterThan(0)
    expect(screen.getByText('proposal-1')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Confirm paper proposal' })).toBeDisabled()
    expect(mocked.confirmPaperProposal).not.toHaveBeenCalled()
  })

  it('sends operator-edited quantity and limit while retaining server defaults as the starting point', async () => {
    const user = userEvent.setup()
    render(<DecisionRail workspace={workspace} />, { wrapper: Providers })
    const quantityInput = screen.getByLabelText('Quantity')
    const limitInput = screen.getByLabelText('Optional limit price')
    await user.clear(quantityInput)
    await user.type(quantityInput, '12')
    await user.clear(limitInput)
    await user.type(limitInput, '181.5')
    await user.click(screen.getByRole('button', { name: 'Create paper proposal' }))

    await waitFor(() => expect(mocked.applyDecisionPacketAction).toHaveBeenCalledWith(packet.packet_id, {
      disposition: 'paper_proposal', limit_price: 181.5, operator_reason: null, quantity: 12, side: 'buy',
    }))
  })

  it('requires the displayed token and delegates the only second confirmation to the existing authority', async () => {
    const user = userEvent.setup()
    render(<DecisionRail workspace={workspace} />, { wrapper: Providers })
    await user.click(screen.getByRole('button', { name: 'Create paper proposal' }))
    const confirm = await screen.findByRole('button', { name: 'Confirm paper proposal' })
    expect(confirm).toBeDisabled()
    await user.type(screen.getByLabelText('Confirmation token'), proposal.confirmation_token)
    expect(confirm).toBeEnabled()
    await user.click(confirm)

    await waitFor(() => expect(mocked.confirmPaperProposal).toHaveBeenCalledWith(
      proposal.id,
      proposal.confirmation_token,
    ))
    expect(screen.getByText('Paper order created')).toBeInTheDocument()
    expect(screen.getByText('Order ID').closest('div')).toHaveTextContent('paper-order-1')
    expect(screen.getByRole('link', { name: 'Open audit lineage' })).toHaveAttribute(
      'href',
      '/ops/audit?order=paper-order-1',
    )
  })

  it('resumes a persisted packet-bound pending proposal after remount', () => {
    const proposedPacket = {
      ...packet,
      disposition: 'paper_proposal' as const,
      packet_id: 'packet-paper-persisted-001',
      parent_packet_id: packet.packet_id,
      proposal_id: proposal.id,
      version: 2,
    }
    render(
      <DecisionRail
        packet={proposedPacket}
        workspace={{
          ...workspace,
          decision: { draft: packet, latest: proposedPacket },
          proposal: { ...workspace.proposal, proposals: [proposal] },
        }}
      />,
      { wrapper: Providers },
    )

    expect(screen.getByText('Paper proposed')).toBeInTheDocument()
    expect(screen.getAllByText('packet-paper-persisted-001')).toHaveLength(2)
    expect(screen.getByText('proposal-1')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Confirm paper proposal' })).toBeInTheDocument()
    expect(mocked.applyDecisionPacketAction).not.toHaveBeenCalled()
  })

  it('does not attach an unrelated pending proposal to a fresh draft', () => {
    render(
      <DecisionRail workspace={{
        ...workspace,
        proposal: { ...workspace.proposal, proposals: [proposal] },
      }} />,
      { wrapper: Providers },
    )

    expect(screen.getByText('Draft analysis')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Create paper proposal' })).toBeInTheDocument()
    expect(screen.queryByText('Immutable proposal preview')).not.toBeInTheDocument()
  })

  it('keeps a configured draft visible but disables Paper during retained evidence refresh', () => {
    render(<DecisionRail evidenceUpdating workspace={workspace} />, { wrapper: Providers })

    expect(screen.getByText('Paper action waits for the selected evidence to finish loading.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Create paper proposal' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Reject decision' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Watch decision' })).toBeDisabled()
  })

  it('keeps incomplete valuation and a confirmation refusal visible', async () => {
    const user = userEvent.setup()
    const incomplete = {
      ...workspace,
      position: { ...workspace.position!, mark: null, mark_status: { provenance: 'real', reason: 'Quote is stale.', received_at: '2026-08-08T11:50:00Z', status: 'stale' }, unrealized_pnl: null },
      risk: { ...workspace.risk, valuation_complete: false, valuation_reason: 'One held position has no current mark.' },
    } as InstrumentWorkspace
    const refused: ProposalConfirmation = {
      blocker: 'Quote crossed the freshness fence.',
      order: null,
      proposal: { ...proposal, blockers: ['Quote crossed the freshness fence.'], status: 'rejected' },
      quote_provenance: null,
    }
    mocked.confirmPaperProposal.mockRejectedValue(new ProposalRefusalError(refused))
    render(<DecisionRail workspace={incomplete} />, { wrapper: Providers })

    expect(screen.getByText('Account equity').closest('div')).toHaveTextContent('Unavailable')
    expect(screen.getByText('Incomplete valuation')).toBeInTheDocument()
    expect(screen.getByText('One held position has no current mark.')).toBeInTheDocument()
    expect(screen.getByText('Quote is stale.')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Create paper proposal' }))
    await user.type(await screen.findByLabelText('Confirmation token'), proposal.confirmation_token)
    await user.click(screen.getByRole('button', { name: 'Confirm paper proposal' }))
    expect(await screen.findByText('Quote crossed the freshness fence.')).toBeInTheDocument()
    expect(screen.getByText('Proposal rejected')).toBeInTheDocument()
  })

  it('renders a persisted Watch packet without fixed-width overflow utilities', () => {
    const onNewAnalysis = vi.fn()
    const watch = { ...packet, disposition: 'watch' as const, operator_reason: 'Wait', packet_id: 'packet-watch-persisted-0001', parent_packet_id: packet.packet_id, version: 2 }
    const view = render(<DecisionRail onNewAnalysis={onNewAnalysis} packet={watch} workspace={{ ...workspace, decision: { draft: packet, latest: watch } }} />, { wrapper: Providers })

    expect(screen.getByText('Watching')).toBeInTheDocument()
    expect(screen.getByText('packet-watch-persisted-0001')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'New analysis' })).toBeInTheDocument()
    expect(view.container.querySelector('[class*="w-["]')).not.toBeInTheDocument()
  })
})
