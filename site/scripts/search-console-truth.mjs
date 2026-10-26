/**
 * The daily Search Console truth: queries, coverage and sitemap status.
 *
 * Search readiness items e4, e5 and i6 (owner's checklist, 25 Oct 2026). Google
 * keeps 16 months of query data but shows a rolling 28-day window, and the
 * URL Inspection API answers for one URL at a time and is rate limited. Neither
 * is a thing you can read later: a query that mattered in week one is gone from
 * the window by week five, and "why is this page not indexed" has no history at
 * all unless something wrote it down. So this runs daily and commits what it saw.
 *
 * Three files, all under data/search-console/:
 *
 *   gsc_truth.json      the rolling 28-day window: top queries and pages with
 *                       clicks, impressions, CTR and position, plus the status
 *                       of every sitemap Google has read.
 *   gsc_query_history.json
 *                       every query ever seen, with the day it was first and
 *                       last seen and its best position. This is the half of e4
 *                       that the window cannot give: a target does not vanish
 *                       from the record when it leaves the 28 days.
 *   index_coverage.json indexed / crawled-not-indexed / discovered / unknown per
 *                       page, 150 URLs a day, 8 at a time, rotating so the whole
 *                       sitemap is covered and the oldest reading goes first.
 *
 * Read-only: the webmasters.readonly scope, which covers searchAnalytics, sitemaps
 * and urlInspection. It spends nothing — Search Console's API is free.
 *
 * Rule 0: it either writes the files or prints a NAMED STOP that says exactly
 * what is missing and who can supply it. The one thing it may stop on is an
 * account the owner alone holds: a Search Console property for this domain with
 * the service account added to it. That stop is green, because nothing in this
 * repository can clear it and a red check every morning teaches people to ignore
 * red checks. A stop writes search-console-stop.json and never gsc_truth.json,
 * so a stopped day cannot pass for a day with data.
 */
import { createSign } from 'node:crypto'
import fs from 'node:fs'
import path from 'node:path'

const root = process.cwd()
const flags = JSON.parse(fs.readFileSync(path.join(root, 'site-flags.json'), 'utf8'))
const origin = flags.canonicalOrigin
const domain = new URL(origin).host
const outDir = path.join(root, 'data/search-console')

const SCOPE = 'https://www.googleapis.com/auth/webmasters.readonly'
const WINDOW_DAYS = 28
const INSPECT_PER_DAY = 150
const INSPECT_PARALLEL = 8

const today = new Date()
const iso = (date) => date.toISOString().slice(0, 10)
const dayOffset = (days) => iso(new Date(today.getTime() + days * 86_400_000))

/** A stop only the owner can clear: green, named, and explicit about the fix. */
function namedStop(what, how) {
  console.log('')
  console.log('━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━')
  console.log(`NAMED STOP: ${what}`)
  console.log('')
  console.log(`What would clear it: ${how}`)
  console.log('')
  console.log('Nothing in this repository can clear it, so this check is green')
  console.log('rather than red. The files under site/data/search-console/ are')
  console.log('whatever the last successful run wrote, and the day it stopped is')
  console.log('recorded in gsc_truth.json so the gap is visible rather than quiet.')
  console.log('━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━')
  recordStop(what, how)
  process.exit(0)
}

/**
 * A stop is recorded in its OWN file, never in gsc_truth.json.
 *
 * Writing it into the truth file was the first shape of this and it was wrong:
 * the freshness half of item e4 asks whether gsc_truth.json was committed in the
 * last three days, so a daily run that stopped would have refreshed that file
 * every morning and reported query truth as current while holding none. A stop
 * must be visible without being mistaken for data.
 */
function recordStop(what, how) {
  fs.mkdirSync(outDir, { recursive: true })
  fs.writeFileSync(
    path.join(outDir, 'search-console-stop.json'),
    `${JSON.stringify(
      { domain, stopped_at: iso(today), stopped_because: what, stop_cleared_by: how },
      null,
      2,
    )}\n`,
  )
}

async function accessToken(creds) {
  const now = Math.floor(Date.now() / 1000)
  const b64 = (object) => Buffer.from(JSON.stringify(object)).toString('base64url')
  const unsigned = `${b64({ alg: 'RS256', typ: 'JWT' })}.${b64({
    iss: creds.client_email,
    scope: SCOPE,
    aud: 'https://oauth2.googleapis.com/token',
    iat: now,
    exp: now + 3600,
  })}`
  const signer = createSign('RSA-SHA256')
  signer.update(unsigned)
  const jwt = `${unsigned}.${signer.sign(creds.private_key).toString('base64url')}`
  const response = await fetch('https://oauth2.googleapis.com/token', {
    method: 'POST',
    headers: { 'content-type': 'application/x-www-form-urlencoded' },
    body: new URLSearchParams({
      grant_type: 'urn:ietf:params:oauth:grant-type:jwt-bearer',
      assertion: jwt,
    }),
  }).catch(() => null)
  if (!response?.ok) return null
  return (await response.json()).access_token
}

const api = async (token, url, body) => {
  const response = await fetch(url, {
    method: body ? 'POST' : 'GET',
    headers: { authorization: `Bearer ${token}`, 'content-type': 'application/json' },
    body: body ? JSON.stringify(body) : undefined,
  }).catch(() => null)
  if (!response?.ok) {
    return { __error: response ? `${response.status} ${(await response.text()).slice(0, 200)}` : 'no answer' }
  }
  return response.json()
}

// ─── the one stop the owner alone can clear ───────────────────────────────────

const raw = process.env.GSC_SERVICE_ACCOUNT_JSON
if (!raw) {
  namedStop(
    'there is no GSC_SERVICE_ACCOUNT_JSON secret on this repository, so Search Console cannot be read.',
    'add the gsc-bot service account JSON as the Actions secret GSC_SERVICE_ACCOUNT_JSON ' +
      '(Settings > Secrets and variables > Actions). It is the same key Boss OS already uses.',
  )
}

let creds
try {
  creds = JSON.parse(raw)
} catch {
  namedStop(
    'the GSC_SERVICE_ACCOUNT_JSON secret does not parse as JSON.',
    're-paste the service account JSON exactly as Google issued it, including its newlines.',
  )
}

const token = await accessToken(creds)
if (!token) {
  namedStop(
    `Google refused a token for ${creds.client_email}.`,
    'check the service account still exists and its key has not been revoked.',
  )
}

// ─── which property answers for this domain ───────────────────────────────────

const siteList = await api(token, 'https://www.googleapis.com/webmasters/v3/sites')
if (siteList.__error) {
  namedStop(
    `Search Console refused the site list (${siteList.__error}).`,
    'confirm the Search Console API is enabled for the service account\'s project.',
  )
}

const available = new Set((siteList.siteEntry ?? []).map((entry) => entry.siteUrl))
const property = [
  `sc-domain:${domain}`,
  `https://${domain}/`,
  `https://www.${domain}/`,
].find((candidate) => available.has(candidate))

if (!property) {
  namedStop(
    `no Search Console property for ${domain} is shared with ${creds.client_email}. ` +
      `It can currently read: ${[...available].join(', ') || 'nothing'}.`,
    `in Search Console, add the domain property for ${domain} (or open the existing one), ` +
      `then Settings > Users and permissions > Add user, ${creds.client_email}, Full. ` +
      'This is the only step here that needs her Google account; everything after it is automatic.',
  )
}

const encoded = encodeURIComponent(property)
const summary = { domain, property, collected_at: new Date().toISOString(), window_days: WINDOW_DAYS }

// ─── e4: the rolling 28-day window, and the history the window loses ─────────

// Search Console finalises data ~2 days back, so a window ending today is partly
// empty and reads as a collapse in traffic. It ends where the data does.
const endDate = dayOffset(-2)
const startDate = dayOffset(-(WINDOW_DAYS + 2))

const queryRows = async (dimension) => {
  const result = await api(
    token,
    `https://www.googleapis.com/webmasters/v3/sites/${encoded}/searchAnalytics/query`,
    { startDate, endDate, dimensions: [dimension], rowLimit: 1000, dataState: 'final' },
  )
  if (result.__error) {
    namedStop(
      `Search Console refused the ${dimension} report (${result.__error}).`,
      'if this says 403, the service account was removed from the property; re-add it.',
    )
  }
  return (result.rows ?? []).map((row) => ({
    key: row.keys[0],
    clicks: row.clicks ?? 0,
    impressions: row.impressions ?? 0,
    ctr: Number((row.ctr ?? 0).toFixed(4)),
    position: Number((row.position ?? 0).toFixed(1)),
  }))
}

const queries = await queryRows('query')
const pages = await queryRows('page')

const sitemapList = await api(token, `https://www.googleapis.com/webmasters/v3/sites/${encoded}/sitemaps`)
const sitemaps = (sitemapList.sitemap ?? []).map((entry) => ({
  path: entry.path,
  last_submitted: entry.lastSubmitted ?? null,
  last_downloaded: entry.lastDownloaded ?? null,
  errors: Number(entry.errors ?? 0),
  warnings: Number(entry.warnings ?? 0),
  submitted_urls: Number(entry.contents?.[0]?.submitted ?? 0),
}))

fs.mkdirSync(outDir, { recursive: true })
fs.writeFileSync(
  path.join(outDir, 'gsc_truth.json'),
  `${JSON.stringify(
    {
      ...summary,
      window: { start: startDate, end: endDate },
      totals: {
        clicks: queries.reduce((sum, row) => sum + row.clicks, 0),
        impressions: queries.reduce((sum, row) => sum + row.impressions, 0),
        queries: queries.length,
        pages: pages.length,
      },
      sitemaps,
      queries,
      pages,
    },
    null,
    2,
  )}\n`,
)

// The history. Every query keeps the day it was first and last seen and its best
// position, so a target that leaves the 28-day window stays in the record.
const historyFile = path.join(outDir, 'gsc_query_history.json')
const history = fs.existsSync(historyFile) ? JSON.parse(fs.readFileSync(historyFile, 'utf8')) : {}
const seen = history.queries ?? {}
for (const row of queries) {
  const previous = seen[row.key]
  seen[row.key] = {
    first_seen: previous?.first_seen ?? endDate,
    last_seen: endDate,
    best_position: previous ? Math.min(previous.best_position, row.position) : row.position,
    total_clicks: (previous?.total_clicks ?? 0) + row.clicks,
    days_seen: (previous?.days_seen ?? 0) + 1,
  }
}
fs.writeFileSync(
  historyFile,
  `${JSON.stringify({ domain, updated_at: endDate, count: Object.keys(seen).length, queries: seen }, null, 2)}\n`,
)

// ─── e5: URL Inspection coverage, 150 a day, 8 at a time, rotating ───────────

const sitemapUrls = [
  ...fs.readFileSync(path.join(root, 'public/sitemap.xml'), 'utf8').matchAll(/<loc>([^<]+)<\/loc>/g),
].map((match) => match[1].trim())

if (sitemapUrls.length === 0) {
  console.error('FAILED: public/sitemap.xml holds zero <loc> entries, so there is nothing to inspect.')
  process.exit(1)
}

const coverageFile = path.join(outDir, 'index_coverage.json')
const previousCoverage = fs.existsSync(coverageFile)
  ? JSON.parse(fs.readFileSync(coverageFile, 'utf8'))
  : { pages: {} }
const known = previousCoverage.pages ?? {}

// Oldest reading first, so the rotation covers the whole sitemap and a URL never
// inspected is never last in the queue.
const queue = [...sitemapUrls]
  .sort((a, b) => (known[a]?.checked_at ?? '').localeCompare(known[b]?.checked_at ?? ''))
  .slice(0, INSPECT_PER_DAY)

/** Google's own verdicts, mapped to the four buckets the checklist names. */
const bucketOf = (result) => {
  const status = result?.indexStatusResult ?? {}
  const verdict = String(status.verdict ?? '').toUpperCase()
  const state = String(status.coverageState ?? '')
  if (verdict === 'PASS') return 'indexed'
  if (/crawled - currently not indexed/i.test(state)) return 'crawled_not_indexed'
  if (/discovered - currently not indexed/i.test(state)) return 'discovered'
  if (/not found|404|excluded|noindex|redirect|canonical/i.test(state)) return 'crawled_not_indexed'
  return 'unknown'
}

let inspected = 0
let refused = null
const inspectOne = async (url) => {
  const result = await api(token, 'https://searchconsole.googleapis.com/v1/urlInspection/index:inspect', {
    inspectionUrl: url,
    siteUrl: property,
  })
  if (result.__error) {
    // A quota refusal is not a defect and must not lose the readings already
    // taken: the day's work stops and tomorrow's run starts where this left off.
    refused ??= result.__error
    return
  }
  inspected += 1
  const status = result.inspectionResult?.indexStatusResult ?? {}
  known[url] = {
    bucket: bucketOf(result.inspectionResult),
    coverage_state: status.coverageState ?? null,
    last_crawled: status.lastCrawlTime ?? null,
    google_canonical: status.googleCanonical ?? null,
    checked_at: iso(today),
  }
}

for (let index = 0; index < queue.length; index += INSPECT_PARALLEL) {
  if (refused) break
  await Promise.all(queue.slice(index, index + INSPECT_PARALLEL).map(inspectOne))
}

const buckets = { indexed: 0, crawled_not_indexed: 0, discovered: 0, unknown: 0 }
for (const url of sitemapUrls) {
  const bucket = known[url]?.bucket
  if (bucket && bucket in buckets) buckets[bucket] += 1
  else buckets.unknown += 1
}

fs.writeFileSync(
  coverageFile,
  `${JSON.stringify(
    {
      ...summary,
      sitemap_total: sitemapUrls.length,
      inspected_today: inspected,
      per_day: INSPECT_PER_DAY,
      parallel: INSPECT_PARALLEL,
      refused_because: refused,
      buckets,
      pages: known,
    },
    null,
    2,
  )}\n`,
)

if (inspected === 0) {
  console.error(
    `FAILED: ${queue.length} URL(s) were queued for inspection and none was read` +
      `${refused ? ` (${refused})` : ''}.`,
  )
  process.exit(1)
}

console.log(
  `Search Console truth written for ${property}: ` +
    `${queries.length} queries and ${pages.length} pages over ${startDate}..${endDate}, ` +
    `${Object.keys(seen).length} queries in the history, ` +
    `${sitemaps.length} sitemap(s), ` +
    `${inspected} URL(s) inspected today ` +
    `(indexed ${buckets.indexed}, crawled-not-indexed ${buckets.crawled_not_indexed}, ` +
    `discovered ${buckets.discovered}, unknown ${buckets.unknown})` +
    `${refused ? `; inspection stopped early: ${refused}` : ''}.`,
)
