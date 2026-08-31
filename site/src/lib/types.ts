import type { MethodId, SubjectId } from './taxonomy'

export type SourceReference = {
  id: string
  name: string
  organization: string
  url: string
  sourceType: 'government' | 'research-institution' | 'museum-research' | 'peer-reviewed'
  checkedAt: string
  notes: string
}

export type VideoChapter = { time: string; title: string }
export type VideoRecord = {
  status: 'unplanned' | 'planned' | 'in-production' | 'published'
  videoId: string | null
  title: string | null
  descriptionFirstLine: string | null
  thumbnailUrl: string | null
  uploadDate: string | null
  duration: string | null
  transcript: string | null
  chapters: VideoChapter[]
}

export type QuestionSection = { heading: string; paragraphs: string[] }
export type QuestionPageRecord = {
  question: string
  slug: string
  /** How a reader browses. Orthogonal to `method`. */
  subject: SubjectId
  /** How the answer is known. This is the axis that links pages across subjects. */
  method: MethodId
  directAnswer: string
  description: string
  publishedAt: string
  reviewedAt: string
  keyStat: { value: string; label: string; sourceId: string }
  sections: QuestionSection[]
  comparison: { columns: string[]; rows: string[][] }
  faqs: { question: string; answer: string }[]
  sourceIds: string[]
  relatedZones: string[]
  relatedCreatures: string[]
  video: VideoRecord
}

export type OceanZoneRecord = {
  slug: string
  name: string
  scientificName: string
  minDepthM: number
  maxDepthM: number
  light: string
  temperature: string
  pressureAtBaseAtm: number
  summary: string
  conditions: string[]
  sourceIds: string[]
}

export type CreatureRecord = {
  slug: string
  name: string
  scientificName: string
  minDepthM: number
  maxDepthM: number
  zones: string[]
  summary: string
  adaptations: string[]
  sourceIds: string[]
}
