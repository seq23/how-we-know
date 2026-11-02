import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import { redirects, isKept, consolidateQuestions } from '../src/lib/search-rescue.mjs'
import { onRequest } from '../functions/_middleware.js'
const read = p => JSON.parse(fs.readFileSync(p, 'utf8'))
const raw = read('content/questions.json')
const creatures = read('content/creatures.json')
const zones = read('content/zones.json')
const sitemap = fs.readFileSync('public/sitemap.xml', 'utf8')
const kept = new Set([...sitemap.matchAll(/<loc>([^<]+)<\/loc>/g)].map(m => new URL(m[1]).pathname))

test('every source URL remains published or redirects directly to a published page', () => {
  assert.equal(Object.keys(redirects).length, 7)
  assert.equal(kept.size, 45)
  const rules = fs.readFileSync('public/_redirects','utf8').split('\n')
  for (const [kind, rows] of [['questions',raw],['creatures',creatures],['zones',zones]]) {
    assert.ok(rows.length > 0)
    for (const row of rows) {
      const path = `/${kind}/${row.slug}`
      if (isKept(path)) assert.ok(kept.has(`${path}/`), path)
      else {
        assert.ok(!kept.has(`${path}/`), path)
        assert.ok(kept.has(redirects[path]), redirects[path])
        assert.ok(isKept(redirects[path]), 'redirect chain')
        for (const from of [path, `${path}/`]) assert.ok(rules.includes(`${from} ${redirects[path]} 301`), from)
      }
    }
  }
})

test('removed URLs return HTTP 301 in both slash forms with query parameters preserved', async () => {
  for (const [from,to] of Object.entries(redirects)) {
    for (const suffix of ['', '/']) {
      for (const method of ['GET','HEAD']) {
        const response = await onRequest({ request: new Request(`https://howweknowdeep.com${from}${suffix}?ref=test`,{method}), next:()=>new Response('fallthrough') })
        assert.equal(response.status,301)
        assert.equal(response.headers.get('location'),`https://howweknowdeep.com${to}?ref=test`)
      }
    }
  }
  const response = await onRequest({request:new Request('https://howweknowdeep.com/questions/not-a-real-question/'), next:()=>new Response('missing',{status:404})})
  assert.equal(response.status,404, 'unknown URLs must not become soft 404s')
})

test('consolidation retains every donor section and source without republishing retired records', () => {
  const articles = consolidateQuestions(raw,creatures)
  assert.equal(articles.length,17)
  for (const [from,to] of Object.entries(redirects)) {
    const target = articles.find(q=>`/questions/${q.slug}/`===to)
    assert.ok(target,to)
    const donor = (from.startsWith('/questions/')?raw:creatures).find(r=>from.endsWith(`/${r.slug}`))
    assert.ok(donor,from)
    for (const id of donor.sourceIds) assert.ok(target.sourceIds.includes(id),id)
    for (const section of donor.sections ?? []) for (const p of section.paragraphs) assert.ok(target.sections.some(s=>s.paragraphs.includes(p)))
    assert.ok(!articles.some(q=>`/questions/${q.slug}`===from))
  }
  // A future generator attempting to restore a retired record is still filtered.
  const retired = raw.find(q=>!isKept(`/questions/${q.slug}`))
  assert.ok(!consolidateQuestions([retired],creatures).length)
})
