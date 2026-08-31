import fs from 'node:fs'
import { assert, readJson } from './validation-helpers.mjs'

const questions = readJson('content/questions.json')
const zones = readJson('content/zones.json')
const creatures = readJson('content/creatures.json')

const requiredFiles = [
  'src/routes/__root.tsx',
  'src/routes/index.tsx',
  'src/routes/questions.index.tsx',
  'src/routes/questions.$question.tsx',
  'src/routes/zones.index.tsx',
  'src/routes/zones.$zone.tsx',
  'src/routes/creatures.index.tsx',
  'src/routes/creatures.$creature.tsx',
  'src/routes/watch.index.tsx',
  'src/routes/explore.tsx',
  'src/routes/admin.tsx',
  'src/routes/methods.index.tsx',
  'src/routes/methods.$method.tsx',
  'src/routes/privacy.tsx',
  'src/routes/terms.tsx',
  'public/sitemap.xml',
  'public/robots.txt',
  'public/llms.txt',
]
for (const file of requiredFiles) assert(fs.existsSync(file), `Missing required file: ${file}`)

const activeMethodIds = [...new Set(questions.map((item) => item.method))]
assert(activeMethodIds.length > 0, 'Route validation resolved zero active method ids')

const expectedPaths = [
  '/',
  '/questions',
  '/methods',
  ...activeMethodIds.map((id) => `/methods/${id}`),
  '/zones',
  '/creatures',
  '/watch',
  '/explore',
  '/methodology',
  '/editorial-policy',
  '/privacy',
  '/terms',
  ...questions.map((item) => `/questions/${item.slug}`),
  ...zones.map((item) => `/zones/${item.slug}`),
  ...creatures.map((item) => `/creatures/${item.slug}`),
]

const sitemap = fs.readFileSync('public/sitemap.xml', 'utf8')
const llms = fs.readFileSync('public/llms.txt', 'utf8')
  // The sitemap carries canonical URLs, which since 2026-08-31 end in a trailing
  // slash for route paths - Cloudflare Pages serves `<path>/index.html`, so the
  // slash-less form 308-redirects, and a canonical pointing at a redirect is a real
  // defect on a site whose purpose is being cited. This check is about the route
  // universe, not URL spelling, so normalise both sides rather than asserting one
  // spelling and quietly forbidding the correct one.
  const routeKey = (p) => (p !== '/' && p.endsWith('/') ? p.slice(0, -1) : p)
const sitemapLocations = [...sitemap.matchAll(/<loc>([^<]+)<\/loc>/g)].map((match) => routeKey(new URL(match[1]).pathname))
assert(sitemapLocations.length === expectedPaths.length, 'Sitemap route count does not match the approved universe')
assert(new Set(sitemapLocations).size === sitemapLocations.length, 'Sitemap contains duplicate URLs')
for (const pathname of expectedPaths) {
  assert(sitemapLocations.includes(pathname), `Sitemap is missing ${pathname}`)
}
for (const question of questions) {
  assert(llms.includes(`/questions/${question.slug}`), `llms.txt is missing ${question.slug}`)
  assert(llms.includes(question.directAnswer), `llms.txt is missing the canonical answer for ${question.slug}`)
}


const publishedVideos = questions.filter((question) => question.video.status === 'published')
const videoSitemapExists = fs.existsSync('public/video-sitemap.xml')
if (publishedVideos.length === 0) {
  assert(!videoSitemapExists, 'Video sitemap must remain absent when no video is public')
  assert(!fs.readFileSync('public/robots.txt', 'utf8').includes('video-sitemap.xml'), 'Robots must not advertise an empty video sitemap')
} else {
  assert(videoSitemapExists, 'Published videos require a video sitemap')
  const videoSitemap = fs.readFileSync('public/video-sitemap.xml', 'utf8')
  for (const question of publishedVideos) assert(videoSitemap.includes(`/questions/${question.slug}`), `Video sitemap is missing ${question.slug}`)
}

const viteConfig = fs.readFileSync('vite.config.ts', 'utf8')
for (const pathname of ['/questions/${item.slug}', '/zones/${item.slug}', '/creatures/${item.slug}', '/methods/${id}']) {
  assert(viteConfig.includes(pathname), `Vite prerender inventory is missing pattern ${pathname}`)
}
assert(viteConfig.includes('failOnError: true'), 'Prerendering must fail closed')
assert(viteConfig.includes("'/admin'"), 'Admin route is missing from the explicit prerender inventory')

console.log(`Route and static-asset validation passed (${expectedPaths.length} routes).`)
