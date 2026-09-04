import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { api, type DecisionOutcomeReviewState } from '@/lib/api'
import { PreferencesProvider } from '@/lib/preferences'

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>()
  return {
    ...actual,
    api: {
      ...actual.api,
      packetOutcomeReview: vi.fn(),
      savePacketOutcomeReview: vi.fn(),
    },
  }
})

import { PacketOutcomeReview } from './PacketOutcomeReview'

const mockedPreview = vi.mocked(api.packetOutcomeReview)
const mockedSave = vi.mocked(api.savePacketOutcomeReview)

const previewState = {
  outcome: {
    attribution_basis: 'completed_daily_close',
    attribution_equality: 'equality_does_not_cross',
    attribution_policy_version: 'strict-close-v1',
    entry_fill_deviation_r: { reason: 'No exact entry fill.', status: 'unavailable', value: null },
    evaluated_at: '2026-08-08T12:00:00Z',
    evidence_status: 'pending',
    gross_path_r: { reason: 'No terminal close.', status: 'unavailable', value: null },
    horizon_target_at: '2026-09-21T20:00:00Z',
    mark_to_market_paper_r: { reason: 'No fill and mark.', status: 'unavailable', value: null },
    monitoring: { evaluations: [], event_ids: [], registration: null, status: 'not_monitored' },
    outcome_id: 'outcome-000000000000000000000001',
    packet: { disposition: 'watch', packet_id: 'packet-000000000000000000000001' },
    packet_id: 'packet-000000000000000000000001',
    paper: { order: null, proposal: null, reason: null, state: 'watch_only' },
    path: { bars: [], cutoff_at: '2026-08-08T12:00:00Z', status: 'pending', target_at: '2026-09-21T20:00:00Z' },
    planned_reward_to_risk: 2,
    realized_paper_r: { reason: 'Exit fills and complete fees are unavailable.', status: 'unavailable', value: null },
    root_packet: { packet_id: 'packet-root-000000000000000001' },
    scenarios: [
      { invalidation_at: null, invalidation_level: 176, invalidation_state: 'unavailable', kind: 'bull', threshold: 190, threshold_at: null, threshold_kind: 'resistance', threshold_state: 'unavailable' },
      { invalidation_at: null, invalidation_level: 176, invalidation_state: 'unavailable', kind: 'base', threshold: 180, threshold_at: null, threshold_kind: 'support', threshold_state: 'unavailable' },
      { invalidation_at: null, invalidation_level: null, invalidation_state: 'unavailable', kind: 'bear', threshold: 180, threshold_at: null, threshold_kind: 'support', threshold_state: 'unavailable' },
    ],
    target_stop_ordering: 'unavailable',
  },
  packet_id: 'packet-000000000000000000000001',
  review: null,
  root_packet: { packet_id: 'packet-root-000000000000000001' },
} as unknown as DecisionOutcomeReviewState

const savedState = {
  ...previewState,
  review: {
    classification: 'inconclusive',
    note: 'Wait for the pinned horizon.',
    outcome: previewState.outcome,
    packet_id: previewState.packet_id,
    review_id: 'review-000000000000000000000001',
    reviewed_at: '2026-08-08T12:00:00Z',
  },
} as unknown as DecisionOutcomeReviewState

function renderReview(packetId: string | null = previewState.packet_id, contextKey = 'moomoo:NVDA:6m') {
  return render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <PreferencesProvider>
        <PacketOutcomeReview contextKey={contextKey} packetId={packetId} />
      </PreferencesProvider>
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  window.localStorage.clear()
  mockedPreview.mockResolvedValue(previewState)
  mockedSave.mockResolvedValue(savedState)
})

describe('PacketOutcomeReview', () => {
  it('keeps a draft save-first and never requests an outcome', () => {
    renderReview(null)

    expect(screen.getByText('Save an action DecisionPacket before reviewing its outcome.')).toBeVisible()
    expect(mockedPreview).not.toHaveBeenCalled()
  })

  it('renders honest pending evidence and saves only the exact outcome identity', async () => {
    const user = userEvent.setup()
    renderReview()

    expect(await screen.findByText('Horizon pending')).toBeVisible()
    expect(screen.getByText('Planned reward / risk')).toBeVisible()
    expect(screen.getByText('Gross path R')).toBeVisible()
    expect(screen.getByText('Realized paper R')).toBeVisible()
    expect(screen.getAllByText('Unavailable').length).toBeGreaterThan(0)
    expect(screen.getByRole('option', { name: 'Supported' })).toBeDisabled()
    expect(screen.getByRole('option', { name: 'Inconclusive' })).toBeEnabled()

    await user.type(screen.getByLabelText('Review note (optional)'), 'Wait for the pinned horizon.')
    await user.click(screen.getByRole('button', { name: 'Save review' }))

    await waitFor(() => expect(mockedSave).toHaveBeenCalledWith(
      previewState.packet_id,
      {
        classification: 'inconclusive',
        expected_outcome_id: previewState.outcome.outcome_id,
        note: 'Wait for the pinned horizon.',
      },
    ))
    expect(await screen.findByText('Review saved')).toBeVisible()
    expect(screen.getByText('review-000000000000000000000001')).toBeVisible()
    expect(screen.queryByRole('button', { name: 'Save review' })).not.toBeInTheDocument()
  })

  it('shows explicit attribution provenance, invalidation, and exact paper/watch timeline facts', async () => {
    mockedPreview.mockResolvedValueOnce({
      ...previewState,
      outcome: {
        ...previewState.outcome,
        evidence_status: 'partial',
        monitoring: {
          evaluations: [{
            evaluation_id: 'evaluation-000000000000000000000001',
            observation: { evaluated_at: '2026-08-08T12:03:00Z' },
            registration_id: 'registration-000000000000000000000001',
            results: [{
              condition_id: 'condition-000000000000000000000001',
              event_id: 'watch-event-000000000000000000000001',
              facts: { current_price: 181 },
              state: 'triggered',
            }],
          }],
          event_ids: ['watch-event-000000000000000000000001'],
          registration: {
            conditions: [],
            packet_id: previewState.packet_id,
            registration_id: 'registration-000000000000000000000001',
          },
          status: 'triggered',
        },
        paper: {
          order: {
            created_at: '2026-08-08T12:02:00Z',
            events: [
              {
                broker_fill_id: null,
                event_type: 'accepted',
                price: null,
                quantity: null,
                reason: null,
                sequence: 1,
                status: 'accepted',
                timestamp: '2026-08-08T12:01:30Z',
              },
              {
                broker_fill_id: 'fill-nvda-1',
                event_type: 'fill',
                price: 181,
                quantity: 1,
                reason: null,
                sequence: 2,
                status: 'filled',
                timestamp: '2026-08-08T12:02:00Z',
              },
            ],
            order_id: 'paper-proposal:proposal-000000000000000000000001',
          },
          proposal: {
            created_at: '2026-08-08T12:01:00Z',
            id: 'proposal-000000000000000000000001',
          },
          reason: null,
          state: 'filled_open',
        },
        path: {
          ...previewState.outcome.path,
          cutoff_at: '2026-08-12T20:00:00Z',
          dataset_id: 'demo-moomoo-nvda',
          dataset_revision: 2,
          path_digest: 'a'.repeat(64),
          reason: 'One expected 30-session timestamp is missing.',
          source: 'demo-synthetic',
          status: 'partial',
        },
      },
    } as unknown as DecisionOutcomeReviewState)
    renderReview()

    expect(await screen.findByText('demo-synthetic')).toBeVisible()
    expect(screen.getByText('demo-moomoo-nvda · r2')).toBeVisible()
    expect(screen.getByText('aaaaaaaaaaaa…')).toBeVisible()
    expect(screen.getByText('One expected 30-session timestamp is missing.')).toBeVisible()
    expect(screen.getByText('strict-close-v1')).toBeVisible()
    expect(screen.getByText(/completed_daily_close/)).toBeVisible()
    expect(screen.getByText(/equality_does_not_cross/)).toBeVisible()
    expect(screen.getByText(/Equality does not cross a level\./)).toBeVisible()
    expect(screen.getAllByText(/Invalidation 176/)).toHaveLength(2)
    expect(screen.getByText('proposal-000000000000000000000001')).toBeVisible()
    expect(screen.getByText('paper-proposal:proposal-000000000000000000000001')).toBeVisible()
    expect(screen.getByText('#1 · accepted · accepted')).toBeVisible()
    expect(screen.getByText('#2 · fill · filled')).toBeVisible()
    expect(screen.getByText('fill-nvda-1')).toBeVisible()
    expect(screen.getByText('registration-000000000000000000000001')).toBeVisible()
    expect(screen.getByText('evaluation-000000000000000000000001')).toBeVisible()
    expect(screen.getByText('watch-event-000000000000000000000001')).toBeVisible()
  })

  it('shows the exact rejected order event time and reason', async () => {
    mockedPreview.mockResolvedValueOnce({
      ...previewState,
      outcome: {
        ...previewState.outcome,
        paper: {
          order: {
            created_at: '2026-08-08T12:02:00Z',
            events: [{
              broker_fill_id: null,
              event_type: 'rejected',
              price: null,
              quantity: null,
              reason: 'Global kill switch is active.',
              sequence: 1,
              status: 'rejected',
              timestamp: '2026-08-08T12:02:01Z',
            }],
            order_id: 'paper-proposal:proposal-000000000000000000000002',
          },
          proposal: {
            created_at: '2026-08-08T12:01:00Z',
            id: 'proposal-000000000000000000000002',
          },
          reason: 'Global kill switch is active.',
          state: 'risk_rejected',
        },
      },
    } as unknown as DecisionOutcomeReviewState)
    renderReview()

    expect(await screen.findByText('#1 · rejected · rejected')).toBeVisible()
    expect(screen.getAllByText('Global kill switch is active.').length).toBeGreaterThan(0)
    expect(screen.getAllByText(/Aug 8, 2026/).length).toBeGreaterThan(0)
  })

  it('renders a saved review from its frozen outcome instead of a newer preview', async () => {
    const frozen = {
      ...savedState,
      outcome: {
        ...savedState.outcome,
        outcome_id: 'outcome-000000000000000000000002',
      },
    }
    mockedPreview.mockResolvedValueOnce(frozen)
    renderReview()

    expect(await screen.findByText('Review saved')).toBeVisible()
    expect(screen.getByText('outcome-000000000000000000000001')).toBeVisible()
    expect(screen.queryByText('outcome-000000000000000000000002')).not.toBeInTheDocument()
  })

  it('isolates late responses and failures by exact packet context', async () => {
    let resolveFirst!: (value: DecisionOutcomeReviewState) => void
    mockedPreview.mockImplementationOnce(() => new Promise((resolve) => { resolveFirst = resolve }))
    mockedPreview.mockResolvedValueOnce({
      ...previewState,
      packet_id: 'packet-000000000000000000000002',
    })
    const rendered = renderReview()

    rendered.rerender(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <PreferencesProvider>
          <PacketOutcomeReview contextKey="moomoo:NVDA:1y" packetId="packet-000000000000000000000002" />
        </PreferencesProvider>
      </QueryClientProvider>,
    )
    resolveFirst(savedState)

    await waitFor(() => expect(mockedPreview).toHaveBeenCalledWith('packet-000000000000000000000002'))
    expect(screen.queryByText('review-000000000000000000000001')).not.toBeInTheDocument()
  })

  it('has recovery, compact wrapping and Simplified Chinese copy', async () => {
    mockedPreview.mockRejectedValueOnce(new Error('corrupt store'))
    window.localStorage.setItem('quantmesh.preferences', JSON.stringify({ locale: 'zh-CN', theme: 'dark' }))
    renderReview()

    expect(await screen.findByText('结果复盘暂时不可用；决策包、风控与纸面订单不会被修改。')).toBeVisible()
    fireEvent.resize(window)
    expect(screen.getByTestId('packet-outcome-review')).toHaveClass('min-w-0')
  })
})
