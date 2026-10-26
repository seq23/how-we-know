/**
 * The deployed site, checked from outside, after the deploy.
 *
 * A deploy that reports success is not the same as a site that answers. Three
 * things were wrong on the live origin on 2026-10-25 and invisible to every
 * check in this repository, because every check read source:
 *
 *   - https://www.howweknowdeep.com/ answered 200 with the whole homepage
 *     instead of a 301 to the apex, splitting every signal between two hosts.
 *   - /favicon.ico and /apple-touch-icon.png answered 404.
 *   - the homepage's own title was eleven characters long.
 *
 * This reads the live origin the way the weekly search-readiness audit reads it,
 * so the next person to find those is this job and not the following Monday.
 *
 * It is also the whole of the post-deploy live check (search readiness item h4:
 * crawl files, icons, og image, schema types, redirects of measured URLs, the
 * IndexNow key). Two callers, one list: the deploy job in site-check.yml runs it
 * the moment a deploy lands, and site-post-deploy-check.yml re-runs it on a
 * schedule so live drift that no deploy caused is found by a job and not by the
 * next audit.
 *
 * Rule 0: a run that made zero requests fails.
 */
import fs from 'node:fs'
import { assert, readJson } from './validation-helpers.mjs'

const flags = readJson('site-flags.json')
const origin = process.env.LIVE_ORIGIN || flags.canonicalOrigin
const host = new URL(origin).host
const UA = 'Mozilla/5.0 (compatible; HowWeKnow-PostDeploy/1.0)'

const get = async (url, redirect = 'follow') => {
  const response = await fetch(url, { redirect, headers: { 'user-agent': UA } })
  return { status: response.status, location: response.headers.get('location'), response }
}

/**
 * Cloudflare Pages promotes a deployment to the production alias within seconds,
 * but not instantly, and a check that runs a second early reds main for a reason
 * that is not a defect. Five attempts fifteen seconds apart, then it is real.
 */
const ATTEMPTS = 5
const GAP_MS = 15_000
let failures = []
let checks = 0

for (let attempt = 1; attempt <= ATTEMPTS; attempt += 1) {
  failures = []
  checks = 0
  await runChecks()
  if (!failures.length) break
  if (attempt < ATTEMPTS) {
    console.log(`Attempt ${attempt}/${ATTEMPTS}: ${failures.length} not right yet; waiting ${GAP_MS / 1000}s.`)
    await new Promise((resolve) => setTimeout(resolve, GAP_MS))
  }
}

assert(checks > 0, 'Live-host validation made zero requests')
assert(
  fs.existsSync('functions/_middleware.js'),
  'functions/_middleware.js is missing, so nothing could be canonicalising the host',
)
assert(failures.length === 0, `The deployed site is not search-ready:\n  ${failures.join('\n  ')}`)
console.log(`Live-host validation passed (${checks} checks against ${origin}).`)

async function runChecks() {

// The canonical host answers, and its homepage is the homepage.
{
  checks += 1
  const { status, response } = await get(`${origin}/`)
  if (status !== 200) failures.push(`${origin}/ answered ${status}`)
  else {
    const html = await response.text()
    const title = (/<title[^>]*>([\s\S]*?)<\/title>/iu.exec(html)?.[1] ?? '').trim()
    if (title.length < 30 || title.length > 65) failures.push(`homepage title is ${title.length} characters: "${title}"`)
    if (!/property=["']og:site_name["']/iu.test(html)) failures.push('homepage has no og:site_name')
  }
}

// Every other host 301s to it. This is the one that had never worked.
for (const other of [`https://www.${host}/`, 'https://how-we-know.pages.dev/']) {
  checks += 1
  const { status, location } = await get(other, 'manual')
  if (![301, 308].includes(status)) {
    failures.push(`${other} answered ${status}, not a 301 to ${host}`)
  } else if (!location || new URL(location, other).host !== host) {
    failures.push(`${other} redirects to ${location}, not ${host}`)
  }
}

// The files that were 404ing, and the OG card they are declared alongside.
for (const file of ['/favicon.ico', '/apple-touch-icon.png', '/site.webmanifest', '/og-default.png', '/logo.png']) {
  checks += 1
  const { status, response } = await get(`${origin}${file}`)
  if (status !== 200) failures.push(`${file} answered ${status}`)
  else if (/\.(?:png|ico)$/u.test(file) && !/^(?:image|application\/octet-stream)/u.test(response.headers.get('content-type') ?? '')) {
    failures.push(`${file} answered 200 as ${response.headers.get('content-type')}`)
  }
}

// A made-up path is a real 404, not a redirect home. A soft 404 hides broken links.
{
  checks += 1
  const { status } = await get(`${origin}/this-path-does-not-exist-${Date.now()}`, 'manual')
  if (status !== 404) failures.push(`an unknown path answered ${status}, not 404`)
}

// The About page the homepage links. Its absence was its own audit failure.
{
  checks += 1
  const { status } = await get(`${origin}/about/`)
  if (status !== 200) failures.push(`/about/ answered ${status}`)
}

// ─── the rest of the post-deploy live check (search readiness h4) ───────────
//
// h4 names six things to read on the deployed site: crawl files, icons, the og
// image, schema types, the redirects of measured URLs, and the IndexNow key. The
// three above cover icons, the og image and the host redirect. These cover the
// rest, so this one script is the whole check and nothing keeps a second list.

// Crawl files. robots.txt that does not point at the sitemap, or a sitemap that
// does not answer, is a site no crawler can enumerate — and both are generated,
// so a generator regression would show up here first.
{
  checks += 1
  const { status, response } = await get(`${origin}/robots.txt`)
  if (status !== 200) failures.push(`/robots.txt answered ${status}`)
  else {
    const text = await response.text()
    if (!/^sitemap:\s*\S+/im.test(text)) failures.push('/robots.txt names no Sitemap')
    if (/^disallow:\s*\/\s*$/im.test(text)) {
      failures.push('/robots.txt disallows the whole site')
    }
  }
}

for (const file of ['/sitemap.xml', '/llms.txt']) {
  checks += 1
  const { status, response } = await get(`${origin}${file}`)
  if (status !== 200) failures.push(`${file} answered ${status}`)
  else if (file.endsWith('.xml')) {
    const text = await response.text()
    const locs = [...text.matchAll(/<loc>([^<]+)<\/loc>/g)].map((m) => m[1])
    if (locs.length === 0) failures.push('/sitemap.xml holds zero <loc> entries')
    else if (locs.some((loc) => new URL(loc).host !== host)) {
      failures.push(`/sitemap.xml lists URLs on another host (e.g. ${locs.find((loc) => new URL(loc).host !== host)})`)
    }
  }
}

// The IndexNow key, read over HTTP from the deployed host. The build guards the
// file (validate-indexnow.mjs); this proves the deploy actually serves it, which
// is the only thing IndexNow itself will check.
{
  checks += 1
  const key = flags.indexNowKey
  const { status, response } = await get(`${origin}/${key}.txt`)
  if (status !== 200) failures.push(`/${key}.txt answered ${status}, so IndexNow cannot verify the key`)
  else if ((await response.text()).trim() !== key) {
    failures.push(`/${key}.txt does not contain the key it is named for`)
  }
}

// Schema types. The homepage declares an Organization, a WebSite and a WebPage;
// a prerender that dropped the JSON-LD would leave the pages looking fine and
// make the site unquotable, which is the entire point of this publication.
{
  checks += 1
  const { status, response } = await get(`${origin}/`)
  if (status !== 200) failures.push(`${origin}/ answered ${status} when reading its schema`)
  else {
    const html = await response.text()
    const types = new Set()
    for (const match of html.matchAll(
      /<script[^>]+application\/ld\+json[^>]*>([\s\S]*?)<\/script>/gi,
    )) {
      let parsed
      try {
        parsed = JSON.parse(match[1])
      } catch {
        failures.push('the homepage carries JSON-LD that does not parse')
        continue
      }
      const nodes = Array.isArray(parsed) ? parsed : (parsed['@graph'] ?? [parsed])
      for (const node of nodes) {
        for (const type of [node?.['@type']].flat()) if (type) types.add(String(type))
      }
    }
    for (const required of ['Organization', 'WebSite', 'WebPage']) {
      if (!types.has(required)) {
        failures.push(`the homepage declares no ${required} in JSON-LD (found: ${[...types].join(', ') || 'nothing'})`)
      }
    }
  }
}

// The redirects of measured URLs. Every sitemap URL is a URL search engines are
// told to index, so one that redirects wastes the signal it was given — this is
// the defect the sitemap generator's trailing-slash rule exists to prevent, read
// from outside instead of trusted. A sample keeps the check inside a minute.
{
  const sitemap = await get(`${origin}/sitemap.xml`)
  const locs =
    sitemap.status === 200
      ? [...(await sitemap.response.text()).matchAll(/<loc>([^<]+)<\/loc>/g)].map((m) => m[1])
      : []
  const sample = locs.filter((_, index) => index % Math.ceil(locs.length / 12 || 1) === 0).slice(0, 12)
  for (const url of sample) {
    checks += 1
    const { status, location } = await get(url, 'manual')
    if (status !== 200) failures.push(`sitemap URL ${url} answered ${status}${location ? ` -> ${location}` : ''}`)
  }
}

}
