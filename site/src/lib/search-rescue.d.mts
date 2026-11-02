import type { QuestionPageRecord, CreatureRecord } from './types'
export const redirects: Record<string, string>
export function routeKey(path: string): string
export function isKept(path: string): boolean
export function canonicalPath(path: string): string
export function keptQuestions<T extends {slug: string}>(records: T[]): T[]
export function keptCreatures<T extends {slug: string}>(records: T[]): T[]
export function consolidateQuestions(records: QuestionPageRecord[], creatures: CreatureRecord[]): QuestionPageRecord[]
