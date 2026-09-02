import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, render, screen, waitFor, within } from '@testing-library/react'
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

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((next) => { resolve = next })
  return { promise, resolve }
}

function Providers({ children }: { children: React.ReactNode }) {
  return (
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <PreferencesProvider><MemoryRouter>{children}</MemoryRouter></PreferencesProvider>
    </QueryClientProvider>
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  window.localStorage.clear()
  mocked.saveDecisionPacket.mockResolvedValue(packet)
  mocked.applyDecisionPacketAction.mockResolvedValue({
    packet: { ...packet, disposition: 'paper_proposal', packet_id: 'packet-paper-000000000001', parent_packet_id: packet.packet_id, proposal_id: proposal.id, version: 2 },
    proposal,
  })
  mocked.confirmPaperProposal.mockResolvedValue(confirmation)
})

describe('DecisionRail', () => {
  it('localizes a known English blocker while keeping the raw server evidence visible', () => {
    const raw = 'Forecast artifact forecast-raw-123 exceeds one session.'
    const blocked = {
      ...packet,
      paper_capability: {
        allowed: false,
        blockers: [{ code: 'forecast-freshness', evidence_ref: 'forecast-raw-123', message: raw }],
      },
    } as DecisionPacket

    render(<DecisionRail packet={blocked} workspace={{ ...workspace, decision: { draft: blocked, latest: null } }} />, { wrapper: Providers })

    expect(screen.getByText('Forecast evidence is stale.')).toBeInTheDocument()
    expect(screen.getByText(`Original server evidence: ${raw}`)).toBeInTheDocument()
  })

  it('localizes a known zh-CN blocker while keeping the raw server evidence visible', () => {
    const raw = 'Raw checksum gap in history manifest history-raw-456.'
    const blocked = {
      ...packet,
      paper_capability: {
        allowed: false,
        blockers: [{ code: 'history-quality', evidence_ref: 'history-raw-456', message: raw }],
      },
    } as DecisionPacket
    window.localStorage.setItem('quantmesh.preferences', JSON.stringify({ locale: 'zh-CN', theme: 'dark' }))

    render(<DecisionRail packet={blocked} workspace={{ ...workspace, decision: { draft: blocked, latest: null } }} />, { wrapper: Providers })

    expect(screen.getByText('历史数据未通过质量检查。')).toBeInTheDocument()
    expect(screen.getByText(`服务端原始证据：${raw}`)).toBeInTheDocument()
  })

  it('shows an unknown server blocker message verbatim instead of inventing localized authority', () => {
    const raw = 'Future server policy blocked Paper.'
    const blocked = {
      ...packet,
      paper_capability: {
        allowed: false,
        blockers: [{ code: 'future-policy', evidence_ref: 'future-policy', message: raw }],
      },
    } as unknown as DecisionPacket

    render(<DecisionRail packet={blocked} workspace={{ ...workspace, decision: { draft: blocked, latest: null } }} />, { wrapper: Providers })

    expect(screen.getByText(raw)).toBeInTheDocument()
    expect(screen.queryByText(/Original server evidence:/)).not.toBeInTheDocument()
  })

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
    expect(screen.getByText('Global kill switch').closest('div')).toHaveTextContent('Disarmed')
    expect(screen.getByText('Venue kill switch').closest('div')).toHaveTextContent('Disarmed')
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
    expect(screen.getByText('Original server evidence: Forecast is stale.')).toBeInTheDocument()
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

  it('acts directly on an exact persisted Draft and offers an explicit fresh-analysis switch', async () => {
    const user = userEvent.setup()
    const persistedDraft = { ...packet, packet_id: 'packet-persisted-draft-0001' }
    const watch = {
      ...persistedDraft,
      disposition: 'watch' as const,
      operator_reason: 'Wait for entry',
      packet_id: 'packet-persisted-watch-0001',
      parent_packet_id: persistedDraft.packet_id,
      version: 2,
    }
    mocked.applyDecisionPacketAction.mockResolvedValue({ packet: watch, proposal: null })
    render(
      <DecisionRail
        contextKey="moomoo:NVDA:6m"
        onNewAnalysis={vi.fn()}
        packet={persistedDraft}
        packetSource="persisted"
        workspace={{ ...workspace, decision: { draft: packet, latest: persistedDraft } }}
      />,
      { wrapper: Providers },
    )

    expect(screen.getByRole('button', { name: 'New analysis' })).toBeInTheDocument()
    await user.type(screen.getByLabelText('Decision reason'), 'Wait for entry')
    await user.click(screen.getByRole('button', { name: 'Watch decision' }))

    expect(mocked.saveDecisionPacket).not.toHaveBeenCalled()
    expect(mocked.applyDecisionPacketAction).toHaveBeenCalledWith(persistedDraft.packet_id, {
      disposition: 'watch', limit_price: null, operator_reason: 'Wait for entry', quantity: null, side: null,
    })
    expect(await screen.findByText('packet-persisted-watch-0001')).toBeInTheDocument()
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

  it('preserves draft inputs and a completed action result across same-context polling', async () => {
    const user = userEvent.setup()
    const watch = {
      ...packet,
      disposition: 'watch' as const,
      operator_reason: 'Wait for entry',
      packet_id: 'packet-watch-stable-result',
      parent_packet_id: packet.packet_id,
      version: 2,
    }
    mocked.applyDecisionPacketAction.mockResolvedValue({ packet: watch, proposal: null })
    const view = render(
      <DecisionRail contextKey="moomoo:NVDA:6m" packet={packet} packetSource="fresh" workspace={workspace} />,
      { wrapper: Providers },
    )
    await user.type(screen.getByLabelText('Decision reason'), 'Wait for entry')
    await user.clear(screen.getByLabelText('Quantity'))
    await user.type(screen.getByLabelText('Quantity'), '12')
    const refreshedDraft = {
      ...packet,
      as_of: '2026-08-08T12:01:00Z',
      packet_id: 'packet-refresh-draft-0002',
    }
    mocked.saveDecisionPacket.mockResolvedValue(refreshedDraft)
    mocked.applyDecisionPacketAction.mockResolvedValue({
      packet: { ...watch, parent_packet_id: refreshedDraft.packet_id },
      proposal: null,
    })
    view.rerender(
      <DecisionRail
        contextKey="moomoo:NVDA:6m"
        packet={refreshedDraft}
        packetSource="fresh"
        workspace={{ ...workspace, decision: { draft: refreshedDraft, latest: null } }}
      />,
    )

    expect(screen.getByLabelText('Decision reason')).toHaveValue('Wait for entry')
    expect(screen.getByLabelText('Quantity')).toHaveValue(12)
    await user.click(screen.getByRole('button', { name: 'Watch decision' }))
    expect(await screen.findByText('packet-watch-stable-result')).toBeInTheDocument()

    const nextDraft = { ...refreshedDraft, packet_id: 'packet-refresh-draft-0003' }
    view.rerender(
      <DecisionRail
        contextKey="moomoo:NVDA:6m"
        packet={nextDraft}
        packetSource="fresh"
        workspace={{ ...workspace, decision: { draft: nextDraft, latest: null } }}
      />,
    )
    expect(screen.getByText('packet-watch-stable-result')).toBeInTheDocument()
    expect(screen.queryByText('packet-refresh-draft-0003')).not.toBeInTheDocument()
  })

  it('completes an exact saved action when same-context polling replaces the fresh draft ID', async () => {
    const user = userEvent.setup()
    const pendingSave = deferred<DecisionPacket>()
    const watch = {
      ...packet,
      disposition: 'watch' as const,
      operator_reason: 'Keep exact action',
      packet_id: 'packet-watch-after-save-refetch',
      parent_packet_id: packet.packet_id,
      version: 2,
    }
    mocked.saveDecisionPacket.mockReturnValue(pendingSave.promise)
    mocked.applyDecisionPacketAction.mockResolvedValue({ packet: watch, proposal: null })
    const view = render(
      <DecisionRail contextKey="moomoo:NVDA:6m" packet={packet} packetSource="fresh" workspace={workspace} />,
      { wrapper: Providers },
    )
    await user.type(screen.getByLabelText('Decision reason'), 'Keep exact action')
    await user.click(screen.getByRole('button', { name: 'Watch decision' }))

    const refreshedDraft = { ...packet, packet_id: 'packet-same-context-refresh-during-save' }
    view.rerender(
      <DecisionRail
        contextKey="moomoo:NVDA:6m"
        packet={refreshedDraft}
        packetSource="fresh"
        workspace={{ ...workspace, decision: { draft: refreshedDraft, latest: null } }}
      />,
    )
    await act(async () => pendingSave.resolve(packet))

    expect(await screen.findByText('packet-watch-after-save-refetch')).toBeInTheDocument()
    expect(mocked.applyDecisionPacketAction).toHaveBeenCalledWith(packet.packet_id, expect.objectContaining({
      disposition: 'watch', operator_reason: 'Keep exact action',
    }))
  })

  it('accepts a durable action result when same-context polling changes the draft during the request', async () => {
    const user = userEvent.setup()
    const pendingAction = deferred<Awaited<ReturnType<typeof api.applyDecisionPacketAction>>>()
    mocked.applyDecisionPacketAction.mockReturnValue(pendingAction.promise)
    const view = render(
      <DecisionRail contextKey="moomoo:NVDA:6m" packet={packet} packetSource="fresh" workspace={workspace} />,
      { wrapper: Providers },
    )
    await user.type(screen.getByLabelText('Decision reason'), 'Keep durable result')
    await user.click(screen.getByRole('button', { name: 'Watch decision' }))
    await waitFor(() => expect(mocked.applyDecisionPacketAction).toHaveBeenCalledTimes(1))

    const refreshedDraft = { ...packet, packet_id: 'packet-same-context-refresh-during-action' }
    view.rerender(
      <DecisionRail
        contextKey="moomoo:NVDA:6m"
        packet={refreshedDraft}
        packetSource="fresh"
        workspace={{ ...workspace, decision: { draft: refreshedDraft, latest: null } }}
      />,
    )
    await act(async () => pendingAction.resolve({
      packet: {
        ...packet,
        disposition: 'watch',
        operator_reason: 'Keep durable result',
        packet_id: 'packet-watch-durable-result',
        parent_packet_id: packet.packet_id,
        version: 2,
      },
      proposal: null,
    }))

    expect(await screen.findByText('packet-watch-durable-result')).toBeInTheDocument()
    expect(screen.queryByText('packet-same-context-refresh-during-action')).not.toBeInTheDocument()
  })

  it('drops a deferred save/action response after the full workspace context changes', async () => {
    const user = userEvent.setup()
    const pendingSave = deferred<DecisionPacket>()
    mocked.saveDecisionPacket.mockReturnValue(pendingSave.promise)
    const view = render(
      <DecisionRail contextKey="moomoo:NVDA:6m" packet={packet} packetSource="fresh" workspace={workspace} />,
      { wrapper: Providers },
    )
    await user.type(screen.getByLabelText('Decision reason'), 'Wait here')
    await user.click(screen.getByRole('button', { name: 'Watch decision' }))

    const aaplInstrument = { ...instrument, symbol: 'AAPL' }
    const aaplPacket = {
      ...packet,
      instrument: aaplInstrument,
      packet_id: 'packet-aapl-draft-0001',
    } as DecisionPacket
    view.rerender(
      <DecisionRail
        contextKey="moomoo:AAPL:6m"
        packet={aaplPacket}
        packetSource="fresh"
        workspace={{
          ...workspace,
          decision: { draft: aaplPacket, latest: null },
          history: { ...workspace.history, instrument: aaplInstrument },
          instrument: aaplInstrument,
        }}
      />,
    )
    await act(async () => pendingSave.resolve(packet))

    await waitFor(() => expect(screen.getByText('packet-aapl-draft-0001')).toBeInTheDocument())
    expect(mocked.applyDecisionPacketAction).not.toHaveBeenCalled()
    expect(screen.queryByText('packet-watch-stable-result')).not.toBeInTheDocument()
  })

  it('drops a deferred action result after the full workspace context changes', async () => {
    const user = userEvent.setup()
    const pendingAction = deferred<Awaited<ReturnType<typeof api.applyDecisionPacketAction>>>()
    mocked.applyDecisionPacketAction.mockReturnValue(pendingAction.promise)
    const view = render(
      <DecisionRail contextKey="moomoo:NVDA:6m" packet={packet} packetSource="fresh" workspace={workspace} />,
      { wrapper: Providers },
    )
    await user.type(screen.getByLabelText('Decision reason'), 'Wait here')
    await user.click(screen.getByRole('button', { name: 'Watch decision' }))
    await waitFor(() => expect(mocked.applyDecisionPacketAction).toHaveBeenCalledTimes(1))

    const aaplInstrument = { ...instrument, symbol: 'AAPL' }
    const aaplPacket = {
      ...packet,
      instrument: aaplInstrument,
      packet_id: 'packet-aapl-draft-0002',
    } as DecisionPacket
    view.rerender(
      <DecisionRail
        contextKey="moomoo:AAPL:6m"
        packet={aaplPacket}
        packetSource="fresh"
        workspace={{
          ...workspace,
          decision: { draft: aaplPacket, latest: null },
          history: { ...workspace.history, instrument: aaplInstrument },
          instrument: aaplInstrument,
        }}
      />,
    )
    await act(async () => pendingAction.resolve({
      packet: {
        ...packet,
        disposition: 'watch',
        packet_id: 'packet-watch-stale-response',
        parent_packet_id: packet.packet_id,
        version: 2,
      },
      proposal: null,
    }))

    expect(screen.getByText('packet-aapl-draft-0002')).toBeInTheDocument()
    expect(screen.queryByText('packet-watch-stale-response')).not.toBeInTheDocument()
  })

  it('rejects an action response that is not bound to the submitted packet context', async () => {
    const user = userEvent.setup()
    mocked.applyDecisionPacketAction.mockResolvedValue({
      packet: {
        ...packet,
        instrument: { ...instrument, symbol: 'AAPL' },
        disposition: 'watch',
        packet_id: 'packet-wrong-context',
        parent_packet_id: packet.packet_id,
        version: 2,
      },
      proposal: null,
    })
    render(
      <DecisionRail contextKey="moomoo:NVDA:6m" packet={packet} packetSource="fresh" workspace={workspace} />,
      { wrapper: Providers },
    )
    await user.type(screen.getByLabelText('Decision reason'), 'Wait here')
    await user.click(screen.getByRole('button', { name: 'Watch decision' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('does not match')
    expect(screen.queryByText('packet-wrong-context')).not.toBeInTheDocument()
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
    const terminal = screen.getByText('Paper order created').closest('section')!
    expect(within(terminal).getByText('packet-paper-000000000001')).toHaveClass('break-all')
    expect(within(terminal).getByText(proposal.id)).toHaveClass('break-all')
    expect(within(terminal).getByText('Order ID').closest('div')).toHaveTextContent('paper-order-1')
    expect(within(terminal).getByText('paper-order-1')).toHaveClass('break-all')
    expect(screen.getByRole('link', { name: 'Open audit lineage' })).toHaveAttribute(
      'href',
      '/ops/audit?order=paper-order-1',
    )
  })

  it('wraps long packet, proposal, and order identities in the terminal state', async () => {
    const user = userEvent.setup()
    const longPacketId = `packet-${'p'.repeat(96)}`
    const longProposalId = `proposal-${'r'.repeat(96)}`
    const longOrderId = `order-${'o'.repeat(96)}`
    const longRoot = { ...packet, packet_id: longPacketId }
    const longProposal = { ...proposal, id: longProposalId }
    mocked.saveDecisionPacket.mockResolvedValue(longRoot)
    mocked.applyDecisionPacketAction.mockResolvedValue({
      packet: {
        ...longRoot,
        disposition: 'paper_proposal',
        packet_id: `packet-result-${'x'.repeat(96)}`,
        parent_packet_id: longRoot.packet_id,
        proposal_id: longProposal.id,
        version: 2,
      },
      proposal: longProposal,
    })
    mocked.confirmPaperProposal.mockResolvedValue({
      ...confirmation,
      order: { ...confirmation.order!, order_id: longOrderId },
      proposal: { ...longProposal, order_id: longOrderId, status: 'confirmed' },
    })
    render(
      <DecisionRail
        contextKey="moomoo:NVDA:6m"
        packet={longRoot}
        packetSource="fresh"
        workspace={{ ...workspace, decision: { draft: longRoot, latest: null } }}
      />,
      { wrapper: Providers },
    )
    await user.click(screen.getByRole('button', { name: 'Create paper proposal' }))
    await user.type(await screen.findByLabelText('Confirmation token'), longProposal.confirmation_token)
    await user.click(screen.getByRole('button', { name: 'Confirm paper proposal' }))

    const terminal = (await screen.findByText('Paper order created')).closest('section')!
    for (const identity of [`packet-result-${'x'.repeat(96)}`, longProposal.id, longOrderId]) {
      expect(within(terminal).getByText(identity)).toHaveClass('break-all', '[overflow-wrap:anywhere]')
    }
  })

  it('rejects a confirmation response for another instrument context', async () => {
    const user = userEvent.setup()
    mocked.confirmPaperProposal.mockResolvedValue({
      ...confirmation,
      order: { ...confirmation.order!, instrument: { ...instrument, symbol: 'AAPL' } },
      proposal: { ...confirmation.proposal, instrument: { ...instrument, symbol: 'AAPL' } },
    })
    render(<DecisionRail workspace={workspace} />, { wrapper: Providers })
    await user.click(screen.getByRole('button', { name: 'Create paper proposal' }))
    await user.type(await screen.findByLabelText('Confirmation token'), proposal.confirmation_token)
    await user.click(screen.getByRole('button', { name: 'Confirm paper proposal' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('does not match')
    expect(screen.queryByText('Paper order created')).not.toBeInTheDocument()
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
