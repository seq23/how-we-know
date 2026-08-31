import { creatures } from './creatures-data'
import { oceanZones } from './ocean-data'
import {
  axisLength,
  bandAt,
  clampToAxis,
  formatScaleValue,
  interpolate,
  offsetFor,
  type ScaleAxis,
} from './scale'

export const CHALLENGER_DEEP_M = 10_935

/**
 * Ocean depth expressed as one instance of the generic magnitude axis in
 * ./scale. Nothing in the axis is ocean-specific except the values supplied
 * here, so a second subject supplies its own axis — light-years, years before
 * present — and reuses the same geometry, formatting and lookup helpers.
 */
export const oceanDepthAxis: ScaleAxis = {
  id: 'ocean-depth',
  unit: 'm',
  quantity: 'Depth',
  from: 0,
  to: CHALLENGER_DEEP_M,
  pixelsPerUnit: 1,
  descending: true,
  bands: oceanZones.map((zone) => ({
    id: zone.slug,
    name: zone.name,
    from: zone.minDepthM,
    to: zone.maxDepthM,
    href: `/zones/${zone.slug}`,
    detail: zone.summary,
  })),
  landmarks: [
    { at: 0, label: 'Sea surface', detail: 'Sunlight, waves, and one atmosphere of pressure' },
    { at: 200, label: 'Last strong sunlight', detail: 'Publishing boundary between sunlight and twilight zones' },
    { at: 1_000, label: 'Midnight begins', detail: 'Sunlight no longer supports vision or photosynthesis' },
    { at: 4_000, label: 'Abyssal zone', detail: 'Broad deep seafloor and near-freezing water' },
    { at: 6_000, label: 'Hadal zone', detail: 'Ocean trenches begin' },
    { at: 8_336, label: 'Deepest confirmed fish sighting', detail: 'A snailfish filmed in the Izu-Ogasawara Trench' },
    { at: CHALLENGER_DEEP_M, label: 'Challenger Deep', detail: 'Deepest known part of the ocean' },
  ],
}

/** Retained for the existing depth-explorer call sites. */
export const explorerLandmarks = oceanDepthAxis.landmarks.map((item) => ({
  depthM: item.at,
  label: item.label,
  detail: item.detail,
}))

export const explorerCreatures = creatures.map((creature, index) => ({
  ...creature,
  markerDepthM: Math.min(CHALLENGER_DEEP_M, Math.round((creature.minDepthM + creature.maxDepthM) / 2)),
  side: index % 2 === 0 ? 'left' : 'right',
}))

export const explorerAxisLength = axisLength(oceanDepthAxis)
export const explorerOffsetFor = (depthM: number) => offsetFor(oceanDepthAxis, depthM)

export function getZoneAtDepth(depthM: number) {
  const band = bandAt(oceanDepthAxis, depthM)
  return oceanZones.find((zone) => zone.slug === band?.id) ?? oceanZones.at(-1)!
}

export function estimatePressureAtm(depthM: number) {
  return 1 + Math.max(0, depthM) / 10
}

const OCEAN_TEMPERATURE_POINTS = [
  [0, 20],
  [200, 5],
  [1_000, 4],
  [4_000, 2],
  [6_000, 1.5],
  [CHALLENGER_DEEP_M, 1],
] as const

export function estimateTemperatureC(depthM: number) {
  return interpolate(OCEAN_TEMPERATURE_POINTS, clampToAxis(oceanDepthAxis, depthM))
}

export function formatExplorerDepth(depthM: number) {
  return formatScaleValue(oceanDepthAxis, depthM)
}
