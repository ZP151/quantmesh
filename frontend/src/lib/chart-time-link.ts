export interface ChartTimeRange { from: number; to: number }
export interface LinkedChartPort { setRange: (range: ChartTimeRange) => void; setCrosshair: (time: number | null) => void }
export interface ChartInteraction {
  mount: (port: LinkedChartPort) => () => void
  leadRange: () => void
  leadHover: () => void
  rangeChanged: (range: ChartTimeRange | null) => void
  hoverChanged: (time: number | null) => void
}
export type LinkedChartId = 'daily' | 'weekly'

export function createChartTimeLink(weeks: readonly { timestamp: string; sourceTimestamps: readonly string[] }[]): { binding: (id: LinkedChartId) => ChartInteraction; setRange: (range: ChartTimeRange) => void } {
  const dayToWeek = new Map<number, number>()
  const weekToDay = new Map<number, number>()
  for (const week of weeks) {
    const anchor = Date.parse(week.timestamp) / 1000
    for (const timestamp of week.sourceTimestamps) dayToWeek.set(Date.parse(timestamp) / 1000, anchor)
    weekToDay.set(anchor, Date.parse(week.sourceTimestamps[0]) / 1000)
  }
  const ports = new Map<LinkedChartId, { token: symbol; port: LinkedChartPort }>()
  let rangeLeader: symbol | null = null
  let hoverLeader: symbol | null = null
  let lastRange: ChartTimeRange | null = null
  const validRange = (range: ChartTimeRange | null): range is ChartTimeRange => range !== null && Number.isFinite(range.from) && Number.isFinite(range.to) && range.from < range.to
  return {
    binding(id) {
      const token = Symbol(id)
      const active = () => ports.get(id)?.token === token
      return {
        mount(port) {
          ports.set(id, { token, port })
          if (lastRange) port.setRange(lastRange)
          return () => {
            if (!active()) return
            ports.delete(id)
            if (rangeLeader === token) rangeLeader = null
            if (hoverLeader === token) {
              hoverLeader = null
              for (const peer of ports.values()) peer.port.setCrosshair(null)
            }
          }
        },
        leadRange() { if (active()) rangeLeader = token },
        leadHover() { if (active()) hoverLeader = token },
        rangeChanged(range) {
          if (!active() || rangeLeader !== token || !validRange(range)) return
          lastRange = { ...range }
          for (const [peerId, peer] of ports) if (peerId !== id) peer.port.setRange(lastRange)
        },
        hoverChanged(time) {
          if (!active() || hoverLeader !== token) return
          const mapped = time === null ? null : (id === 'daily' ? dayToWeek : weekToDay).get(time) ?? null
          for (const [peerId, peer] of ports) if (peerId !== id) peer.port.setCrosshair(mapped)
        },
      }
    },
    setRange(range) {
      if (!validRange(range)) return
      rangeLeader = null
      lastRange = { ...range }
      for (const peer of ports.values()) peer.port.setRange(lastRange)
    },
  }
}
