import { questions } from './questions-data'
import { methods, subjects, type MethodId, type SubjectId } from './taxonomy'

/**
 * Only vocabulary entries that a published page actually carries are exposed to
 * navigation. An unused method or subject is not a shelf waiting to be filled —
 * it simply does not appear until content exists for it.
 */
export const activeMethods = methods
  .map((definition) => ({
    ...definition,
    pages: questions.filter((item) => item.method === definition.id),
  }))
  .filter((entry) => entry.pages.length > 0)

export const activeSubjects = subjects
  .map((definition) => ({
    ...definition,
    pages: questions.filter((item) => item.subject === definition.id),
  }))
  .filter((entry) => entry.pages.length > 0)

export function getMethodEntry(id: string) {
  return activeMethods.find((entry) => entry.id === (id as MethodId))
}

export function getSubjectEntry(id: string) {
  return activeSubjects.find((entry) => entry.id === (id as SubjectId))
}
