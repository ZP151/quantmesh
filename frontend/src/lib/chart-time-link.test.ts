import { describe, expect, it, vi } from 'vitest'
import { createChartTimeLink, type LinkedChartPort } from './chart-time-link'

const t = (day: number) => Date.parse(`2026-11-${day}T05:00:00Z`) / 1000
const week = { timestamp: '2026-11-23T05:00:00Z', sourceTimestamps: [23, 24, 25, 27].map((d) => `2026-11-${d}T05:00:00Z`) }
const port = (): LinkedChartPort => ({ setRange: vi.fn(), setCrosshair: vi.fn() })

describe('time-linked day/week views', () => {
  it('maps daily hover to its actual weekly anchor, never a bar index', () => {
    const link = createChartTimeLink([week])
    const daily = link.binding('daily'), weekly = port()
    daily.mount(port()); link.binding('weekly').mount(weekly)
    daily.leadHover(); daily.hoverChanged(t(27))
    expect(weekly.setCrosshair).toHaveBeenLastCalledWith(t(23))
    daily.hoverChanged(t(26))
    expect(weekly.setCrosshair).toHaveBeenLastCalledWith(null)
  })
  it('maps weekly hover back to the first actual daily session and clears both ways', () => {
    const link = createChartTimeLink([week]), daily = port(), weekly = link.binding('weekly')
    link.binding('daily').mount(daily); weekly.mount(port())
    weekly.leadHover(); weekly.hoverChanged(t(23))
    expect(daily.setCrosshair).toHaveBeenLastCalledWith(t(23))
    weekly.hoverChanged(null)
    expect(daily.setCrosshair).toHaveBeenLastCalledWith(null)
  })
  it('forwards absolute visible times and ignores synchronous and delayed echoes', () => {
    const link = createChartTimeLink([week]), daily = link.binding('daily'), weekly = link.binding('weekly')
    const a = port(), b = port()
    daily.mount(a); weekly.mount(b)
    b.setRange = vi.fn((range) => weekly.rangeChanged(range))
    daily.leadRange(); daily.rangeChanged({ from: t(23), to: t(27) })
    expect(b.setRange).toHaveBeenCalledExactlyOnceWith({ from: t(23), to: t(27) })
    weekly.rangeChanged({ from: t(23), to: t(27) })
    expect(a.setRange).not.toHaveBeenCalled()
    weekly.leadRange(); weekly.rangeChanged({ from: t(24), to: t(27) })
    expect(a.setRange).toHaveBeenCalledExactlyOnceWith({ from: t(24), to: t(27) })
  })
  it('does not move the peer crosshair in response to programmatic hover', () => {
    const link = createChartTimeLink([week]), daily = link.binding('daily'), weekly = link.binding('weekly'), a = port(), b = port()
    daily.mount(a); weekly.mount(b)
    b.setCrosshair = vi.fn((time) => weekly.hoverChanged(time))
    daily.leadHover(); daily.hoverChanged(t(25))
    expect(b.setCrosshair).toHaveBeenCalledExactlyOnceWith(t(23))
    expect(a.setCrosshair).not.toHaveBeenCalled()
  })
  it('applies a lookback by time to both views and remembers it for remount', () => {
    const link = createChartTimeLink([week]), a = port(), b = port()
    link.binding('daily').mount(a)
    const range = { from: t(23), to: t(27) }
    link.setRange(range); link.binding('weekly').mount(b)
    expect(a.setRange).toHaveBeenLastCalledWith(range)
    expect(b.setRange).toHaveBeenLastCalledWith(range)
  })
  it('makes stale cleanup and callbacks harmless after a view is replaced', () => {
    const link = createChartTimeLink([week]), old = link.binding('daily'), fresh = link.binding('daily'), a = port(), b = port(), w = port()
    const cleanup = old.mount(a)
    fresh.mount(b); link.binding('weekly').mount(w); cleanup()
    link.setRange({ from: t(23), to: t(27) })
    expect(b.setRange).toHaveBeenCalledOnce()
    old.leadRange(); old.rangeChanged({ from: 1, to: 2 })
    expect(w.setRange).toHaveBeenCalledTimes(1)
  })
})
