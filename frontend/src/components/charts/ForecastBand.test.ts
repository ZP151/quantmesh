import type { IPrimitivePaneRenderer, SeriesAttachedParameter, UTCTimestamp } from 'lightweight-charts'
import { describe, expect, it, vi } from 'vitest'

import { ForecastBand } from './ForecastBand'

const time = (value: number) => value as UTCTimestamp
const points = [{ time: time(20), low: 90, high: 110 }, { time: time(30), low: 80, high: 120 }]

function setup() {
  const context = {
    beginPath: vi.fn(), closePath: vi.fn(), fill: vi.fn(), fillText: vi.fn(),
    lineTo: vi.fn(), moveTo: vi.fn(), restore: vi.fn(), save: vi.fn(),
    setLineDash: vi.fn(), stroke: vi.fn(), measureText: vi.fn(() => ({ width: 100 })),
  }
  const timeToCoordinate = vi.fn((value: number) => value * 10)
  const priceToCoordinate = vi.fn((value: number) => 500 - value * 2)
  const requestUpdate = vi.fn()
  const attachment = {
    chart: { timeScale: () => ({ timeToCoordinate }) },
    series: { priceToCoordinate }, requestUpdate,
  } as unknown as SeriesAttachedParameter
  const size = { width: 600, height: 400 }
  const target = {
    useMediaCoordinateSpace: (draw: (scope: unknown) => void) => draw({ context, mediaSize: size }),
  } as unknown as Parameters<IPrimitivePaneRenderer['draw']>[0]
  const band = new ForecastBand({ fill: 'green', boundary: 'gray', boundaryLabel: 'Observed | Forecast' })
  band.attached(attachment)
  band.setData(points, time(10))
  const draw = () => band.paneViews()[0].renderer()!.draw(target)
  return { band, context, draw, priceToCoordinate, requestUpdate, size, timeToCoordinate }
}

describe('ForecastBand', () => {
  it('fills the actual P10/P90 polygon below the series and locates the split between actual times', () => {
    const { band, context, draw } = setup()
    draw()
    expect(band.paneViews()[0].zOrder?.()).toBe('bottom')
    expect(context.moveTo.mock.calls).toEqual([[200, 280], [150, 0]])
    expect(context.lineTo.mock.calls).toEqual([[300, 260], [300, 340], [200, 320], [150, 400]])
    expect(context.fill).toHaveBeenCalledOnce()
    expect(context.setLineDash).toHaveBeenCalledWith([5, 4])
    expect(context.fillText).toHaveBeenCalledWith('Observed | Forecast', 156, 18)
  })

  it('remaps time, price and pane height on viewport redraws without retaining stale coordinates', () => {
    const { context, draw, priceToCoordinate, size, timeToCoordinate } = setup()
    draw()
    context.moveTo.mockClear()
    context.lineTo.mockClear()
    timeToCoordinate.mockImplementation((value) => value * 5)
    priceToCoordinate.mockImplementation((value) => 600 - value)
    size.height = 200
    draw()
    expect(context.moveTo.mock.calls).toEqual([[100, 490], [75, 0]])
    expect(context.lineTo).toHaveBeenLastCalledWith(75, 200)
  })

  it('clears forecast graphics and releases chart references when detached', () => {
    const { band, context, draw, requestUpdate, timeToCoordinate } = setup()
    band.setData([], time(10))
    draw()
    expect(context.fill).not.toHaveBeenCalled()
    expect(context.stroke).not.toHaveBeenCalled()
    band.detached()
    const updates = requestUpdate.mock.calls.length
    band.setData(points, time(10))
    draw()
    expect(requestUpdate).toHaveBeenCalledTimes(updates)
    expect(timeToCoordinate).not.toHaveBeenCalled()
  })

  it('does not invent a band across unavailable coordinates or a separator for overlapping history', () => {
    const { band, context, draw, timeToCoordinate } = setup()
    timeToCoordinate.mockReturnValue(null as unknown as number)
    draw()
    expect(context.fill).not.toHaveBeenCalled()
    expect(context.stroke).not.toHaveBeenCalled()
    timeToCoordinate.mockImplementation((value) => value * 10)
    band.setData(points, time(25))
    draw()
    expect(context.stroke).not.toHaveBeenCalled()
  })
})
