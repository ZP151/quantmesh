import { act, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { InstrumentWorkspace } from '@/lib/api'
import { PreferencesProvider } from '@/lib/preferences'

import { workspace as fixture } from './scenario-lab-fixture'
import { WorkspaceHeader } from './WorkspaceHeader'

const SOURCE_TIME = '2026-09-12T12:00:00Z'

function observed(overrides: Partial<InstrumentWorkspace['live']> = {}): InstrumentWorkspace {
  return {
    ...fixture,
    live: {
      ...fixture.live,
      age_ms: 0,
      data_time: SOURCE_TIME,
      received_at: SOURCE_TIME,
      status: 'available',
      label: 'real',
      provenance: 'real',
      source: 'hyperliquid-public-ws',
      reason: null,
      ...overrides,
    },
  }
}

function header(workspace: InstrumentWorkspace, stream: 'live' | 'down' | 'fallback' = 'down') {
  return <PreferencesProvider><WorkspaceHeader stream={stream} workspace={workspace} /></PreferencesProvider>
}

function field(label: string) {
  return screen.getByText(label, { selector: 'dt' }).nextElementSibling!
}

describe('WorkspaceHeader cached freshness', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    localStorage.clear()
    vi.setSystemTime(new Date(Date.parse(SOURCE_TIME) - 3_600_000))
  })
  afterEach(() => vi.useRealTimers())

  it('ages and degrades a cached quote without changing values or source times', () => {
    const workspace = observed()
    const view = render(header(workspace))
    const original = ['Mark', 'Live source', 'Data time', 'Received'].map(label => field(label).textContent)
    expect(screen.getByText('Live proven')).toBeInTheDocument()
    expect(field('Age')).toHaveTextContent('0 ms')
    act(() => vi.advanceTimersByTime(31_000))
    expect(field('Age')).toHaveTextContent('31 s')
    expect(screen.getByText('Live degraded')).toBeInTheDocument()
    expect(field('Live classification')).toHaveTextContent('stale · real')
    expect(['Mark', 'Live source', 'Data time', 'Received'].map(label => field(label).textContent)).toEqual(original)
    expect(workspace.live.age_ms).toBe(0)
    view.unmount()
    expect(vi.getTimerCount()).toBe(0)
  })

  it('retains monotonic age through wall-clock rollback and identical HTTP snapshots', () => {
    const workspace = observed()
    const view = render(header(workspace, 'live'))
    act(() => vi.advanceTimersByTime(31_000))
    vi.setSystemTime(new Date(Date.parse(SOURCE_TIME) - 7_200_000))
    view.rerender(header({ ...workspace, live: { ...workspace.live } }, 'live'))
    act(() => vi.advanceTimersByTime(1_000))
    expect(field('Age')).toHaveTextContent('32 s')
    expect(screen.getByText('Live degraded')).toBeInTheDocument()
  })

  it('recovers with a new fresh HTTP observation even while the stream stays down', () => {
    const view = render(header(observed()))
    act(() => vi.advanceTimersByTime(31_000))
    expect(screen.getByText('Live degraded')).toBeInTheDocument()
    view.rerender(header(observed({ data_time: '2026-09-12T12:00:31Z', received_at: '2026-09-12T12:00:31Z' })))
    expect(screen.getByText('Live proven')).toBeInTheDocument()
    expect(field('Age')).toHaveTextContent('0 ms')
    expect(field('Live classification')).toHaveTextContent('real · real')
  })

  it('uses source age when a newly received quote already contains old data', () => {
    render(header(observed({ received_at: '2026-09-12T12:00:45Z' })))
    expect(field('Age')).toHaveTextContent('45 s')
    expect(screen.getByText('Live degraded')).toBeInTheDocument()
  })

  it.each(['demo-synthetic', 'synthetic'])('never promotes %s observations to real', (provenance) => {
    render(header(observed({ provenance, label: 'synthetic', status: 'degraded' })))
    act(() => vi.advanceTimersByTime(31_000))
    expect(field('Live classification')).toHaveTextContent(`synthetic · ${provenance}`)
    expect(screen.queryByText('Live proven')).not.toBeInTheDocument()
  })

  it('preserves server unavailability while aging retained values', () => {
    render(header(observed({ status: 'unavailable', label: 'unavailable' })))
    act(() => vi.advanceTimersByTime(31_000))
    expect(screen.getByText('Live unavailable')).toBeInTheDocument()
    expect(field('Age')).toHaveTextContent('31 s')
  })
})
