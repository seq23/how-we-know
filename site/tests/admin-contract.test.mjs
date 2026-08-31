import assert from 'node:assert/strict'
import fs from 'node:fs'
import test from 'node:test'

const read = (file) => fs.readFileSync(file, 'utf8')

test('credentialless admin stays outside public discovery and provider APIs', () => {
  const route = read('src/routes/admin.tsx')
  const sitemap = read('public/sitemap.xml')
  assert.match(route, /noindex, nofollow, noarchive/)
  assert.doesNotMatch(route, /api\.github\.com|import\.meta\.env\.(?:GITHUB_TOKEN|YOUTUBE_TOKEN)/)
  assert.doesNotMatch(sitemap, /\/admin/)
})

test('human-pass workflow is a real receipt-backed GitHub action', () => {
  const workflow = read('.github/workflows/approve-human-pass.yml')
  assert.match(workflow, /workflow_dispatch:/)
  assert.match(workflow, /contents: write/)
  assert.match(workflow, /approve_human_pass\.py/)
  assert.match(workflow, /git commit/)
  assert.match(workflow, /git push/)
})

test('admin snapshot covers the complete launch slate', () => {
  const status = JSON.parse(read('content/admin-status.json'))
  assert.equal(status.humanPass.total, 20)
  assert.equal(status.humanPass.items.length, 20)
})
