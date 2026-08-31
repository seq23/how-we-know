/**
 * Guards the two expansion seams: every question page must carry a `subject`
 * and a `method`, both drawn from the controlled vocabulary in src/lib/taxonomy.ts.
 *
 * This is the check that makes a second subject cheap. Without it, a page added
 * later can silently omit the fields and the cross-subject method index quietly
 * loses it.
 */
import fs from 'node:fs'
import { assert, readJson } from './validation-helpers.mjs'

const questions = readJson('content/questions.json')
const taxonomySource = fs.readFileSync('src/lib/taxonomy.ts', 'utf8')

function vocabulary(typeName) {
  const block = taxonomySource.match(new RegExp(`export type ${typeName}\\s*=([\\s\\S]*?)\\n\\n`, 'u'))
  assert(block, `taxonomy.ts is missing the ${typeName} union`)
  const ids = [...block[1].matchAll(/'([a-z-]+)'/gu)].map((match) => match[1])
  assert(ids.length > 0, `${typeName} union parsed to zero ids`)
  return new Set(ids)
}

const subjectIds = vocabulary('SubjectId')
const methodIds = vocabulary('MethodId')

// Every declared id must also have a definition object, or navigation renders a blank label.
for (const id of subjectIds) {
  assert(taxonomySource.includes(`id: '${id}'`), `Subject ${id} is declared but has no definition`)
}
for (const id of methodIds) {
  assert(taxonomySource.includes(`id: '${id}'`), `Method ${id} is declared but has no definition`)
}

// Rule 0: never pass on an empty loop.
assert(questions.length > 0, 'Taxonomy validation examined zero question records')

let checked = 0
for (const question of questions) {
  assert(typeof question.subject === 'string' && question.subject, `${question.slug} is missing a subject`)
  assert(typeof question.method === 'string' && question.method, `${question.slug} is missing a method`)
  assert(subjectIds.has(question.subject), `${question.slug} has unknown subject "${question.subject}"`)
  assert(methodIds.has(question.method), `${question.slug} has unknown method "${question.method}"`)
  checked += 1
}
assert(checked === questions.length, 'Taxonomy validation skipped a question record')

// The method axis only earns its place if it actually crosses pages.
const usedMethods = new Set(questions.map((item) => item.method))
assert(usedMethods.size >= 2, 'Method axis is degenerate: every page shares one method')

// A subject may only appear in navigation if a page carries it; a method likewise.
const usedSubjects = new Set(questions.map((item) => item.subject))
assert(usedSubjects.size >= 1, 'No subject is in use')

console.log(
  `Taxonomy validation passed (${checked} pages, ${usedSubjects.size} subjects in use, ${usedMethods.size} methods in use).`,
)
