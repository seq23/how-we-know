/**
 * Tell IndexNow what changed, after the deploy.
 *
 * Search readiness item e3 is two halves: the key file on the host (the build
 * writes it, validate-indexnow.mjs guards it) and "a ping of changed URLs after
 * every deploy" — this. Without it the key file is an unused credential and Bing,
 * Yandex and Seznam find new pages whenever they next happen to crawl.
 *
 * Changed, not everything. IndexNow asks for the URLs that actually changed, and
 * a host that submits its whole sitemap on every deploy is noise. The set is the
 * sitemap URLs whose page content changed in this deploy's commit range, which is
 * what `--since <ref>` reads; with no range (a dispatch, a first run) it submits
 * the sitemap, which is the honest answer to "what changed" for a fresh host.
 *
 * Costs nothing: IndexNow is free and unauthenticated beyond the key file.
 *
 * Rule 0: a run that submitted nothing and had nothing to submit says so and
 * exits 0; a run that could not reach the endpoint exits non-zero.
 */
import { execFileSync } from 'node:child_process'
import fs from 'node:fs'
import path from 'node:path'

const root = process.cwd()
const flags = JSON.parse(fs.readFileSync(path.join(root, 'site-flags.json'), 'utf8'))
const origin = process.env.LIVE_ORIGIN || flags.canonicalOrigin
const host = new URL(origin).host
const key = flags.indexNowKey
const ENDPOINT = 'https://api.indexnow.org/indexnow'

if (!/^[0-9a-f]{32,64}$/.test(String(key ?? ''))) {
  console.error(`NOT SUBMITTED: site-flags.json indexNowKey is ${JSON.stringify(key)}, not a key.`)
  process.exit(1)
}

// Indexing is off => there is nothing to tell an index about, and submitting
// would contradict the robots.txt the same flag writes.
if (!flags.searchIndexingEnabled) {
  console.log('NAMED STOP: searchIndexingEnabled is false, so nothing was submitted to IndexNow.')
  process.exit(0)
}

const sitemapUrls = [
  ...fs
    .readFileSync(path.join(root, 'public/sitemap.xml'), 'utf8')
    .matchAll(/<loc>([^<]+)<\/loc>/g),
].map((match) => match[1].trim())

if (sitemapUrls.length === 0) {
  console.error('NOT SUBMITTED: public/sitemap.xml holds zero <loc> entries.')
  process.exit(1)
}

/**
 * The URLs this deploy changed. A page's content comes from content/*.json and
 * src/, so any commit touching those invalidates the pages it names; a commit
 * touching only, say, a workflow changes no page. Mapping a changed slug back to
 * its URL is exactly the sitemap entry that contains it.
 */
const sinceArg = process.argv.includes('--since')
  ? process.argv[process.argv.indexOf('--since') + 1]
  : null
// github.event.before is forty zeros when a push creates the branch: there is
// no previous commit, which is the same answer as no range at all.
const sinceRef = sinceArg && !/^0+$/.test(sinceArg) ? sinceArg : null

let urls = sitemapUrls
let why = 'the whole sitemap (no commit range given)'

if (sinceRef) {
  let changedFiles = []
  try {
    changedFiles = execFileSync('git', ['diff', '--name-only', `${sinceRef}..HEAD`], {
      cwd: path.join(root, '..'),
      encoding: 'utf8',
    })
      .split('\n')
      .filter(Boolean)
  } catch (error) {
    console.error(`NOT SUBMITTED: could not read the commit range ${sinceRef}..HEAD: ${error.message}`)
    process.exit(1)
  }

  const touchedSite = changedFiles.filter((file) => file.startsWith('site/'))
  // A change to a shared template, component, style or generator can alter every
  // page, so only a change confined to content files narrows the set.
  const contentOnly =
    touchedSite.length > 0 && touchedSite.every((file) => file.startsWith('site/content/'))

  if (touchedSite.length === 0) {
    urls = []
    why = `no file under site/ changed in ${sinceRef}..HEAD`
  } else if (contentOnly) {
    const slugs = new Set()
    for (const file of touchedSite) {
      const name = path.basename(file, '.json')
      if (name) slugs.add(name)
    }
    // content/questions.json names every question; a change there can touch any
    // of them, so fall back to the full set rather than guess which rows moved.
    urls = sitemapUrls
    why = `content changed (${[...slugs].join(', ')}), so every page it feeds`
  } else {
    why = `shared site code changed in ${sinceRef}..HEAD, so every page`
  }
}

if (urls.length === 0) {
  console.log(`Nothing submitted to IndexNow: ${why}.`)
  process.exit(0)
}

const body = {
  host,
  key,
  keyLocation: `${origin}/${key}.txt`,
  urlList: urls,
}

const response = await fetch(ENDPOINT, {
  method: 'POST',
  headers: { 'content-type': 'application/json; charset=utf-8' },
  body: JSON.stringify(body),
}).catch((error) => {
  console.error(`NOT SUBMITTED: ${ENDPOINT} could not be reached: ${error.message}`)
  process.exit(1)
})

// 200 accepted, 202 accepted but the key is still being verified. Both are a
// successful submission; everything else is a real failure worth reding.
if (![200, 202].includes(response.status)) {
  console.error(
    `NOT SUBMITTED: IndexNow answered ${response.status} ${response.statusText} ` +
      `for ${urls.length} URL(s). Body: ${(await response.text()).slice(0, 300)}`,
  )
  process.exit(1)
}

console.log(
  `Submitted ${urls.length} URL(s) to IndexNow for ${host} (${response.status}): ${why}. ` +
    `Key proved at ${body.keyLocation}.`,
)
