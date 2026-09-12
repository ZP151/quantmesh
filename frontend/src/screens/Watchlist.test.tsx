import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import userEvent from '@testing-library/user-event'

import { api, type DecisionInbox } from '@/lib/api'
import { dateTime } from '@/lib/format'
import { PreferencesProvider } from '@/lib/preferences'

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>()
  return {
    ...actual,
    api: { ...actual.api, health: vi.fn(), decisionInbox: vi.fn(), refreshDecisionSession: vi.fn() },
  }
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

const actionInbox = {
  ...inbox,
  entries: [
    {
      ...inbox.entries[0],
      attention_reason: 'A local watch condition triggered.',
      attention_state: 'watch_triggered',
      readiness: { ...inbox.entries[0].readiness, status: 'blocked' },
    },
    {
      ...inbox.entries[0],
      attention_reason: 'Trusted evidence is blocked.',
      attention_state: 'review_available',
      evidence_status: 'unavailable',
      instrument_type: 'perpetual',
      mark_context: { reason: null, status: 'available', value: 65_000 },
      packet_id: 'packet-222222222222222222222222',
      parent_packet_id: null,
      readiness: {
        ...inbox.entries[0].readiness,
        limiting_evidence_at: null,
        reason: 'No promoted forecast is available.',
        reason_code: 'forecast_unavailable',
        status: 'blocked',
      },
      symbol: 'BTC-USD',
      venue: 'hyperliquid',
    },
    {
      ...inbox.entries[0],
      attention_reason: 'A saved outcome is ready for review.',
      attention_state: 'review_available',
      packet_id: 'packet-333333333333333333333333',
      readiness: {
        ...inbox.entries[0].readiness,
        reason: 'Exact packet evidence is trusted for research.',
        reason_code: 'trusted_evidence',
        status: 'ready',
      },
      symbol: 'AAPL',
    },
    {
      ...inbox.entries[0],
      attention_reason: 'The saved watch remains active.',
      attention_state: 'watching',
      packet_id: 'packet-444444444444444444444444',
      symbol: 'SOL-USD',
      venue: 'hyperliquid',
    },
  ],
} satisfies DecisionInbox

const mockedDecisionInbox = vi.mocked(api.decisionInbox)
const mockedRefresh = vi.mocked(api.refreshDecisionSession)

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((promiseResolve) => {
    resolve = promiseResolve
  })
  return { promise, resolve }
}

function renderWatchlist(locale: 'en-US' | 'zh-CN' = 'en-US') {
  if (locale === 'zh-CN') {
    localStorage.setItem('quantmesh.preferences', JSON.stringify({ locale, theme: 'dark' }))
  }
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={client}>
      <PreferencesProvider><MemoryRouter><WatchlistScreen /></MemoryRouter></PreferencesProvider>
    </QueryClientProvider>,
  )
  return client
}

beforeEach(() => {
  vi.restoreAllMocks()
  vi.clearAllMocks()
  localStorage.clear()
  vi.mocked(api.health).mockResolvedValue({ status: 'ok', project: 'QuantMesh', version: 'test', runtime_mode: 'demo', paper_mode: true, live_trading: false })
  mockedDecisionInbox.mockResolvedValue(inbox)
  mockedRefresh.mockResolvedValue({
    started_at: '2026-09-08T12:00:00Z',
    completed_at: '2026-09-08T12:00:01Z',
    status: 'complete',
    registered_count: 2,
    evaluated_count: 2,
    items: [
      { packet_id: 'packet-aaaaaaaaaaaaaaaaaaaaaaaa', registration_id: 'registration-aaaaaaaaaaaaaaaaaaaaaaaa', evaluation_id: 'evaluation-aaaaaaaaaaaaaaaaaaaaaaaa', status: 'evaluated', triggered: true, not_comparable_codes: [], reason_code: null, reason: null },
      { packet_id: 'packet-bbbbbbbbbbbbbbbbbbbbbbbb', registration_id: 'registration-bbbbbbbbbbbbbbbbbbbbbbbb', evaluation_id: 'evaluation-bbbbbbbbbbbbbbbbbbbbbbbb', status: 'evaluated', triggered: false, not_comparable_codes: [], reason_code: null, reason: null },
    ],
  })
})

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

it.each(['en-US', 'zh-CN'] as const)('shows durable session summary on initial load in %s without refresh', async (locale) => {
  mockedDecisionInbox.mockResolvedValue({
    ...inbox,
    session: { ...inbox.session, last_checked_at: '2026-09-05T11:59:00Z', registered_count: 3, triggered_count: 1 },
  })
  renderWatchlist(locale)
  const summary = within(await screen.findByRole('region', {
    name: locale === 'en-US' ? 'Session summary' : '会话摘要',
  }))
  const displayLocale = locale === 'en-US' ? 'en' : locale
  const generated = dateTime(inbox.generated_at, displayLocale)
  const checked = dateTime('2026-09-05T11:59:00Z', displayLocale)
  expect(summary.getByText(locale === 'en-US' ? `View generated ${generated}` : `视图生成于 ${generated}`)).toBeVisible()
  expect(summary.getByText(locale === 'en-US' ? `Last local check: ${checked}` : `上次本地检查：${checked}`)).toBeVisible()
  expect(summary.getByText(locale === 'en-US' ? 'Registered watches 3 · Triggered 1 · Evidence blocked or unavailable 2' : '已注册观察 3 · 已触发 1 · 证据受阻或不可用 2')).toBeVisible()
  expect(mockedRefresh).not.toHaveBeenCalled()
})

it('shows an explicit never-checked session summary for an empty inbox', async () => {
  mockedDecisionInbox.mockResolvedValue({ ...inbox, entries: [] })
  renderWatchlist()
  const summary = within(await screen.findByRole('region', { name: 'Session summary' }))
  expect(summary.getByText('Last local check: Never checked')).toBeVisible()
  expect(mockedRefresh).not.toHaveBeenCalled()
})

it('keeps not-started entries in No action while unavailable venue entries stay Blocked', async () => {
  const user = userEvent.setup()
  renderWatchlist()
  await user.click(await screen.findByRole('button', { name: 'No action 2' }))
  expect(screen.getByText('AAPL')).toBeVisible()
  expect(screen.getByRole('link', { name: 'Open workspace' })).toHaveAttribute('href', '/instruments/moomoo/AAPL')
  expect(screen.queryByText('UNKNOWN')).not.toBeInTheDocument()
  await user.click(screen.getByRole('button', { name: 'Blocked 1' }))
  expect(screen.getByText('UNKNOWN')).toBeVisible()
  expect(screen.queryByText('AAPL')).not.toBeInTheDocument()
})

it('filters the four textual attention buckets while preserving exact packet identity', async () => {
  mockedDecisionInbox.mockResolvedValue(actionInbox)
  const user = userEvent.setup()
  renderWatchlist()

  const all = await screen.findByRole('button', { name: 'All 4' })
  expect(all).toHaveAttribute('aria-pressed', 'true')
  for (const name of ['Triggered 1', 'Blocked 1', 'Review due 1', 'No action 1']) {
    expect(screen.getByRole('button', { name })).toBeVisible()
  }
  for (const symbol of ['NVDA', 'BTC-USD', 'AAPL', 'SOL-USD']) {
    expect(screen.getByText(symbol)).toBeVisible()
  }

  await user.click(screen.getByRole('button', { name: 'Blocked 1' }))

  expect(screen.getByRole('button', { name: 'Blocked 1' })).toHaveAttribute('aria-pressed', 'true')
  expect(screen.getByText('BTC-USD')).toBeVisible()
  expect(screen.getByText('Trusted evidence blocked')).toBeVisible()
  expect(screen.queryByText('NVDA')).not.toBeInTheDocument()
  expect(screen.getByRole('link', { name: 'Open exact packet' })).toHaveAttribute(
    'href',
    '/instruments/hyperliquid/BTC-USD?range=6m&packet=packet-222222222222222222222222',
  )

  for (const [name, symbol, packet] of [
    ['Triggered 1', 'NVDA', 'packet-111111111111111111111111'],
    ['Review due 1', 'AAPL', 'packet-333333333333333333333333'],
    ['No action 1', 'SOL-USD', 'packet-444444444444444444444444'],
  ] as const) {
    await user.click(screen.getByRole('button', { name }))
    expect(screen.getByText(symbol)).toBeVisible()
    expect(screen.getByRole('link', { name: 'Open exact packet' })).toHaveAttribute(
      'href',
      expect.stringContaining(`packet=${packet}`),
    )
  }
})

it('keeps a keyboard-selected bucket stable through explicit Inbox invalidation only', async () => {
  mockedDecisionInbox.mockResolvedValue(actionInbox)
  const requestPermission = vi.fn()
  vi.stubGlobal('Notification', { requestPermission })
  const setInterval = vi.spyOn(globalThis, 'setInterval')
  const user = userEvent.setup()
  renderWatchlist()

  const triggered = await screen.findByRole('button', { name: 'Triggered 1' })
  await user.tab()
  expect(screen.getByRole('textbox', { name: 'Ticker' })).toHaveFocus()
  await user.tab()
  expect(screen.getByRole('button', { name: 'Open chart' })).toHaveFocus()
  await user.tab()
  expect(screen.getByRole('button', { name: 'Refresh session' })).toHaveFocus()
  await user.tab()
  expect(screen.getByRole('button', { name: 'All 4' })).toHaveFocus()
  await user.tab()
  expect(triggered).toHaveFocus()
  await user.keyboard('{Enter}')
  expect(triggered).toHaveAttribute('aria-pressed', 'true')
  expect(screen.getByText('NVDA')).toBeVisible()
  expect(screen.queryByText('BTC-USD')).not.toBeInTheDocument()

  await user.click(screen.getByRole('button', { name: 'Refresh session' }))

  expect(await screen.findByText('2 watches checked · 1 triggered')).toBeVisible()
  expect(mockedDecisionInbox).toHaveBeenCalledTimes(2)
  expect(screen.getByRole('button', { name: 'Triggered 1' })).toHaveAttribute('aria-pressed', 'true')
  expect(screen.getByText('NVDA')).toBeVisible()
  expect(setInterval.mock.calls.some(([, delay]) => delay === 60_000)).toBe(false)
  expect(requestPermission).not.toHaveBeenCalled()
  expect(screen.queryByText(/notification|provider|OpenD/i)).not.toBeInTheDocument()
})

it('offers the complete compact action queue in Simplified Chinese', async () => {
  mockedDecisionInbox.mockResolvedValue(actionInbox)
  renderWatchlist('zh-CN')

  for (const name of ['全部 4', '已触发 1', '受阻 1', '待复盘 1', '无需操作 1']) {
    expect(await screen.findByRole('button', { name })).toBeVisible()
  }
})

it('restores explicit keyboard refresh focus after Chromium blurs the disabled pending button', async () => {
  const refresh = deferred<Awaited<ReturnType<typeof api.refreshDecisionSession>>>()
  mockedRefresh.mockImplementationOnce(() => refresh.promise)
  const setInterval = vi.spyOn(globalThis, 'setInterval')
  const setItem = vi.spyOn(Storage.prototype, 'setItem')
  const checkPacketMonitoring = vi.spyOn(api, 'checkPacketMonitoring')
    .mockImplementation(() => { throw new Error('per-packet monitoring must not run') })
  const client = renderWatchlist()

  // A 60-second automatic refresh must schedule at mount; observing that
  // boundary catches it without waiting a real minute in the component test.
  expect(setInterval).not.toHaveBeenCalled()
  const all = await screen.findByRole('button', { name: 'All 3' })
  const button = screen.getByRole('button', { name: 'Refresh session' })
  const invalidate = vi.spyOn(client, 'invalidateQueries')
  expect(setItem.mock.calls).toEqual([[
    'quantmesh.preferences',
    JSON.stringify({ locale: 'en', theme: 'dark' }),
  ]])
  setInterval.mockClear()
  setItem.mockClear()

  button.focus()
  expect(button).toHaveFocus()
  fireEvent.keyDown(button, { key: 'Enter' })
  button.blur()
  all.focus()
  fireEvent.click(button)

  await waitFor(() => expect(button).toBeDisabled())
  expect(mockedRefresh).toHaveBeenCalledTimes(1)
  expect(button).not.toHaveFocus()
  expect(invalidate).not.toHaveBeenCalled()
  expect(mockedDecisionInbox).toHaveBeenCalledTimes(1)
  expect(setInterval).not.toHaveBeenCalledWith(expect.any(Function), 60_000)
  expect(checkPacketMonitoring).not.toHaveBeenCalled()
  expect(setItem).not.toHaveBeenCalled()
  expect(screen.queryByText(/automatic refresh|seconds/i)).not.toBeInTheDocument()

  refresh.resolve({
    started_at: '2026-09-08T12:00:00Z', completed_at: '2026-09-08T12:00:01Z',
    status: 'complete', registered_count: 2, evaluated_count: 2,
    items: [
      { packet_id: 'packet-aaaaaaaaaaaaaaaaaaaaaaaa', registration_id: 'registration-aaaaaaaaaaaaaaaaaaaaaaaa', evaluation_id: 'evaluation-aaaaaaaaaaaaaaaaaaaaaaaa', status: 'evaluated', triggered: true, not_comparable_codes: [], reason_code: null, reason: null },
      { packet_id: 'packet-bbbbbbbbbbbbbbbbbbbbbbbb', registration_id: 'registration-bbbbbbbbbbbbbbbbbbbbbbbb', evaluation_id: 'evaluation-bbbbbbbbbbbbbbbbbbbbbbbb', status: 'evaluated', triggered: false, not_comparable_codes: [], reason_code: null, reason: null },
    ],
  })
  await Promise.resolve()
  await Promise.resolve()
  expect(setInterval).not.toHaveBeenCalledWith(expect.any(Function), 60_000)
  expect(checkPacketMonitoring).not.toHaveBeenCalled()
  expect(setItem).not.toHaveBeenCalled()

  expect(await screen.findByText('2 watches checked · 1 triggered')).toBeVisible()
  await act(async () => {
    await Promise.resolve()
  })
  expect(mockedDecisionInbox).toHaveBeenCalledTimes(2)
  expect(invalidate).toHaveBeenCalledTimes(1)
  expect(invalidate).toHaveBeenCalledWith({ queryKey: ['decision-inbox'] })
  expect(mockedRefresh).toHaveBeenCalledTimes(1)
  expect(button).toHaveFocus()
  // `findByText` polls through Testing Library's 50ms interval. The product
  // scheduler boundary is the prohibited 60-second automatic refresh.
  expect(setInterval).not.toHaveBeenCalledWith(expect.any(Function), 60_000)
  expect(checkPacketMonitoring).not.toHaveBeenCalled()
  expect(setItem).not.toHaveBeenCalled()
  expect(screen.queryByText(/automatic refresh|seconds/i)).not.toBeInTheDocument()
})

it('does not steal focus when refresh activation did not own it', async () => {
  const refresh = deferred<Awaited<ReturnType<typeof api.refreshDecisionSession>>>()
  mockedRefresh.mockImplementationOnce(() => refresh.promise)
  renderWatchlist()

  const button = await screen.findByRole('button', { name: 'Refresh session' })
  const all = await screen.findByRole('button', { name: 'All 3' })
  all.focus()
  expect(all).toHaveFocus()
  fireEvent.click(button)
  await waitFor(() => expect(button).toBeDisabled())

  refresh.resolve({
    started_at: '2026-09-08T12:00:00Z', completed_at: '2026-09-08T12:00:01Z',
    status: 'no_registered_watches', registered_count: 0, evaluated_count: 0, items: [],
  })
  expect(await screen.findByText('No local watches are registered.')).toBeVisible()
  await act(async () => {
    await Promise.resolve()
  })

  expect(all).toHaveFocus()
})

it.each([
  ['en-US', 'complete', '2 watches checked · 1 triggered'],
  ['zh-CN', 'complete', '已检查 2 个观察 · 已触发 1 个'],
  ['en-US', 'partial', '1 of 2 watches checked'],
  ['zh-CN', 'partial', '已检查 1 / 2 个观察'],
  ['en-US', 'no_registered_watches', 'No local watches are registered.'],
  ['zh-CN', 'no_registered_watches', '没有已注册的本地观察。'],
] as const)('renders the %s %s explicit refresh outcome', async (locale, status, feedback) => {
  mockedRefresh.mockResolvedValue({
    started_at: '2026-09-08T12:00:00Z', completed_at: '2026-09-08T12:00:01Z',
    status,
    registered_count: status === 'no_registered_watches' ? 0 : 2,
    evaluated_count: status === 'complete' ? 2 : status === 'partial' ? 1 : 0,
    items: status === 'complete'
      ? [
          { packet_id: 'packet-aaaaaaaaaaaaaaaaaaaaaaaa', registration_id: 'registration-aaaaaaaaaaaaaaaaaaaaaaaa', evaluation_id: 'evaluation-aaaaaaaaaaaaaaaaaaaaaaaa', status: 'evaluated', triggered: true, not_comparable_codes: [], reason_code: null, reason: null },
          { packet_id: 'packet-bbbbbbbbbbbbbbbbbbbbbbbb', registration_id: 'registration-bbbbbbbbbbbbbbbbbbbbbbbb', evaluation_id: 'evaluation-bbbbbbbbbbbbbbbbbbbbbbbb', status: 'evaluated', triggered: false, not_comparable_codes: [], reason_code: null, reason: null },
        ]
      : status === 'partial'
      ? [
          { packet_id: 'packet-aaaaaaaaaaaaaaaaaaaaaaaa', registration_id: 'registration-aaaaaaaaaaaaaaaaaaaaaaaa', evaluation_id: 'evaluation-aaaaaaaaaaaaaaaaaaaaaaaa', status: 'evaluated', triggered: false, not_comparable_codes: [], reason_code: null, reason: null },
          { packet_id: 'packet-bbbbbbbbbbbbbbbbbbbbbbbb', registration_id: 'registration-bbbbbbbbbbbbbbbbbbbbbbbb', evaluation_id: null, status: 'failed', triggered: false, not_comparable_codes: [], reason_code: 'packet_unavailable', reason: 'This local watch could not be evaluated.' },
        ]
      : [],
  })
  const user = userEvent.setup()
  renderWatchlist(locale)

  await user.click(await screen.findByRole('button', {
    name: locale === 'zh-CN' ? '刷新会话' : 'Refresh session',
  }))

  expect(await screen.findByText(feedback)).toBeVisible()
  if (status === 'partial') {
    expect(screen.getByText('packet-bbbbbbbbbbbbbbbbbbbbbbbb')).toBeVisible()
    const reason = screen.getByText(
      locale === 'zh-CN' ? '已保存的决策包不可用。' : 'Saved packet is unavailable.',
    )
    expect(reason).toHaveAttribute('title', 'This local watch could not be evaluated.')
  }
})

it.each([
  ['en-US', 'Refresh session', 'Local session refresh is unavailable.'],
  ['zh-CN', '刷新会话', '本地会话刷新不可用。'],
] as const)('renders localized sanitized rejected-refresh feedback for %s', async (locale, buttonName, feedback) => {
  mockedRefresh.mockRejectedValueOnce(new Error('raw server response must not render'))
  const user = userEvent.setup()
  renderWatchlist(locale)

  await user.click(await screen.findByRole('button', { name: buttonName }))

  expect(await screen.findByText(feedback)).toBeVisible()
  expect(screen.queryByText('raw server response must not render')).not.toBeInTheDocument()
})

it('lists failed packet-bound partial refresh facts in English and Chinese', async () => {
  const user = userEvent.setup()
  mockedRefresh.mockResolvedValue({
    started_at: '2026-09-08T12:00:00Z', completed_at: '2026-09-08T12:00:01Z',
    status: 'partial', registered_count: 2, evaluated_count: 1,
    items: [
      { packet_id: 'packet-aaaaaaaaaaaaaaaaaaaaaaaa', registration_id: 'registration-aaaaaaaaaaaaaaaaaaaaaaaa', evaluation_id: 'evaluation-aaaaaaaaaaaaaaaaaaaaaaaa', status: 'evaluated', triggered: false, not_comparable_codes: [], reason_code: null, reason: null },
      { packet_id: 'packet-bbbbbbbbbbbbbbbbbbbbbbbb', registration_id: 'registration-bbbbbbbbbbbbbbbbbbbbbbbb', evaluation_id: null, status: 'failed', triggered: false, not_comparable_codes: [], reason_code: 'packet_unavailable', reason: 'This local watch could not be evaluated.' },
    ],
  })
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={client}>
      <PreferencesProvider><MemoryRouter><WatchlistScreen /></MemoryRouter></PreferencesProvider>
    </QueryClientProvider>,
  )

  await user.click(await screen.findByRole('button', { name: 'Refresh session' }))

  expect(await screen.findByText('1 of 2 watches checked')).toBeVisible()
  expect(screen.getByText('packet-bbbbbbbbbbbbbbbbbbbbbbbb')).toBeVisible()
  const reason = screen.getByText('Saved packet is unavailable.')
  expect(reason).toHaveAttribute('title', 'This local watch could not be evaluated.')

  localStorage.setItem('quantmesh.preferences', JSON.stringify({ locale: 'zh-CN', theme: 'dark' }))
  const chineseClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={chineseClient}>
      <PreferencesProvider><MemoryRouter><WatchlistScreen /></MemoryRouter></PreferencesProvider>
    </QueryClientProvider>,
  )
  await user.click((await screen.findAllByRole('button', { name: '刷新会话' }))[0])
  expect(await screen.findByText('已检查 1 / 2 个观察')).toBeVisible()
  expect(screen.getByText('已保存的决策包不可用。')).toHaveAttribute(
    'title',
    'This local watch could not be evaluated.',
  )
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
  expect(
    screen.getAllByText(`Readiness evaluated ${dateTime('2026-09-05T12:04:00Z')}`),
  ).toHaveLength(3)
  expect(within(screen.getByRole('table')).queryByText(/Last local check/)).not.toBeInTheDocument()
  expect(screen.getByText('configured mark is stale')).toBeVisible()
})

it('renders exact readiness reason in zh-CN with separate chart and packet actions', async () => {
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
  expect(screen.getAllByRole('link')).toHaveLength(2)
  expect(screen.getByRole('link', { name: '打开图表 NVDA' })).toHaveAttribute(
    'href', '/instruments/moomoo/NVDA?horizon=30&analysis=fresh',
  )
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

  expect(await screen.findByText(localized)).toHaveAttribute('title', status)
})

it.each([
  ['unusable_price_evidence', 'Price evidence cannot be used for this watch.', '价格证据不能用于此观察。'],
  ['future_reference', 'Watch reference time is in the future.', '观察参考时间在未来。'],
  ['calendar_unavailable', 'Watch calendar is unavailable.', '观察日历不可用。'],
  ['missing_forecast', 'Required forecast is unavailable.', '所需预测不可用。'],
  ['candidate_not_comparable', 'Candidate forecast cannot be compared.', '候选预测无法比较。'],
  ['candidate_incompatible', 'Candidate forecast is incompatible.', '候选预测不兼容。'],
])('localizes the persisted monitoring reason %s and retains it in title', async (code, _serverReason, localized) => {
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

it.each(['constructor', 'toString', '__proto__'])('keeps adversarial unknown code %s verbatim', async (code) => {
  const readinessReason = `Unknown readiness ${code}.`
  mockedDecisionInbox.mockResolvedValue({
    ...inbox,
    entries: [{
      ...inbox.entries[0],
      readiness: { ...inbox.entries[0].readiness, reason_code: code, reason: readinessReason },
      monitoring: {
        registration_id: 'registration-111', latest_evaluation_id: 'evaluation-111', triggered: false,
        event_ids: [], last_checked_at: '2026-09-05T12:05:00Z', latest_status: code, latest_reason: code,
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

  expect(await screen.findByText(readinessReason)).toHaveAttribute('title', readinessReason)
  const renderedCodes = screen.getAllByText(code)
  expect(renderedCodes).toHaveLength(2)
  for (const element of renderedCodes) {
    expect(element).toHaveAttribute('title', code)
  }
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
    session: inbox.session,
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
  expect(
    screen.getByText(`Last local check ${dateTime('2026-09-05T12:05:00Z')}`),
  ).toBeVisible()
  expect(screen.getByText('Monitoring data is unavailable.')).toBeVisible()
  expect(screen.getByText('Inconclusive')).toBeVisible()
  expect(screen.getByText(/Current account context only/)).toBeVisible()
  expect(screen.queryByText(/Sharpe|ranking|aggregate return|closed P&L/i)).not.toBeInTheDocument()
  expect(screen.queryByText('321')).not.toBeInTheDocument()
})
