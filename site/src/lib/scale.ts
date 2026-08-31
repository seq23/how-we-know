/**
 * A generic magnitude axis.
 *
 * The depth explorer is not really about metres — it is about placing landmarks,
 * bands and markers on one continuous run of a quantity so a reader can feel the
 * size of it. Light-years, years before present, degrees, pascals and metres are
 * all the same problem.
 *
 * Everything here is unit-agnostic. A subject supplies the unit, the range, its
 * bands and its landmarks; nothing in this file knows about the ocean.
 */

export type ScaleBand = {
  id: string
  name: string
  /** Inclusive lower bound, in the axis unit. */
  from: number
  /** Exclusive upper bound, except for the final band. */
  to: number
  /** Optional link target for the band label. */
  href?: string
  /** Optional supporting line under the band label. */
  detail?: string
}

export type ScaleLandmark = { at: number; label: string; detail: string }

export type ScaleMarker = {
  id: string
  name: string
  at: number
  detail?: string
  href?: string
}

export type ScaleAxis = {
  /** Machine id, e.g. 'ocean-depth', 'cosmic-distance', 'geological-time'. */
  id: string
  /** Unit symbol shown after a value, e.g. 'm', 'ly', 'Ma'. */
  unit: string
  /** What the axis measures, for labels and aria text, e.g. 'Depth'. */
  quantity: string
  from: number
  to: number
  /**
   * Pixels rendered per one unit of the quantity. Depth uses 1, so one scroll
   * pixel is one metre; an axis spanning billions of years will use a far
   * smaller value. Only this number needs to change for a new unit.
   */
  pixelsPerUnit: number
  /** Larger values are rendered further down the track. Set false for axes that run upward. */
  descending: boolean
  bands: ScaleBand[]
  landmarks: ScaleLandmark[]
  /** Optional override; defaults to a grouped integer plus the unit symbol. */
  format?: (value: number) => string
}

export function clampToAxis(axis: ScaleAxis, value: number) {
  return Math.min(axis.to, Math.max(axis.from, value))
}

export function formatScaleValue(axis: ScaleAxis, value: number) {
  if (axis.format) return axis.format(value)
  return `${Math.round(value).toLocaleString()} ${axis.unit}`
}

/** Offset in pixels from the start of the track for a given value. */
export function offsetFor(axis: ScaleAxis, value: number) {
  return (clampToAxis(axis, value) - axis.from) * axis.pixelsPerUnit
}

/** Total rendered length of the track in pixels. */
export function axisLength(axis: ScaleAxis) {
  return (axis.to - axis.from) * axis.pixelsPerUnit
}

export function bandAt(axis: ScaleAxis, value: number) {
  const target = clampToAxis(axis, value)
  return (
    axis.bands.find(
      (band, index) => target >= band.from && (target < band.to || index === axis.bands.length - 1),
    ) ?? axis.bands.at(-1)
  )
}

/**
 * Linear interpolation over a table of (value, reading) points. Used for any
 * derived readout that varies along the axis — ocean temperature today, lookback
 * time or decay fraction later.
 */
export function interpolate(points: readonly (readonly [number, number])[], value: number) {
  if (points.length === 0) throw new Error('interpolate() called with no points')
  const first = points[0]
  const last = points[points.length - 1]
  const target = Math.min(last[0], Math.max(first[0], value))
  for (let index = 1; index < points.length; index += 1) {
    const [nextAt, nextReading] = points[index]
    const [prevAt, prevReading] = points[index - 1]
    if (target <= nextAt) {
      const span = nextAt - prevAt
      const progress = span === 0 ? 0 : (target - prevAt) / span
      return prevReading + (nextReading - prevReading) * progress
    }
  }
  return last[1]
}
