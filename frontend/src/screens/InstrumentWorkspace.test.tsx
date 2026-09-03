import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { MemoryRouter, Route, Routes } from 'react-router-dom'

import { ApiError, api, type DecisionPacket, type InstrumentWorkspace } from '@/lib/api'
import { dateTime } from '@/lib/format'
import { useLiveConnection } from '@/lib/live'
import { PreferencesProvider } from '@/lib/preferences'

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>()
  return {
    ...actual,
    api: {
      ...actual.api,
      applyDecisionPacketAction: vi.fn(),
      confirmPaperProposal: vi.fn(),
      decisionPacket: vi.fn(),
      health: vi.fn(),
      instrumentWorkspace: vi.fn(),
      liveState: vi.fn(),
      markets: vi.fn(),
      packetCopilot: vi.fn(),
      requestPacketCopilot: vi.fn(),
      saveDecisionPacket: vi.fn(),
    },
  }
})

vi.mock('@/lib/live', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/live')>()
  return { ...actual, useLiveConnection: vi.fn(() => 'live') }
})

vi.mock('@/components/charts/InstrumentChart', () => ({
  InstrumentChart: ({ primary }: { primary: InstrumentWorkspace['history'] }) => (
    <div data-testid="instrument-chart">{primary.instrument.symbol} chart</div>
  ),
}))

import { InstrumentWorkspaceScreen } from './InstrumentWorkspace'
import { retainSameInstrument } from './instrument/workspace-query'

const workspace: InstrumentWorkspace = {
  comparison: null,
  decision: {
    draft: {
      as_of: '2026-08-08T12:00:00Z',
      created_at: '2026-08-08T12:00:00Z',
      disposition: 'draft',
      evidence: {
        costs: { fee_bps: 1.5, half_spread_bps: null, slippage_bps: 2.5, spread_status: 'confirmation-quote-required' },
        forecast_artifact_id: null,
        forecast_blockers: ['No promoted artifact for this range.'],
        forecast_eligible: null,
        forecast_limitations: [],
        forecast_metrics: [],
        forecast_paths: [],
        forecast_synthetic: null,
        history_dataset_id: 'demo-history',
        history_dataset_revision: 1,
        history_duplicates: [],
        history_gaps: [],
        history_generated_at: '2026-08-08T12:00:00Z',
        history_limitations: ['Synthetic data'],
        history_source: 'demo-synthetic',
      },
      instrument: {
        currency: 'USD', instrument_type: 'equity', metadata: {}, symbol: 'NVDA', venue: 'moomoo',
      },
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
      paper_capability: {
        allowed: false,
        blockers: [{ code: 'forecast-missing', evidence_ref: 'workspace', message: 'No promoted artifact for this range.' }],
      },
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
    },
    latest: null,
  },
  forecast: null,
  forecast_unavailable_reason: 'No promoted artifact for this range.',
  generated_at: '2026-08-08T12:00:00Z',
  history: {
    adjustment: 'unadjusted',
    as_of: '2026-08-08T12:00:00Z',
    bars: [
      {
        adjusted_close: null,
        close: 184,
        high: 185,
        instrument: {
          currency: 'USD',
          instrument_type: 'equity',
          metadata: {},
          symbol: 'NVDA',
          venue: 'moomoo',
        },
        interval: '1d',
        is_live_tail: false,
        live_lineage: null,
        low: 180,
        open: 181,
        timestamp: '2026-08-07T20:00:00Z',
        volume: 1_200_000,
      },
    ],
    calendar: 'XNYS',
    coverage: {
      end: '2026-08-07T20:00:00Z',
      interval: '1d',
      rows: 1,
      start: '2026-08-07T20:00:00Z',
      symbol: 'NVDA',
      venue: 'moomoo',
    },
    coverage_scope: 'historical-only',
    dataset_id: 'demo-history',
    dataset_revision: 1,
    duplicates: [],
    gaps: [],
    generated_at: '2026-08-08T12:00:00Z',
    instrument: {
      currency: 'USD',
      instrument_type: 'equity',
      metadata: {},
      symbol: 'NVDA',
      venue: 'moomoo',
    },
    interval: '1d',
    license: 'demo-synthetic',
    limitations: ['Synthetic data'],
    range: '6m',
    resolution_fallback: null,
    source: 'demo-synthetic',
  },
  instrument: {
    currency: 'USD',
    instrument_type: 'equity',
    metadata: {},
    symbol: 'NVDA',
    venue: 'moomoo',
  },
  live: {
    age_ms: 95_000,
    ask: 184.2,
    bid: 183.8,
    data_time: '2026-08-08T11:58:25Z',
    label: 'stale',
    last: 184,
    provenance: 'demo-synthetic',
    reason: 'Quote age exceeds the paper-action fence.',
    received_at: '2026-08-08T11:58:25Z',
    sequence: 12,
    sequence_gap: false,
    source: 'demo-synthetic',
    status: 'degraded',
  },
  position: null,
  proposal: {
    allowed: false,
    blockers: ['Quote age exceeds the paper-action fence.'],
    proposals: [],
  },
  risk: {
    cash: 100_000,
    equity: 100_000,
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

const mockedWorkspace = vi.mocked(api.instrumentWorkspace)
const mockedDecisionPacket = vi.mocked(api.decisionPacket)
const mockedSaveDecisionPacket = vi.mocked(api.saveDecisionPacket)
const mockedApplyDecisionPacketAction = vi.mocked(api.applyDecisionPacketAction)
const mockedConfirmPaperProposal = vi.mocked(api.confirmPaperProposal)
const mockedHealth = vi.mocked(api.health)
const mockedLiveState = vi.mocked(api.liveState)
const mockedMarkets = vi.mocked(api.markets)
const mockedPacketCopilot = vi.mocked(api.packetCopilot)
const mockedRequestPacketCopilot = vi.mocked(api.requestPacketCopilot)
const mockedLiveConnection = vi.mocked(useLiveConnection)
let publishLiveUpdate: Parameters<typeof useLiveConnection>[0]

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((next) => { resolve = next })
  return { promise, resolve }
}

function renderWorkspace(path = '/instruments/moomoo/NVDA?range=6m') {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <PreferencesProvider>
        <MemoryRouter initialEntries={[path]}>
          <main data-testid="app-main">
            <Routes>
              <Route path="/instruments/:venue/:symbol" element={<InstrumentWorkspaceScreen />} />
            </Routes>
          </main>
        </MemoryRouter>
      </PreferencesProvider>
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  mockedLiveConnection.mockImplementation((onUpdate) => {
    publishLiveUpdate = onUpdate
    return 'live'
  })
  mockedWorkspace.mockResolvedValue(workspace)
  mockedPacketCopilot.mockImplementation(async (packetId) => ({
    packet_id: packetId,
    reason_code: null,
    record: null,
    status: 'idle',
  }))
  mockedRequestPacketCopilot.mockImplementation(async (packetId) => ({
    packet_id: packetId,
    reason_code: 'copilot-unavailable',
    record: null,
    status: 'degraded',
  }))
  mockedDecisionPacket.mockRejectedValue(new ApiError(404, 'Exact packet fixture not configured'))
  mockedLiveState.mockResolvedValue({
    generated_at: '2026-08-08T12:00:00Z',
    instruments: {
      'hyperliquid:BTC': {
        instrument: 'BTC',
        kinds: {
          quote: {
            age_ms: 10,
            data_time: '2026-08-08T12:00:00Z',
            kind: 'quote',
            label: 'real',
            payload: { ask: 100.5, bid: 100 },
            provenance: 'real',
            received_at: '2026-08-08T12:00:00Z',
            sequence: 1,
            sequence_gap: false,
          },
        },
        label: 'real',
        venue: 'hyperliquid',
      },
    },
  })
  mockedMarkets.mockResolvedValue({
    instruments: [{ mark: null, symbol: 'BTC', venue: 'hyperliquid' }],
  })
  mockedHealth.mockResolvedValue({
    live_trading: false,
    paper_mode: true,
    project: 'QuantMesh',
    runtime_mode: 'demo',
    status: 'ok',
    version: '0.1.1rc1',
  })
})

describe('InstrumentWorkspaceScreen', () => {
  it('promotes an action result across market, scenarios, evidence, risk, and actions during polling', async () => {
    const user = userEvent.setup()
    const parent = {
      ...workspace.decision.draft,
      evidence: {
        ...workspace.decision.draft.evidence,
        history_dataset_id: 'action-lineage-history',
      },
      market_state: {
        ...workspace.decision.draft.market_state,
        support: 181.25,
      },
      packet_id: 'packet-action-parent-0001',
      risk_plan: {
        ...workspace.decision.draft.risk_plan,
        entry_price: 182.25,
      },
      scenarios: workspace.decision.draft.scenarios.map((scenario) => scenario.kind === 'bull'
        ? { ...scenario, thesis: 'Action lineage bull thesis' }
        : scenario),
    } satisfies DecisionPacket
    const child = {
      ...parent,
      disposition: 'watch' as const,
      operator_reason: 'Keep the action lineage',
      packet_id: 'packet-action-watch-0002',
      parent_packet_id: parent.packet_id,
      version: 2,
    } satisfies DecisionPacket
    const initial = {
      ...workspace,
      decision: { draft: parent, latest: null },
      history: { ...workspace.history, dataset_id: 'action-lineage-history' },
    } satisfies InstrumentWorkspace
    const backgroundDraft = {
      ...parent,
      evidence: { ...parent.evidence, history_dataset_id: 'background-draft-history' },
      market_state: { ...parent.market_state, support: 999.25 },
      packet_id: 'packet-background-draft-0003',
      risk_plan: { ...parent.risk_plan, entry_price: 998.25 },
      scenarios: parent.scenarios.map((scenario) => scenario.kind === 'bull'
        ? { ...scenario, thesis: 'Background draft bull thesis' }
        : scenario),
    } satisfies DecisionPacket
    const refreshed = {
      ...initial,
      decision: { draft: backgroundDraft, latest: null },
      generated_at: '2026-08-08T12:01:00Z',
      history: { ...initial.history, dataset_id: 'background-draft-history' },
    } satisfies InstrumentWorkspace
    mockedWorkspace.mockResolvedValueOnce(initial).mockResolvedValue(refreshed)
    mockedSaveDecisionPacket.mockResolvedValue(parent)
    mockedApplyDecisionPacketAction.mockResolvedValue({ packet: child, proposal: null })
    renderWorkspace()

    await user.type(await screen.findByLabelText('Decision reason'), 'Keep the action lineage')
    await user.click(screen.getByRole('button', { name: 'Watch decision' }))
    expect(await screen.findByText(child.packet_id)).toBeInTheDocument()

    await act(async () => publishLiveUpdate({
      data_time: '2026-08-08T12:00:30Z',
      instrument: 'NVDA',
      kind: 'quote',
      payload: { ask: 185, bid: 184 },
      provenance: 'demo-synthetic',
      received_at: '2026-08-08T12:00:30Z',
      sequence: 13,
      sequence_gap: false,
      state: 'connected',
      state_note: null,
      venue: 'moomoo',
    }))
    await waitFor(() => expect(mockedWorkspace).toHaveBeenCalledTimes(2))

    const market = screen.getByRole('region', { name: 'Observed market canvas' })
    expect(within(market).getByText('181.25')).toBeInTheDocument()
    expect(within(market).queryByText('999.25')).not.toBeInTheDocument()
    const evidence = screen.getByRole('region', { name: 'Evidence' })
    expect(within(evidence).getByText('Action lineage bull thesis')).toBeInTheDocument()
    expect(within(evidence).getByText('action-lineage-history')).toBeInTheDocument()
    expect(within(evidence).queryByText('Background draft bull thesis')).not.toBeInTheDocument()
    expect(within(evidence).queryByText('background-draft-history')).not.toBeInTheDocument()
    const decision = screen.getByRole('complementary', { name: 'Decision rail' })
    expect(within(decision).getByText('Entry').closest('div')).toHaveTextContent('$182.2500')
    expect(within(decision).getByText(child.packet_id)).toBeInTheDocument()
    expect(within(decision).queryByText('$998.2500')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'New analysis' })).toBeInTheDocument()
  })

  it('keeps a persisted decision visible when a background refresh returns a fresh draft', async () => {
    const persisted = {
      ...workspace.decision.draft,
      disposition: 'watch' as const,
      operator_reason: 'Wait for entry',
      packet_id: 'packet-watch-persisted-0001',
      parent_packet_id: workspace.decision.draft.packet_id,
      version: 2,
    }
    const first = { ...workspace, decision: { draft: workspace.decision.draft, latest: persisted } }
    const refreshed = {
      ...workspace,
      generated_at: '2026-08-08T12:01:00Z',
      decision: {
        draft: {
          ...workspace.decision.draft,
          as_of: '2026-08-08T12:01:00Z',
          packet_id: 'packet-fresh-background-0001',
        },
        latest: {
          ...persisted,
          operator_reason: 'A newer persisted decision',
          packet_id: 'packet-watch-newer-0002',
        },
      },
    }
    mockedDecisionPacket.mockResolvedValue(persisted)
    mockedWorkspace.mockResolvedValueOnce(first).mockResolvedValue(refreshed)
    renderWorkspace()

    expect(await screen.findByText('packet-watch-persisted-0001')).toBeInTheDocument()
    expect(screen.getByText('Watching')).toBeInTheDocument()

    await act(async () => publishLiveUpdate({
      data_time: '2026-08-08T12:00:30Z',
      instrument: 'NVDA',
      kind: 'quote',
      payload: { ask: 185, bid: 184 },
      provenance: 'demo-synthetic',
      received_at: '2026-08-08T12:00:30Z',
      sequence: 13,
      sequence_gap: false,
      state: 'connected',
      state_note: null,
      venue: 'moomoo',
    }))
    await waitFor(() => expect(mockedWorkspace).toHaveBeenCalledTimes(2))

    expect(screen.getByText('packet-watch-persisted-0001')).toBeInTheDocument()
    expect(screen.queryByText('packet-fresh-background-0001')).not.toBeInTheDocument()
    expect(screen.queryByText('packet-watch-newer-0002')).not.toBeInTheDocument()
    expect(mockedDecisionPacket).toHaveBeenCalledWith('packet-watch-persisted-0001')
    expect(screen.getByRole('button', { name: 'New analysis' })).toBeInTheDocument()
  })

  it('separates current chart context from complete archived packet evidence', async () => {
    const archivedDataset = 'dataset-archived-without-any-break-opportunity-0123456789'
    const archivedModel = 'model-archived-without-any-break-opportunity-0123456789'
    const persisted = {
      ...workspace.decision.draft,
      disposition: 'watch' as const,
      evidence: {
        ...workspace.decision.draft.evidence,
        forecast_artifact_id: 'artifact-archived-without-any-break-opportunity-0123456789',
        forecast_benchmark_name: 'archived-last-close',
        forecast_chronology: {
          test_end: '2026-06-30T20:00:00Z',
          test_start: '2026-06-01T20:00:00Z',
          train_end: '2026-04-30T20:00:00Z',
          train_start: '2024-01-01T20:00:00Z',
          validation_end: '2026-05-31T20:00:00Z',
          validation_start: '2026-05-01T20:00:00Z',
        },
        forecast_dataset_id: 'forecast-dataset-archived-0123456789',
        forecast_dataset_revision: 11,
        forecast_eligible: false,
        forecast_generated_at: '2026-07-01T12:00:00Z',
        forecast_metrics: [{
          benchmark_mae: 4.5,
          coverage_50: 0.51,
          coverage_80: 0.79,
          coverage_95: 0.94,
          interval_test_count: 12,
          mae: 3.5,
          residual_count: 120,
          rmse: 4.1,
          sessions: 30 as const,
          test_end: '2026-06-30T20:00:00Z',
          test_start: '2026-06-01T20:00:00Z',
          validation_end: '2026-05-31T20:00:00Z',
          validation_start: '2026-05-01T20:00:00Z',
        }],
        forecast_model_name: archivedModel,
        forecast_model_version: 'archived-model-version-1',
        forecast_paths: [{
          points: [{
            p025: 150, p10: 160, p25: 170, p50: 185, p75: 195, p90: 205, p975: 215,
            session: 1, timestamp: '2026-07-02T20:00:00Z',
          }],
          sessions: 30 as const,
        }],
        forecast_synthetic: true,
        history_dataset_id: archivedDataset,
        history_dataset_revision: 7,
        history_duplicates: ['2026-06-02T20:00:00Z'],
        history_gaps: ['2026-06-03T20:00:00Z'],
        history_generated_at: '2026-07-01T12:00:00Z',
      },
      operator_reason: 'Replay archived decision',
      packet_id: 'packet-archived-without-any-break-opportunity-0123456789',
      parent_packet_id: workspace.decision.draft.packet_id,
      version: 2,
    }
    mockedDecisionPacket.mockResolvedValue(persisted)
    mockedWorkspace.mockResolvedValue({
      ...workspace,
      history: { ...workspace.history, dataset_id: 'current-workspace-dataset' },
      decision: { draft: workspace.decision.draft, latest: persisted },
    })
    renderWorkspace()

    const evidence = await screen.findByRole('region', { name: 'Evidence' })
    expect(within(evidence).getByText('Archived DecisionPacket evidence')).toBeInTheDocument()
    expect(within(evidence).getByText(archivedDataset)).toHaveClass('break-all', '[overflow-wrap:anywhere]')
    expect(within(evidence).getByText(archivedModel)).toHaveClass('break-all', '[overflow-wrap:anywhere]')
    expect(within(evidence).queryByText('current-workspace-dataset')).not.toBeInTheDocument()
    expect(within(evidence).getByText('forecast-dataset-archived-0123456789')).toBeInTheDocument()
    expect(within(evidence).getByText(/Not eligible/)).toBeInTheDocument()
    expect(within(evidence).getByText('Synthetic')).toBeInTheDocument()
    expect(within(evidence).getByText('Rolling validation window').closest('div')).toHaveTextContent('May')
    expect(within(evidence).getByText('Rolling test window').closest('div')).toHaveTextContent('Jun')
    expect(within(evidence).getByText(/30-session forecast path/).closest('details')).toHaveTextContent('185')
    expect(within(evidence).getByText('History gaps').closest('details')).toHaveTextContent(
      dateTime('2026-06-03T20:00:00Z', 'en'),
    )
    expect(within(evidence).getByText('History duplicates').closest('details')).toHaveTextContent(
      dateTime('2026-06-02T20:00:00Z', 'en'),
    )
    expect(within(evidence).getByText(/Coverage 50\/80\/95/).closest('div')).toHaveTextContent('51%')
    expect(screen.getByText('Current chart only — not archived packet evidence')).toBeInTheDocument()
    expect(screen.getByText(/Archived packet levels as of/)).toHaveTextContent('Aug 8')
  })

  it('pauses Reject, Watch, and Paper while a requested range still shows placeholder evidence', async () => {
    const pending = deferred<InstrumentWorkspace>()
    const allowedDraft = {
      ...workspace.decision.draft,
      paper_capability: { allowed: true, blockers: [] },
    }
    mockedWorkspace
      .mockResolvedValueOnce({
        ...workspace,
        decision: { draft: allowedDraft, latest: null },
        proposal: { allowed: true, blockers: [], proposals: [] },
      })
      .mockReturnValueOnce(pending.promise)
    const user = userEvent.setup()
    renderWorkspace()
    await user.type(await screen.findByLabelText('Decision reason'), 'Wait for alignment')
    expect(screen.getByRole('button', { name: 'Reject decision' })).toBeEnabled()
    expect(screen.getByRole('button', { name: 'Watch decision' })).toBeEnabled()
    expect(screen.getByRole('button', { name: 'Create paper proposal' })).toBeEnabled()
    expect(screen.getByTestId('packet-copilot')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: '1M' }))

    expect(await screen.findByText('Decision actions and confirmation are paused while requested evidence replaces the displayed prior context.')).toBeInTheDocument()
    expect(screen.queryByTestId('packet-copilot')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Reject decision' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Watch decision' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Create paper proposal' })).toBeDisabled()
    await user.click(screen.getByRole('button', { name: 'Reject decision' }))
    await user.click(screen.getByRole('button', { name: 'Watch decision' }))
    await user.click(screen.getByRole('button', { name: 'Create paper proposal' }))
    expect(api.saveDecisionPacket).not.toHaveBeenCalled()
    expect(api.applyDecisionPacketAction).not.toHaveBeenCalled()
  })

  it('pauses an existing proposal confirmation while a requested range still shows placeholder evidence', async () => {
    const pending = deferred<InstrumentWorkspace>()
    const proposed = {
      ...workspace.decision.draft,
      disposition: 'paper_proposal' as const,
      packet_id: 'packet-proposed-range-gate',
      parent_packet_id: workspace.decision.draft.packet_id,
      proposal_id: 'proposal-range-gate',
      version: 2,
    }
    const pendingProposal = {
      artifact_id: 'artifact-range-gate', blockers: [], config_digest: 'config-range-gate',
      confirmation_token: 'CONFIRM-RANGE', created_at: '2026-08-08T12:01:00Z',
      dataset_id: 'demo-history', dataset_revision: 1, forecast_generated_at: '2026-08-08T12:00:00Z',
      history_digest: 'history-range-gate', id: 'proposal-range-gate', instrument: workspace.instrument,
      limit_price: 182, model_version: '1.0.0', order_id: null, order_type: 'limit' as const,
      quantity: 10, quote_provenance: null, side: 'buy' as const, status: 'pending' as const,
    }
    mockedDecisionPacket.mockResolvedValue(proposed)
    mockedWorkspace
      .mockResolvedValueOnce({
        ...workspace,
        decision: { draft: workspace.decision.draft, latest: proposed },
        proposal: { allowed: true, blockers: [], proposals: [pendingProposal] },
      })
      .mockReturnValueOnce(pending.promise)
    const user = userEvent.setup()
    renderWorkspace()
    await user.type(await screen.findByLabelText('Confirmation token'), pendingProposal.confirmation_token)
    expect(screen.getByRole('button', { name: 'Confirm paper proposal' })).toBeEnabled()

    await user.click(screen.getByRole('button', { name: '1M' }))

    expect(await screen.findByText('Decision actions and confirmation are paused while requested evidence replaces the displayed prior context.')).toBeInTheDocument()
    expect(screen.getByLabelText('Confirmation token')).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Confirm paper proposal' })).toBeDisabled()
    await user.click(screen.getByRole('button', { name: 'Confirm paper proposal' }))
    expect(mockedConfirmPaperProposal).not.toHaveBeenCalled()
  })

  it('resets packet selection when the venue-symbol-range context changes', async () => {
    const user = userEvent.setup()
    const persisted = {
      ...workspace.decision.draft,
      disposition: 'watch' as const,
      operator_reason: 'Six month archive',
      packet_id: 'packet-6m-latest',
      parent_packet_id: workspace.decision.draft.packet_id,
      version: 2,
    }
    const nextDraft = {
      ...workspace.decision.draft,
      packet_id: 'packet-1m-draft',
      selected_range: '1m' as const,
    }
    const nextLatest = {
      ...nextDraft,
      disposition: 'watch' as const,
      operator_reason: 'One month archive',
      packet_id: 'packet-1m-latest',
      parent_packet_id: nextDraft.packet_id,
      version: 2,
    }
    mockedWorkspace
      .mockResolvedValueOnce({ ...workspace, decision: { draft: workspace.decision.draft, latest: persisted } })
      .mockResolvedValue({
        ...workspace,
        history: { ...workspace.history, range: '1m' },
        decision: { draft: nextDraft, latest: nextLatest },
      })
    renderWorkspace()

    expect(await screen.findByText('packet-6m-latest')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'New analysis' }))
    expect(screen.getByText(workspace.decision.draft.packet_id)).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: '1M' }))

    expect(await screen.findByText('packet-1m-latest')).toBeInTheDocument()
    expect(screen.queryByText('packet-1m-draft')).not.toBeInTheDocument()
  })

  it('reuses placeholder evidence only for the same venue and symbol', () => {
    expect(retainSameInstrument(
      workspace,
      ['instrument-workspace', 'moomoo', 'NVDA', '6m', []],
      'moomoo',
      'NVDA',
    )).toBe(workspace)
    expect(retainSameInstrument(
      workspace,
      ['instrument-workspace', 'moomoo', 'AAPL', '6m', []],
      'moomoo',
      'NVDA',
    )).toBeUndefined()
  })

  it('loads the venue-aware instrument and renders the workspace hierarchy', async () => {
    renderWorkspace()

    await waitFor(() => expect(screen.getByRole('heading', { name: 'NVDA' })).toBeInTheDocument())
    expect(mockedWorkspace).toHaveBeenCalledWith('moomoo', 'NVDA', '6m', [])
    expect(mockedLiveConnection).toHaveBeenLastCalledWith(expect.any(Function), false)
    expect(screen.getByTestId('workspace-grid')).toHaveClass('xl:grid-cols-[minmax(0,1fr)_18rem_22rem]')
    expect(screen.getByTestId('instrument-chart')).toHaveTextContent('NVDA chart')
    expect(screen.getByTestId('app-main').querySelector('main')).not.toBeInTheDocument()
    expect(screen.getByText('Historical source').closest('div')).toHaveTextContent('demo-synthetic')
    expect(screen.getByText('Live source').closest('div')).toHaveTextContent('demo-synthetic')
    expect(screen.getByText('Live classification').closest('div')).toHaveTextContent(
      'stale · demo-synthetic',
    )
    expect(screen.getByText('Data time').closest('div')).toHaveTextContent('Aug 8')
    expect(screen.getByText('Received').closest('div')).toHaveTextContent('Aug 8')
    expect(screen.getByText('Age').closest('div')).toHaveTextContent('1 m 35 s')
  })

  it('uses a three-column matching skeleton while the workspace is loading', () => {
    mockedWorkspace.mockReturnValue(new Promise(() => {}))
    renderWorkspace()

    expect(screen.getByLabelText('Loading instrument workspace')).toHaveClass(
      'xl:grid-cols-[minmax(0,1fr)_18rem_22rem]',
    )
  })

  it('explains a missing historical instrument without hiding the route context', async () => {
    mockedWorkspace.mockRejectedValue(new ApiError(404, 'No trusted history for moomoo:UNKNOWN'))
    renderWorkspace('/instruments/moomoo/UNKNOWN')

    await waitFor(() => expect(screen.getByText('History unavailable')).toBeInTheDocument())
    expect(screen.getByText('No trusted history for moomoo:UNKNOWN')).toBeInTheDocument()
    expect(screen.getByText('moomoo / UNKNOWN')).toBeInTheDocument()
  })

  it('keeps the live detail usable when replay history is not ready', async () => {
    mockedHealth.mockResolvedValue({
      live_trading: false,
      paper_mode: true,
      project: 'QuantMesh',
      runtime_mode: 'live',
      status: 'ok',
      version: '0.1.1rc1',
    })
    mockedWorkspace.mockRejectedValue(new ApiError(404, 'live replay continuity is not proven'))

    renderWorkspace('/instruments/hyperliquid/BTC')

    expect(await screen.findByRole('heading', { name: 'BTC' })).toBeInTheDocument()
    expect(screen.getByText('Order book')).toBeInTheDocument()
    expect(screen.getByText('Trade tape')).toBeInTheDocument()
    expect(screen.queryByText('History unavailable')).not.toBeInTheDocument()
  })

  it('keeps stale evidence visible and blocks the paper action', async () => {
    renderWorkspace()

    await waitFor(() => expect(screen.getByText('Stale market evidence')).toBeInTheDocument())
    expect(screen.getByText('Quote age exceeds the paper-action fence.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Create paper proposal' })).toBeDisabled()
  })

  it('refetches history for URL-backed range and comparison controls', async () => {
    const user = userEvent.setup()
    renderWorkspace()
    await waitFor(() => expect(screen.getByRole('heading', { name: 'NVDA' })).toBeInTheDocument())

    await user.click(screen.getByRole('button', { name: '1M' }))
    await waitFor(() =>
      expect(mockedWorkspace).toHaveBeenCalledWith('moomoo', 'NVDA', '1m', []),
    )
    await user.type(screen.getByRole('textbox', { name: 'Comparison instrument' }), 'moomoo:AAPL')
    await user.click(screen.getByRole('button', { name: 'Add comparison' }))
    await waitFor(() =>
      expect(mockedWorkspace).toHaveBeenCalledWith('moomoo', 'NVDA', '1m', ['moomoo:AAPL']),
    )
  })

  it('keeps the active range control mounted and focused while its data refetches', async () => {
    let resolveNext!: (value: InstrumentWorkspace) => void
    mockedWorkspace
      .mockResolvedValueOnce(workspace)
      .mockReturnValueOnce(new Promise((resolve) => { resolveNext = resolve }))
    const user = userEvent.setup()
    renderWorkspace()
    await waitFor(() => expect(screen.getByRole('heading', { name: 'NVDA' })).toBeInTheDocument())

    const oneMonth = screen.getByRole('button', { name: '1M' })
    await user.click(oneMonth)
    await waitFor(() => expect(mockedWorkspace).toHaveBeenCalledWith('moomoo', 'NVDA', '1m', []))

    expect(screen.queryByLabelText('Loading instrument workspace')).not.toBeInTheDocument()
    expect(screen.getByText(/Updating the selected evidence/)).toBeInTheDocument()
    expect(oneMonth).toHaveFocus()
    expect(oneMonth).toHaveAttribute('aria-pressed', 'false')
    expect(screen.getByRole('button', { name: '6M' })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByRole('heading', { name: 'NVDA' })).toBeInTheDocument()

    await act(async () => resolveNext({
      ...workspace,
      history: { ...workspace.history, range: '1m' },
    }))
    await waitFor(() => expect(oneMonth).toHaveAttribute('aria-pressed', 'true'))
    expect(screen.queryByText(/Updating the selected evidence/)).not.toBeInTheDocument()
  })

  it('shows the complete history license instead of permanently truncating it', async () => {
    mockedWorkspace.mockResolvedValue({
      ...workspace,
      history: { ...workspace.history, license: 'A complete operator-supplied license notice' },
    })
    renderWorkspace()

    const license = await screen.findByText('A complete operator-supplied license notice')
    expect(license).toHaveAttribute('title', 'A complete operator-supplied license notice')
    expect(license).not.toHaveClass('truncate')
  })

  it('surfaces resolution fallback, history quality findings and a live sequence gap', async () => {
    mockedWorkspace.mockResolvedValue({
      ...workspace,
      history: {
        ...workspace.history,
        duplicates: ['2026-08-06T20:00:00Z'],
        gaps: ['2026-08-05T20:00:00Z'],
        resolution_fallback: 'Requested 1h; serving trusted 1d bars.',
        limitations: ['XNYS holiday gap detection was not run.'],
      },
      comparison: {
        as_of: workspace.generated_at,
        keys: ['moomoo:NVDA', 'moomoo:AAPL'],
        limitations: ['Comparison uses a shared 1d resolution fallback.'],
        points: [],
        range: '6m',
      },
      live: { ...workspace.live, sequence_gap: true },
    })
    renderWorkspace()

    await waitFor(() => expect(screen.getByText(/Requested 1h; serving trusted 1d bars/)).toBeInTheDocument())
    expect(screen.getByText(/Historical gaps: 1/)).toBeInTheDocument()
    expect(screen.getByText(/Historical duplicates: 1/)).toBeInTheDocument()
    expect(screen.getByText('Live sequence gap detected')).toBeInTheDocument()
    expect(screen.getByText(/History limitation: XNYS holiday gap detection was not run/)).toBeInTheDocument()
    expect(screen.getByText(/Comparison limitation: Comparison uses a shared 1d resolution fallback/)).toBeInTheDocument()
  })

  it('refreshes authoritative quote, position and risk truth for matching live updates', async () => {
    mockedWorkspace
      .mockResolvedValueOnce(workspace)
      .mockResolvedValue({
        ...workspace,
        live: {
          ...workspace.live,
          age_ms: 25,
          data_time: '2026-08-08T12:00:01Z',
          last: 190,
          received_at: '2026-08-08T12:00:01Z',
        },
        position: {
          average_cost: 180,
          mark: 190,
          mark_status: {
            provenance: 'real',
            reason: null,
            received_at: '2026-08-08T12:00:01Z',
            status: 'available',
          },
          quantity: 5,
          realized_pnl: 12,
          unrealized_pnl: 50,
        },
        risk: { ...workspace.risk, equity: 100_050 },
      })
    renderWorkspace()
    await waitFor(() => expect(screen.getByRole('heading', { name: 'NVDA' })).toBeInTheDocument())

    act(() => publishLiveUpdate({
      data_time: '2026-08-08T12:00:01Z',
      instrument: 'NVDA',
      kind: 'quote',
      payload: { last: 190 },
      provenance: 'real',
      received_at: '2026-08-08T12:00:01Z',
      sequence: 13,
      sequence_gap: false,
      state: 'connected',
      state_note: null,
      venue: 'moomoo',
    }))

    await waitFor(() => expect(screen.getByText('Mark').closest('div')).toHaveTextContent('190'))
    expect(mockedWorkspace).toHaveBeenCalledTimes(2)
    expect(screen.getByText('Account equity').closest('div')).toHaveTextContent('100,050')
    expect(screen.getByText('Unrealized P&L').closest('div')).toHaveTextContent('50')
  })

  it('retains last-known workspace truth when a background refresh fails', async () => {
    mockedWorkspace
      .mockResolvedValueOnce(workspace)
      .mockRejectedValueOnce(new Error('refresh transport offline'))
    renderWorkspace()
    await waitFor(() => expect(screen.getByRole('heading', { name: 'NVDA' })).toBeInTheDocument())

    act(() => publishLiveUpdate({
      data_time: '2026-08-08T12:00:01Z',
      instrument: 'NVDA',
      kind: 'quote',
      payload: { last: 190 },
      provenance: 'real',
      received_at: '2026-08-08T12:00:01Z',
      sequence: 13,
      sequence_gap: false,
      state: 'connected',
      state_note: null,
      venue: 'moomoo',
    }))

    expect(await screen.findByText('Background refresh failed — showing last known workspace')).toBeInTheDocument()
    expect(screen.getByText('refresh transport offline')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'NVDA' })).toBeInTheDocument()
  })
})
