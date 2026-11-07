// Guard for 7 Nov 2026 (Search Readiness o1, howweknowdeep.com): the footer on
// every page linked /privacy and /terms without the trailing slash the server
// canonicalises to, so every page sent crawlers through a 308 hop. Page routes
// live at slash URLs (canonicals, sitemap); a hard-coded internal page href must
// end in "/" or name a file (sitemap.xml, llms.txt).
import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'

const files = (dir) => fs.readdirSync(dir, { withFileTypes: true }).flatMap((e) => {
  const p = path.join(dir, e.name)
  return e.isDirectory() ? files(p) : /\.(tsx|ts)$/.test(e.name) && !e.name.includes('routeTree.gen') ? [p] : []
})
const hrefs = (src) => [...src.matchAll(/href=["'](\/[^"'#?]*)["']/g)].map((m) => m[1])
const hops = (href) => href !== '/' && !href.endsWith('/') && !/\.[a-z0-9]+$/i.test(href.split('/').pop())

test('every hard-coded internal page link uses the slash URL the server serves', () => {
  const found = files('src').flatMap((f) => hrefs(fs.readFileSync(f, 'utf8')).map((h) => ({ f, h })))
  assert.ok(found.length > 5, `only ${found.length} internal hrefs found; the scan is broken`)
  assert.deepEqual(found.filter(({ h }) => hops(h)), [])
})

test('the check catches the 7 Nov footer defect', () => {
  assert.deepEqual(hrefs('<a href="/privacy">x</a><a href="/about/">y</a><a href="/llms.txt">z</a>').filter(hops), ['/privacy'])
})
