import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'

const questions = JSON.parse(fs.readFileSync('content/questions.json', 'utf8'))
const scripts = JSON.parse(fs.readFileSync('production/scripts/index.json', 'utf8'))
const queue = JSON.parse(fs.readFileSync('production/video-queue.json', 'utf8'))
const rights = JSON.parse(fs.readFileSync('production/asset-rights-manifest.json', 'utf8'))

test('every launch question has a production-ready package', () => {
  assert.equal(scripts.length, questions.length)
  assert.equal(queue.length, questions.length)
  for (let i = 0; i < questions.length; i += 1) {
    assert.equal(queue[i].articleSlug, questions[i].slug)
    assert.ok(['production-ready-unrendered', 'production-ready-unrendered-human-pass-required'].includes(queue[i].status))
    assert.equal(queue[i].rightsManifestReady, true)
    assert.ok(scripts[i].wordCount >= 1150)
  }
})

test('all admitted media is commercially editable and hashed', () => {
  assert.ok(rights.length >= 64)
  for (const item of rights) {
    assert.equal(item.assetStatus, 'approved')
    assert.equal(item.commercialUseAllowed, true)
    assert.equal(item.modificationAllowed, true)
    assert.match(item.fileSha256, /^[a-f0-9]{64}$/)
    assert.ok(fs.existsSync(item.localFilename))
  }
})
