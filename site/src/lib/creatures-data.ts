import rawCreatures from '../../content/creatures.json'
import type { CreatureRecord } from './types'
export const creatures = rawCreatures as CreatureRecord[]
export function getCreatureBySlug(slug: string) { return creatures.find((item) => item.slug === slug) }
