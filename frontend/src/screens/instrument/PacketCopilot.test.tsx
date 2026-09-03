import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { api, type PacketCopilotState } from '@/lib/api'
import { PreferencesProvider } from '@/lib/preferences'

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>()
  return {
    ...actual,
    api: {
      ...actual.api,
      packetCopilot: vi.fn(),
      requestPacketCopilot: vi.fn(),
    },
  }
})

import { PacketCopilot } from './PacketCopilot'

const packetA = 'packet-aaaaaaaaaaaaaaaaaaaaaaaa'
const packetB = 'packet-bbbbbbbbbbbbbbbbbbbbbbbb'

const idle = (packetId: string): PacketCopilotState => ({
  packet_id: packetId,
  reason_code: null,
  record: null,
  status: 'idle',
})

const ready = (packetId: string): PacketCopilotState => ({
  packet_id: packetId,
  reason_code: null,
  status: 'ready',
  record: {
    analyst_decision_id: 'a'.repeat(16),
    analyst_model: { endpoint_kind: 'scripted', name: 'fixture-copilot', version: 'v1' },
    critic_decision_id: 'b'.repeat(16),
    critic_model: { endpoint_kind: 'scripted', name: 'fixture-copilot', version: 'v1' },
    packet_id: packetId,
    recorded_at: '2026-09-03T10:00:00Z',
    record_id: `copilot-${'c'.repeat(24)}`,
    report: {
      packet_id: packetId,
      base_explanation: item('Base explanation', '/market_state/trend', '1'.repeat(64)),
      bull_challenge: item('Bull challenge', '/scenarios/0/trigger', '2'.repeat(64)),
      bear_challenge: item('Bear challenge', '/scenarios/2/thesis', '3'.repeat(64)),
      evidence_gaps_or_contradictions: [
        item('Evidence gap', '/evidence/history_limitations', '4'.repeat(64)),
      ],
      limitations: [item('Report limitation', '/scenarios/1/confidence', '5'.repeat(64))],
      operator_questions: [
        item('Operator question', '/market_state/support', '6'.repeat(64)),
      ],
    },
    request_kind: 'explain-and-challenge',
    schema_version: 1,
  },
})

function item(text: string, jsonPointer: string, valueDigest: string) {
  return {
    citations: [{
      json_pointer: jsonPointer,
      source_id: packetA,
      source_kind: 'packet' as const,
      span: null,
      value_digest: valueDigest,
    }],
    text,
  }
}

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((next) => { resolve = next })
  return { promise, resolve }
}

function renderPanel(props: { contextKey?: string; packetId?: string | null } = {}) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const rendered = render(
    <QueryClientProvider client={queryClient}>
      <PreferencesProvider>
        <PacketCopilot
          contextKey={props.contextKey ?? 'moomoo:NVDA:6m'}
          packetId={props.packetId === undefined ? packetA : props.packetId}
        />
      </PreferencesProvider>
    </QueryClientProvider>,
  )
  return { ...rendered, queryClient }
}

const mockedLatest = vi.mocked(api.packetCopilot)
const mockedRequest = vi.mocked(api.requestPacketCopilot)

beforeEach(() => {
  vi.clearAllMocks()
  window.localStorage.clear()
  mockedLatest.mockResolvedValue(idle(packetA))
})

describe('PacketCopilot', () => {
  it('keeps a fresh draft ineligible and explains that it must be saved first', () => {
    renderPanel({ packetId: null })

    expect(screen.getByText('Save this DecisionPacket before requesting Copilot.')).toBeVisible()
    expect(screen.getByRole('button', { name: 'Explain & challenge' })).toBeDisabled()
    expect(mockedLatest).not.toHaveBeenCalled()
  })

  it('requests by keyboard, isolates loading, and renders every cited section', async () => {
    const user = userEvent.setup()
    const pending = deferred<PacketCopilotState>()
    mockedRequest.mockReturnValue(pending.promise)
    renderPanel()
    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'Explain & challenge' })).toBeEnabled()
    })
    const action = screen.getByRole('button', { name: 'Explain & challenge' })

    action.focus()
    expect(action).toHaveFocus()
    await user.keyboard('{Enter}')

    expect(screen.getByRole('status')).toHaveTextContent('Checking the exact packet')
    expect(screen.getByRole('button', { name: 'Explain & challenge' })).toBeDisabled()
    pending.resolve(ready(packetA))

    expect(await screen.findByRole('heading', { name: 'Base explanation' })).toBeVisible()
    for (const text of [
      'Bull challenge',
      'Bear challenge',
      'Evidence gap',
      'Report limitation',
      'Operator question',
    ]) {
      expect(screen.getAllByText(text)[0]).toBeVisible()
    }
    const citations = screen.getAllByText('1 packet fact')
    await user.click(citations[0])
    expect(screen.getByText('/market_state/trend')).toBeVisible()
    expect(screen.getByText('1'.repeat(64))).toBeVisible()
    expect(mockedRequest).toHaveBeenCalledWith(packetA)
  })

  it('shows a localized degraded reason and keeps retry available', async () => {
    const user = userEvent.setup()
    window.localStorage.setItem(
      'quantmesh.preferences',
      JSON.stringify({ locale: 'zh-CN', theme: 'dark' }),
    )
    mockedLatest.mockResolvedValue({
      packet_id: packetA,
      reason_code: 'copilot-unavailable',
      record: null,
      status: 'degraded',
    })
    mockedRequest.mockResolvedValue(idle(packetA))
    renderPanel()

    expect(await screen.findByText('Copilot 暂时不可用；DecisionPacket 与决策操作不受影响。')).toBeVisible()
    await user.click(screen.getByRole('button', { name: '重试解释与质疑' }))
    expect(mockedRequest).toHaveBeenCalledWith(packetA)
  })

  it('discards a late response when packet, range, or instrument context changes', async () => {
    const first = deferred<PacketCopilotState>()
    mockedLatest.mockImplementation((packetId) => {
      if (packetId === packetA) return first.promise
      return Promise.resolve(idle(packetB))
    })
    const rendered = renderPanel()

    rendered.rerender(
      <QueryClientProvider client={rendered.queryClient}>
        <PreferencesProvider>
          <PacketCopilot contextKey="moomoo:AAPL:1m" packetId={packetB} />
        </PreferencesProvider>
      </QueryClientProvider>,
    )
    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'Explain & challenge' })).toBeEnabled()
    })

    first.resolve(ready(packetA))
    await waitFor(() => expect(screen.queryByText('Base explanation')).not.toBeInTheDocument())
    expect(mockedLatest).toHaveBeenCalledWith(packetB)
  })

  it('discards a late request when only the context changes for the same packet', async () => {
    const user = userEvent.setup()
    const pending = deferred<PacketCopilotState>()
    mockedRequest.mockReturnValue(pending.promise)
    const rendered = renderPanel()
    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'Explain & challenge' })).toBeEnabled()
    })

    await user.click(screen.getByRole('button', { name: 'Explain & challenge' }))
    rendered.rerender(
      <QueryClientProvider client={rendered.queryClient}>
        <PreferencesProvider>
          <PacketCopilot contextKey="moomoo:NVDA:1m" packetId={packetA} />
        </PreferencesProvider>
      </QueryClientProvider>,
    )
    pending.resolve(ready(packetA))

    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'Explain & challenge' })).toBeEnabled()
    })
    expect(screen.queryByText('Base explanation')).not.toBeInTheDocument()
    expect(rendered.queryClient.getQueryData(['packet-copilot', 'moomoo:NVDA:6m', packetA]))
      .toEqual(idle(packetA))
  })

  it('keeps long packet fields and digests inside a compact rail', async () => {
    mockedLatest.mockResolvedValue(ready(packetA))
    const { container } = renderPanel()

    expect(await screen.findByRole('heading', { name: 'Base explanation' })).toBeVisible()
    expect(container.querySelector('[data-testid="packet-copilot"]')).toHaveClass('min-w-0')
    expect(container.querySelector('[data-testid="packet-copilot-citation"]')).toHaveClass(
      '[overflow-wrap:anywhere]',
    )
  })
})
