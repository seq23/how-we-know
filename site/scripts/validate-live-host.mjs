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

}
