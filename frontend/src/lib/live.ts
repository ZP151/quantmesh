// The live feed client (iteration 0015 Phase C). The browser talks only
// to the local server — venue transports live server-side. This module
// owns the WS-first / SSE-fallback stream connection and the pure
// reconciliation helpers the cockpit screens render against: merging a
// pushed MarketUpdate into the latest-state snapshot, deriving the
// instrument badge from the worst of its data kinds, and the quote
// math (mid, spread bps, age text). The pure parts are deterministic
// and unit-drilled; the connection factory takes injectable transports
// so the fallback ladder is testable without a network.

import { useEffect, useRef, useState } from 'react'
import type {
  LiveInstrumentState,
  LiveKind,
  LiveLabel,
  LiveView,
  MarketUpdate,
} from '@/lib/api'

// --- Labels --------------------------------------------------------------

/** Degradation rank; the instrument badge shows the worst data kind. */
const LABEL_RANK: Record<LiveLabel, number> = {
  real: 0,
  delayed: 1,
  synthetic: 2,
  stale: 3,
  unavailable: 4,
}

/** Kinds that carry market data — status updates are connector health
 * (shown in the health panel), never part of the instrument badge. */
const DATA_KINDS: readonly LiveKind[] = [
  'quote',
  'trade',
  'candle',
  'l2_snapshot',
  'l2_delta',
  'metrics',
]

export function dataViews(instrument: LiveInstrumentState): LiveView[] {
  return DATA_KINDS.filter((kind) => kind in instrument.kinds)
    .map((kind) => instrument.kinds[kind])
    .sort((a, b) => LABEL_RANK[a.label] - LABEL_RANK[b.label])
}

/** The instrument badge: the most degraded data kind's label. */
export function instrumentLabel(instrument: LiveInstrumentState): LiveLabel {
  const views = dataViews(instrument)
  if (views.length === 0) return 'unavailable'
  return views[views.length - 1].label
}

export const LABEL_TEXT: Record<LiveLabel, string> = {
  real: 'Real',
  delayed: 'Delayed',
  stale: 'Stale',
  synthetic: 'Synthetic',
  unavailable: 'Unavailable',
}

export function labelTone(label: LiveLabel): string {
  switch (label) {
    case 'real':
      return 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400'
    case 'delayed':
      return 'bg-amber-500/10 text-amber-600 dark:text-amber-400'
    case 'stale':
      return 'bg-orange-500/10 text-orange-600 dark:text-orange-400'
    case 'synthetic':
      return 'bg-violet-500/10 text-violet-600 dark:text-violet-400'
    case 'unavailable':
      return 'bg-muted text-muted-foreground'
  }
}

// --- Reconciliation (pure) ------------------------------------------------

/** Merge one streamed update into a latest-state map. The update's
 * kind replaces the previous view for venue+instrument+kind; the
 * instrument's badge label is recomputed from its data kinds. */
export function mergeUpdate(
  instruments: Record<string, LiveInstrumentState>,
  update: MarketUpdate,
): Record<string, LiveInstrumentState> {
  const previous = instruments[update.instrument]
  const instrument: LiveInstrumentState = {
    venue: update.venue,
    label: previous?.label ?? 'unavailable',
    kinds: { ...(previous?.kinds ?? {}) },
  }
  instrument.kinds[update.kind] = {
    kind: update.kind,
    provenance: update.provenance,
    data_time: update.data_time,
    received_at: update.received_at,
    age_ms: 0,
    sequence: update.sequence,
    sequence_gap: update.sequence_gap,
    label: update.provenance === 'real' ? 'real' : (update.provenance as LiveLabel),
    payload: update.payload,
  }
  instrument.label = instrumentLabel(instrument)
  return { ...instruments, [update.instrument]: instrument }
}

// --- Quote math -----------------------------------------------------------

function asNumber(value: unknown): number | undefined {
  return typeof value === 'number' && Number.isFinite(value) ? value : undefined
}

export interface QuoteNumbers {
  bid?: number
  ask?: number
}

/** Reads the quote numbers from any update carrying a payload — the
 * streamed MarketUpdate and the snapshot's LiveView both qualify. */
export function quoteNumbers(
  update: { payload: Record<string, unknown> } | undefined,
): QuoteNumbers {
  if (!update) return {}
  return { bid: asNumber(update.payload.bid), ask: asNumber(update.payload.ask) }
}

/** Midpoint, or the one-sided number when only one side exists. */
export function midOf(quote: QuoteNumbers): number | undefined {
  if (quote.bid !== undefined && quote.ask !== undefined) return (quote.bid + quote.ask) / 2
  return quote.bid ?? quote.ask
}

/** Spread in basis points of the mid; undefined without both sides. */
export function spreadBps(quote: QuoteNumbers): number | undefined {
  const mid = midOf(quote)
  if (quote.bid === undefined || quote.ask === undefined || mid === undefined || mid <= 0) {
    return undefined
  }
  return ((quote.ask - quote.bid) / mid) * 10_000
}

export function ageText(ageMs: number): string {
  if (ageMs < 1000) return `${ageMs} ms`
  const seconds = Math.round(ageMs / 1000)
  if (seconds < 60) return `${seconds} s`
  return `${Math.floor(seconds / 60)} m ${seconds % 60} s`
}

/** The candle-close series the detail chart draws (newest last). */
export function candleCloses(updates: readonly MarketUpdate[]): number[] {
  const closes: number[] = []
  for (const update of updates) {
    const close = asNumber(update.payload.close)
    if (close !== undefined) closes.push(close)
  }
  return closes
}

// --- Connection (WS first, SSE fallback) ----------------------------------

export type LiveConnectionStatus = 'connecting' | 'live' | 'fallback' | 'down'

export interface LiveHandlers {
  onUpdate(update: MarketUpdate): void
  onStatus(status: LiveConnectionStatus): void
}

export interface LiveTransportEnv {
  WebSocketImpl?: typeof WebSocket
  EventSourceImpl?: typeof EventSource
  wsUrl?: string
  sseUrl?: string
}

export interface LiveConnection {
  close(): void
}

const RETRY_DELAY_MS = 2_000

/** The fallback ladder: WebSocket first, SSE (EventSource) when the
 * socket fails, then a 2 s backoff retry of the whole chain. SSE
 * framing (``data: {json}`` lines) is parsed defensively; heartbeat
 * comments and retry lines are skipped. Injectable transports keep the
 * ladder drillable in unit tests (jsdom has neither WebSocket nor
 * EventSource). */
export function openLiveConnection(
  handlers: LiveHandlers,
  env: LiveTransportEnv = {},
): LiveConnection {
  let closed = false
  let current: { close(): void } | null = null
  let timer: ReturnType<typeof setTimeout> | null = null

  const report = (status: LiveConnectionStatus) => {
    if (!closed) handlers.onStatus(status)
  }

  const teardown = () => {
    current?.close()
    current = null
  }

  const openEventSource = () => {
    const EventSourceImpl = env.EventSourceImpl ?? EventSource
    const url = env.sseUrl ?? '/api/live/stream'
    report('fallback')
    const source = new EventSourceImpl(url)
    current = { close: () => source.close() }
    source.onmessage = (event: MessageEvent) => {
      try {
        handlers.onUpdate(JSON.parse(String(event.data)) as MarketUpdate)
      } catch {
        // Malformed frame — the server stream is broken; the retry
        // ladder re-arms on the next error.
      }
    }
    source.onerror = () => {
      if (closed) return
      source.close()
      current = null
      report('down')
      timer = setTimeout(openWebSocket, RETRY_DELAY_MS)
    }
  }

  const openWebSocket = () => {
    const WebSocketImpl = env.WebSocketImpl ?? WebSocket
    const url = env.wsUrl ?? `ws${location.protocol === 'https:' ? 's' : ''}://${location.host}/api/live/ws`
    report('connecting')
    const socket = new WebSocketImpl(url)
    current = { close: () => socket.close() }
    socket.onopen = () => report('live')
    socket.onmessage = (event: MessageEvent) => {
      try {
        handlers.onUpdate(JSON.parse(String(event.data)) as MarketUpdate)
      } catch {
        // Malformed frame; keep the socket — the next frame may be fine.
      }
    }
    socket.onerror = () => {
      if (closed) return
      socket.close()
      current = null
      openEventSource()
    }
  }

  openWebSocket()
  return {
    close() {
      closed = true
      if (timer !== null) clearTimeout(timer)
      teardown()
    },
  }
}

/** React binding: one connection per mount, status surfaced for the
 * screen's banner. onUpdate is kept in a ref so a re-render cannot
 * re-arm the connection. */
export function useLiveConnection(onUpdate: (update: MarketUpdate) => void) {
  const callbackRef = useRef(onUpdate)
  callbackRef.current = onUpdate
  const [status, setStatus] = useState<LiveConnectionStatus>('connecting')
  useEffect(() => {
    const connection = openLiveConnection({
      onUpdate: (update) => callbackRef.current(update),
      onStatus: setStatus,
    })
    return () => connection.close()
  }, [])
  return status
}
