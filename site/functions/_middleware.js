/**
 * Host canonicalisation, for the one host that is allowed to serve this site.
 *
 * www.howweknowdeep.com served the whole site at 200 next to the apex, and so did
 * how-we-know.pages.dev. The rules meant to stop that lived in public/_redirects
 * as absolute-URL sources:
 *
 *   https://www.howweknowdeep.com/* https://howweknowdeep.com/:splat 301!
 *
 * That is Netlify syntax. Cloudflare Pages matches _redirects by PATH only and
 * never looks at the Host header, so those two rules had never fired since the
 * day they were written — verified on 2026-10-25, when a GET of
 * https://www.howweknowdeep.com/ answered 200 with the full homepage, not a 301.
 * The same defect, with the same two dead rules, had already been found and fixed
 * in the approvalprep repository on its own domain.
 *
 * Two hosts serving one site is not fatal on its own — the canonical tag names
 * the apex — but it splits every signal Google collects until it decides to
 * believe the hint, and a 301 is a directive where a canonical is a hint. On a
 * site whose entire purpose is being cited, the address has to be one address.
 *
 * This is a Pages root middleware, so it sees every request including static
 * assets, and it must stay cheap: one hostname comparison, then next().
 *
 * scripts/validate-launch-flags.mjs asserts that this file exists, that the host
 * it names is the canonicalOrigin in site-flags.json, and that public/_redirects
 * carries no absolute-URL source ever again.
 */

const CANONICAL_HOST = 'howweknowdeep.com'

/**
 * Hosts that are legitimately not the canonical one and must be left alone:
 * every Pages deployment preview (each one has its own *.pages.dev hostname and
 * is how a change is checked before it is promoted) and local development.
 *
 * The project's own how-we-know.pages.dev is deliberately NOT exempt: it is a
 * second public address for the production site, and leaving it indexable is the
 * other half of the same split.
 */
const isDevelopmentHost = (hostname) =>
  hostname === 'localhost' ||
  hostname === '127.0.0.1' ||
  hostname === '0.0.0.0' ||
  // <hash>.how-we-know.pages.dev and <branch>.how-we-know.pages.dev are previews.
  /\.how-we-know\.pages\.dev$/.test(hostname)

export const onRequest = (context) => {
  const { request, next } = context
  const url = new URL(request.url)
  const hostname = url.hostname.toLowerCase()

  if (hostname === CANONICAL_HOST || isDevelopmentHost(hostname)) return next()

  // Redirecting a POST turns it into a GET, which would silently break anything
  // posted to the wrong host. Only navigations get moved.
  if (request.method !== 'GET' && request.method !== 'HEAD') return next()

  return Response.redirect(`https://${CANONICAL_HOST}${url.pathname}${url.search}`, 301)
}
