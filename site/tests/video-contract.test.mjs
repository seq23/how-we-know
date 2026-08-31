import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
const questions = JSON.parse(fs.readFileSync('content/questions.json', 'utf8'))
const queue = JSON.parse(fs.readFileSync('production/video-queue.json', 'utf8'))
test('all twenty queued videos map one-to-one to canonical articles', () => {
  assert.equal(queue.length, 20)
  for (const item of queue) {
    const question = questions.find((record) => record.slug === item.articleSlug)
    assert.ok(question, item.query)
    assert.equal(item.query, question.question)
    assert.equal(item.articlePath, `/questions/${question.slug}`)
  }
})
