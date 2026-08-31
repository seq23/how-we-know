import rawZones from '../../content/zones.json'
import type { OceanZoneRecord } from './types'
export const oceanZones = rawZones as OceanZoneRecord[]
export function getZoneBySlug(slug: string) { return oceanZones.find((item) => item.slug === slug) }
export function formatDepth(min: number, max: number) { return `${min.toLocaleString()}–${max.toLocaleString()} m` }
