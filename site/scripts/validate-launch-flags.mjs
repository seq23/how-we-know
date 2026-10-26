/**
 * Guards the launch switches in site-flags.json.
 *
 * The failure this exists to prevent: the noindex meta tag and robots.txt drifting
 * apart, so the site claims one thing in HTML and another to crawlers. Both must
 * be driven by the same single flag, and this asserts they actually are.
 */
import fs from 'node:fs'
import { assert, readJson } from './validation-helpers.mjs'

const flags = readJson('site-flags.json')
const root = fs.readFileSync('src/routes/__root.tsx', 'utf8')
const siteLib = fs.readFileSync('src/lib/site.ts', 'utf8')
const robots = fs.readFileSync('public/robots.txt', 'utf8')
const redirects = fs.readFileSync('public/_redirects', 'utf8')
const sitemap = fs.readFileSync('public/sitemap.xml', 'utf8')

assert(typeof flags.searchIndexingEnabled === 'boolean', 'searchIndexingEnabled must be a boolean')
assert(typeof flags.customDomainLive === 'boolean', 'customDomainLive must be a boolean')
assert(typeof flags.webAnalyticsToken === 'string', 'webAnalyticsToken must be a string')

// Canonical origin must be an absolute https apex, with no trailing slash or www.
const origin = flags.canonicalOrigin
assert(/^https:\/\/[^/]+$/u.test(origin), `canonicalOrigin must be an absolute https origin: ${origin}`)
const host = new URL(origin).host
assert(!host.startsWith('www.'), 'canonicalOrigin must be the apex, not www')

// The switch must be read from the flags file, never hardcoded in a template.
assert(siteLib.includes('site-flags.json'), 'site.ts must read the flags file')
assert(
  siteLib.includes('flags.searchIndexingEnabled'),
  'searchIndexingEnabled must come from the flags file',
)
assert(
  root.includes('searchIndexingEnabled'),
  'The root document must gate its robots meta on searchIndexingEnabled',
)
assert(root.includes("'noindex,follow'"), 'The noindex meta value is missing from the root document')

// Both surfaces must agree with the flag.
if (flags.searchIndexingEnabled) {
  assert(/^\s*Disallow:\s*\/\s*$/mu.test(robots) === false, 'Indexing is enabled but robots.txt disallows everything')
  assert(robots.includes('Sitemap:'), 'Indexing is enabled but robots.txt advertises no sitemap')
} else {
  assert(/^\s*Disallow:\s*\/\s*$/mu.test(robots), 'Indexing is disabled but robots.txt does not disallow')
  assert(!robots.includes('Sitemap:'), 'A noindexed site must not advertise a sitemap')
}

// Host canonicalisation must live where it can actually fire.
//
// The three assertions that used to be here checked public/_redirects for
// `https://www.<host>/* ...` and passed for weeks while that rule did nothing:
// Cloudflare Pages matches _redirects by path and never reads the Host header,
// so www.howweknowdeep.com answered 200 with the whole site next to the apex.
// A validator that asserts the presence of an inert line is worse than no
// validator, so these now check the mechanism that does see the Host header and
// forbid the syntax that cannot.
assert(
  !/^\s*https?:\/\//mu.test(redirects),
  'public/_redirects has an absolute-URL source. Pages matches by path only, so such a ' +
    'rule never fires; host canonicalisation belongs in functions/_middleware.js',
)
assert(fs.existsSync('functions/_middleware.js'), 'functions/_middleware.js is missing')
const middleware = fs.readFileSync('functions/_middleware.js', 'utf8')
assert(
  middleware.includes(`const CANONICAL_HOST = '${host}'`),
  `functions/_middleware.js must canonicalise to ${host}, the canonicalOrigin host`,
)
assert(middleware.includes('301'), 'Host canonicalisation must be a 301, not a soft redirect')
assert(
  /request\.method !== 'GET'/u.test(middleware),
  'Host canonicalisation must leave non-GET requests alone; redirecting a POST drops its body',
)
assert(
  middleware.includes("hostname === 'localhost'"),
  'Host canonicalisation must exempt local development',
)
assert(
  /how-we-know\\\.pages\\\.dev\$/u.test(middleware),
  'Host canonicalisation must exempt Pages deployment previews',
)

// Canonical URLs must already be absolute apex URLs. Rule 0: never pass on nothing.
const locs = [...sitemap.matchAll(/<loc>([^<]+)<\/loc>/gu)].map((match) => match[1])
assert(locs.length > 0, 'Launch-flag validation examined zero sitemap URLs')
for (const loc of locs) {
  assert(loc.startsWith(`${origin}/`), `Sitemap URL is not on the canonical apex: ${loc}`)
}

console.log(
  `Launch-flag validation passed (${locs.length} canonical URLs on ${host}; ` +
    `indexing ${flags.searchIndexingEnabled ? 'enabled' : 'DISABLED'}; ` +
    `custom domain ${flags.customDomainLive ? 'live' : 'not live'}; ` +
    `host canonicalisation to ${host} in functions/_middleware.js).`,
)
