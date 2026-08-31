import rawSources from '../../content/sources.json'
import type { SourceReference } from './types'
export const sources = rawSources as SourceReference[]
export const sourceById = new Map(sources.map((source) => [source.id, source]))
export function getSources(ids: string[]) {
  return ids.map((id) => sourceById.get(id)).filter((source): source is SourceReference => Boolean(source))
}
