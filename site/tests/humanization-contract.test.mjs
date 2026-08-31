import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'

const root = process.cwd()
const finalDir = path.join(root, 'production/scripts/final')
const files = fs.readdirSync(finalDir).filter((name) => /^\d{2}-.*\.md$/.test(name)).sort()

function words(text) {
  return (text.match(/\b[\p{L}\p{N}’'-]+\b/gu) || []).length
}

test('all twenty scripts have a distinct humanized editorial contract', () => {
  assert.equal(files.length, 20)
  const opens = new Set()
  const variations = new Set()
  for (const name of files) {
    const md = fs.readFileSync(path.join(finalDir, name), 'utf8')
    const plain = fs.readFileSync(path.join(root, 'production/scripts/plaintext', name.replace(/\.md$/, '.txt')), 'utf8')
    const pass = fs.readFileSync(path.join(root, 'production/human-pass', name), 'utf8')
    assert.ok(words(plain) >= 1150 && words(plain) <= 1350, `${name} length`)
    assert.equal((md.match(/\[HUMAN\]/g) || []).length, 1, `${name} Markdown human marker`)
    assert.equal((plain.match(/\[HUMAN\]/g) || []).length, 1, `${name} plaintext human marker`)
    assert.match(md, /### Evidence limit/)
    assert.match(md, /Final human watch-through: PENDING/)
    assert.match(pass, /Watch the final rendered MP4 from beginning to end/)
    const open = md.match(/### (?:Cold open|Opening)\n\n([\s\S]*?)(?=\n### )/)?.[1]
    assert.ok(open)
    assert.ok(!opens.has(open))
    opens.add(open)
    const variation = pass.match(/## Structural variation\n\n([^\n]+)/)?.[1]
    assert.ok(variation)
    assert.ok(!variations.has(variation))
    variations.add(variation)
  }
})

test('key-claim audit has three resolved entries per video', () => {
  const audit = JSON.parse(fs.readFileSync(path.join(root, 'production/research/number-verification.json'), 'utf8'))
  assert.equal(audit.claims.length, 60)
  for (let sequence = 1; sequence <= 20; sequence += 1) {
    const claims = audit.claims.filter((claim) => claim.sequence === sequence)
    assert.equal(claims.length, 3)
    assert.ok(claims.every((claim) => !/unverified|requires|pending/i.test(claim.status)))
  }
})

test('every digit-bearing narration sentence is source-mapped', () => {
  const audit = JSON.parse(fs.readFileSync(path.join(root, 'production/research/number-verification-exhaustive.json'), 'utf8'))
  const current = []
  for (let sequence = 1; sequence <= files.length; sequence += 1) {
    const md = fs.readFileSync(path.join(finalDir, files[sequence - 1]), 'utf8')
    const narration = md.match(/## Narration\n([\s\S]*?)(?=\n## Human fingerprint gate)/)?.[1] || ''
    const compact = narration.replace(/^### .*$/gm, '').replace(/\s+/g, ' ').trim()
    for (const sentence of compact.split(/(?<=[.!?])\s+/).filter((item) => /\d/.test(item))) current.push({ sequence, sentence })
  }
  assert.equal(audit.sentences.length, current.length)
  for (let index = 0; index < current.length; index += 1) {
    assert.equal(audit.sentences[index].sequence, current[index].sequence)
    assert.equal(audit.sentences[index].sentence, current[index].sentence)
    assert.ok(audit.sentences[index].sourceUrls.length > 0)
  }
})
