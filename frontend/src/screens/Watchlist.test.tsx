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
      mark_context: { reason: 'configured mark is stale', received_at: '2026-09-05T12:03:00Z', status: 'stale', value: 184.2 },
      monitoring: null,
      packet_id: 'packet-111111111111111111111111',
      paper: { proposal_id: 'proposal-111', status: 'pending' },
      parent_packet_id: 'packet-000000000000000000000000',
      position_context: null,
      review: null,
      readiness: {
        checked_at: '2026-09-05T12:04:00Z', forecast: null, history: null,
        limiting_evidence_at: '2026-09-05T12:00:00Z', reason: 'This packet uses demo-synthetic evidence.',
        reason_code: 'demo_evidence', status: 'demo',
      },
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
      readiness: {
        checked_at: '2026-09-05T12:04:00Z', forecast: null, history: null,
        limiting_evidence_at: null, reason: 'No saved DecisionPacket exists yet.',
        reason_code: 'no_saved_packet', status: 'unavailable',
      },
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
      readiness: {
        checked_at: '2026-09-05T12:04:00Z', forecast: null, history: null,
        limiting_evidence_at: null, reason: 'A venue is required to resolve exact packet evidence.',
        reason_code: 'venue_unavailable', status: 'unavailable',
      },
      selected_range: null,
      symbol: 'UNKNOWN',
      venue: null,
    },
  ],
  generated_at: '2026-09-05T12:00:00Z',
  session: {
    blocked_count: 2, generated_at: '2026-09-05T12:00:00Z', last_checked_at: null,
    registered_count: 0, triggered_count: 0,
  },
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
  expect(screen.getByText('Demo evidence')).toBeVisible()
  expect(screen.getAllByText('Trusted evidence unavailable')).toHaveLength(2)
  expect(screen.getAllByText('Readiness evaluated Sep 5, 08:04 PM')).toHaveLength(3)
  expect(screen.queryByText(/Last local check/)).not.toBeInTheDocument()
  expect(screen.getByText('configured mark is stale')).toBeVisible()
})

it('renders exact readiness reason in zh-CN without adding a second row action', async () => {
  localStorage.setItem('quantmesh.preferences', JSON.stringify({ locale: 'zh-CN', theme: 'dark' }))
  mockedDecisionInbox.mockResolvedValue({
    ...inbox,
    entries: [{
      ...inbox.entries[0],
      readiness: {
        ...inbox.entries[0].readiness,
        reason: 'Exact quality evaluation does not match this packet.',
        reason_code: 'history_evaluation_mismatch',
        status: 'blocked',
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

  expect(await screen.findByText('可信证据受阻')).toBeVisible()
  const localizedReason = screen.getByText('精确质量评估与此决策包不匹配。')
  expect(localizedReason).toHaveAttribute('title', 'Exact quality evaluation does not match this packet.')
  expect(screen.getAllByRole('link')).toHaveLength(1)
})

it.each([
  ['demo_evidence', 'This packet uses demo-synthetic evidence.', '此决策包使用演示合成证据。'],
  ['catalog_unavailable', 'Trusted evidence catalog is unavailable.', '可信证据目录不可用。'],
  ['missing_history_binding', 'Exact history manifest and quality evaluation are required.', '需要精确的历史清单和质量评估。'],
  ['trusted_evidence', 'Exact packet evidence is trusted for research.', '精确决策包证据可用于研究。'],
  ['missing_forecast_binding', 'Exact forecast manifest and quality evaluation are required.', '需要精确的预测清单和质量评估。'],
  ['history_manifest_unavailable', 'Exact history manifest is unavailable.', '精确历史清单不可用。'],
  ['history_catalog_unavailable', 'Exact history catalog closure is unavailable.', '精确历史目录闭包不可用。'],
  ['history_manifest_mismatch', 'Exact history manifest identity does not match this packet.', '精确历史清单身份与此决策包不匹配。'],
  ['history_quality_unavailable', 'Exact history quality evidence is unavailable.', '精确历史质量证据不可用。'],
  ['history_evaluation_mismatch', 'Exact quality evaluation does not match this packet.', '精确质量评估与此决策包不匹配。'],
  ['history_checkpoint_mismatch', 'Exact history quality report does not match its checkpoint.', '精确历史质量报告与其检查点不匹配。'],
  ['history_rights_unknown', 'Exact history source rights are unknown.', '精确历史来源权利未知。'],
  ['history_not_trusted', 'Exact history evidence is not trusted for research.', '精确历史证据不受研究信任。'],
  ['forecast_manifest_unavailable', 'Exact forecast manifest is unavailable.', '精确预测清单不可用。'],
  ['forecast_catalog_unavailable', 'Exact forecast catalog closure is unavailable.', '精确预测目录闭包不可用。'],
  ['forecast_manifest_mismatch', 'Exact forecast manifest identity does not match this packet.', '精确预测清单身份与此决策包不匹配。'],
  ['forecast_quality_unavailable', 'Exact forecast quality evidence is unavailable.', '精确预测质量证据不可用。'],
  ['forecast_evaluation_mismatch', 'Exact quality evaluation does not match this packet.', '精确质量评估与此决策包不匹配。'],
  ['forecast_checkpoint_mismatch', 'Exact forecast quality report does not match its checkpoint.', '精确预测质量报告与其检查点不匹配。'],
  ['forecast_rights_unknown', 'Exact forecast source rights are unknown.', '精确预测来源权利未知。'],
  ['forecast_not_trusted', 'Exact forecast evidence is not trusted for research.', '精确预测证据不受研究信任。'],
  ['no_saved_packet', 'No saved DecisionPacket exists yet.', '尚无已保存的决策包。'],
  ['venue_unavailable', 'A venue is required to resolve exact packet evidence.', '解析精确决策包证据需要市场。'],
])('localizes the known readiness reason %s and retains its server reason in title', async (code, serverReason, localized) => {
  localStorage.setItem('quantmesh.preferences', JSON.stringify({ locale: 'zh-CN', theme: 'dark' }))
  mockedDecisionInbox.mockResolvedValue({
    ...inbox,
    entries: [{
      ...inbox.entries[0],
      readiness: { ...inbox.entries[0].readiness, reason_code: code, reason: serverReason },
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

  expect(await screen.findByText(localized)).toHaveAttribute('title', serverReason)
})

it.each([
  ['armed', 'Armed', '已布防'],
  ['not_triggered', 'Not triggered', '未触发'],
  ['triggered', 'Triggered', '已触发'],
  ['not_comparable', 'Not comparable', '无法比较'],
])('localizes the persisted monitoring status %s', async (status, _english, localized) => {
  localStorage.setItem('quantmesh.preferences', JSON.stringify({ locale: 'zh-CN', theme: 'dark' }))
  mockedDecisionInbox.mockResolvedValue({
    ...inbox,
    entries: [{
      ...inbox.entries[0],
      monitoring: {
        registration_id: 'registration-111', latest_evaluation_id: 'evaluation-111', triggered: false,
        event_ids: [], last_checked_at: '2026-09-05T12:05:00Z', latest_status: status, latest_reason: null,
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

  expect(await screen.findByText(localized)).toBeVisible()
})

it.each([
  ['unusable_price_evidence', 'Price evidence cannot be used for this watch.', '价格证据不能用于此观察。'],
  ['future_reference', 'Watch reference time is in the future.', '观察参考时间在未来。'],
  ['calendar_unavailable', 'Watch calendar is unavailable.', '观察日历不可用。'],
  ['missing_forecast', 'Required forecast is unavailable.', '所需预测不可用。'],
  ['candidate_not_comparable', 'Candidate forecast cannot be compared.', '候选预测无法比较。'],
  ['candidate_incompatible', 'Candidate forecast is incompatible.', '候选预测不兼容。'],
])('localizes the persisted monitoring reason %s and retains it in title', async (code, serverReason, localized) => {
  localStorage.setItem('quantmesh.preferences', JSON.stringify({ locale: 'zh-CN', theme: 'dark' }))
  mockedDecisionInbox.mockResolvedValue({
    ...inbox,
    entries: [{
      ...inbox.entries[0],
      monitoring: {
        registration_id: 'registration-111', latest_evaluation_id: 'evaluation-111', triggered: false,
        event_ids: [], last_checked_at: '2026-09-05T12:05:00Z', latest_status: null, latest_reason: code,
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

  expect(await screen.findByText(localized)).toHaveAttribute('title', code)
})

it('keeps an unknown readiness and monitoring reason verbatim', async () => {
  mockedDecisionInbox.mockResolvedValue({
    ...inbox,
    entries: [{
      ...inbox.entries[0],
      readiness: { ...inbox.entries[0].readiness, reason_code: 'server_reason_v2', reason: 'Server reason v2.' },
      monitoring: {
        registration_id: 'registration-111', latest_evaluation_id: 'evaluation-111', triggered: false,
        event_ids: [], last_checked_at: '2026-09-05T12:05:00Z', latest_status: 'server_status_v2', latest_reason: 'server_reason_v2',
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

  expect(await screen.findByText('Server reason v2.')).toHaveAttribute('title', 'Server reason v2.')
  expect(screen.getByText('server_status_v2')).toBeVisible()
  expect(screen.getByText('server_reason_v2')).toHaveAttribute('title', 'server_reason_v2')
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
        readiness: {
          checked_at: '2026-09-05T12:04:00Z', forecast: null, history: null,
          limiting_evidence_at: null, reason: 'No promoted forecast is available.',
          reason_code: 'forecast_unavailable', status: 'blocked',
        },
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
  expect(screen.getAllByText('No promoted forecast is available.')).toHaveLength(2)
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
      last_checked_at: '2026-09-05T12:05:00Z', latest_status: 'triggered', latest_reason: 'quote_missing',
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
  expect(screen.getAllByText('Triggered')).toHaveLength(2)
  expect(screen.getByText('Last local check Sep 5, 08:05 PM')).toBeVisible()
  expect(screen.getByText('Monitoring data is unavailable.')).toBeVisible()
  expect(screen.getByText('Inconclusive')).toBeVisible()
  expect(screen.getByText(/Current account context only/)).toBeVisible()
  expect(screen.queryByText(/Sharpe|ranking|aggregate return|closed P&L/i)).not.toBeInTheDocument()
  expect(screen.queryByText('321')).not.toBeInTheDocument()
})
