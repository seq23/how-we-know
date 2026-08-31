import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'

const read = (p) => JSON.parse(fs.readFileSync(p, 'utf8'))
const questions = read('content/questions.json')
const zones = read('content/zones.json')
const creatures = read('content/creatures.json')
const sitemap = fs.readFileSync('public/sitemap.xml', 'utf8')

// Fixed pages that exist regardless of content.
const STATIC_ROUTES = [
  '/',
  '/questions',
  '/zones',
  '/creatures',
  '/watch',
  '/explore',
  '/methods',
  '/methodology',
  '/editorial-policy',
  '/privacy',
  '/terms',
]

// The method index is content-derived: only methods a page actually carries
// become routes. Deriving it here keeps the test tracking reality instead of a
// number that has to be hand-bumped whenever the taxonomy grows.
const activeMethodIds = [...new Set(questions.map((item) => item.method))]

test('sitemap materializes the approved route universe', () => {
  assert.ok(questions.length > 0, 'no question records to check')
  assert.ok(activeMethodIds.length > 0, 'no active method ids resolved')

  const expected =
    STATIC_ROUTES.length +
    activeMethodIds.length +
    questions.length +
    zones.length +
    creatures.length

  assert.equal((sitemap.match(/<url>/g) || []).length, expected)
    // Route URLs in the sitemap carry a trailing slash since 2026-08-31 -
    // Cloudflare Pages serves `<path>/index.html`, so the slash-less form
    // 308-redirects and a canonical pointing at a redirect is a real defect
    // on a site whose purpose is being cited. Assert the route is present,
    // not one particular spelling of it.
    assert.match(sitemap, /\/explore\/?<\/loc>/)

  for (const route of STATIC_ROUTES) {
    // Optional trailing slash: route URLs carry one since 2026-08-31 because
    // Cloudflare Pages serves `<path>/index.html` and the slash-less form
    // 308-redirects. Assert the route exists, not one spelling of it.
    assert.match(sitemap, new RegExp(`<loc>[^<]*${route === '/' ? '/</loc>' : `${route}/?</loc>`}`))
  }
  for (const id of activeMethodIds) {
    assert.match(sitemap, new RegExp(`/methods/${id}/?</loc>`))
  }
})
