import flags from '../../site-flags.json'
import entityJson from '../../entity.json'

/** THE NOINDEX SWITCH lives in site-flags.json. Do not hardcode it anywhere else. */
export const searchIndexingEnabled: boolean = flags.searchIndexingEnabled
export const webAnalyticsToken: string = flags.webAnalyticsToken
/** Published on /privacy and /terms. Empty => those pages say so explicitly. See site-flags.json. */
export const privacyContactEmail: string = flags.privacyContactEmail

export const site = {
  name: 'How We Know',
  description:
    'How we know what we know. Evidence-backed answers that show the instrument, the proxy, or the observation behind each figure — and say plainly where the evidence stops.',
  /** Canonical origin. Apex from day one, so canonical tags never need retrofitting. */
  origin: import.meta.env.VITE_SITE_URL || flags.canonicalOrigin,
  tagline: 'evidence-backed answers about the deep ocean',
  author: 'How We Know',
  publisher: 'How We Know',
  themeColor: '#04111f',
  youtubeHandle: '@howweknowdeep',
  youtubeUrl: 'https://youtube.com/@howweknowdeep',
} as const

/**
 * The entity: the one definition in site/entity.json of who publishes this site,
 * which profiles are the same entity (sameAs), and the parent organisation.
 * schema.ts reads it; scripts/validate-entity-graph.mjs fails the build if the
 * emitted JSON-LD drifts from it; the weekly entity-backlink-watch keeps sameAs
 * honest (dead URLs removed, pending profiles promoted) by PR.
 */
export const entity = {
  id: entityJson['@id'],
  name: entityJson.name,
  logo: entityJson.logo,
  description: entityJson.description,
  sameAs: entityJson.sameAs as string[],
  /** Spry Labs, whose entity home is billionairehighperformancecoach.com/spry-labs. */
  parentOrganization: entityJson.parentOrganization,
}

/**
 * The absolute URL for a path, normalised to the form the server actually serves.
 *
 * Cloudflare Pages emits every route as `<path>/index.html`, so it serves
 * `/questions/x/` and 308-redirects `/questions/x` to it. Until 2026-08-31 this
 * function returned the slash-less form, so every canonical tag and every og:url
 * on the site pointed at a URL that redirects — the page declaring its canonical
 * address to be one the server will not serve directly. Search engines follow the
 * redirect, but on a site whose entire purpose is being cited, the canonical
 * should be the final URL, not a hop away from it.
 *
 * A trailing slash is added to route paths only. Files keep their names: a path
 * with an extension (`/og-default.svg`, `/robots.txt`, `/sitemap.xml`) is a file,
 * not a directory, and slashing it would 404.
 */
export function absoluteUrl(path: string) {
  const url = new URL(path, site.origin)
  const isFile = /\.[a-z0-9]+$/i.test(url.pathname)
  if (!isFile && !url.pathname.endsWith('/')) url.pathname += '/'
  return url.toString()
}
