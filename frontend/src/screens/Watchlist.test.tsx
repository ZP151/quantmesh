import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'
import { MemoryRouter } from 'react-router-dom'

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

it('labels an evidence-blocked crypto packet and preserves its exact route', async () => {
  mockedDecisionInbox.mockResolvedValue({
    entries: [
      {
        attention_reason: 'No promoted forecast is available.',
        attention_state: 'blocked',
        disposition: 'watch',
        evidence_status: 'blocked',
        instrument_type: 'crypto_perp',
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
