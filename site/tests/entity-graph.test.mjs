// Negative proofs for validate_entity_graph and entity_backlink_watch: each check is broken on
// purpose here and must fail, so neither can quietly turn into a check that passes on anything.
import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { spawnSync } from 'node:child_process'
import { classify, heal } from '../scripts/entity-backlink-watch.mjs'

const entity = JSON.parse(fs.readFileSync('entity.json', 'utf8'))
const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'entity-graph-'))

const runValidator = (entityValue, html) => {
  const entityFile = path.join(tmp, `entity-${Math.random()}.json`)
  fs.writeFileSync(entityFile, JSON.stringify(entityValue))
  const args = ['scripts/validate-entity-graph.mjs']
  const env = { ...process.env, ENTITY_FILE: entityFile }
  if (html !== undefined) {
    const out = fs.mkdtempSync(path.join(tmp, 'built-'))
    fs.writeFileSync(path.join(out, 'sitemap.xml'), '<urlset><url><loc>https://howweknowdeep.com/</loc></url></urlset>')
    fs.writeFileSync(path.join(out, 'index.html'), html)
    args.push('--built')
    env.BUILT_DIR = out
  }
  return spawnSync(process.execPath, args, { env, encoding: 'utf8' })
}
const page = (node) => `<html><script type="application/ld+json">${JSON.stringify(node)}</script></html>`
const goodNode = {
  '@type': 'Organization',
  '@id': entity['@id'],
  name: entity.name,
  description: entity.description,
  logo: { '@type': 'ImageObject', url: entity.logo },
  sameAs: entity.sameAs,
  parentOrganization: { '@id': entity.parentOrganization['@id'] },
}

test('entity.json: sameAs is real, not self-referential, and the parent is Spry Labs', () => {
  assert.ok(entity.sameAs.length >= 1)
  assert.ok(entity.sameAs.every((url) => !new URL(url).hostname.endsWith('howweknowdeep.com')))
  assert.equal(entity.parentOrganization['@id'], 'https://billionairehighperformancecoach.com/spry-labs#organization')
  assert.equal(runValidator(entity).status, 0)
  assert.equal(runValidator(entity, page(goodNode)).status, 0)
})

test('validate-entity-graph fails on each planted break', () => {
  const breaks = {
    'self-host sameAs': [{ ...entity, sameAs: [...entity.sameAs, 'https://howweknowdeep.com/about/'] }],
    'empty sameAs': [{ ...entity, sameAs: [] }],
    'live and pending at once': [{ ...entity, profiles_pending: [entity.sameAs[0]] }],
    'wrong parent': [{ ...entity, parentOrganization: { '@id': 'https://example.com/#org' } }],
    'built sameAs drift': [entity, page({ ...goodNode, sameAs: ['https://example.com/other'] })],
    'built name drift': [entity, page({ ...goodNode, name: 'Someone Else' })],
    'built parent missing': [entity, page({ ...goodNode, parentOrganization: undefined })],
    'zero matching nodes': [entity, page({ '@type': 'WebPage', name: 'x' })],
  }
  for (const [name, [value, html]] of Object.entries(breaks)) {
    assert.notEqual(runValidator(value, html).status, 0, `${name} passed`)
  }
})

const fakeFetch = (status, body, url) => async (requested) => ({
  ok: status >= 200 && status < 300,
  status,
  url: url ?? requested,
  text: async () => body,
})

test('watch classifies each state and never passes a profile it cannot read', async () => {
  const yt = 'https://www.youtube.com/@howweknowdeep'
  assert.equal((await classify(yt, 'howweknowdeep.com', fakeFetch(200, '@howweknowdeep ... https://howweknowdeep.com'))).state, 'linked')
  assert.equal((await classify(yt, 'howweknowdeep.com', fakeFetch(200, '@howweknowdeep channel'))).state, 'no_linkback')
  assert.equal((await classify(yt, 'howweknowdeep.com', fakeFetch(200, 'Before you continue to YouTube'))).state, 'unverifiable')
  assert.equal((await classify('https://www.instagram.com/x/', 'howweknowdeep.com', fakeFetch(200, 'x'))).state, 'unverifiable')
  assert.equal((await classify(yt, 'howweknowdeep.com', fakeFetch(404, ''), 1)).state, 'dead')
  assert.equal((await classify(yt, 'howweknowdeep.com', fakeFetch(503, ''), 1)).state, 'unreachable')
})

test('watch self-heals: dead removed, linked pending promoted, missing link-back is a named stop', () => {
  const base = { ...entity, sameAs: ['https://a.example/p', 'https://b.example/q'], profiles_pending: [{ url: 'https://c.example/r' }] }
  const { next, changes, stops } = heal(
    base,
    [
      { url: 'https://a.example/p', state: 'dead', status: 404 },
      { url: 'https://b.example/q', state: 'no_linkback', status: 200 },
      { url: 'https://c.example/r', state: 'linked', status: 200 },
    ],
    '2026-10-30',
  )
  assert.deepEqual(next.sameAs, ['https://b.example/q', 'https://c.example/r'])
  assert.equal(next.profiles_pending.length, 1)
  assert.equal(next.profiles_pending[0].url, 'https://a.example/p')
  assert.equal(changes.length, 2)
  assert.equal(stops.length, 1)
  assert.match(stops[0], /NAMED STOP \[ENTITY_LINKBACK_MISSING\]/)
  // unreachable and unverifiable change nothing
  const quiet = heal(base, [{ url: 'https://a.example/p', state: 'unreachable', status: 503 }, { url: 'https://c.example/r', state: 'unverifiable', status: 200 }], '2026-10-30')
  assert.deepEqual(quiet.next.sameAs, base.sameAs)
  assert.equal(quiet.changes.length, 0)
})
