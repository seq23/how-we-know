import { absoluteUrl, site } from './site'
import { seoCopy } from './seo-copy'
import { breadcrumbSchema, jsonLdScript, webPageSchema } from './schema'

/** The shared OG card: a real raster image on this site's own host, with its dimensions declared. */
export const ogImage = { path: '/og-default.png', width: 1200, height: 630 } as const

const routeKey = (path: string) => {
  const clean = path.split(/[?#]/)[0]
  return clean !== '/' && clean.endsWith('/') ? clean.slice(0, -1) : clean
}

/** The labels a crumb shows for the one segment above a content page. */
const parentCrumb: Record<string, { name: string; path: string }> = {
  questions: { name: 'Questions', path: '/questions' },
  zones: { name: 'Ocean zones', path: '/zones' },
  creatures: { name: 'Creatures', path: '/creatures' },
  methods: { name: 'How we know it', path: '/methods' },
}

function crumbs(path: string, label: string) {
  const key = routeKey(path)
  if (key === '/') return null
  const segments = key.split('/').filter(Boolean)
  const trail = [{ name: 'Home', path: '/' }]
  if (segments.length > 1) {
    const parent = parentCrumb[segments[0]]
    if (parent) trail.push(parent)
  }
  trail.push({ name: label, path: key })
  return breadcrumbSchema(trail)
}

/**
 * Every page's head, from one place.
 *
 * The title and description come from src/lib/seo-copy.ts when that table has an
 * entry for the path, and from the caller otherwise. A page's visible summary is
 * written for a reader who is already on the page; a search result line has a
 * hard length band. Those are two jobs, so they are two strings.
 *
 * It also returns the per-page JSON-LD that every page needs and no page had:
 * a WebPage node tying the page to the site, and a BreadcrumbList on every page
 * below the homepage. A route that adds schema of its own concatenates onto
 * these rather than replacing them — spreading pageMeta() and then setting
 * `scripts` silently dropped both.
 */
export function pageMeta(
  title: string,
  description: string,
  path: string,
  type: 'website' | 'article' = 'website',
) {
  const copy = seoCopy[routeKey(path)]
  const bareTitle = copy?.title ?? title
  const text = copy?.description ?? description
  const fullTitle = bareTitle === site.name ? bareTitle : `${bareTitle} | ${site.name}`
  const url = absoluteUrl(path)
  const image = absoluteUrl(ogImage.path)
  const breadcrumb = crumbs(path, bareTitle)
  return {
    meta: [
      { title: fullTitle },
      { name: 'description', content: text },
      { property: 'og:title', content: fullTitle },
      { property: 'og:description', content: text },
      { property: 'og:type', content: type },
      { property: 'og:url', content: url },
      { property: 'og:site_name', content: site.name },
      { property: 'og:image', content: image },
      { property: 'og:image:width', content: String(ogImage.width) },
      { property: 'og:image:height', content: String(ogImage.height) },
      { property: 'og:image:alt', content: `${site.name}: ${site.tagline}` },
      { property: 'og:locale', content: 'en_US' },
      { name: 'twitter:card', content: 'summary_large_image' },
      { name: 'twitter:title', content: fullTitle },
      { name: 'twitter:description', content: text },
      { name: 'twitter:image', content: image },
    ],
    links: [{ rel: 'canonical', href: url }],
    scripts: [
      jsonLdScript(webPageSchema({ url, name: fullTitle, description: text, type })),
      ...(breadcrumb ? [jsonLdScript(breadcrumb)] : []),
    ],
  }
}
