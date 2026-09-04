import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { api } from '@/lib/api'
import { PreferencesProvider } from '@/lib/preferences'

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>()
  return {
    ...actual,
    api: {
      ...actual.api,
      checkPacketMonitoring: vi.fn(),
      packetMonitoring: vi.fn(),
    },
  }
})

import { PacketMonitoring } from './PacketMonitoring'

const mockedPacketMonitoring = vi.mocked(api.packetMonitoring)
const mockedCheckPacketMonitoring = vi.mocked(api.checkPacketMonitoring)

const emptyState = {
  packet_id: 'packet-000000000001',
  registration: null,
} as never

const registeredState = {
  evaluation: {
    evaluation_id: 'evaluation-000000000001',
    observation: { evaluated_at: '2026-09-03T10:01:00Z' },
    registration_id: 'registration-000000000001',
    results: [
      { condition_id: 'condition-entry', facts: { current_price: 181 }, state: 'armed' },
      { condition_id: 'condition-invalidation', facts: { current_price: 181 }, state: 'armed' },
    ],
  },
  packet_id: 'packet-000000000001',
  registration: {
    conditions: [
      { condition_id: 'condition-entry', definition: { lower: 180, upper: 184 }, kind: 'entry_zone', packet_id: 'packet-000000000001' },
      { condition_id: 'condition-invalidation', definition: { level: 176 }, kind: 'invalidation', packet_id: 'packet-000000000001' },
    ],
    packet_id: 'packet-000000000001',
    registration_id: 'registration-000000000001',
  },
} as never

function renderMonitoring(
  packetId: string | null = 'packet-000000000001',
  contextKey = 'moomoo:NVDA:6m',
  client = new QueryClient({ defaultOptions: { queries: { retry: false } } }),
) {
  return render(
    <QueryClientProvider client={client}>
      <PreferencesProvider>
        <PacketMonitoring contextKey={contextKey} packetId={packetId} />
      </PreferencesProvider>
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  window.localStorage.clear()
  mockedPacketMonitoring.mockResolvedValue(emptyState)
  mockedCheckPacketMonitoring.mockResolvedValue(registeredState)
})

describe('PacketMonitoring', () => {
  it('keeps a fresh workspace save-first and does not issue a monitoring request', () => {
    renderMonitoring(null)

    expect(screen.getByText('Save this DecisionPacket before monitoring it locally.')).toBeVisible()
    expect(screen.getByRole('button', { name: 'Save & check' })).toBeDisabled()
    expect(mockedPacketMonitoring).not.toHaveBeenCalled()
  })

  it('registers the persisted packet with fixed checks and renders typed evaluation facts', async () => {
    const user = userEvent.setup()
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const invalidate = vi.spyOn(client, 'invalidateQueries')
    renderMonitoring('packet-000000000001', 'moomoo:NVDA:6m', client)

    await screen.findByRole('checkbox', { name: 'Entry zone crossing' })
    await user.click(screen.getByRole('checkbox', { name: 'Forecast drift' }))
    await user.click(screen.getByRole('button', { name: 'Save & check' }))

    await waitFor(() => {
      expect(mockedCheckPacketMonitoring).toHaveBeenCalledWith('packet-000000000001', [
        'entry_zone', 'invalidation', 'data_stale',
      ])
    })
    expect(screen.getByText('Entry zone 180–184')).toBeVisible()
    expect(screen.getAllByText('Price 181')).toHaveLength(2)
    expect(screen.getByRole('button', { name: 'Check now' })).toBeVisible()
    expect(invalidate).toHaveBeenCalledWith({
      exact: true,
      queryKey: ['packet-outcome-review', 'moomoo:NVDA:6m', 'packet-000000000001'],
    })
  })

  it('does not display a late response after the operator switches context', async () => {
    let resolveFirst!: (value: never) => void
    mockedPacketMonitoring.mockImplementationOnce(() => new Promise((resolve) => { resolveFirst = resolve }))
    mockedPacketMonitoring.mockResolvedValueOnce(emptyState)
    const rendered = renderMonitoring('packet-000000000001', 'moomoo:NVDA:6m')

    rendered.rerender(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <PreferencesProvider>
          <PacketMonitoring contextKey="moomoo:AMD:6m" packetId="packet-000000000002" />
        </PreferencesProvider>
      </QueryClientProvider>,
    )
    resolveFirst(registeredState)

    await waitFor(() => expect(mockedPacketMonitoring).toHaveBeenCalledWith('packet-000000000002'))
    expect(screen.queryByText('Entry zone 180–184')).not.toBeInTheDocument()
  })

  it('does not leak a failed save into a switched packet context', async () => {
    mockedCheckPacketMonitoring.mockRejectedValueOnce(new Error('offline'))
    const user = userEvent.setup()
    const rendered = renderMonitoring()
    await screen.findByRole('checkbox', { name: 'Entry zone crossing' })
    await user.click(screen.getByRole('button', { name: 'Save & check' }))
    await waitFor(() => expect(mockedCheckPacketMonitoring).toHaveBeenCalledTimes(1))
    await screen.findByText('Local packet monitoring is temporarily unavailable. The DecisionPacket and decision actions are unaffected.')

    rendered.rerender(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <PreferencesProvider>
          <PacketMonitoring contextKey="moomoo:AMD:6m" packetId="packet-000000000002" />
        </PreferencesProvider>
      </QueryClientProvider>,
    )

    expect(screen.queryByText('Local packet monitoring is temporarily unavailable. The DecisionPacket and decision actions are unaffected.')).not.toBeInTheDocument()
  })

  it('wraps the disclosure on a narrow viewport', async () => {
    renderMonitoring()
    await screen.findByRole('checkbox', { name: 'Entry zone crossing' })
    fireEvent.resize(window)
    expect(screen.getByTestId('packet-monitoring')).toHaveClass('min-w-0')
  })

  it('uses the Simplified Chinese disclosure copy when selected', () => {
    window.localStorage.setItem('quantmesh.preferences', JSON.stringify({ locale: 'zh-CN', theme: 'dark' }))
    renderMonitoring(null)

    expect(screen.getByText('本地数据包监控')).toBeVisible()
    expect(screen.getByText('请先保存此 DecisionPacket，再进行本地监控。')).toBeVisible()
  })
})
