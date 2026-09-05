import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import userEvent from '@testing-library/user-event'

import { api, type DecisionInbox } from '@/lib/api'
import { PreferencesProvider } from '@/lib/preferences'

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>()
  return { ...actual, api: { ...actual.api, decisionInbox: vi.fn() } }
})

import { WatchlistScreen } from './Watchlist'

const inbox = {
  entries: [
    {
      attention_reason: 'A persisted Paper proposal needs explicit confirmation.',
      attention_state: 'paper_pending_confirmation',
      disposition: 'paper_proposal',
      evidence_status: 'complete',
      instrument_type: 'equity',
      mark_context: { reason: null, status: 'available', value: 184.2 },
      monitoring: null,
      packet_id: 'packet-111111111111111111111111',
      paper: { proposal_id: 'proposal-111', status: 'pending' },
      parent_packet_id: 'packet-000000000000000000000000',
      position_context: null,
      review: null,
      selected_range: '6m',
      symbol: 'NVDA',
      venue: 'moomoo',
    },
    {
      attention_reason: 'No saved DecisionPacket exists yet.',
      attention_state: 'not_started',
      disposition: null,
      evidence_status: null,
      instrument_type: 'equity',
      mark_context: { reason: null, status: 'available', value: 201.1 },
      monitoring: null,
      packet_id: null,
      paper: null,
      parent_packet_id: null,
      position_context: null,
      review: null,
      selected_range: null,
      symbol: 'AAPL',
      venue: 'moomoo',
    },
    {
      attention_reason: 'The watchlist row has no venue identity.',
      attention_state: 'unavailable',
      disposition: null,
      evidence_status: 'unavailable',
      instrument_type: null,
      mark_context: { reason: 'No venue identity.', status: 'unavailable', value: null },
      monitoring: null,
      packet_id: null,
      paper: null,
      parent_packet_id: null,
      position_context: null,
      review: null,
      selected_range: null,
      symbol: 'UNKNOWN',
      venue: null,
    },
  ],
  generated_at: '2026-09-05T12:00:00Z',
} satisfies DecisionInbox

const mockedDecisionInbox = vi.mocked(api.decisionInbox)

beforeEach(() => {
  localStorage.clear()
  mockedDecisionInbox.mockResolvedValue(inbox)
})

it('opens the exact pending packet and routes recoverable inbox states', async () => {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={client}>
      <PreferencesProvider>
        <MemoryRouter><WatchlistScreen /></MemoryRouter>
      </PreferencesProvider>
    </QueryClientProvider>,
  )

  expect(await screen.findByRole('link', { name: /Open exact packet/i }))
    .toHaveAttribute(
      'href',
      '/instruments/moomoo/NVDA?range=6m&packet=packet-111111111111111111111111',
    )
  expect(screen.getByText('Pending confirmation')).toBeInTheDocument()
  expect(screen.getByRole('link', { name: 'Open workspace' }))
    .toHaveAttribute('href', '/instruments/moomoo/AAPL')
  expect(screen.getByRole('link', { name: 'Choose venue' }))
    .toHaveAttribute('href', '/markets')
})

it('does not claim a position opened for an accepted zero-fill paper order in zh-CN', async () => {
  localStorage.setItem('quantmesh.preferences', JSON.stringify({ locale: 'zh-CN', theme: 'dark' }))
  mockedDecisionInbox.mockResolvedValue({
    ...inbox,
    entries: [{
      ...inbox.entries[0],
      attention_state: 'paper_open',
      attention_reason: 'Paper order accepted with no fills.',
      paper: {
        proposal_id: 'proposal-111', status: 'confirmed',
        order_id: 'paper-proposal:proposal-111', order_status: 'accepted', filled_quantity: 0,
      },
    }],
  })
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={client}>
      <PreferencesProvider>
        <MemoryRouter><WatchlistScreen /></MemoryRouter>
      </PreferencesProvider>
    </QueryClientProvider>,
  )
  expect(await screen.findByText('模拟订单进行中')).toBeVisible()
  expect(screen.queryByText('模拟仓位已开')).not.toBeInTheDocument()
  await userEvent.click(screen.getByText('模拟与决策记录'))
  expect(screen.getByText('已接受')).toBeVisible()
  expect(screen.getByText('成交数量').nextElementSibling).toHaveTextContent('0')
})

it('labels an evidence-blocked crypto packet and preserves its exact route', async () => {
  mockedDecisionInbox.mockResolvedValue({
    entries: [
      {
        attention_reason: 'No promoted forecast is available.',
        attention_state: 'blocked',
        disposition: 'watch',
        evidence_status: 'unavailable',
        instrument_type: 'perpetual',
        mark_context: { reason: null, status: 'available', value: 65_000 },
        monitoring: null,
        packet_id: 'packet-222222222222222222222222',
        paper: null,
        parent_packet_id: 'packet-111111111111111111111111',
        position_context: null,
        review: null,
        selected_range: '6m',
        symbol: 'BTC-USD',
        venue: 'hyperliquid',
      },
    ],
    generated_at: '2026-09-05T12:00:00Z',
  } satisfies DecisionInbox)
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={client}>
      <PreferencesProvider>
        <MemoryRouter><WatchlistScreen /></MemoryRouter>
      </PreferencesProvider>
    </QueryClientProvider>,
  )

  expect(await screen.findByText('Evidence blocked')).toBeInTheDocument()
  expect(screen.getByText('No promoted forecast is available.')).toBeInTheDocument()
  expect(screen.getByRole('link', { name: 'Open exact packet' })).toHaveAttribute(
    'href',
    '/instruments/hyperliquid/BTC-USD?range=6m&packet=packet-222222222222222222222222',
  )
})

it('discloses exact paper, watch and review facts with a context-only position warning', async () => {
  const row = {
    ...inbox.entries[0],
    attention_state: 'reviewed',
    outcome_id: 'outcome-111111111111111111111111',
    paper: {
      proposal_id: 'proposal-111111111111111111111111', status: 'confirmed',
      order_id: 'paper-proposal:proposal-111111111111111111111111',
      order_status: 'filled', filled_quantity: 1,
    },
    monitoring: {
      registration_id: 'registration-111111111111111111111111',
      latest_evaluation_id: 'evaluation-111111111111111111111111',
      triggered: true, event_ids: ['event-111111111111111111111111'],
    },
    review: {
      review_id: 'review-111111111111111111111111', state: 'inconclusive',
      outcome_id: 'outcome-222222222222222222222222',
    },
    position_context: {
      quantity: 42, average_cost: 100, realized_pnl: 321, mark: 101,
      attribution: 'current-account-context-only',
    },
  } as const
  mockedDecisionInbox.mockResolvedValue({ ...inbox, entries: [row] })
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={client}>
      <PreferencesProvider>
        <MemoryRouter><WatchlistScreen /></MemoryRouter>
      </PreferencesProvider>
    </QueryClientProvider>,
  )
  const disclosure = await screen.findByText('Paper & decision records')
  await userEvent.click(disclosure)
  for (const id of [
    row.packet_id, row.paper.proposal_id, row.paper.order_id,
    row.monitoring.registration_id, row.monitoring.latest_evaluation_id,
    row.monitoring.event_ids[0], row.outcome_id, row.review.review_id, row.review.outcome_id,
  ]) {
    expect(screen.getByText(id)).toHaveClass('font-mono', 'break-all')
  }
  expect(screen.getByText('Confirmed')).toBeVisible()
  expect(screen.getByText('Filled')).toBeVisible()
  expect(screen.getByText('Filled quantity')).toBeVisible()
  expect(screen.getByText('Triggered')).toBeVisible()
  expect(screen.getByText('Inconclusive')).toBeVisible()
  expect(screen.getByText(/Current account context only/)).toBeVisible()
  expect(screen.queryByText(/Sharpe|ranking|aggregate return|closed P&L/i)).not.toBeInTheDocument()
  expect(screen.queryByText('321')).not.toBeInTheDocument()
})
