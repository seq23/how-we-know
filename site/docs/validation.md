# Validation Contract

## Structural validation in this artifact

- JSON parsing and unique slugs/IDs.
- Ten admitted questions and ten one-to-one video queue records.
- Direct answers limited to 40 words.
- Minimum section, FAQ and comparison depth.
- Source and related-record integrity.
- Explorer route, canonical article link, depth constant, controls, and reduced-motion behavior.
- Sitemap and `llms.txt` route coverage.
- Conditional video sitemap generation.
- Dormant/published video metadata rules.
- Traffic-source rule integrity and KPI truth contract.
- Optional analytics boundary and privacy disclosure.
- YouTube API Services policy compliance (`scripts/validate-legal-policy.mjs`). Nineteen literal
  elements the YouTube API audit is graded on must be present on `/privacy`, `/terms` and the
  homepage footer: the YouTube Terms of Service link, the Google Privacy Policy link, the "uses
  YouTube API Services" notice, the requested scopes, the cookie disclosure, the 30-day
  refresh-or-delete rule, the data-deletion section, the 7-day post-revocation deletion commitment,
  the revocation links, the contact section, and the policy links on the homepage itself. Each
  requirement names the Developer Policy clause it comes from. Runs inside `npm run validate`
  against the route sources, and again with `--live` inside `npm run validate:live` against the
  deployed HTML. Hard-fails if its check set is empty or truncated.
- Rights-manifest duplicate, hash, commercial-use and attribution rules.
- ZIP root and required-file checks during packaging.

## Artifact report

The executed check results are recorded in `docs/validation-report.md`.

## Local validation still required

- Dependency installation and lockfile creation.
- TanStack route regeneration.
- TypeScript compilation against installed framework packages.
- Production build and prerender output inspection.
- Browser journeys at mobile and desktop widths.
- Explorer behavior with real browser scrolling and reduced-motion preferences.
- Cloudflare or alternate deployment and canonical-domain replacement.
- Google Rich Results and video-sitemap testing after a real video is published.
- Analytics and consent validation if tracking is enabled.
