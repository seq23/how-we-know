import { createFileRoute } from '@tanstack/react-router'
import { NotFound } from '~/components/NotFound'
import { site } from '~/lib/site'

/**
 * Prerendered so the build can emit a real `404.html`. Cloudflare Pages serves
 * that file with a genuine 404 status for any unmatched path; without it, Pages
 * falls back to `index.html` with a 200 and every typo'd URL becomes a soft
 * duplicate of the homepage.
 *
 * This route deliberately emits NO canonical link. A 404 that canonicalises to
 * "/" tells crawlers the junk URL is the homepage. It is always noindex,
 * regardless of the site-wide indexing switch.
 */
export const Route = createFileRoute('/404')({
  head: () => ({
    meta: [
      { title: `Page not found | ${site.name}` },
      { name: 'description', content: 'This page does not exist.' },
      { name: 'robots', content: 'noindex,nofollow' },
    ],
  }),
  component: NotFound,
})
