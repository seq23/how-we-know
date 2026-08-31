import test from 'node:test'
import assert from 'node:assert/strict'
import crypto from 'node:crypto'
import fs from 'node:fs'
import { execFileSync } from 'node:child_process'

const baseFiles = ['public/sitemap.xml', 'public/robots.txt', 'public/llms.txt']
const files = () => [...baseFiles, ...(fs.existsSync('public/video-sitemap.xml') ? ['public/video-sitemap.xml'] : [])]
const digest = () =>
  Object.fromEntries(
    files().map((file) => [file, crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex')]),
  )

test('static machine-readable assets regenerate deterministically', () => {
  execFileSync(process.execPath, ['scripts/generate-static-assets.mjs'], { stdio: 'pipe' })
  const first = digest()
  execFileSync(process.execPath, ['scripts/generate-static-assets.mjs'], { stdio: 'pipe' })
  assert.deepEqual(digest(), first)
})
