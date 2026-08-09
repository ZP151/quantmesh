import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { LiveInstrumentState, LiveKind, LiveLabel, LiveView, MarketUpdate } from '@/lib/api'
import {
  ageText,
  bookSide,
  candleCloses,
  dataViews,
  instrumentLabel,
  mergeUpdate,
  midOf,
  openLiveConnection,
  quoteNumbers,
  spreadBps,
} from './live'

// The deterministic half of the live client: label derivation, the
// update-into-snapshot reconciliation, quote math and the WS→SSE
// fallback ladder (drilled with injectable fake transports — jsdom
// ships neither WebSocket nor EventSource).

const T0 = '2026-08-09T10:00:00+00:00'

function quote(
  instrument: string,
  bid: number,
  ask: number,
  overrides: Partial<MarketUpdate> = {},
): MarketUpdate {
  return {
    venue: 'hyperliquid',
    instrument,
    kind: 'quote',
    provenance: 'real',
    data_time: T0,
    received_at: T0,
    sequence: 1,
    sequence_gap: false,
    payload: { bid, ask },
    state: null,
    state_note: null,
    ...overrides,
  }
}

function statusUpdate(instrument: string): MarketUpdate {
  return {
    venue: 'hyperliquid',
    instrument,
    kind: 'status',
    provenance: 'real',
    data_time: T0,
    received_at: T0,
    sequence: null,
    sequence_gap: false,
    payload: {},
    state: 'connected',
    state_note: null,
  }
}

function instrument(kinds: Record<string, MarketUpdate>): LiveInstrumentState {
  const views: Record<string, LiveView> = {}
  for (const [kind, update] of Object.entries(kinds)) {
    views[kind] = {
      kind: kind as LiveKind,
      provenance: update.provenance,
      data_time: update.data_time,
      received_at: update.received_at,
      age_ms: 0,
      sequence: update.sequence,
      sequence_gap: update.sequence_gap,
      label: update.provenance === 'real' ? 'real' : (update.provenance as LiveLabel),
      payload: update.payload,
    }
  }
  return { venue: 'hyperliquid', label: 'real', kinds: views }
}

describe('instrument labels', () => {
  it('derives the badge from the worst data kind', () => {
    const both = instrument({ quote: quote('BTC', 100, 100.5), trade: quote('BTC', 0, 0, { kind: 'trade', payload: { price: 100.25, size: 1, side: 'buy' }, provenance: 'synthetic' }) })
    expect(instrumentLabel(both)).toBe('synthetic')
    // dataViews sorts most-degraded last: the badge takes the final one.
    expect(dataViews(both).map((view) => view.kind)).toEqual(['quote', 'trade'])
  })

  it('ignores status kinds in the badge', () => {
    const healthy = instrument({ quote: quote('BTC', 100, 100.5), status: statusUpdate('BTC') })
    expect(instrumentLabel(healthy)).toBe('real')
  })

  it('reports unavailable when no data kind has arrived', () => {
    expect(instrumentLabel(instrument({ status: statusUpdate('BTC') }))).toBe('unavailable')
  })
})

describe('mergeUpdate', () => {
  it('writes a fresh kind and recomputes the badge', () => {
    const first = quote('BTC', 100, 100.5)
    const after = mergeUpdate({}, first)
    expect(after.BTC.kinds.quote.payload).toEqual({ bid: 100, ask: 100.5 })
    expect(after.BTC.label).toBe('real')

    const stale = mergeUpdate(after, quote('BTC', 99, 99.5, { provenance: 'delayed' }))
    expect(stale.BTC.kinds.quote.provenance).toBe('delayed')
    expect(stale.BTC.label).toBe('delayed')
  })

  it('keeps other instruments untouched', () => {
    const after = mergeUpdate({}, quote('BTC', 100, 100.5))
    const withEth = mergeUpdate(after, quote('ETH', 3, 3.1))
    expect(Object.keys(withEth).sort()).toEqual(['BTC', 'ETH'])
    expect(withEth.BTC.kinds.quote.payload.bid).toBe(100)
  })

  it('carries the sequence gap flag into the view', () => {
    const after = mergeUpdate({}, quote('BTC', 100, 100.5, { sequence_gap: true }))
    expect(after.BTC.kinds.quote.sequence_gap).toBe(true)
  })
})

describe('quote math', () => {
  it('computes mid and spread bps', () => {
    const quoteView = quoteNumbers(quote('BTC', 100, 100.5))
    expect(midOf(quoteView)).toBe(100.25)
    expect(spreadBps(quoteView)).toBeCloseTo(49.8753, 3)
  })

  it('handles one-sided and empty quotes', () => {
    expect(spreadBps({ bid: 100 })).toBeUndefined()
    expect(midOf({ ask: 101 })).toBe(101)
    expect(midOf({})).toBeUndefined()
  })
})

describe('age and chart helpers', () => {
  it('formats ages', () => {
    expect(ageText(450)).toBe('450 ms')
    expect(ageText(3_200)).toBe('3 s')
    expect(ageText(65_000)).toBe('1 m 5 s')
  })

  it('collects candle closes in arrival order', () => {
    const candles = [10, 11, 10.5].map((close) => quote('BTC', 0, 0, { kind: 'candle', payload: { open: 10, high: 11, low: 9, close, volume: 5 } }))
    expect(candleCloses(candles)).toEqual([10, 11, 10.5])
    expect(candleCloses([quote('BTC', 1, 2)])).toEqual([])
  })
})

describe('bookSide', () => {
  // The wire contract (ADR-0014 _validate_l2) emits levels as
  // [price, size] pairs, strictly monotonic in price — this pins the
  // client parse to that shape so the two sides cannot drift again.
  it('parses [price, size] level pairs from an l2 snapshot view', () => {
    const bid = quote('BTC', 0, 0, {
      kind: 'l2_snapshot',
      payload: { side: 'bid', levels: [[100.0, 1.0], [99.5, 2.0]] },
    })
    expect(bookSide(bid)).toEqual([
      { price: 100.0, size: 1.0 },
      { price: 99.5, size: 2.0 },
    ])
  })

  it('returns an empty side when the view has no levels', () => {
    expect(bookSide(undefined)).toEqual([])
    expect(bookSide(quote('BTC', 100, 100.5))).toEqual([])
    expect(bookSide(quote('BTC', 0, 0, { kind: 'l2_snapshot', payload: { side: 'ask' } }))).toEqual([])
  })

  it('drops malformed levels instead of rendering them', () => {
    const bid = quote('BTC', 0, 0, {
      kind: 'l2_snapshot',
      payload: {
        side: 'bid',
        levels: [[100.0, 1.0], [99.5], [98.5, 3.0, 4], '99', { price: 97.5, size: 5 }, [NaN, 1], [97.0, 2.0]],
      },
    })
    expect(bookSide(bid)).toEqual([
      { price: 100.0, size: 1.0 },
      { price: 97.0, size: 2.0 },
    ])
  })
})

describe('openLiveConnection', () => {
  class FakeSocket {
    static instances: FakeSocket[] = []
    url: string
    onopen: (() => void) | null = null
    onmessage: ((event: MessageEvent) => void) | null = null
    onerror: (() => void) | null = null
    close = vi.fn(() => {
      this.onerror = null
      this.onmessage = null
    })

    constructor(url: string) {
      this.url = url
      FakeSocket.instances.push(this)
    }
  }

  class FakeEventSource {
    static instances: FakeEventSource[] = []
    url: string
    onmessage: ((event: MessageEvent) => void) | null = null
    onerror: (() => void) | null = null
    close = vi.fn()

    constructor(url: string) {
      this.url = url
      FakeEventSource.instances.push(this)
    }
  }

  const updates: MarketUpdate[] = []
  const statuses: string[] = []

  beforeEach(() => {
    FakeSocket.instances = []
    FakeEventSource.instances = []
    updates.length = 0
    statuses.length = 0
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  function open() {
    return openLiveConnection(
      {
        onUpdate: (update) => updates.push(update),
        onStatus: (status) => statuses.push(status),
      },
      {
        WebSocketImpl: FakeSocket as unknown as typeof WebSocket,
        EventSourceImpl: FakeEventSource as unknown as typeof EventSource,
        wsUrl: 'ws://test/api/live/ws',
        sseUrl: '/api/live/stream',
      },
    )
  }

  function emit(socket: FakeSocket, payload: MarketUpdate) {
    socket.onmessage?.({ data: JSON.stringify(payload) } as MessageEvent)
  }

  it('uses the WebSocket when it opens', () => {
    const connection = open()
    expect(FakeSocket.instances).toHaveLength(1)
    expect(FakeSocket.instances[0].url).toBe('ws://test/api/live/ws')
    FakeSocket.instances[0].onopen?.()
    expect(statuses).toEqual(['connecting', 'live'])
    emit(FakeSocket.instances[0], quote('BTC', 100, 100.5))
    expect(updates).toHaveLength(1)
    connection.close()
  })

  it('falls back to SSE when the socket errors', () => {
    const connection = open()
    FakeSocket.instances[0].onerror?.()
    expect(statuses).toEqual(['connecting', 'fallback'])
    expect(FakeEventSource.instances).toHaveLength(1)
    FakeEventSource.instances[0].onmessage?.({ data: JSON.stringify(quote('BTC', 1, 2)) } as MessageEvent)
    expect(updates).toHaveLength(1)
    expect(FakeSocket.instances[0].close).toHaveBeenCalled()
    connection.close()
  })

  it('drops malformed frames silently', () => {
    const connection = open()
    FakeSocket.instances[0].onmessage?.({ data: 'not json' } as MessageEvent)
    expect(updates).toHaveLength(0)
    connection.close()
  })

  it('retries the ladder after the SSE stream dies', () => {
    const connection = open()
    FakeSocket.instances[0].onerror?.()
    expect(statuses).toContain('fallback')
    FakeEventSource.instances[0].onerror?.()
    expect(statuses).toContain('down')
    expect(FakeEventSource.instances[0].close).toHaveBeenCalled()
    vi.advanceTimersByTime(2_000)
    expect(FakeSocket.instances).toHaveLength(2) // retried from the top
    connection.close()
  })

  it('stops everything once closed', () => {
    const connection = open()
    connection.close()
    FakeSocket.instances[0].onerror?.()
    FakeSocket.instances[0].onopen?.()
    expect(statuses).toEqual(['connecting'])
    expect(FakeEventSource.instances).toHaveLength(0)
  })
})
