import fs from 'node:fs'
import path from 'node:path'

const root = process.cwd()
const readJson = (relativePath) =>
  JSON.parse(fs.readFileSync(path.join(root, relativePath), 'utf8'))

const questions = readJson('content/questions.json')
const taxonomy = fs.readFileSync(path.join(root, 'src/lib/taxonomy.ts'), 'utf8')
// Only methods a published page actually carries become routes. No empty shelves.
const activeMethodIds = [...new Set(questions.map((item) => item.method))].filter((id) =>
  taxonomy.includes(`id: '${id}'`),
)
if (activeMethodIds.length === 0) throw new Error('No active method ids resolved from content')
const zones = readJson('content/zones.json')
const creatures = readJson('content/creatures.json')
const flags = readJson('site-flags.json')
const origin = process.env.VITE_SITE_URL || flags.canonicalOrigin

// Match what the server serves. Cloudflare Pages emits `<path>/index.html`, so it
// serves `/questions/x/` and 308-redirects `/questions/x`. A sitemap of redirecting
// URLs and canonicals pointing at redirects is a real defect on a site whose whole
// purpose is being cited - fixed 2026-08-31 alongside absoluteUrl() in src/lib/site.ts,
// which is the same rule for the same reason. Files keep their names: anything with
// an extension is not a directory and slashing it would 404.
const canonicalUrl = (pathname) => {
  const u = new URL(pathname, origin)
  if (!/\.[a-z0-9]+$/i.test(u.pathname) && !u.pathname.endsWith('/')) u.pathname += '/'
  return u.toString()
}

const paths = [
  '/',
  '/questions',
  '/zones',
  '/creatures',
  '/watch',
  '/explore',
  '/methods',
  '/methodology',
  '/editorial-policy',
  '/privacy',
  '/terms',
  ...activeMethodIds.map((id) => `/methods/${id}`),
  ...questions.map((item) => `/questions/${item.slug}`),
  ...zones.map((item) => `/zones/${item.slug}`),
  ...creatures.map((item) => `/creatures/${item.slug}`),
]


const xmlEscape = (value) =>
  String(value)
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&apos;')

const parseDurationSeconds = (value) => {
  const match = /^PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?$/.exec(value || '')
  if (!match) return null
  return Number(match[1] || 0) * 3600 + Number(match[2] || 0) * 60 + Number(match[3] || 0)
}

const publishedVideos = questions.filter((question) => {
  const video = question.video
  return (
    video.status === 'published' &&
    video.videoId &&
    video.title &&
    video.descriptionFirstLine &&
    video.thumbnailUrl &&
    video.uploadDate &&
    video.duration &&
    video.transcript
  )
})

const videoSitemapPath = path.join(root, 'public/video-sitemap.xml')
if (publishedVideos.length) {
  const entries = publishedVideos
    .map((question) => {
      const video = question.video
      const durationSeconds = parseDurationSeconds(video.duration)
      const duration = durationSeconds ? `\n      <video:duration>${durationSeconds}</video:duration>` : ''
      return `  <url>\n    <loc>${xmlEscape(canonicalUrl(`/questions/${question.slug}`))}</loc>\n    <video:video>\n      <video:thumbnail_loc>${xmlEscape(video.thumbnailUrl)}</video:thumbnail_loc>\n      <video:title>${xmlEscape(video.title)}</video:title>\n      <video:description>${xmlEscape(video.descriptionFirstLine)}</video:description>\n      <video:player_loc>${xmlEscape(`https://www.youtube.com/embed/${video.videoId}`)}</video:player_loc>${duration}\n      <video:publication_date>${xmlEscape(video.uploadDate)}</video:publication_date>\n    </video:video>\n  </url>`
    })
    .join('\n')
  fs.writeFileSync(
    videoSitemapPath,
    `<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" xmlns:video="http://www.google.com/schemas/sitemap-video/1.1">\n${entries}\n</urlset>\n`,
  )
} else if (fs.existsSync(videoSitemapPath)) {
  fs.rmSync(videoSitemapPath)
}

const urls = paths
  .map((pathname) => `  <url><loc>${canonicalUrl(pathname)}</loc></url>`)
  .join('\n')

fs.writeFileSync(
  path.join(root, 'public/sitemap.xml'),
  `<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n${urls}\n</urlset>\n`,
)

// Driven by the single noindex switch in site-flags.json.
const robots = flags.searchIndexingEnabled
  ? `User-agent: *\nAllow: /\n\nSitemap: ${new URL('/sitemap.xml', origin)}${publishedVideos.length ? `\nSitemap: ${new URL('/video-sitemap.xml', origin)}` : ''}\n`
  : `# Search indexing is disabled via site-flags.json (searchIndexingEnabled: false).\n# Flip that one flag and rebuild to open the site to crawlers.\nUser-agent: *\nDisallow: /\n`
fs.writeFileSync(path.join(root, 'public/robots.txt'), robots)

// Host canonicalisation. Only emitted once the custom domain is actually live,
// otherwise the *.pages.dev staging URL would redirect to a host that does not
// resolve yet.
const canonicalHost = new URL(origin).host
const redirects = flags.customDomainLive
  ? [
      `https://www.${canonicalHost}/* ${origin}/:splat 301!`,
      `https://:project.pages.dev/* ${origin}/:splat 301!`,
      '',
    ].join('\n')
  : `# customDomainLive is false in site-flags.json, so no host redirects are active.\n# Flip it after ${canonicalHost} is attached and resolving, then rebuild.\n`
fs.writeFileSync(path.join(root, 'public/_redirects'), redirects)

const llms = [
  `# ${origin}`,
  '',
  '## Canonical question answers',
  ...questions.flatMap((question) => [
    `- ${question.question}: ${canonicalUrl(`/questions/${question.slug}`)}`,
    `  ${question.directAnswer}`,
  ]),
  '',
  '## Ocean zones',
  ...zones.map((zone) => `- ${zone.name}: ${new URL(`/zones/${zone.slug}`, origin)}`),
  '',
  '## Creature references',
  ...creatures.map(
    (creature) => `- ${creature.name}: ${new URL(`/creatures/${creature.slug}`, origin)}`,
  ),
  '',
  '## How we know it — evidence method index',
  `- Method index: ${new URL('/methods', origin)}`,
  ...activeMethodIds.map((id) => `- ${id}: ${new URL(`/methods/${id}`, origin)}`),
  '',
  '## Interactive and video surfaces',
  `- Depth explorer: ${new URL('/explore', origin)}`,
  `- Watch library: ${new URL('/watch', origin)}`,
  '',
  '## Editorial controls',
  `- Methodology: ${new URL('/methodology', origin)}`,
  `- Editorial policy: ${new URL('/editorial-policy', origin)}`,
  `- Privacy policy: ${new URL('/privacy', origin)}`,
  `- Terms of Service: ${new URL('/terms', origin)}`,
]

fs.writeFileSync(path.join(root, 'public/llms.txt'), `${llms.join('\n')}\n`)

console.log(
  `Generated sitemap, robots, _redirects and llms.txt for ${paths.length} routes ` +
    `(indexing ${flags.searchIndexingEnabled ? 'ENABLED' : 'DISABLED'}, ` +
    `custom domain ${flags.customDomainLive ? 'LIVE' : 'not live'}).`,
)
