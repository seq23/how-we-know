import rawQuestions from '../../content/questions.json'
import type { QuestionPageRecord } from './types'
export const questions = rawQuestions as QuestionPageRecord[]
export function getQuestionBySlug(slug: string) { return questions.find((item) => item.slug === slug) }
