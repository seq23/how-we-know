/**
 * Every indexable route has a title and a description that fit a search result.
 *
 * Measured on the live site on 2026-10-25: 15 of 54 pages carried a title outside
 * 30–65 characters — the homepage's was "How We Know", 11 characters — and 50 of
 * 54 carried a description outside 120–160. Nothing in the build had an opinion
 * about either, so the lengths drifted with whatever the page's visible summary
 * happened to say.
 *
 * This reads src/lib/seo-copy.ts as data and checks the composed value for every
 * route in the approved universe. scripts/validate-built-html.mjs then checks the
 * same thing in the emitted HTML, which is what a crawler reads; this one fails
 * first and says which entry to fix.
 *
 * Rule 0: a run that examined zero routes fails.
 */
import fs from 'node:fs'
import { assert, readJson } from './validation-helpers.mjs'

const TITLE_MIN = 30
const TITLE_MAX = 65
const DESCRIPTION_MIN = 120
const DESCRIPTION_MAX = 160
const SUFFIX = ' | How We Know'

const questions = readJson('content/questions.json')
const zones = readJson('content/zones.json')
const creatures = readJson('content/creatures.json')
const activeMethodIds = [...new Set(questions.map((item) => item.method))]

/** The indexable universe: exactly the routes in the sitemap. /404 and /admin are noindex. */
const routes = [
  '/',
  '/questions',
  '/zones',
  '/creatures',
  '/watch',
  '/explore',
  '/methods',
  ...activeMethodIds.map((id) => `/methods/${id}`),
  '/methodology',
  '/editorial-policy',
  '/about',
  '/privacy',
  '/terms',
  ...questions.map((item) => `/questions/${item.slug}`),
  ...zones.map((item) => `/zones/${item.slug}`),
  ...creatures.map((item) => `/creatures/${item.slug}`),
]
assert(routes.length > 0, 'SEO copy validation resolved zero routes')

// seo-copy.ts is a plain table of string literals, read here without a TypeScript
// toolchain so this validator stays in the dependency-free set like its siblings.
const source = fs.readFileSync('src/lib/seo-copy.ts', 'utf8')
const table = source.slice(source.indexOf('export const seoCopy'))
const unquote = (value) => value.replace(/\\(['\\])/gu, '$1')
const entries = new Map()
for (const block of table.matchAll(/'(\/[^']*)':\s*\{([\s\S]*?)\n {2}\},/gu)) {
  const [, path, body] = block
  const title = /title:\s*'((?:[^'\\]|\\.)*)'/u.exec(body)
  const description = /description:\s*\n?\s*'((?:[^'\\]|\\.)*)'/u.exec(body)
  entries.set(path, {
    title: title ? unquote(title[1]) : null,
    description: description ? unquote(description[1]) : null,
  })
}
assert(entries.size > 0, 'SEO copy validation parsed zero entries from src/lib/seo-copy.ts')

/** A question page with no title override ships the question itself, which is the query. */
const fallbackTitle = new Map(questions.map((item) => [`/questions/${item.slug}`, item.question]))

const titles = new Map()
const descriptions = new Map()
const failures = []

for (const route of routes) {
  const entry = entries.get(route)
  if (!entry) {
    failures.push(`${route} has no entry in src/lib/seo-copy.ts`)
    continue
  }
  const bare = entry.title ?? fallbackTitle.get(route)
  if (!bare) {
    failures.push(`${route} has no title and no fallback`)
  } else {
    const composed = `${bare}${SUFFIX}`
    if (composed.length < TITLE_MIN || composed.length > TITLE_MAX) {
      failures.push(`${route} title is ${composed.length} characters: "${composed}"`)
    }
    const seen = titles.get(composed)
    if (seen) failures.push(`${route} repeats the title on ${seen}`)
    else titles.set(composed, route)
  }
  const text = entry.description
  if (!text) {
    failures.push(`${route} has no description`)
  } else {
    if (text.length < DESCRIPTION_MIN || text.length > DESCRIPTION_MAX) {
      failures.push(`${route} description is ${text.length} characters`)
    }
    const seen = descriptions.get(text)
    if (seen) failures.push(`${route} repeats the description on ${seen}`)
    else descriptions.set(text, route)
  }
}

for (const path of entries.keys()) {
  if (!routes.includes(path)) failures.push(`src/lib/seo-copy.ts has an entry for ${path}, which is not a route`)
}

assert(failures.length === 0, `Search-result copy is out of band:\n  ${failures.join('\n  ')}`)
assert(
  titles.size + descriptions.size > 0,
  'SEO copy validation measured zero titles and zero descriptions',
)
console.log(
  `Search-result copy validation passed (${routes.length} routes; titles ${TITLE_MIN}-${TITLE_MAX}, ` +
    `descriptions ${DESCRIPTION_MIN}-${DESCRIPTION_MAX}, all unique).`,
)
