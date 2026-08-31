/**
 * Fetches the DEPLOYED site and asserts that what is actually served is correct.
 *
 * WHERE THIS RUNS: after deploy (`npm run deploy:pages`), never inside
 * `validate:all`. A network check inside the build gate deadlocks — if
 * production is broken, `npm run build` fails, so the fix for the broken
 * production cannot be built. The check must gate the deployment, not the
 * build. Run standalone any time with `npm run validate:live`.
 *
 * This exists because a build-output check cannot catch it. Every prerendered
 * file on disk can be perfect while the host serves something else entirely —
 * wrong deploy target, missing 404 handler, a redirect rule, a stale upload.
 * The only way to know what a crawler sees is to be a crawler.
 *
 * Two failure classes, both observed on this project:
 *
 *   1. Collapsed routes — several URLs returning the same canonical, or a
 *      canonical that does not match the URL that served it. To an LLM or a
 *      search engine the whole site is then one page.
 *
 *   2. Soft 404 — an unknown path returning 200 with the homepage's canonical
 *      instead of a real 404. Junk URLs become indexable duplicates of "/".
 */
import { assert, readJson } from './validation-helpers.mjs'

const flags = readJson('site-flags.json')
const questions = readJson('content/questions.json')

const origin = process.env.LIVE_ORIGIN || flags.canonicalOrigin

// A named stop, not a silent skip: when no custom domain is live there is no
// production origin whose serving behaviour we can meaningfully assert.
if (!flags.customDomainLive && !process.env.LIVE_ORIGIN) {
  console.log(
    'Live-canonical validation NAMED STOP: customDomainLive is false and LIVE_ORIGIN is unset, ' +
      'so there is no deployed origin to check. Set customDomainLive after attaching a domain, ' +
      'or pass LIVE_ORIGIN=https://... to check a preview deployment.',
  )
  process.exit(0)
}

// Real routes that must each be distinct and self-canonical.
const routes = [
  '/',
  `/questions/${questions[0].slug}`,
  `/questions/${questions.at(-1).slug}`,
  `/methods/${questions[0].method}`,
]
// Paths that must NOT exist, to catch a soft 404.
const unknownRoutes = ['/questions/this-slug-does-not-exist', '/definitely/not/a/route']

assert(routes.length >= 3, 'Live validation needs at least three real routes to compare')

async function fetchPage(pathname) {
  const url = new URL(pathname, origin).toString()
  const response = await fetch(url, { redirect: 'follow', headers: { 'user-agent': 'how-we-know-validator' } })
  const html = await response.text()
  const canonical = html.match(/rel=["']canonical["'][^>]*href=["']([^"']+)["']/u)
    ?? html.match(/href=["']([^"']+)["'][^>]*rel=["']canonical["']/u)
  const title = html.match(/<title>([\s\S]*?)<\/title>/u)
  return {
    url,
    status: response.status,
    finalUrl: response.url,
    canonical: canonical?.[1] ?? null,
    title: title?.[1]?.trim() ?? null,
  }
}

const results = []
for (const pathname of routes) {
  results.push(await fetchPage(pathname))
}

// Rule 0: never pass having examined nothing.
assert(results.length === routes.length, 'Live validation did not fetch every route')

for (const result of results) {
  assert(result.status === 200, `${result.url} returned ${result.status}`)
  assert(result.title, `${result.url} served no <title>`)
  assert(result.canonical, `${result.url} served no canonical link`)

  // The canonical must name THIS page, on the canonical origin.
  //
  // Note it is compared against flags.canonicalOrigin, not against the host that
  // served the response. A preview deployment correctly emits apex canonicals —
  // that is the whole point of a canonical — so asserting "canonical === serving
  // URL" would wrongly fail every preview host while still missing the real bug.
  const actual = new URL(result.canonical)
  const served = new URL(result.finalUrl)
  const normalise = (value) => value.replace(/\/+$/u, '') || '/'
  assert(
    actual.origin === flags.canonicalOrigin,
    `Canonical origin is ${actual.origin}, expected ${flags.canonicalOrigin} (${result.finalUrl})`,
  )
  assert(
    normalise(actual.pathname) === normalise(served.pathname),
    `Canonical path mismatch: ${result.finalUrl} serves canonical ${result.canonical}`,
  )
}

// No two routes may share a canonical or a title.
for (let i = 0; i < results.length; i += 1) {
  for (let j = i + 1; j < results.length; j += 1) {
    assert(
      results[i].canonical !== results[j].canonical,
      `Duplicate canonical: ${results[i].url} and ${results[j].url} both serve ${results[i].canonical}`,
    )
    assert(
      results[i].title !== results[j].title,
      `Duplicate title: ${results[i].url} and ${results[j].url} both serve "${results[i].title}"`,
    )
  }
}

// Unknown paths must 404, and must never canonicalise to the homepage.
let unknownChecked = 0
for (const pathname of unknownRoutes) {
  const result = await fetchPage(pathname)
  assert(
    result.status === 404,
    `Soft 404: ${result.url} returned ${result.status} instead of 404` +
      (result.canonical ? ` and canonicalised to ${result.canonical}` : ''),
  )
  assert(
    !result.canonical,
    `${result.url} is a 404 but still emits canonical ${result.canonical}`,
  )
  unknownChecked += 1
}
assert(unknownChecked === unknownRoutes.length, 'Soft-404 check skipped a path')

console.log(
  `Live-canonical validation passed against ${origin} ` +
    `(${results.length} routes distinct and self-canonical, ${unknownChecked} unknown paths return a clean 404).`,
)
