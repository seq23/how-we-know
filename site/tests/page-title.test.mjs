import { test } from 'node:test'
import assert from 'node:assert/strict'
import { pageTitle } from '../src/lib/page-title.mjs'
test('search titles keep the query first and trim at a word boundary', () => {
  const query = 'Why do deep sea animals survive the enormous pressure at the bottom of the ocean?'
  const result = pageTitle(query)
  assert.ok(result.length <= 65 && result.length >= 30)
  assert.ok(query.startsWith(result.slice(0, -1)))
  assert.equal(pageTitle('Why does bread rise?'), 'Why does bread rise? | How We Know')
  const fitting = 'Why do deep sea animals look different from surface fish?'
  assert.equal(pageTitle(fitting), fitting)
})
