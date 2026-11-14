/**
 * A mailto link Cloudflare leaves alone.
 *
 * The howweknowdeep.com zone has Email Address Obfuscation on, which rewrites every
 * address in the HTML into a link to /cdn-cgi/l/email-protection. Crawlers follow
 * that link and get a dead page, so /privacy/ and /terms/ each linked to a broken
 * page (site crawl, 10 Nov 2026). email_off / email_on are Cloudflare's documented
 * opt-out; React cannot emit an HTML comment, so the link is written as markup.
 * scripts/validate-built-html.mjs fails any built page with a mailto outside them.
 */
const escape = (value: string) =>
  value.replace(/&/gu, '&amp;').replace(/</gu, '&lt;').replace(/>/gu, '&gt;').replace(/"/gu, '&quot;')

export function PlainEmail({ address }: { address: string }) {
  const safe = escape(address)
  return (
    <span
      dangerouslySetInnerHTML={{ __html: `<!--email_off--><a href="mailto:${safe}">${safe}</a><!--email_on-->` }}
    />
  )
}
