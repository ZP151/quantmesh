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
  LiveInstrumentKey,
  LiveKind,
  LiveLabel,
  LiveView,
  MarketUpdate,
} from '@/lib/api'
import type { MessageKey } from '@/lib/messages'

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

function updateIdentity(update: MarketUpdate): string {
  const providerIdentity = update.source_event_id
    ?? `${update.received_at}:${update.sequence ?? ''}`
  return `${update.venue}:${update.instrument}:${update.kind}:${providerIdentity}`
}

function updateInstant(update: MarketUpdate): number {
  const received = Date.parse(update.received_at)
  if (Number.isFinite(received)) return received
  const event = Date.parse(update.data_time)
  return Number.isFinite(event) ? event : 0
}

export function reconcileUpdates(
  previous: readonly MarketUpdate[],
  incoming: readonly MarketUpdate[],
): MarketUpdate[] {
  const byIdentity = new Map(previous.map((update) => [updateIdentity(update), update]))
  for (const update of incoming) {
    if (!byIdentity.has(updateIdentity(update))) {
      byIdentity.set(updateIdentity(update), update)
    }
  }
  return [...byIdentity.values()].sort((left, right) => {
    const timeOrder = updateInstant(left) - updateInstant(right)
    return timeOrder || updateIdentity(left).localeCompare(updateIdentity(right))
  })
}

export function latestCompleteBookSides(updates: readonly MarketUpdate[]): {
  bid?: MarketUpdate
  ask?: MarketUpdate
} {
  const epochs = new Map<string, { bid?: MarketUpdate; ask?: MarketUpdate }>()
  for (const update of updates) {
    if (update.kind !== 'l2_snapshot' || !update.snapshot_epoch) continue
    const sides = epochs.get(update.snapshot_epoch) ?? {}
    if (update.payload.side === 'bid') sides.bid = update
    else if (update.payload.side === 'ask') sides.ask = update
    epochs.set(update.snapshot_epoch, sides)
  }
  let selected: { bid?: MarketUpdate; ask?: MarketUpdate } = {}
  let selectedAt = Number.NEGATIVE_INFINITY
  for (const sides of epochs.values()) {
    if (!sides.bid || !sides.ask) continue
    const epochAt = Math.max(updateInstant(sides.bid), updateInstant(sides.ask))
    if (epochAt > selectedAt) {
      selected = sides
      selectedAt = epochAt
    }
  }
  return selected
}

function liveViewInstant(view: LiveView): number {
  const received = Date.parse(view.received_at)
  if (Number.isFinite(received)) return received
  const event = Date.parse(view.data_time)
  return Number.isFinite(event) ? event : 0
}

function newestView(current: LiveView | undefined, candidate: LiveView): LiveView {
  if (!current) return candidate
  if (candidate.source_event_id
    && current.source_event_id === candidate.source_event_id) return candidate
  return liveViewInstant(candidate) >= liveViewInstant(current) ? candidate : current
}

export function reconcileInstrumentState(
  previous: LiveInstrumentState | undefined,
  incoming: LiveInstrumentState,
): LiveInstrumentState {
  if (!previous
    || previous.venue !== incoming.venue
    || previous.instrument !== incoming.instrument) {
    return incoming
  }
  const kinds = { ...previous.kinds }
  for (const [kind, candidate] of Object.entries(incoming.kinds)) {
    kinds[kind] = newestView(kinds[kind], candidate)
  }
  const book_sides = { ...(previous.book_sides ?? {}) }
  for (const [side, candidate] of Object.entries(incoming.book_sides ?? {})) {
    if (side === 'bid' || side === 'ask') {
      book_sides[side] = newestView(book_sides[side], candidate)
    }
  }
  const reconciled: LiveInstrumentState = {
    venue: incoming.venue,
    instrument: incoming.instrument,
    label: incoming.label,
    kinds,
    book_sides,
  }
  reconciled.label = instrumentLabel(reconciled)
  return reconciled
}

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

/** Instrument badge text keys — screens render t(LABEL_TEXT[label]); the
 * label identity itself (LiveLabel) stays raw on the wire and in state. */
export const LABEL_TEXT: Record<LiveLabel, MessageKey> = {
  real: 'live.label.real',
  delayed: 'live.label.delayed',
  stale: 'live.label.stale',
  synthetic: 'live.label.synthetic',
  unavailable: 'live.label.unavailable',
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

const LIVE_ID_SEPARATOR = ':'

/** Canonical venue-scoped identity shared by the API snapshot and streamed
 * updates. This prevents same-symbol instruments from different venues from
 * overwriting each other in client state. */
export function liveInstrumentKey(venue: string, instrument: string): LiveInstrumentKey {
  return `${venue}${LIVE_ID_SEPARATOR}${instrument}`
}

export function liveInstrumentSymbol(key: string): string {
  const separator = key.indexOf(LIVE_ID_SEPARATOR)
  return separator === -1 ? key : key.slice(separator + LIVE_ID_SEPARATOR.length)
}

/** Validate the venue:instrument keyed wire snapshot at the frontend
 * boundary. The wire key and both value identity fields must agree;
 * contradictory or malformed rows are omitted rather than rewritten. */
export function normalizeLiveInstruments(
  instruments: Record<string, unknown>,
): Record<string, LiveInstrumentState> {
  const normalized: Record<string, LiveInstrumentState> = {}
  for (const [wireKey, state] of Object.entries(instruments)) {
    const separator = wireKey.indexOf(LIVE_ID_SEPARATOR)
    if (separator <= 0 || separator !== wireKey.lastIndexOf(LIVE_ID_SEPARATOR)) continue
    const venue = wireKey.slice(0, separator)
    const instrument = wireKey.slice(separator + LIVE_ID_SEPARATOR.length)
    if (!isLiveInstrumentState(state)) continue
    if (!instrument || state.venue !== venue || state.instrument !== instrument) continue
    normalized[wireKey] = state
  }
  return normalized
}

function isLiveInstrumentState(value: unknown): value is LiveInstrumentState {
  if (value === null || typeof value !== 'object' || Array.isArray(value)) return false
  const candidate = value as Partial<LiveInstrumentState>
  return typeof candidate.venue === 'string'
    && typeof candidate.instrument === 'string'
    && typeof candidate.label === 'string'
    && candidate.label in LABEL_RANK
    && candidate.kinds !== null
    && typeof candidate.kinds === 'object'
    && !Array.isArray(candidate.kinds)
}

/** Merge one streamed update into a latest-state map. The update's
 * kind replaces the previous view for venue+instrument+kind; the
 * instrument's badge label is recomputed from its data kinds. */
export function mergeUpdate(
  instruments: Record<string, LiveInstrumentState>,
  update: MarketUpdate,
): Record<string, LiveInstrumentState> {
  const key = liveInstrumentKey(update.venue, update.instrument)
  const previous = instruments[key]
  const view: LiveView = {
    kind: update.kind,
    provenance: update.provenance,
    data_time: update.data_time,
    received_at: update.received_at,
    age_ms: 0,
    sequence: update.sequence,
    sequence_gap: update.sequence_gap,
    continuity: update.continuity ?? (update.sequence_gap ? 'known-gap' : 'complete'),
    source_event_id: update.source_event_id,
    content_digest: update.content_digest,
    snapshot_epoch: update.snapshot_epoch,
    continuity_evidence: update.continuity_evidence,
    label: update.provenance === 'real' ? 'real' : (update.provenance as LiveLabel),
    payload: update.payload,
  }
  const instrument: LiveInstrumentState = {
    venue: update.venue,
    instrument: update.instrument,
    label: view.label,
    kinds: { [update.kind]: view },
    book_sides: {},
  }
  if (update.kind === 'l2_snapshot') {
    const side = update.payload.side
    if (side === 'bid' || side === 'ask') {
      instrument.book_sides![side] = view
    }
  }
  return { ...instruments, [key]: reconcileInstrumentState(previous, instrument) }
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

export function ageText(ageMs: number, locale: 'en' | 'zh-CN' = 'en'): string {
  const units = locale === 'zh-CN'
    ? { millisecond: '毫秒', minute: '分', second: '秒' }
    : { millisecond: 'ms', minute: 'm', second: 's' }
  if (ageMs < 1000) return `${ageMs} ${units.millisecond}`
  const seconds = Math.round(ageMs / 1000)
  if (seconds < 60) return `${seconds} ${units.second}`
  return `${Math.floor(seconds / 60)} ${units.minute} ${seconds % 60} ${units.second}`
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

export interface BookLevel {
  price: number
  size: number
}

/** The per-side order book from an L2 snapshot view. The wire contract
 * (ADR-0014, ``_validate_l2``) emits levels as ``[price, size]`` pairs,
 * strictly monotonic in price — a malformed level is dropped, never
 * rendered. */
export function bookSide(
  view: { payload: Record<string, unknown> } | undefined,
): BookLevel[] {
  const levels = view?.payload.levels
  if (!Array.isArray(levels)) return []
  return levels
    .map((level) => {
      if (!Array.isArray(level) || level.length !== 2) return undefined
      const [price, size] = level
      if (!Number.isFinite(price) || !Number.isFinite(size)) return undefined
      return { price, size }
    })
    .filter((level): level is BookLevel => level !== undefined)
}

// --- Research metrics (iteration 0019, slice 2) ---------------------------
//
// Every helper here is a pure fold of frames the venue already sent —
// nothing is estimated, and an absent input yields undefined so the UI
// renders unavailable rather than a guessed number.

/** Total resting size of one book side (depth from the L2 snapshot). */
export function bookDepth(levels: BookLevel[]): number | undefined {
  if (levels.length === 0) return undefined
  return levels.reduce((total, level) => total + level.size, 0)
}

/** The last-close vs previous-close return of the candle series. */
export function candleReturn(closes: number[]): number | undefined {
  if (closes.length < 2) return undefined
  const previous = closes[closes.length - 2]
  const last = closes[closes.length - 1]
  if (!Number.isFinite(previous) || !Number.isFinite(last) || previous === 0) {
    return undefined
  }
  return (last - previous) / previous
}

/** Realized volatility of the candle series: the standard deviation of
 * the per-candle log returns, presented per candle (the frame carries
 * no interval, so nothing is annualized). */
export function realizedVol(closes: number[]): number | undefined {
  if (closes.length < 2) return undefined
  const returns: number[] = []
  for (let index = 1; index < closes.length; index += 1) {
    const previous = closes[index - 1]
    const current = closes[index]
    if (!Number.isFinite(previous) || !Number.isFinite(current) || previous <= 0) {
      return undefined
    }
    returns.push(Math.log(current / previous))
  }
  if (returns.length === 0) return undefined
  const mean = returns.reduce((sum, value) => sum + value, 0) / returns.length
  const variance =
    returns.reduce((sum, value) => sum + (value - mean) ** 2, 0) / returns.length
  return Math.sqrt(variance)
}

/** Mark–index divergence from the metrics frame, as a fraction of the
 * index price. Only finite venue-provided values qualify. */
export function markIndexDivergence(
  view: { payload: Record<string, unknown> } | undefined,
): number | undefined {
  const mark = asNumber(view?.payload.mark_price)
  const index = asNumber(view?.payload.index_price)
  if (mark === undefined || index === undefined || index === 0) return undefined
  return (mark - index) / index
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
    let advanced = false
    current = { close: () => socket.close() }
    socket.onopen = () => report('live')
    socket.onmessage = (event: MessageEvent) => {
      try {
        handlers.onUpdate(JSON.parse(String(event.data)) as MarketUpdate)
      } catch {
        // Malformed frame; keep the socket — the next frame may be fine.
      }
    }
    const advanceToFallback = () => {
      if (closed || advanced) return
      advanced = true
      socket.close()
      current = null
      openEventSource()
    }
    socket.onerror = advanceToFallback
    socket.onclose = advanceToFallback
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
export function useLiveConnection(onUpdate: (update: MarketUpdate) => void, enabled = true) {
  const callbackRef = useRef(onUpdate)
  callbackRef.current = onUpdate
  const [status, setStatus] = useState<LiveConnectionStatus>(enabled ? 'connecting' : 'down')
  useEffect(() => {
    if (!enabled) {
      setStatus('down')
      return undefined
    }
    const connection = openLiveConnection({
      onUpdate: (update) => callbackRef.current(update),
      onStatus: setStatus,
    })
    return () => connection.close()
  }, [enabled])
  return status
}
