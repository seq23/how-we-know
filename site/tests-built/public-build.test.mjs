// Reads the emitted static build (.output/public) the way a stranger's browser
// would, after `vite build`. It runs as the last step of `npm run build`, which
// is the site-check CI gate, so a PR that brings any of this back cannot land.
//
// Security audit row 4 (2026-11-23): /admin/ was a public noindex page that
// printed the YouTube upload commands and a local credential-file location.
// noindex hides a page from search, not from anyone who types the URL. The page
// was removed on 2026-11-27; operator steps live in RUNBOOK.md, not the site.
//
// Audit row 7: the deploy is static Pages (`wrangler pages deploy
// .output/public`), which is why the TanStack Start server-function advisory was
// unreachable. This file also fails if the build ever stops being static.
//
// PUBLIC_DIR may point at another directory (used for the mutation proof).
import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import test from 'node:test'

const publicDir = path.resolve(process.env.PUBLIC_DIR || '.output/public')

function walk(dir) {
  const out = []
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name)
    if (entry.isDirectory()) out.push(...walk(full))
    else out.push(full)
  }
  return out
}

const TEXT = /\.(html|js|mjs|css|json|txt|xml|webmanifest)$/u

// Operator-only details that must never ship in a public file. Each marker is
// specific to the removed page's content, not a word a normal page might use.
const PRIVATE_MARKERS = [
  /youtube-token\.json/iu,
  /YOUTUBE_TOKEN_JSON/u,
  /~\/secure\//u,
  /upload_batch\.py/u,
  /sync_site_from_receipts\.py/u,
]

test('the build exists and holds the real public pages (never passes on an empty build)', () => {
  assert.ok(fs.existsSync(publicDir), `no build at ${publicDir}; run vite build first`)
  const home = path.join(publicDir, 'index.html')
  assert.ok(fs.existsSync(home), 'home page index.html is missing')
  const homeHtml = fs.readFileSync(home, 'utf8')
  assert.match(homeHtml, /<title>[^<]*How We Know[^<]*<\/title>/u, 'home page has no How We Know title')
  const questionsDir = path.join(publicDir, 'questions')
  const questionPages = fs.existsSync(questionsDir)
    ? fs.readdirSync(questionsDir).filter((d) => fs.existsSync(path.join(questionsDir, d, 'index.html')))
    : []
  assert.ok(questionPages.length >= 5, `expected at least 5 prerendered question pages, saw ${questionPages.length}`)
  const one = fs.readFileSync(path.join(questionsDir, questionPages[0], 'index.html'), 'utf8')
  assert.match(one, /<h1[^>]*>[^<]+/u, `question page ${questionPages[0]} renders no heading`)
  assert.ok(fs.existsSync(path.join(publicDir, '404.html')), '404.html is missing, so /admin/ would fall back to a 200')
})

test('no /admin page is in the public build', () => {
  const adminDir = path.join(publicDir, 'admin')
  assert.ok(!fs.existsSync(adminDir), `${adminDir} exists: the operator page is back in the public build`)
  assert.ok(!fs.existsSync(path.join(publicDir, 'admin.html')), 'admin.html exists in the public build')
})

test('no public file carries an upload command or a local credential path', () => {
  const files = walk(publicDir).filter((f) => TEXT.test(f))
  assert.ok(files.length > 20, `only ${files.length} text files scanned; the build looks empty`)
  const hits = []
  for (const file of files) {
    const body = fs.readFileSync(file, 'utf8')
    for (const marker of PRIVATE_MARKERS) {
      if (marker.test(body)) hits.push(`${path.relative(publicDir, file)} matches ${marker}`)
    }
  }
  assert.deepEqual(hits, [], `private operator details in the public build:\n${hits.join('\n')}`)
})

test('the deploy stays static: no server worker, no server-function route', () => {
  assert.ok(!fs.existsSync(path.join(publicDir, '_worker.js')), '_worker.js in the build: the deploy is no longer static')
  const fnDir = path.resolve(publicDir, '../../functions')
  if (process.env.PUBLIC_DIR) return // a fixture directory has no sibling functions/ to check
  const fns = walk(fnDir).map((f) => path.relative(fnDir, f))
  assert.deepEqual(fns, ['_middleware.js'], `Pages functions grew beyond the host middleware: ${fns.join(', ')}`)
  assert.doesNotMatch(fs.readFileSync(path.join(fnDir, '_middleware.js'), 'utf8'), /_serverFn/u)
})
