import rawQuestions from '../../content/questions.json'
import rawCreatures from '../../content/creatures.json'
import { consolidateQuestions } from './search-rescue.mjs'
import type { QuestionPageRecord } from './types'
export const questions = consolidateQuestions(rawQuestions as QuestionPageRecord[], rawCreatures)
export function getQuestionBySlug(slug: string) { return questions.find((item) => item.slug === slug) }
