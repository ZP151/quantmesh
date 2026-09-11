import type {
  IPrimitivePaneRenderer,
  IPrimitivePaneView,
  ISeriesPrimitive,
  SeriesAttachedParameter,
  UTCTimestamp,
} from 'lightweight-charts'

interface BandPoint {
  time: UTCTimestamp
  low: number
  high: number
}

interface BandStyle {
  fill: string
  boundary: string
  boundaryLabel: string
}

/** Owned chart primitive; the existing quantile series supply time and autoscale bounds. */
export class ForecastBand implements ISeriesPrimitive {
  private attachment: SeriesAttachedParameter | null = null
  private points: readonly BandPoint[] = []
  private observedEnd: UTCTimestamp | null = null
  private readonly style: BandStyle
  private readonly views: readonly IPrimitivePaneView[]

  constructor(style: BandStyle) {
    this.style = style
    const renderer: IPrimitivePaneRenderer = { draw: (target) => this.draw(target) }
    this.views = [{ zOrder: () => 'bottom', renderer: () => renderer }]
  }

  attached(attachment: SeriesAttachedParameter): void {
    this.attachment = attachment
    attachment.requestUpdate()
  }

  detached(): void {
    this.attachment = null
  }

  setData(points: readonly BandPoint[], observedEnd: UTCTimestamp | null): void {
    this.points = points
    this.observedEnd = observedEnd
    this.attachment?.requestUpdate()
  }

  paneViews(): readonly IPrimitivePaneView[] {
    return this.views
  }

  private draw(target: Parameters<IPrimitivePaneRenderer['draw']>[0]): void {
    const attachment = this.attachment
    if (attachment === null || this.points.length === 0) return
    const timeScale = attachment.chart.timeScale()
    // Resolve on every library redraw, including pan, zoom, autoscale and resize.
    // Media coordinates let FancyCanvas apply the current device pixel ratio.
    const coordinates = this.points.map((point) => {
      const x = timeScale.timeToCoordinate(point.time)
      const low = attachment.series.priceToCoordinate(point.low)
      const high = attachment.series.priceToCoordinate(point.high)
      return x === null || low === null || high === null
        || !Number.isFinite(x) || !Number.isFinite(low) || !Number.isFinite(high)
        || point.low > point.high ? null : { x, low, high }
    })
    const firstTime = this.points[0].time
    const observedX = this.observedEnd !== null && this.observedEnd < firstTime
      ? timeScale.timeToCoordinate(this.observedEnd) : null
    const forecastX = timeScale.timeToCoordinate(firstTime)

    target.useMediaCoordinateSpace(({ context, mediaSize }) => {
      context.save()
      // Missing coordinates split the polygon instead of bridging unavailable data.
      let segment: Array<{ x: number; low: number; high: number }> = []
      const fillSegment = () => {
        if (segment.length > 1) {
          context.beginPath()
          context.moveTo(segment[0].x, segment[0].high)
          for (const point of segment.slice(1)) context.lineTo(point.x, point.high)
          for (const point of [...segment].reverse()) context.lineTo(point.x, point.low)
          context.closePath()
          context.fillStyle = this.style.fill
          context.fill()
        }
        segment = []
      }
      for (const point of coordinates) {
        if (point === null) fillSegment()
        else segment.push(point)
      }
      fillSegment()

      if (observedX !== null && forecastX !== null) {
        const boundaryX = (observedX + forecastX) / 2
        if (Number.isFinite(boundaryX) && boundaryX >= 0 && boundaryX <= mediaSize.width) {
          context.strokeStyle = this.style.boundary
          context.lineWidth = 1
          context.setLineDash([5, 4])
          context.beginPath()
          context.moveTo(boundaryX, 0)
          context.lineTo(boundaryX, mediaSize.height)
          context.stroke()
          context.fillStyle = this.style.boundary
          context.font = '11px "Geist Variable", sans-serif'
          const labelWidth = context.measureText(this.style.boundaryLabel).width
          const labelX = Math.max(4, Math.min(boundaryX + 6, mediaSize.width - labelWidth - 4))
          context.fillText(this.style.boundaryLabel, labelX, 18)
        }
      }
      context.restore()
    })
  }
}
