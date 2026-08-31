/**
 * Promotes the prerendered /404 route to `.output/public/404.html`.
 *
 * Cloudflare Pages serves `404.html` with a real 404 status for any unmatched
 * path. Without it Pages falls back to `index.html` with a 200, so every
 * mistyped or stale URL returns the homepage — same title, same description,
 * and a canonical pointing at "/". That is a soft 404: it invites crawlers to
 * index junk URLs and collapses them onto the homepage.
 *
 * Runs after `vite build`, because it operates on prerendered output.
 */
import fs from 'node:fs'
import path from 'node:path'

const publicDir = path.join(process.cwd(), '.output/public')
const source = path.join(publicDir, '404/index.html')
const target = path.join(publicDir, '404.html')

if (!fs.existsSync(source)) {
  throw new Error(
    `Prerendered 404 is missing at ${source}. The /404 route must be in the vite prerender inventory.`,
  )
}

const html = fs.readFileSync(source, 'utf8')

// A 404 must never claim to be another URL.
if (/rel=["']canonical["']/u.test(html)) {
  throw new Error('The 404 page emits a canonical link; it must not.')
}
if (!/name=["']robots["'][^>]*noindex/u.test(html)) {
  throw new Error('The 404 page is missing a noindex robots meta tag.')
}
if (!html.includes('<title>')) {
  throw new Error('The 404 page has no title.')
}

fs.writeFileSync(target, html)
console.log(`Emitted 404.html (${html.length} bytes) with no canonical and noindex set.`)
