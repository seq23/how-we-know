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
- Entity graph (`scripts/validate-entity-graph.mjs`). `entity.json` is the one definition of the
  publisher: `@id`, name, logo, description, `sameAs` (only profiles that resolve now),
  `parentOrganization` (Spry Labs) and `profiles_pending`. Inside `npm run validate` it checks the
  file (no self-host `sameAs`, no duplicates, nothing both live and pending, parent is Spry Labs);
  with `--built`, at the end of `npm run build`, every built page's Organization node must carry
  exactly that `sameAs`, name, description, logo and parent. Zero pages or zero matching nodes
  fails. The weekly `entity-backlink-watch` workflow keeps `sameAs` true: dead URLs removed and
  pending profiles promoted by PR, a missing link-back filed as one named-stop issue.
- Page shape in the emitted HTML (`scripts/validate-built-html.mjs`). Runs at the end of
  `npm run build` against `.output/public`, because every defect it catches is invisible in source
  and plain in the HTML a crawler reads. Titles, descriptions, social tags, the Organization node,
  a `WebPage` on every page, a `BreadcrumbList` below the homepage and a priced `Offer`; and, since
  2026-11-03, the three page-quality rules the owner's Search Readiness checklist applies to five
  live pages every Monday, measured here on all of them instead:
  - **A visible author** (item c6). Some schema node on the page must name an author, and that name
    must appear in the page's visible text. The four `/methods/` pages emit no `Article`, so they
    named no author at all while showing "By How We Know" in their byline; `webPageSchema()` now
    carries the author, so the rule is met by construction on every page.
  - **No repeated slot text** (item q1). No eight-word phrase may appear more than three times in
    one page's body. This is what a padded template looks like from outside: on 2026-11-03, 13 of
    the 45 live pages repeated a body sentence four to six times because every FAQ answer had been
    topped up with text copied from the sections above it.
  - **No near-duplicate pages** (item q1). No two bodies may share more than half their five-word
    shingles. `/zones/hadal/` and `/creatures/hadal-snailfish/` measured 60% because the generated
    reference prose did not name its own record and the related-answers list reprinted other pages'
    paragraphs.

  The four constants (8, 3, 5, 0.5) are boss-os
  `src/shared/boss/searchReadiness/page-quality-sample.mjs` `QUALITY`, and `bodyText`/`wordsOf`
  mirror that module, so a page that passes here passes the Monday audit on the same arithmetic.
  Zero pages examined or zero pairs compared fails.
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
